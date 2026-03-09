"""
db/migrate_categories_l2l3.py
Populate categories table with all level-2 and level-3 taxonomy entries.

Level-2 rows: slug + all children (if any) in filter_activity_tags
Level-3 rows: slug only (leaf nodes — exact match)

Run once:
  source .venv/bin/activate && python3 db/migrate_categories_l2l3.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

# ── Level-2 tags that have level-3 children ──────────────────────────────────
# Format: parent_slug → [child_slugs]
LEVEL2_WITH_CHILDREN = {
    # ARTS
    "dance-multi": [
        "acro-dance", "ballet", "ballroom", "breakdancing", "contemporary",
        "hip-hop", "jazz", "lyrical", "modern", "preschool-dance", "tap", "technique",
    ],
    "fantasy-multi": [
        "dungeons-and-dragons", "harry-potter", "medieval", "star-wars",
        "superhero-marvel-dc",
    ],
    "music-multi": [
        "djing", "glee", "guitar", "jam-camp", "music-recording",
        "musical-instrument-training", "percussion", "piano", "songwriting",
        "string", "vocal-training-singing",
    ],
    "performing-arts-multi": [
        "acting-film-tv", "magic", "modeling", "musical-theatre",
        "set-and-costume-design", "theatre-arts", "playwriting", "podcasting",
        "puppetry", "storytelling",
    ],
    "visual-arts-multi": [
        "arts-crafts", "cartooning", "ceramics", "comic-art", "drawing",
        "filmmaking", "knitting-and-crochet", "mixed-media", "painting",
        "papier-mache", "photography", "pottery", "videography",
    ],
    # COMPUTERS & TECH
    "programming-multi": [
        "arduino", "c-sharp", "c-plus-plus", "java", "pygame", "python",
        "scratch", "swift-apple",
    ],
    # EDUCATION
    "academic-tutoring-multi": [
        "instructor-led-group", "instructor-led-one-on-one",
    ],
    "leadership-multi": [
        "cit-lit-program", "empowerment", "leadership-training", "social-justice",
    ],
    "science-multi": [
        "animals", "archaeology-paleontology", "architecture", "engineering",
        "forensic-science", "health-science", "marine-biology", "medical-science",
        "meteorology", "safari", "space", "zoology",
    ],
    # SPORTS
    "ball-sports-multi": [
        "baseball-softball", "basketball", "cricket", "dodgeball", "flag-football",
        "gaga", "golf", "lacrosse", "pickleball", "rugby", "soccer", "squash",
        "tennis", "volleyball",
    ],
    "extreme-sports-multi": [
        "bmx-motocross", "mountain-biking", "rollerblading", "skateboarding",
        "skiing", "snowboarding",
    ],
    "water-sports-multi": [
        "board-sailing", "canoeing", "diving", "fishing", "kayaking-sea-kayaking",
        "rowing", "sailing-marine-skills", "stand-up-paddle-boarding", "surfing",
        "swimming", "tubing", "water-polo", "waterskiing-wakeboarding",
        "whitewater-rafting",
    ],
}

# ── Level-2 leaf slugs (no children) ─────────────────────────────────────────
LEVEL2_LEAVES = [
    # ADVENTURE
    "adventure-multi", "military", "ropes-course", "survival-skills", "travel",
    "wilderness-out-tripping", "wilderness-skills",
    # ARTS
    "arts-multi", "baking-decorating", "circus", "comedy", "cooking",
    "fashion-design", "makeup-artistry", "sculpture", "sewing", "woodworking",
    "youtube-vlogging",
    # COMPUTERS & TECH
    "3d-design", "3d-printing", "ai-artificial-intelligence", "animation",
    "computer-multi", "drone-technology", "gaming", "mechatronics", "micro-bit",
    "minecraft", "raspberry-pi", "roblox", "robotics", "technology",
    "video-game-design", "video-game-development", "virtual-reality",
    "web-design", "web-development",
    # EDUCATION
    "education-multi", "aviation", "board-games", "chess", "creative-writing",
    "credit-courses", "debate", "entrepreneurship", "essay-writing",
    "financial-literacy", "journalism", "language-instruction", "super-camp",
    "lego", "logical-thinking", "makerspace", "math", "nature-environment",
    "public-speaking", "reading", "skilled-trades-activities", "steam", "stem",
    "test-preparation", "urban-exploration", "writing",
    # HEALTH & FITNESS
    "health-fitness-multi", "behavioral-therapy", "bronze-cross",
    "first-aid-lifesaving", "meditation", "mindfulness-training", "nutrition",
    "pilates", "strength-and-conditioning", "weight-loss-program", "yoga",
    # SPORTS
    "sport-multi", "archery", "badminton", "cheer", "cycling", "disc-golf",
    "fencing", "figure-skating", "football", "gymnastics", "hiking", "hockey",
    "horseback-riding-equestrian", "ice-skating", "karate", "martial-arts",
    "ninja-warrior", "paintball", "parkour", "ping-pong", "rock-climbing",
    "scooter", "sports-instructional-training", "taekwondo", "track-and-field",
    "trampoline", "ultimate-frisbee", "zip-line",
]


def run():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Verify all slugs in our lists actually exist in activity_tags
    all_slugs_to_verify = (
        list(LEVEL2_WITH_CHILDREN.keys())
        + [s for children in LEVEL2_WITH_CHILDREN.values() for s in children]
        + LEVEL2_LEAVES
    )
    ph = ", ".join(["%s"] * len(all_slugs_to_verify))
    cursor.execute(
        f"SELECT slug FROM activity_tags WHERE slug IN ({ph})",
        tuple(all_slugs_to_verify),
    )
    found_slugs = {r["slug"] for r in cursor.fetchall()}
    missing = [s for s in all_slugs_to_verify if s not in found_slugs]
    if missing:
        print(f"WARNING: {len(missing)} slugs not found in activity_tags: {missing}")

    inserted = 0
    skipped = 0

    # ── Level-2 with children ─────────────────────────────────────────────────
    print("=== Level-2 parent categories ===")
    for parent_slug, children in LEVEL2_WITH_CHILDREN.items():
        cursor.execute("SELECT id FROM categories WHERE slug = %s", (parent_slug,))
        if cursor.fetchone():
            print(f"  SKIP (exists): {parent_slug}")
            skipped += 1
            continue

        filter_tags = ",".join([parent_slug] + children)
        # Derive title from activity_tags name
        cursor.execute("SELECT name FROM activity_tags WHERE slug = %s", (parent_slug,))
        row = cursor.fetchone()
        title = row["name"] if row else parent_slug

        cursor.execute(
            "INSERT INTO categories (title, slug, filter_activity_tags, is_active) VALUES (%s, %s, %s, 1)",
            (title, parent_slug, filter_tags),
        )
        print(f"  INSERTED: {parent_slug!r} ({len(children)} children)")
        inserted += 1

    # ── Level-2 leaves ────────────────────────────────────────────────────────
    print("\n=== Level-2 leaf categories ===")
    for slug in LEVEL2_LEAVES:
        cursor.execute("SELECT id FROM categories WHERE slug = %s", (slug,))
        if cursor.fetchone():
            skipped += 1
            continue

        cursor.execute("SELECT name FROM activity_tags WHERE slug = %s", (slug,))
        row = cursor.fetchone()
        title = row["name"] if row else slug

        cursor.execute(
            "INSERT INTO categories (title, slug, filter_activity_tags, is_active) VALUES (%s, %s, %s, 1)",
            (title, slug, slug),
        )
        print(f"  INSERTED leaf: {slug!r}")
        inserted += 1

    # ── Level-3 leaves ────────────────────────────────────────────────────────
    print("\n=== Level-3 leaf categories ===")
    all_l3 = [s for children in LEVEL2_WITH_CHILDREN.values() for s in children]
    for slug in all_l3:
        cursor.execute("SELECT id FROM categories WHERE slug = %s", (slug,))
        if cursor.fetchone():
            skipped += 1
            continue

        cursor.execute("SELECT name FROM activity_tags WHERE slug = %s", (slug,))
        row = cursor.fetchone()
        title = row["name"] if row else slug

        cursor.execute(
            "INSERT INTO categories (title, slug, filter_activity_tags, is_active) VALUES (%s, %s, %s, 1)",
            (title, slug, slug),
        )
        print(f"  INSERTED L3: {slug!r}")
        inserted += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n=== Done ===")
    print(f"  Inserted: {inserted}")
    print(f"  Skipped (already existed): {skipped}")

    # Summary count
    conn2 = get_connection()
    cur2 = conn2.cursor(dictionary=True)
    cur2.execute("SELECT COUNT(*) AS cnt FROM categories")
    total = cur2.fetchone()["cnt"]
    cur2.close()
    conn2.close()
    print(f"  Total categories rows: {total}")


if __name__ == "__main__":
    run()
