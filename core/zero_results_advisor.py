"""
core/zero_results_advisor.py
Zero Results Advisor — fires when ICS is high but RCS = 0.0.
Runs proximity-aware diagnostic query to find where activity exists.
Returns structured suggestion stored in session_context.pending_suggestion.
"""
from db.connection import get_connection

# Map program type labels to SQL conditions (mirrors cssl.py)
_TYPE_SQL = {
    "Day":       "(FIND_IN_SET('1', p.type) OR p.type = 'Day Camp' OR p.type IS NULL)",
    "Overnight": "FIND_IN_SET('2', p.type)",
    "Both":      "(FIND_IN_SET('1', p.type) AND FIND_IN_SET('2', p.type))",
    "Virtual":   "FIND_IN_SET('4', p.type)",
}


def diagnose(
    tag_ids: list[int],
    searched_city: str | None,
    searched_province: str | None,
    program_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    is_virtual: bool = False,
    age_from: int | None = None,
    age_to: int | None = None,
    user_lat: float | None = None,
    user_lon: float | None = None,
) -> dict:
    """
    Find where the requested activity exists, closest first.
    Applies the same type, date, age, and is_virtual filters as the original search
    so the program counts are accurate (no false geo suggestions).

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

    if is_virtual:
        extra_conditions += " AND p.is_virtual = 1"

    if age_from is not None and age_to is not None:
        extra_conditions += (
            " AND (p.age_from IS NULL OR p.age_from <= %s)"
            " AND (p.age_to IS NULL OR p.age_to >= %s)"
        )
        args += [age_to, age_from]

    if date_from and date_to:
        joins = (
            "JOIN program_dates pd ON p.id = pd.program_id "
            "AND pd.start_date <= %s "
            "AND pd.end_date >= %s"
        )
        args += [date_to, date_from]

    # When user coordinates are available, order by distance (Haversine);
    # otherwise fall back to program count.
    if user_lat is not None and user_lon is not None:
        select_extra = (
            ", MIN(111.045 * DEGREES(ACOS(LEAST(1.0, "
            "COS(RADIANS(%s)) * COS(RADIANS(c.lat)) "
            "* COS(RADIANS(c.lon) - RADIANS(%s)) "
            "+ SIN(RADIANS(%s)) * SIN(RADIANS(c.lat)))))) AS dist_km"
        )
        geo_args = [user_lat, user_lon, user_lat]
        having = "HAVING dist_km IS NOT NULL"
        order = "ORDER BY dist_km ASC"
    else:
        select_extra = ""
        geo_args = []
        having = ""
        order = "ORDER BY program_count DESC"

    cursor.execute(
        f"""
        SELECT c.city, c.province, COUNT(DISTINCT p.id) AS program_count
               {select_extra}
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
        {having}
        {order}
        LIMIT 10
        """,
        geo_args + args,
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
