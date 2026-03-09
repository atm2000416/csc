"""
core/category_disambiguator.py
Concierge-style category disambiguation.

When the intent parser returns a single broad parent tag (L1 domain or L2
parent-with-children), this module surfaces child categories that actually have
programs in the DB — so the user can narrow down before a search runs, exactly
as a real concierge would ask "are you thinking dance, music, or visual arts?"

Trigger rule: exactly ONE tag, and it's a known broad parent.
If the user named multiple activities, they're already being specific enough.
"""
from db.connection import get_connection

# Slugs that are too broad to search without clarification.
# L1 domains + L2 parents that have child sub-categories.
BROAD_PARENT_SLUGS = {
    # L1 domains
    "adventure", "arts", "computers-tech", "education", "health-fitness", "sports",
    # L2 parents with children
    "dance-multi", "fantasy-multi", "music-multi", "performing-arts-multi",
    "visual-arts-multi", "programming-multi", "academic-tutoring-multi",
    "leadership-multi", "science-multi", "ball-sports-multi",
    "extreme-sports-multi", "water-sports-multi",
}


def get_broad_parent(tags: list[str]) -> str | None:
    """
    Return the broad-parent slug if disambiguation should be triggered, else None.

    Only fires when there is exactly ONE tag and it is a known broad parent.
    Multi-tag queries imply the user is already being specific.
    """
    if len(tags) != 1:
        return None
    slug = tags[0]
    return slug if slug in BROAD_PARENT_SLUGS else None


def get_viable_children(parent_slug: str, min_programs: int = 1) -> list[dict]:
    """
    Return child categories of parent_slug that have real programs in the DB.

    For L1 slugs: direct children are all level-2 activity_tags in that domain.
    For L2 parent slugs: children come from that slug's categories.filter_activity_tags.

    Returns list of {slug, name, program_count} sorted by program_count desc.
    Capped at 8 options for UI readability.
    """
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, level FROM activity_tags WHERE slug = %s AND is_active = 1",
            (parent_slug,),
        )
        parent = cursor.fetchone()
        if not parent:
            return []

        if parent["level"] == 1:
            # L1: direct children = all level-2 tags sharing this domain_id
            cursor.execute(
                "SELECT slug FROM activity_tags "
                "WHERE level = 2 AND domain_id = %s AND is_active = 1",
                (parent["id"],),
            )
            child_slugs = [r["slug"] for r in cursor.fetchall()]
        else:
            # L2 parent: read children from categories.filter_activity_tags
            cursor.execute(
                "SELECT filter_activity_tags FROM categories "
                "WHERE slug = %s AND is_active = 1",
                (parent_slug,),
            )
            row = cursor.fetchone()
            if not row or not row["filter_activity_tags"]:
                return []
            child_slugs = [
                s.strip()
                for s in row["filter_activity_tags"].split(",")
                if s.strip() and s.strip() != parent_slug
            ]

        if not child_slugs:
            return []

        # Count programs per child — only surfaces children that exist in the DB
        ph = ", ".join(["%s"] * len(child_slugs))
        cursor.execute(
            f"""
            SELECT at.slug, at.name, COUNT(DISTINCT pt.program_id) AS program_count
            FROM activity_tags at
            JOIN program_tags pt ON pt.tag_id = at.id
            JOIN programs p ON p.id = pt.program_id AND p.status = 1
            WHERE at.slug IN ({ph}) AND at.is_active = 1
            GROUP BY at.slug, at.name
            HAVING program_count >= %s
            ORDER BY program_count DESC
            LIMIT 8
            """,
            tuple(child_slugs) + (min_programs,),
        )
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
