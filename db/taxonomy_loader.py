"""
db/taxonomy_loader.py
Loads activity_tags from MySQL at app startup.
DB is authoritative; TAXONOMY_CONTEXT from taxonomy_mapping.py is the fallback.
"""
from taxonomy_mapping import TAXONOMY_CONTEXT, format_taxonomy_for_prompt
from db.connection import get_connection


def load_tags_from_db(cursor) -> dict:
    """
    Fetch all active activity_tags rows from DB.
    Returns {slug: row_dict} mapping.
    """
    cursor.execute(
        "SELECT id, slug, name, short_name, level, domain_id, aliases, is_active "
        "FROM activity_tags WHERE is_active = 1"
    )
    rows = cursor.fetchall()
    return {row["slug"]: row for row in rows}


def get_taxonomy_context() -> dict:
    """
    Load taxonomy from DB, merge with TAXONOMY_CONTEXT fallback.
    DB rows override fallback entries. Returns merged dict.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        db_tags = load_tags_from_db(cursor)
        cursor.close()
        conn.close()
    except Exception:
        db_tags = {}

    # Start from fallback, override with DB rows
    merged = dict(TAXONOMY_CONTEXT)
    for slug, row in db_tags.items():
        aliases = []
        if row.get("aliases"):
            aliases = [a.strip() for a in row["aliases"].split(",") if a.strip()]
        merged[slug] = {
            "display": row.get("name", slug),
            "level": row.get("level", 2),
            "domain": slug,  # fallback domain
            "aliases": aliases,
        }

    return merged


def get_taxonomy_prompt() -> str:
    """Return formatted taxonomy string for injection into Gemini system prompt."""
    taxonomy = get_taxonomy_context()
    return format_taxonomy_for_prompt(taxonomy)
