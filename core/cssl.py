"""
core/cssl.py
CSSL — Camp SQL Search Logic
Executes structured MySQL queries against programs, camps, activity_tags.
Returns result pool and RCS (Result Confidence Score).
"""
import json
import os

from db.connection import get_connection

# ---------------------------------------------------------------------------
# camps.ca-page-derived override index
# Built once at module load from db/camp_tag_overrides.json (committed to repo).
# Provides a parallel lookup path: slug → [camp_ids] that guarantees any camp
# camps.ca listed on a category page is included, even if program_tags has gaps.
# ---------------------------------------------------------------------------
_SLUG_TO_CAMP_IDS: dict[str, list[int]] = {}
try:
    _overrides_path = os.path.join(os.path.dirname(__file__), "..", "db", "camp_tag_overrides.json")
    with open(_overrides_path) as _f:
        for _cid_str, _slugs in json.load(_f).items():
            _cid = int(_cid_str)
            for _slug in _slugs:
                _SLUG_TO_CAMP_IDS.setdefault(_slug, []).append(_cid)
except (FileNotFoundError, json.JSONDecodeError, ValueError):
    pass  # Fail silently — program_tags path still works without overrides


def query(params: dict, limit: int = 500) -> tuple[list[dict], float]:
    """
    Execute CSSL query with structured parameters.

    Args:
        params: Merged session parameters dict
        limit: Pool size (default 100)

    Returns:
        (results list, rcs float 0.0-1.0)
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    conditions = ["p.status = 1", "c.status = 1"]
    joins = ["JOIN camps c ON p.camp_id = c.id"]
    args = {}

    # Tags — expand via categories hierarchy before resolving IDs
    expanded_tags = expand_via_categories(params.get("tags", []), cursor)
    tag_ids = resolve_tag_ids(expanded_tags, cursor)
    if tag_ids:
        # Parallel lookup: collect override camp_ids for all expanded slugs.
        override_camp_ids: list[int] = []
        seen_override: set[int] = set()
        for slug in expanded_tags:
            for cid in _SLUG_TO_CAMP_IDS.get(slug, []):
                if cid not in seen_override:
                    seen_override.add(cid)
                    override_camp_ids.append(cid)

        ph = ", ".join(f"%(tag_{i})s" for i in range(len(tag_ids)))
        for i, tid in enumerate(tag_ids):
            args[f"tag_{i}"] = tid

        if override_camp_ids:
            # Override camps: include if they have an active program with
            # a matching tag.  No fallback to arbitrary active programs —
            # if the camp's tagged program is expired, the camp is excluded.
            camp_ph = ", ".join(str(cid) for cid in override_camp_ids)  # ints — safe
            conditions.append(
                # Path 1: direct program_tags match
                f"(EXISTS (SELECT 1 FROM program_tags pt_m"
                f"  WHERE pt_m.program_id = p.id AND pt_m.tag_id IN ({ph}))"
                # Path 2: override camp with active matching program
                f" OR (p.camp_id IN ({camp_ph})"
                f"     AND p.id = (SELECT MIN(p3.id) FROM programs p3"
                f"          JOIN program_tags pt3 ON pt3.program_id = p3.id"
                f"          WHERE p3.camp_id = p.camp_id AND p3.status = 1"
                f"          AND (p3.end_date IS NULL OR p3.end_date >= CURDATE())"
                f"          AND pt3.tag_id IN ({ph}))))"
            )
        else:
            joins.append("JOIN program_tags pt ON p.id = pt.program_id")
            conditions.append(f"pt.tag_id IN ({ph})")

    # Exclude tags
    exclude_ids = resolve_tag_ids(params.get("exclude_tags", []), cursor)
    if exclude_ids:
        ph = ", ".join(f"%(ex_{i})s" for i in range(len(exclude_ids)))
        conditions.append(
            f"p.id NOT IN ("
            f"  SELECT program_id FROM program_tags WHERE tag_id IN ({ph})"
            f")"
        )
        for i, eid in enumerate(exclude_ids):
            args[f"ex_{i}"] = eid

    # Location — lat/lon proximity search takes precedence over city-string matching.
    # Falls back to cities list, then single city string.
    if params.get("lat") is not None and params.get("lon") is not None:
        radius = params.get("radius_km") or 25
        conditions.append(
            "c.lat IS NOT NULL AND c.lon IS NOT NULL AND "
            "(6371 * ACOS(GREATEST(-1.0, LEAST(1.0, "
            "COS(RADIANS(%(lat)s)) * COS(RADIANS(c.lat)) "
            "* COS(RADIANS(c.lon) - RADIANS(%(lon)s)) "
            "+ SIN(RADIANS(%(lat)s)) * SIN(RADIANS(c.lat))"
            ")))) <= %(radius_km)s"
        )
        args["lat"] = params["lat"]
        args["lon"] = params["lon"]
        args["radius_km"] = radius
    elif params.get("cities"):
        ph = ", ".join(f"%(city_{i})s" for i in range(len(params["cities"])))
        conditions.append(f"c.city IN ({ph})")
        for i, city in enumerate(params["cities"]):
            args[f"city_{i}"] = city
    elif params.get("city"):
        conditions.append("c.city = %(city)s")
        args["city"] = params["city"]

    if params.get("province"):
        _US_MARKERS = {"_US", "US", "USA", "United States", "United States of America"}
        if params["province"] in _US_MARKERS:
            # US scope: match all known US state values in the province field
            _US_PROVINCES = [
                "California", "California(USA)", "FL", "Florida",
                "Illinois", "Massachusetts", "South Carolina",
                "Texas", "Washington", "Washington(USA)",
            ]
            us_ph = ", ".join(f"%(us_{i})s" for i in range(len(_US_PROVINCES)))
            conditions.append(f"c.province IN ({us_ph})")
            for i, p in enumerate(_US_PROVINCES):
                args[f"us_{i}"] = p
        else:
            conditions.append("c.province = %(province)s")
            args["province"] = params["province"]

    # Age overlap — NULL age_from/age_to means the program accepts any age
    if params.get("age_from") is not None and params.get("age_to") is not None:
        conditions.append(
            "(p.age_from IS NULL OR p.age_from <= %(age_to)s) AND "
            "(p.age_to IS NULL OR p.age_to >= %(age_from)s)"
        )
        args["age_from"] = params["age_from"]
        args["age_to"] = params["age_to"]

    # Type — DB stores legacy numeric codes, not strings
    # OurKids type codes: 1=Day Camp, 2=Overnight, 3=Program, 4=Virtual,
    # 5=Year-round(?), 6=PA Day.  Comma-separated for multi-type sessions.
    # Use FIND_IN_SET to match within comma-separated values.
    # NULL type = unset — most camps are day camps, so Day includes NULL.
    _TYPE_MAP = {
        "Day":       ("(FIND_IN_SET('1', p.type) OR p.type = 'Day Camp' OR p.type IS NULL)", {}),
        "Overnight": ("FIND_IN_SET('2', p.type)", {}),
        "Both":      ("(FIND_IN_SET('1', p.type) AND FIND_IN_SET('2', p.type))", {}),
        "Virtual":   ("FIND_IN_SET('4', p.type)", {}),
    }
    if params.get("type") and params["type"] in _TYPE_MAP:
        cond, extra_args = _TYPE_MAP[params["type"]]
        conditions.append(cond)
        args.update(extra_args)
    elif params.get("type"):
        # Fallback: literal match (handles 'Day Camp' string passed directly)
        conditions.append("p.type = %(type)s")
        args["type"] = params["type"]

    # Gender (NULL=unknown, 0=Coed, 1=Boys, 2=Girls)
    # Soft match: include exact gender match and untagged (NULL) programs.
    # Gender filter is only set when the user explicitly asks for a gender-specific
    # camp (e.g. "all-girls camp") — not when they merely mention the child's gender.
    # Exact gender matches are ranked first via gender_boost in ORDER BY.
    gender_map = {"Boys": 1, "Girls": 2}
    if params.get("gender") and params["gender"] in gender_map:
        gval = gender_map[params["gender"]]
        conditions.append("(p.gender = %(gender)s OR p.gender IS NULL OR p.gender = 0)")
        args["gender"] = gval

    # Cost
    if params.get("cost_max"):
        conditions.append("(p.cost_from IS NULL OR p.cost_from <= %(cost_max)s)")
        args["cost_max"] = params["cost_max"]

    # Special needs / Virtual
    if params.get("is_special_needs"):
        conditions.append("p.is_special_needs = 1")
    if params.get("is_virtual"):
        conditions.append("p.is_virtual = 1")

    # Language immersion — use as a ranking boost, not a hard filter.
    # Only 24 programs have the column populated, so filtering would miss
    # camps found via tags (language-instruction). Instead, boost exact
    # matches in ORDER BY so French-immersion camps rank above general
    # language camps.
    # if params.get("language_immersion"):
    #     conditions.append("p.language_immersion = %(language_immersion)s")
    #     args["language_immersion"] = params["language_immersion"]

    # Date range — only match programs with a scheduled slot overlapping the window
    # (Programs with no program_dates are excluded when this filter is active;
    #  they're year-round/ongoing programs without fixed schedule data.)
    if params.get("date_from") and params.get("date_to"):
        joins.append("JOIN program_dates pd ON p.id = pd.program_id "
                     "AND pd.start_date <= %(date_to)s "
                     "AND pd.end_date >= %(date_from)s")
        args["date_from"] = params["date_from"]
        args["date_to"]   = params["date_to"]

    # Traits — used as a ranking boost, NOT a hard filter.
    # Traits like "shy" or "creative" describe the child's personality;
    # filtering by them eliminates too many relevant camps. Instead, we
    # boost programs that match via ORDER BY and pass traits to the
    # reranker/concierge for narrative context.
    trait_ids = resolve_trait_ids(params.get("traits", []), cursor)
    if trait_ids:
        ph_tr = ", ".join(f"%(trait_{i})s" for i in range(len(trait_ids)))
        for i, tid in enumerate(trait_ids):
            args[f"trait_{i}"] = tid

    # Temporal filter — suppress expired programs
    conditions.append("(p.end_date IS NULL OR p.end_date >= CURDATE())")

    where = " AND ".join(conditions)
    joins_str = " ".join(joins)

    # Relevance sort:
    # 1. Exact gender match first (gender-specific camp beats coed when gender is requested)
    # 2. Exact type match first (pure overnight beats "Both" when overnight is requested)
    # 3. Activity specialization (is_primary tag match > low tag count > generalist)
    # 4. Tier (gold > silver > bronze)
    # 5. Review average
    gender_db = {"Girls": 2, "Boys": 1}.get(params.get("gender", ""), 0)
    type_code  = {"Overnight": "2", "Day": "1"}.get(params.get("type", ""), None)

    gender_boost = (
        f"CASE WHEN p.gender = {gender_db} THEN 0 ELSE 1 END,"
        if gender_db else ""
    )
    type_boost = (
        f"CASE WHEN FIND_IN_SET('{type_code}', p.type) THEN 0 ELSE 1 END,"
        if type_code else ""
    )

    # Build boost expressions for SELECT (required by DISTINCT + ORDER BY)
    gender_select = (
        f"CASE WHEN p.gender = {gender_db} THEN 0 ELSE 1 END AS _gender_boost,"
        if gender_db else ""
    )
    type_select = (
        f"CASE WHEN FIND_IN_SET('{type_code}', p.type) THEN 0 ELSE 1 END AS _type_boost,"
        if type_code else ""
    )

    # Specialty boost — ranks specialist programs above generalist programs.
    # Uses tag_role (specialty > category > activity) when available,
    # falls back to is_primary for legacy rows.
    # _role_match: 0=specialty, 1=category, 2=activity, 3=no match
    # _tag_count: total tags on program (fewer = more specialized)
    if tag_ids:
        ph_sp = ", ".join(f"%(tag_{i})s" for i in range(len(tag_ids)))
        specialty_select = f"""
            (SELECT MIN(CASE
                WHEN pt2.tag_role = 'specialty' THEN 0
                WHEN pt2.tag_role = 'category'  THEN 1
                WHEN pt2.tag_role = 'activity'  THEN 2
                ELSE 3 END)
             FROM program_tags pt2
             WHERE pt2.program_id = p.id AND pt2.tag_id IN ({ph_sp})
            ) AS _role_match,
            (SELECT COUNT(*) FROM program_tags WHERE program_id = p.id) AS _tag_count,"""
        # COALESCE(_role_match, 3): override-only programs have NULL here
        # (no matching program_tags row), treat as lowest priority so they rank
        # after programs with an explicit tag match.
        specialty_boost = "COALESCE(_role_match, 3) ASC, _tag_count ASC,"
    else:
        specialty_select = ""
        specialty_boost = ""

    # Trait boost — soft ranking signal, not a filter.
    # Programs with matching traits rank higher but unmatched programs still appear.
    if trait_ids:
        trait_select = (
            f"(SELECT COUNT(*) FROM program_traits pt_tr"
            f" WHERE pt_tr.program_id = p.id"
            f" AND pt_tr.trait_id IN ({ph_tr})) AS _trait_match,"
        )
        trait_boost = "_trait_match DESC,"
    else:
        trait_select = ""
        trait_boost = ""

    sql = f"""
        SELECT DISTINCT
            p.id, p.camp_id, p.name, p.type,
            p.age_from, p.age_to, p.cost_from, p.cost_to,
            p.gender, p.is_special_needs, p.is_virtual, p.language_immersion,
            p.mini_description, p.description,
            p.start_date, p.end_date,
            c.camp_name, c.tier, c.review_avg, c.review_count, c.city, c.province,
            c.lat, c.lon, c.website, c.lgbtq_welcoming, c.accessibility, c.slug, c.prettyurl,
            {gender_select}
            {type_select}
            {specialty_select}
            {trait_select}
            FIELD(c.tier, 'gold', 'silver', 'bronze') AS _tier_score
        FROM programs p
        {joins_str}
        WHERE {where}
        ORDER BY
            {gender_boost}
            {type_boost}
            {specialty_boost}
            {trait_boost}
            _tier_score ASC,
            COALESCE(c.review_count, 0) DESC,
            c.camp_name ASC
        LIMIT %(limit)s
    """
    args["limit"] = limit

    cursor.execute(sql, args)
    results = cursor.fetchall()

    # Belt-and-suspenders dedup in case DISTINCT doesn't cover all join paths
    seen = set()
    deduped = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    results = deduped

    enrich_with_dates(results, cursor)

    cursor.close()
    conn.close()

    rcs = calculate_rcs(results, params, tag_ids)
    return list(results), rcs


def enrich_with_dates(results: list, cursor) -> None:
    """
    Attach program_dates rows to each result dict (in-place).
    Fetches all future slots for the returned programs in one query.
    Each result gets a 'program_dates' key: list of dicts sorted by start_date.
    """
    if not results:
        return
    ids = [r["id"] for r in results]
    ph = ", ".join(["%s"] * len(ids))
    cursor.execute(
        f"SELECT program_id, start_date, end_date, "
        f"MIN(cost_from) as cost_from, MAX(cost_to) as cost_to, "
        f"MAX(before_care) as before_care, MAX(after_care) as after_care "
        f"FROM program_dates "
        f"WHERE program_id IN ({ph}) AND end_date >= CURDATE() "
        f"GROUP BY program_id, start_date, end_date "
        f"ORDER BY program_id, start_date",
        tuple(ids),
    )
    from collections import defaultdict
    by_prog = defaultdict(list)
    for row in cursor.fetchall():
        by_prog[row["program_id"]].append(row)
    for r in results:
        r["program_dates"] = by_prog.get(r["id"], [])


def calculate_rcs(results: list, params: dict, tag_ids: list) -> float:
    """Calculate Result Confidence Score based on result quality."""
    if not results:
        return 0.0

    count = len(results)
    gold_count = sum(1 for r in results if r.get("tier") == "gold")

    if count >= 20:
        base = 0.90
    elif count >= 10:
        base = 0.80
    elif count >= 5:
        base = 0.70
    elif count >= 1:
        base = 0.50
    else:
        return 0.0

    if gold_count > 0:
        base = min(1.0, base + 0.05)

    if tag_ids and count < 3:
        base = max(0.30, base - 0.20)

    # Age-filter coverage penalty: if fewer than half results cover the requested age range
    if params.get("age_from") is not None and params.get("age_to") is not None:
        age_matched = sum(
            1 for r in results
            if r.get("age_from") is not None
            and r["age_from"] <= params["age_to"]
            and r.get("age_to", 99) >= params["age_from"]
        )
        age_coverage = age_matched / count if count else 0
        if age_coverage < 0.5:
            base = max(0.30, base - 0.10)

    return round(base, 2)


def expand_via_categories(slugs: list[str], cursor) -> list[str]:
    """
    Hierarchical tag expansion via the categories table.

    For each slug, if a categories row exists, its filter_activity_tags replaces
    the single slug with the full child tree.  Example: "dance-multi" expands to
    [dance-multi, ballet, jazz, hip-hop, ...] so programs tagged with any dance
    style are included in results.

    Leaf slugs (level-3 or standalone level-2) have filter_activity_tags = self,
    so they pass through unchanged.
    """
    if not slugs:
        return slugs
    ph = ", ".join(["%s"] * len(slugs))
    cursor.execute(
        f"SELECT slug, filter_activity_tags FROM categories "
        f"WHERE slug IN ({ph}) AND is_active = 1",
        tuple(slugs),
    )
    rows = cursor.fetchall()

    # Build a map of slug → expanded set; slugs with no category row keep themselves
    expanded: set[str] = set(slugs)
    for row in rows:
        if row["filter_activity_tags"]:
            for s in row["filter_activity_tags"].split(","):
                s = s.strip()
                if s:
                    expanded.add(s)
    return list(expanded)


def resolve_tag_ids(slugs: list[str], cursor) -> list[int]:
    """Convert slug list to DB tag IDs."""
    if not slugs:
        return []
    ph = ", ".join(["%s"] * len(slugs))
    cursor.execute(
        f"SELECT id FROM activity_tags WHERE slug IN ({ph}) AND is_active = 1",
        tuple(slugs),
    )
    return [row["id"] for row in cursor.fetchall()]


def resolve_trait_ids(slugs: list[str], cursor) -> list[int]:
    """Convert trait slug list to DB trait IDs."""
    if not slugs:
        return []
    ph = ", ".join(["%s"] * len(slugs))
    cursor.execute(
        f"SELECT id FROM traits WHERE slug IN ({ph})",
        tuple(slugs),
    )
    return [row["id"] for row in cursor.fetchall()]


