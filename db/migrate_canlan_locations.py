"""
db/migrate_canlan_locations.py
Add all Canlan Sports locations to the new DB.

Source: extra_locations table from camp_directory_dump20260205.sql
  cid=1777 has 9 additional locations beyond the active Toronto record.

What this does:
  1. Activates existing status=0 Canlan records (Oakville, Etobicoke, Scarborough)
  2. Creates new camp records for missing locations (Winnipeg, Saskatoon,
     Burnaby, Langley, North Vancouver, Oshawa)
  3. Fixes program tags on the existing Toronto program (removes migration
     artifacts: video-game-development, cit-lit-program)
  4. Creates a correctly-tagged program for each newly active/created location

Run:
  source .venv/bin/activate && python3 db/migrate_canlan_locations.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

# ── Canlan location data from extra_locations (cid=1777) ─────────────────────
# Format: {slug_suffix, camp_name, city, province, lat, lon, postal}
CANLAN_LOCATIONS = [
    # Already in DB — just need activation + programs
    {
        "existing_id": 579,
        "camp_name": "Canlan Sports - Oakville",
        "city": "Oakville", "province": "Ontario",
        "lat": 43.4884604, "lon": -79.6485878, "postal": "L6J 7T9",
        "slug": "canlan-sports-oakville",
    },
    {
        "existing_id": 422,
        "camp_name": "Canlan Sports - Etobicoke",
        "city": "Etobicoke", "province": "Ontario",
        "lat": 43.6999325, "lon": -79.5763217, "postal": "M9W 4W1",
        "slug": "canlan-sports-etobicoke",
    },
    {
        "existing_id": 529,
        "camp_name": "Canlan Sports - Scarborough",
        "city": "Scarborough", "province": "Ontario",
        "lat": 43.8291236, "lon": -79.2516344, "postal": "M1V 5L8",
        "slug": "canlan-sports-scarborough",
    },
    # Missing — need new records
    {
        "existing_id": None,
        "camp_name": "Canlan Sports - Winnipeg",
        "city": "Winnipeg", "province": "Manitoba",
        "lat": 49.8953809, "lon": -97.216016, "postal": "R3H 0C1",
        "slug": "canlan-sports-winnipeg",
    },
    {
        "existing_id": None,
        "camp_name": "Canlan Sports - Saskatoon",
        "city": "Saskatoon", "province": "Saskatchewan",
        "lat": 52.0564036, "lon": -106.6053045, "postal": "S7T 1C9",
        "slug": "canlan-sports-saskatoon",
    },
    {
        "existing_id": None,
        "camp_name": "Canlan Sports - Burnaby",
        "city": "Burnaby", "province": "British Columbia",
        "lat": 49.2511125, "lon": -122.9694595, "postal": "V5B 3B8",
        "slug": "canlan-sports-burnaby",
    },
    {
        "existing_id": None,
        "camp_name": "Canlan Sports - Langley",
        "city": "Langley", "province": "British Columbia",
        "lat": 49.1060760, "lon": -122.6416955, "postal": "V2Y 2P3",
        "slug": "canlan-sports-langley",
    },
    {
        "existing_id": None,
        "camp_name": "Canlan Sports - North Vancouver",
        "city": "North Vancouver", "province": "British Columbia",
        "lat": 49.3135750, "lon": -123.0032601, "postal": "V7H 2Y9",
        "slug": "canlan-sports-north-vancouver",
    },
    {
        "existing_id": None,
        "camp_name": "Canlan Sports - Oshawa",
        "city": "Oshawa", "province": "Ontario",
        "lat": 43.8536950, "lon": -78.8791328, "postal": "L1J 8C4",
        "slug": "canlan-sports-oshawa",
    },
]

# Correct tags for Canlan (hockey/skating day camps)
CANLAN_CORRECT_TAGS = [
    "hockey", "figure-skating", "ice-skating",
    "sport-multi", "sports-instructional-training",
]

# Tags to remove (migration artifacts on existing program)
CANLAN_BAD_TAGS = ["video-game-development", "cit-lit-program"]


def get_or_create_tag_id(cursor, slug: str) -> int | None:
    cursor.execute(
        "SELECT id FROM activity_tags WHERE slug = %s AND is_active = 1", (slug,)
    )
    row = cursor.fetchone()
    return row["id"] if row else None


def fix_existing_program_tags(cursor, program_id: int):
    """Remove bad tags, ensure correct tags on the Toronto master program."""
    print(f"  Fixing tags on program id={program_id}:")

    # Remove bad tags
    for slug in CANLAN_BAD_TAGS:
        tag_id = get_or_create_tag_id(cursor, slug)
        if tag_id:
            cursor.execute(
                "DELETE FROM program_tags WHERE program_id = %s AND tag_id = %s",
                (program_id, tag_id)
            )
            if cursor.rowcount:
                print(f"    Removed bad tag: {slug}")

    # Ensure correct tags
    for slug in CANLAN_CORRECT_TAGS:
        tag_id = get_or_create_tag_id(cursor, slug)
        if not tag_id:
            print(f"    WARNING: tag not found: {slug}")
            continue
        cursor.execute(
            "SELECT 1 FROM program_tags WHERE program_id = %s AND tag_id = %s",
            (program_id, tag_id)
        )
        if not cursor.fetchone():
            cursor.execute(
                "INSERT INTO program_tags (program_id, tag_id) VALUES (%s, %s)",
                (program_id, tag_id)
            )
            print(f"    Added tag: {slug}")
        else:
            print(f"    Tag already present: {slug}")


def create_program_for_camp(cursor, camp_id: int, template_program: dict):
    """Create a program record for a camp, based on the Toronto template."""
    cursor.execute(
        """
        INSERT INTO programs
            (camp_id, name, type, age_from, age_to, cost_from, cost_to,
             mini_description, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
        """,
        (
            camp_id,
            template_program["name"],
            template_program["type"],
            template_program.get("age_from"),
            template_program.get("age_to"),
            template_program.get("cost_from"),
            template_program.get("cost_to"),
            template_program.get("mini_description", ""),
        )
    )
    new_program_id = cursor.lastrowid

    # Copy correct tags to new program
    for slug in CANLAN_CORRECT_TAGS:
        tag_id = get_or_create_tag_id(cursor, slug)
        if tag_id:
            cursor.execute(
                "INSERT INTO program_tags (program_id, tag_id) VALUES (%s, %s)",
                (new_program_id, tag_id)
            )
    return new_program_id


def run():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ── Get Toronto master program as template ────────────────────────────────
    cursor.execute(
        "SELECT * FROM programs WHERE camp_id = 1777 AND status = 1 LIMIT 1"
    )
    template = cursor.fetchone()
    if not template:
        print("ERROR: No active program found for Canlan Toronto (camp_id=1777)")
        cursor.close()
        conn.close()
        return

    print(f"Template program: id={template['id']}  name={template['name']!r}")

    # Fix tags on Toronto master program
    fix_existing_program_tags(cursor, template["id"])

    # Get Toronto master camp details for copying tier/website/description
    cursor.execute("SELECT * FROM camps WHERE id = 1777")
    master_camp = cursor.fetchone()

    print()
    camps_activated = 0
    camps_created = 0
    programs_created = 0

    for loc in CANLAN_LOCATIONS:
        print(f"Processing: {loc['camp_name']} ({loc['city']}, {loc['province']})")

        if loc["existing_id"]:
            # ── Activate existing record ──────────────────────────────────────
            camp_id = loc["existing_id"]

            # Update to correct name, slug, lat/lon, and activate
            cursor.execute(
                """
                UPDATE camps
                SET camp_name = %s,
                    slug = %s,
                    city = %s,
                    province = %s,
                    lat = %s,
                    lon = %s,
                    status = 1,
                    tier = %s,
                    website = %s,
                    description = %s
                WHERE id = %s
                """,
                (
                    loc["camp_name"], loc["slug"], loc["city"], loc["province"],
                    loc["lat"], loc["lon"],
                    master_camp["tier"],
                    master_camp["website"],
                    master_camp["description"],
                    camp_id,
                )
            )
            print(f"  ACTIVATED existing id={camp_id}")
            camps_activated += 1

            # Check if already has a program
            cursor.execute(
                "SELECT id FROM programs WHERE camp_id = %s AND status = 1", (camp_id,)
            )
            if cursor.fetchone():
                print(f"  Program already exists — skipping")
            else:
                pid = create_program_for_camp(cursor, camp_id, template)
                print(f"  Created program id={pid}")
                programs_created += 1

        else:
            # ── Create new camp record ────────────────────────────────────────
            # Check slug doesn't already exist
            cursor.execute(
                "SELECT id FROM camps WHERE slug = %s", (loc["slug"],)
            )
            if cursor.fetchone():
                print(f"  SKIP — slug {loc['slug']!r} already exists")
                continue

            cursor.execute(
                """
                INSERT INTO camps
                    (camp_name, slug, tier, status, lat, lon,
                     city, province, country, website, description)
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                """,
                (
                    loc["camp_name"], loc["slug"],
                    master_camp["tier"],
                    loc["lat"], loc["lon"],
                    loc["city"], loc["province"],
                    master_camp["website"],
                    master_camp["description"],
                )
            )
            camp_id = cursor.lastrowid
            print(f"  CREATED new camp id={camp_id}")
            camps_created += 1

            pid = create_program_for_camp(cursor, camp_id, template)
            print(f"  Created program id={pid}")
            programs_created += 1

        print()

    conn.commit()
    cursor.close()
    conn.close()

    print(f"=== Done ===")
    print(f"  Camps activated (existing records): {camps_activated}")
    print(f"  Camps created (new records):        {camps_created}")
    print(f"  Programs created:                   {programs_created}")


if __name__ == "__main__":
    run()
