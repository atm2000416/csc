"""
db/migrate_taxonomy.py
One-time migration: fix activity_tags slug mismatches and populate categories table.

Run once:
  source .venv/bin/activate && python3 db/migrate_taxonomy.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import get_connection

# ─── Part A: Slug renames ────────────────────────────────────────────────────

RENAMES = [
    ("microbit",                      "micro-bit"),
    ("papier-mch",                    "papier-mache"),
    ("bakingdecorating",              "baking-decorating"),
    ("sports-instructional-and-training", "sports-instructional-training"),
    ("health-and-fitness-multi",      "health-fitness-multi"),
]

# ─── Part C: Categories rows ─────────────────────────────────────────────────

CATEGORIES = [
    {
        "title": "Adventure",
        "slug": "adventure",
        "filter_activity_tags": (
            "adventure-multi,military,ropes-course,survival-skills,travel,"
            "wilderness-out-tripping,wilderness-skills"
        ),
    },
    {
        "title": "Arts",
        "slug": "arts",
        "filter_activity_tags": (
            "arts-multi,baking-decorating,circus,comedy,cooking,dance-multi,"
            "acro-dance,ballet,ballroom,breakdancing,contemporary,hip-hop,jazz,"
            "lyrical,modern,preschool-dance,tap,technique,fantasy-multi,"
            "dungeons-and-dragons,harry-potter,medieval,star-wars,"
            "superhero-marvel-dc,fashion-design,makeup-artistry,music-multi,"
            "djing,glee,guitar,jam-camp,music-recording,musical-instrument-training,"
            "percussion,piano,songwriting,string,vocal-training-singing,"
            "performing-arts-multi,acting-film-tv,magic,modeling,musical-theatre,"
            "set-and-costume-design,theatre-arts,playwriting,podcasting,puppetry,"
            "storytelling,visual-arts-multi,arts-crafts,cartooning,ceramics,"
            "comic-art,drawing,filmmaking,knitting-and-crochet,mixed-media,painting,"
            "papier-mache,photography,pottery,videography,sculpture,sewing,"
            "woodworking,youtube-vlogging"
        ),
    },
    {
        "title": "Computers & Tech",
        "slug": "computers-tech",
        "filter_activity_tags": (
            "computer-multi,3d-design,3d-printing,ai-artificial-intelligence,"
            "animation,drone-technology,gaming,mechatronics,micro-bit,minecraft,"
            "programming-multi,arduino,c-sharp,c-plus-plus,java,pygame,python,"
            "scratch,swift-apple,raspberry-pi,roblox,robotics,technology,"
            "video-game-design,video-game-development,virtual-reality,web-design,"
            "web-development"
        ),
    },
    {
        "title": "Education",
        "slug": "education",
        "filter_activity_tags": (
            "education-multi,academic-tutoring-multi,instructor-led-group,"
            "instructor-led-one-on-one,aviation,board-games,chess,creative-writing,"
            "credit-courses,debate,entrepreneurship,essay-writing,financial-literacy,"
            "journalism,language-instruction,leadership-multi,cit-lit-program,"
            "empowerment,leadership-training,social-justice,super-camp,lego,"
            "logical-thinking,makerspace,math,nature-environment,public-speaking,"
            "reading,science-multi,animals,archaeology-paleontology,architecture,"
            "engineering,forensic-science,health-science,marine-biology,"
            "medical-science,meteorology,safari,space,zoology,"
            "skilled-trades-activities,steam,stem,test-preparation,"
            "urban-exploration,writing"
        ),
    },
    {
        "title": "Health & Fitness",
        "slug": "health-fitness",
        "filter_activity_tags": (
            "health-fitness-multi,behavioral-therapy,bronze-cross,"
            "first-aid-lifesaving,meditation,mindfulness-training,nutrition,"
            "pilates,strength-and-conditioning,weight-loss-program,yoga"
        ),
    },
    {
        "title": "Sports",
        "slug": "sports",
        "filter_activity_tags": (
            "sport-multi,archery,badminton,ball-sports-multi,baseball-softball,"
            "basketball,cricket,dodgeball,flag-football,gaga,golf,lacrosse,"
            "pickleball,rugby,soccer,squash,tennis,volleyball,cheer,cycling,"
            "disc-golf,extreme-sports-multi,bmx-motocross,mountain-biking,"
            "rollerblading,skateboarding,skiing,snowboarding,fencing,"
            "figure-skating,football,gymnastics,hiking,hockey,"
            "horseback-riding-equestrian,ice-skating,karate,martial-arts,"
            "ninja-warrior,paintball,parkour,ping-pong,rock-climbing,scooter,"
            "sports-instructional-training,taekwondo,track-and-field,trampoline,"
            "ultimate-frisbee,water-sports-multi,board-sailing,canoeing,diving,"
            "fishing,kayaking-sea-kayaking,rowing,sailing-marine-skills,"
            "stand-up-paddle-boarding,surfing,swimming,tubing,water-polo,"
            "waterskiing-wakeboarding,whitewater-rafting,zip-line"
        ),
    },
]


def run():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # ── Part A: Rename slugs ──────────────────────────────────────────────────
    print("=== Part A: Renaming slugs ===")
    rename_count = 0
    for old_slug, new_slug in RENAMES:
        cursor.execute("SELECT id, slug FROM activity_tags WHERE slug = %s", (old_slug,))
        row = cursor.fetchone()
        if row:
            cursor.execute(
                "UPDATE activity_tags SET slug = %s WHERE slug = %s",
                (new_slug, old_slug)
            )
            print(f"  RENAMED: {old_slug!r} → {new_slug!r} (id={row['id']})")
            rename_count += 1
        else:
            # Already renamed or doesn't exist — check if new slug already exists
            cursor.execute("SELECT id FROM activity_tags WHERE slug = %s", (new_slug,))
            existing = cursor.fetchone()
            if existing:
                print(f"  SKIP (already renamed): {old_slug!r} → {new_slug!r}")
            else:
                print(f"  WARNING: slug not found in DB: {old_slug!r}")

    # ── Part B: Insert missing slugs (c-sharp, c-plus-plus) ──────────────────
    print("\n=== Part B: Inserting missing slugs ===")

    # Get parent row for programming-multi to copy domain_id/parent_id
    cursor.execute("SELECT * FROM activity_tags WHERE slug = 'programming-multi'")
    prog_multi = cursor.fetchone()
    if not prog_multi:
        print("  ERROR: programming-multi not found — cannot insert c-sharp/c-plus-plus")
    else:
        print(f"  programming-multi row: {prog_multi}")
        # Determine which columns exist (domain_id, parent_id vary by schema)
        columns = list(prog_multi.keys())
        print(f"  activity_tags columns: {columns}")

        NEW_SLUGS = [
            {"slug": "c-sharp",    "name": "C#"},
            {"slug": "c-plus-plus", "name": "C++"},
        ]

        for entry in NEW_SLUGS:
            cursor.execute("SELECT id FROM activity_tags WHERE slug = %s", (entry["slug"],))
            if cursor.fetchone():
                print(f"  SKIP (already exists): {entry['slug']!r}")
                continue

            # Build INSERT based on available columns
            # Core fields we always set:
            insert_data = {"slug": entry["slug"], "is_active": 1}

            # Optional columns — copy from programming-multi where they exist
            for col in ["domain_id", "parent_id", "category_id", "level", "domain"]:
                if col in prog_multi and prog_multi[col] is not None:
                    insert_data[col] = prog_multi[col]

            # name/display_name column
            for col in ["name", "display_name", "title"]:
                if col in columns:
                    insert_data[col] = entry["name"]
                    break

            cols_str = ", ".join(insert_data.keys())
            placeholders = ", ".join(["%s"] * len(insert_data))
            cursor.execute(
                f"INSERT INTO activity_tags ({cols_str}) VALUES ({placeholders})",
                list(insert_data.values())
            )
            print(f"  INSERTED: {entry['slug']!r} (name={entry['name']!r})")

    # ── Part C: Populate categories table ────────────────────────────────────
    print("\n=== Part C: Inserting categories ===")

    # Check current state
    cursor.execute("SELECT COUNT(*) AS cnt FROM categories")
    existing_count = cursor.fetchone()["cnt"]
    print(f"  categories table currently has {existing_count} rows")

    cat_count = 0
    for cat in CATEGORIES:
        cursor.execute("SELECT id FROM categories WHERE slug = %s", (cat["slug"],))
        if cursor.fetchone():
            print(f"  SKIP (already exists): {cat['slug']!r}")
            continue
        cursor.execute(
            """
            INSERT INTO categories (title, slug, filter_activity_tags, is_active)
            VALUES (%s, %s, %s, 1)
            """,
            (cat["title"], cat["slug"], cat["filter_activity_tags"])
        )
        print(f"  INSERTED category: {cat['title']!r} (slug={cat['slug']!r})")
        cat_count += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n=== Done ===")
    print(f"  Slugs renamed: {rename_count}")
    print(f"  Categories inserted: {cat_count}")


if __name__ == "__main__":
    run()
