"""
db/seed_tags.py
Standalone script to seed activity_tags and traits tables from taxonomy_mapping.py.

Usage:
    python db/seed_tags.py

Run ONCE after schema creation. Idempotent — safe to re-run.
"""
import os
import sys

# Allow running from project root or db/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from taxonomy_mapping import TAXONOMY_CONTEXT
from db.connection import get_connection


TRAITS = [
    ("Resilience", "resilience"),
    ("Curiosity", "curiosity"),
    ("Courage", "courage"),
    ("Independence", "independence"),
    ("Responsibility", "responsibility"),
    ("Interpersonal Skills", "interpersonal-skills"),
    ("Creativity", "creativity"),
    ("Physicality", "physicality"),
    ("Generosity", "generosity"),
    ("Tolerance", "tolerance"),
    ("Self-regulation", "self-regulation"),
    ("Religious Faith", "religious-faith"),
]


def seed_traits(cursor) -> int:
    count = 0
    for name, slug in TRAITS:
        cursor.execute(
            "INSERT INTO traits (name, slug) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE name = VALUES(name)",
            (name, slug),
        )
        if cursor.rowcount > 0:
            count += 1
    return count


def seed_tags(cursor) -> int:
    """Insert/update all tags from TAXONOMY_CONTEXT into activity_tags."""
    count = 0

    # First pass: insert level-1 domain tags (no parent/domain_id yet)
    slug_to_id: dict[str, int] = {}

    for slug, meta in TAXONOMY_CONTEXT.items():
        if meta["level"] == 1:
            aliases_str = ", ".join(meta.get("aliases", []))
            cursor.execute(
                """
                INSERT INTO activity_tags (slug, name, short_name, level, aliases, is_active)
                VALUES (%s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    name      = VALUES(name),
                    level     = VALUES(level),
                    aliases   = VALUES(aliases),
                    is_active = 1
                """,
                (slug, meta["display"], meta["display"][:125], meta["level"], aliases_str),
            )
            # Fetch ID
            cursor.execute("SELECT id FROM activity_tags WHERE slug = %s", (slug,))
            row = cursor.fetchone()
            if row:
                slug_to_id[slug] = row["id"] if isinstance(row, dict) else row[0]
            if cursor.rowcount > 0:
                count += 1

    # Second pass: level 2 and 3 tags — set domain_id
    for slug, meta in TAXONOMY_CONTEXT.items():
        if meta["level"] in (2, 3):
            aliases_str = ", ".join(meta.get("aliases", []))
            domain_slug = meta.get("domain", "")
            domain_id = slug_to_id.get(domain_slug)

            cursor.execute(
                """
                INSERT INTO activity_tags (slug, name, short_name, level, domain_id, aliases, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    name      = VALUES(name),
                    level     = VALUES(level),
                    domain_id = VALUES(domain_id),
                    aliases   = VALUES(aliases),
                    is_active = 1
                """,
                (
                    slug,
                    meta["display"],
                    meta["display"][:125],
                    meta["level"],
                    domain_id,
                    aliases_str,
                ),
            )
            if cursor.rowcount > 0:
                count += 1

    return count


def main():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    tag_count = seed_tags(cursor)
    trait_count = seed_traits(cursor)

    conn.commit()
    cursor.close()
    conn.close()

    print(f"Inserted/updated {tag_count} tags, {trait_count} traits")


if __name__ == "__main__":
    main()
