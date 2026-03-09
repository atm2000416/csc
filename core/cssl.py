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

    # Tags
    tag_ids = resolve_tag_ids(params.get("tags", []), cursor)
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

    # Location — cities list takes precedence over single city
    if params.get("cities"):
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

    # Type
    if params.get("type"):
        conditions.append("p.type = %(type)s")
        args["type"] = params["type"]

    # Gender (0=Coed, 1=Boys, 2=Girls)
    gender_map = {"Boys": 1, "Girls": 2, "Coed": 0}
    if params.get("gender") and params["gender"] != "Coed":
        conditions.append("p.gender = %(gender)s")
        args["gender"] = gender_map.get(params["gender"], 0)

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

    sql = f"""
        SELECT DISTINCT
            p.id, p.camp_id, p.name, p.type,
            p.age_from, p.age_to, p.cost_from, p.cost_to,
            p.mini_description, p.description,
            p.start_date, p.end_date,
            c.camp_name, c.tier, c.city, c.province,
            c.lat, c.lon, c.website, c.lgbtq_welcoming, c.accessibility
        FROM programs p
        {joins_str}
        WHERE {where}
        ORDER BY
            c.review_avg DESC,
            FIELD(c.tier, 'gold', 'silver', 'bronze') ASC
        LIMIT %(limit)s
    """
    args["limit"] = limit

    cursor.execute(sql, args)
    results = cursor.fetchall()
    cursor.close()
    conn.close()

    # Belt-and-suspenders dedup in case DISTINCT doesn't cover all join paths
    seen = set()
    deduped = []
    for r in results:
        if r["id"] not in seen:
            seen.add(r["id"])
            deduped.append(r)
    results = deduped

    rcs = calculate_rcs(results, params, tag_ids)
    return list(results), rcs


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
