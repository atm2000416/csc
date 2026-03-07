"""CASL — Semantic tag expansion via related_ids from activity_tags."""
from db.connection import get_connection


def expand(params: dict, limit: int = 100) -> list[dict]:
    """
    Expand search using related_ids from activity_tags.

    For each tag slug in params["tags"], fetches related tag IDs from the DB,
    then runs a CSSL query with the expanded tag set.
    Returns empty list if no related tags found or params has no tags.
    """
    slugs = params.get("tags", [])
    if not slugs:
        return []

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Fetch related_ids for each tag slug
    ph = ", ".join(["%s"] * len(slugs))
    cur.execute(
        f"SELECT related_ids FROM activity_tags WHERE slug IN ({ph}) AND is_active = 1",
        slugs,
    )
    related_ids: set[int] = set()
    for row in cur.fetchall():
        if row["related_ids"]:
            for rid in row["related_ids"].split(","):
                rid = rid.strip()
                if rid.isdigit():
                    related_ids.add(int(rid))

    if not related_ids:
        cur.close()
        conn.close()
        return []

    # Fetch slugs for those related IDs
    ph2 = ", ".join(["%s"] * len(related_ids))
    cur.execute(
        f"SELECT slug FROM activity_tags WHERE id IN ({ph2}) AND is_active = 1",
        list(related_ids),
    )
    related_slugs = [r["slug"] for r in cur.fetchall()]
    cur.close()
    conn.close()

    if not related_slugs:
        return []

    expanded_params = {**params, "tags": related_slugs}
    from core.cssl import query as cssl_query
    results, _ = cssl_query(expanded_params, limit=limit)
    return results
