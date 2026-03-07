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
        conditions.append("pt.tag_id IN %(tag_ids)s")
        args["tag_ids"] = tuple(tag_ids)

    # Exclude tags
    exclude_ids = resolve_tag_ids(params.get("exclude_tags", []), cursor)
    if exclude_ids:
        conditions.append(
            "p.id NOT IN ("
            "  SELECT program_id FROM program_tags WHERE tag_id IN %(exclude_ids)s"
            ")"
        )
        args["exclude_ids"] = tuple(exclude_ids)

    # Location — cities list takes precedence over single city
    if params.get("cities"):
        conditions.append("c.city IN %(cities)s")
        args["cities"] = tuple(params["cities"])
    elif params.get("city"):
        conditions.append("c.city = %(city)s")
        args["city"] = params["city"]

    if params.get("province"):
        conditions.append("c.province = %(province)s")
        args["province"] = params["province"]

    # Age overlap
    if params.get("age_from") is not None and params.get("age_to") is not None:
        conditions.append("p.age_from <= %(age_to)s AND p.age_to >= %(age_from)s")
        args["age_from"] = params["age_from"]
        args["age_to"] = params["age_to"]

    # Type
    if params.get("type"):
        conditions.append("p.type = %(type)s")
        args["type"] = params["type"]

    # Gender (0=Coed, 1=Boys, 2=Girls)
    gender_map = {"Boys": 1, "Girls": 2, "Coed": 0}
    if params.get("gender") and params["gender"] != "Coed":
        conditions.append("p.gender IN (%(gender)s, 0)")
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
        conditions.append("ptrait.trait_id IN %(trait_ids)s")
        args["trait_ids"] = tuple(trait_ids)

    # Temporal filter — suppress expired programs
    conditions.append("(p.end_date IS NULL OR p.end_date >= CURDATE())")

    where = " AND ".join(conditions)
    joins_str = " ".join(joins)

    sql = f"""
        SELECT
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
            FIELD(c.tier, 'gold', 'silver', 'bronze') ASC,
            c.review_avg DESC
        LIMIT %(limit)s
    """
    args["limit"] = limit

    cursor.execute(sql, args)
    results = cursor.fetchall()
    cursor.close()
    conn.close()

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
