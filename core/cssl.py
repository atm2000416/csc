"""
core/cssl.py
CSSL — Camp SQL Search Logic
Executes structured MySQL queries against programs, camps, activity_tags.
Returns result pool and RCS (Result Confidence Score).
"""
from db.connection import get_connection


def query(params: dict, limit: int = 100) -> tuple[list[dict], float]:
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
        joins.append("JOIN program_tags pt ON p.id = pt.program_id")
        ph = ", ".join(f"%(tag_{i})s" for i in range(len(tag_ids)))
        conditions.append(f"pt.tag_id IN ({ph})")
        for i, tid in enumerate(tag_ids):
            args[f"tag_{i}"] = tid

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
    # '1'='Day Camp', '2'='Overnight', '3'='Day+Overnight', '4'='Virtual'
    # 'Day Camp' also appears as a string from the migration
    _TYPE_MAP = {
        "Day":       ("p.type IN ('1','1,3','Day Camp')", {}),
        "Overnight": ("p.type IN ('2','3','1,3')", {}),
        "Both":      ("p.type IN ('3','1,3')", {}),
        "Virtual":   ("p.type = '4'", {}),
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
    # Strict match: when a user asks for girls-only or boys-only, only return
    # programs with an explicit gender tag. NULL means data is missing, not coed.
    gender_map = {"Boys": 1, "Girls": 2}
    if params.get("gender") and params["gender"] in gender_map:
        gval = gender_map[params["gender"]]
        conditions.append("p.gender = %(gender)s")
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

    # Language immersion
    if params.get("language_immersion"):
        conditions.append("p.language_immersion = %(language_immersion)s")
        args["language_immersion"] = params["language_immersion"]

    # Date range — only match programs with a scheduled slot overlapping the window
    # (Programs with no program_dates are excluded when this filter is active;
    #  they're year-round/ongoing programs without fixed schedule data.)
    if params.get("date_from") and params.get("date_to"):
        joins.append("JOIN program_dates pd ON p.id = pd.program_id "
                     "AND pd.start_date <= %(date_to)s "
                     "AND pd.end_date >= %(date_from)s")
        args["date_from"] = params["date_from"]
        args["date_to"]   = params["date_to"]

    # Traits
    trait_ids = resolve_trait_ids(params.get("traits", []), cursor)
    if trait_ids:
        joins.append("JOIN program_traits ptrait ON p.id = ptrait.program_id")
        ph = ", ".join(f"%(trait_{i})s" for i in range(len(trait_ids)))
        conditions.append(f"ptrait.trait_id IN ({ph})")
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
    type_db    = {"Overnight": "'2'", "Day": "'1'"}.get(params.get("type", ""), None)

    gender_boost = (
        f"CASE WHEN p.gender = {gender_db} THEN 0 ELSE 1 END,"
        if gender_db else ""
    )
    type_boost = (
        f"CASE WHEN p.type = {type_db} THEN 0 ELSE 1 END,"
        if type_db else ""
    )

    # Build boost expressions for SELECT (required by DISTINCT + ORDER BY)
    gender_select = (
        f"CASE WHEN p.gender = {gender_db} THEN 0 ELSE 1 END AS _gender_boost,"
        if gender_db else ""
    )
    type_select = (
        f"CASE WHEN p.type = {type_db} THEN 0 ELSE 1 END AS _type_boost,"
        if type_db else ""
    )

    # Specialty boost — ranks specialist programs above generalist programs.
    # Only meaningful when specific activity tags are searched.
    # _primary_match: 0 if any searched tag is marked is_primary for this program, else 1
    # _tag_count: total tags on program (fewer = more specialized)
    if tag_ids:
        ph_sp = ", ".join(f"%(tag_{i})s" for i in range(len(tag_ids)))
        specialty_select = f"""
            (SELECT MIN(CASE WHEN pt2.is_primary = 1 THEN 0 ELSE 1 END)
             FROM program_tags pt2
             WHERE pt2.program_id = p.id AND pt2.tag_id IN ({ph_sp})
            ) AS _primary_match,
            (SELECT COUNT(*) FROM program_tags WHERE program_id = p.id) AS _tag_count,"""
        specialty_boost = "_primary_match ASC, _tag_count ASC,"
    else:
        specialty_select = ""
        specialty_boost = ""

    sql = f"""
        SELECT DISTINCT
            p.id, p.camp_id, p.name, p.type,
            p.age_from, p.age_to, p.cost_from, p.cost_to,
            p.gender, p.is_special_needs, p.is_virtual, p.language_immersion,
            p.mini_description, p.description,
            p.start_date, p.end_date,
            c.camp_name, c.tier, c.review_avg, c.city, c.province,
            c.lat, c.lon, c.website, c.lgbtq_welcoming, c.accessibility, c.slug,
            {gender_select}
            {type_select}
            {specialty_select}
            FIELD(c.tier, 'gold', 'silver', 'bronze') AS _tier_score
        FROM programs p
        {joins_str}
        WHERE {where}
        ORDER BY
            {gender_boost}
            {type_boost}
            {specialty_boost}
            _tier_score ASC,
            c.review_avg DESC
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
