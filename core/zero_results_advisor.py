"""
core/zero_results_advisor.py
Zero Results Advisor — fires when ICS is high but RCS = 0.0.
Runs proximity-aware diagnostic query to find where activity exists.
Returns structured suggestion stored in session_context.pending_suggestion.
"""
from db.connection import get_connection

# Map program type labels to SQL conditions (mirrors cssl.py)
_TYPE_SQL = {
    "Day":       "p.type IN ('1','1,3','Day Camp')",
    "Overnight": "p.type IN ('2','3','1,3')",
    "Both":      "p.type IN ('3','1,3')",
    "Virtual":   "p.type = '4'",
}


def diagnose(
    tag_ids: list[int],
    searched_city: str | None,
    searched_province: str | None,
    program_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict:
    """
    Find where the requested activity exists, closest first.
    Applies the same type and date filters as the original search so the
    program counts are accurate (no false geo suggestions).

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

    ph = ", ".join(["%s"] * len(tag_ids))
    args: list = list(tag_ids)

    joins = ""
    extra_conditions = ""

    if program_type and program_type in _TYPE_SQL:
        extra_conditions += f" AND {_TYPE_SQL[program_type]}"

    if date_from and date_to:
        joins = (
            "JOIN program_dates pd ON p.id = pd.program_id "
            "AND pd.start_date <= %s "
            "AND pd.end_date >= %s"
        )
        args += [date_to, date_from]

    cursor.execute(
        f"""
        SELECT c.city, c.province, COUNT(DISTINCT p.id) AS program_count
        FROM programs p
        JOIN program_tags pt ON p.id = pt.program_id
        JOIN camps c ON p.camp_id = c.id
        {joins}
        WHERE pt.tag_id IN ({ph})
          AND p.status = 1
          AND c.status = 1
          AND (p.end_date IS NULL OR p.end_date >= CURDATE())
          {extra_conditions}
        GROUP BY c.city, c.province
        ORDER BY program_count DESC
        LIMIT 10
        """,
        args,
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
        location_label = searched_city or searched_province or "your location"
        return {
            "type": "geo_broaden_specific",
            "message": (
                f"No results found in {location_label}, but I found "
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
        location_label = searched_city or searched_province or "your location"
        return {
            "type": "geo_broaden_province",
            "message": (
                f"No results found near {location_label}. "
                f"There are {province_total} programs across {province} though — "
                f"want me to search province-wide instead?"
            ),
            "pending_suggestion": {
                "type": "geo_broaden_province",
                "to_province": province,
                "tag_ids": tag_ids,
            },
        }
