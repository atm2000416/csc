"""
core/zero_results_advisor.py
Zero Results Advisor — fires when ICS is high but RCS = 0.0.
Runs proximity-aware diagnostic query to find where activity exists.
Returns structured suggestion stored in session_context.pending_suggestion.
"""
from db.connection import get_connection


def diagnose(
    tag_ids: list[int],
    searched_city: str | None,
    searched_province: str | None,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> dict:
    """
    Find where the requested activity exists, closest first.

    Returns one of:
      - geo_broaden_specific: activity exists nearby, suggest city
      - geo_broaden_province: activity exists but far, suggest province-wide
      - no_supply: activity not in DB
      - no_tags: tag_ids is empty
    """
    if not tag_ids:
        return {"type": "no_tags", "message": "Could not identify the activity requested."}

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    if user_lat and user_lon:
        order_by = "ST_Distance_Sphere(POINT(c.lon, c.lat), POINT(%s, %s)) ASC"
        order_args = [user_lon, user_lat]
    else:
        order_by = "program_count DESC"
        order_args = []

    cursor.execute(
        f"""
        SELECT c.city, c.province, COUNT(p.id) AS program_count
        FROM programs p
        JOIN program_tags pt ON p.id = pt.program_id
        JOIN camps c ON p.camp_id = c.id
        WHERE pt.tag_id IN %s
          AND p.status = 1
          AND c.status = 1
          AND (p.end_date IS NULL OR p.end_date >= CURDATE())
        GROUP BY c.city, c.province
        ORDER BY {order_by}
        LIMIT 10
        """,
        [tuple(tag_ids)] + order_args,
    )

    locations = cursor.fetchall()
    cursor.close()
    conn.close()

    if not locations:
        return {
            "type": "no_supply",
            "message": "We don't currently have camps for that activity in our directory.",
            "pending_suggestion": None,
        }

    nearest = locations[0]
    same_province = (
        nearest["province"] == searched_province if searched_province else False
    )

    if same_province and nearest["city"] != searched_city:
        return {
            "type": "geo_broaden_specific",
            "message": (
                f"No results found in {searched_city}, but I found "
                f"{nearest['program_count']} program(s) in {nearest['city']}. "
                f"Want me to show those instead?"
            ),
            "pending_suggestion": {
                "type": "geo_broaden",
                "to_city": nearest["city"],
                "to_province": nearest["province"],
                "tag_ids": tag_ids,
            },
        }
    else:
        province = searched_province or nearest["province"]
        province_total = sum(
            loc["program_count"] for loc in locations if loc["province"] == province
        )
        return {
            "type": "geo_broaden_province",
            "message": (
                f"No results found near {searched_city or 'your location'}. "
                f"There are {province_total} programs across {province} though — "
                f"want me to search province-wide instead?"
            ),
            "pending_suggestion": {
                "type": "geo_broaden_province",
                "to_province": province,
                "tag_ids": tag_ids,
            },
        }
