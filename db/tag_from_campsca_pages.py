#!/usr/bin/env python3
"""
db/tag_from_campsca_pages.py

Scrapes ALL camps.ca activity category pages (sourced from
csc_collaterals/ALL CAMP PAGES CURRENT.xlsx), extracts camp IDs, and inserts
the corresponding activity_tags into program_tags for every active program
belonging to those camps.

Run:
    python3 db/tag_from_campsca_pages.py [--dry-run]

This is an idempotent backfill — INSERT IGNORE means re-runs are safe.
The automated OurKids sync (sync_from_source.py) will keep tags current once live.
"""

import re
import ssl
import sys
import time
import urllib.request
import urllib.error

_SSL_CTX = ssl._create_unverified_context()  # macOS Python lacks system certs

# ── SQLwebitems display name → our activity_tag slug ───────────────────────
# Skips special-needs conditions (Autism, ADHD, etc.) and age-bracket pages.
WEBITEMS_TO_SLUG: dict[str, str] = {
    "3D Design":                        "3d-design",
    "3D Printing":                      "3d-printing",
    "Academic/Tutoring (multi)":        "academic-tutoring-multi",
    "Acro Dance":                       "acro-dance",
    "Acting (Film & TV)":               "acting-film-tv",
    "AI (Artificial Intelligence)":     "ai-artificial-intelligence",
    "Animals":                          "animals",
    "Animation":                        "animation",
    "Archery":                          "archery",
    "Architecture":                     "architecture",
    "Arduino":                          "arduino",
    "Arts & Crafts":                    "arts-crafts",
    "Aviation":                         "aviation",
    "Badminton":                        "badminton",
    "Baking/Decorating":                "baking-decorating",
    "Ball Sports (multi)":              "ball-sports-multi",
    "Ballet":                           "ballet",
    "Ballroom":                         "ballroom",
    "Baseball/Softball":                "baseball-softball",
    "Basketball":                       "basketball",
    "BMX/Motocross":                    "bmx-motocross",
    "Board Sailing":                    "board-sailing",
    "Breakdancing":                     "breakdancing",
    "Bronze Cross":                     "bronze-cross",
    "Canoeing":                         "canoeing",
    "Cartooning":                       "cartooning",
    "Ceramics":                         "ceramics",
    "Chess":                            "chess",
    "Cheer":                            "cheer",
    "CIT/LIT Program":                  "cit-lit-program",
    "Circus":                           "circus",
    "Comedy":                           "comedy",
    "Cooking":                          "cooking",
    "Creative writing":                 "creative-writing",
    "Credit Courses":                   "credit-courses",
    "Cricket":                          "cricket",
    "Cycling":                          "cycling",
    "Dance (multi)":                    "dance-multi",
    "Debate":                           "debate",
    "Diving":                           "diving",
    "Drawing":                          "drawing",
    "Empowerment":                      "empowerment",
    "Engineering":                      "engineering",
    "Entrepreneurship":                 "entrepreneurship",
    "Extreme Sports (multi)":           "extreme-sports-multi",
    "Fantasy (multi)":                  "fantasy-multi",
    "Fashion Design":                   "fashion-design",
    "Fencing":                          "fencing",
    "Figure Skating":                   "figure-skating",
    "Financial Literacy":               "financial-literacy",
    "First-aid/lifesaving":             "first-aid-lifesaving",
    "Filmmaking":                       "filmmaking",
    "Fishing":                          "fishing",
    "Flag Football":                    "flag-football",
    "Football":                         "football",
    "Gaga":                             "gaga",
    "Gaming":                           "gaming",
    "Glee":                             "glee",
    "Golf":                             "golf",
    "Guitar":                           "guitar",
    "Gymnastics":                       "gymnastics",
    "Harry Potter":                     "harry-potter",
    "Hiking":                           "hiking",
    "Hip Hop":                          "hip-hop",
    "Hockey":                           "hockey",
    "Horseback Riding/Equestrian":      "horseback-riding-equestrian",
    "Ice Skating":                      "ice-skating",
    "Instructor lead (group)":          "instructor-led-group",
    "Instructor lead (one on one)":     "instructor-led-one-on-one",
    "Jam Camp":                         "jam-camp",
    "JAVA":                             "java",
    "Jazz":                             "jazz",
    "Karate":                           "karate",
    "Kayaking/Sea Kayaking":            "kayaking-sea-kayaking",
    "Lacrosse":                         "lacrosse",
    "Language Instruction":             "language-instruction",
    "Leadership (multi)":               "leadership-multi",
    "Leadership Training":              "leadership-training",
    "LEGO":                             "lego",
    "Magic":                            "magic",
    "Makeup Artistry":                  "makeup-artistry",
    "Makerspace":                       "makerspace",
    "Marine Biology":                   "marine-biology",
    "Martial Arts":                     "martial-arts",
    "Math":                             "math",
    "Medical Science":                  "medical-science",
    "Meditation":                       "meditation",
    "Mindfulness Training":             "mindfulness-training",
    "Minecraft":                        "minecraft",
    "Military":                         "military",
    "Modeling":                         "modeling",
    "Mountain Biking":                  "mountain-biking",
    "Music (multi)":                    "music-multi",
    "Music Recording":                  "music-recording",
    "Musical instrument training":      "musical-instrument-training",
    "Musical Theatre":                  "musical-theatre",
    "Nature/Environment":               "nature-environment",
    "Ninja Warrior":                    "ninja-warrior",
    "Paintball":                        "paintball",
    "Painting":                         "painting",
    "Parkour":                          "parkour",
    "Percussion":                       "percussion",
    "Performing Arts (multi)":          "performing-arts-multi",
    "Photography":                      "photography",
    "Piano":                            "piano",
    "Pickleball":                       "pickleball",
    "Ping Pong":                        "ping-pong",
    "Pottery":                          "pottery",
    "Programming (multi)":              "programming-multi",
    "Public Speaking":                  "public-speaking",
    "Python":                           "python",
    "Reading":                          "reading",
    "Robotics":                         "robotics",
    "Rock Climbing":                    "rock-climbing",
    "Roblox":                           "roblox",
    "Rollerblading":                    "rollerblading",
    "Ropes Course":                     "ropes-course",
    "Rowing":                           "rowing",
    "Rugby":                            "rugby",
    "Safari":                           "safari",
    "Sailing/Marine Skills":            "sailing-marine-skills",
    "Science (multi)":                  "science-multi",
    "Scratch":                          "scratch",
    "Sewing":                           "sewing",
    "Skateboarding":                    "skateboarding",
    "Skiing":                           "skiing",
    "Skilled Trades Activities":        "skilled-trades-activities",
    "Soccer":                           "soccer",
    "Social Justice":                   "social-justice",
    "Songwriting":                      "songwriting",
    "Space":                            "space",
    "Sports-Instructional and Training": "sports-instructional-training",
    "Squash":                           "squash",
    "STEAM":                            "steam",
    "STEM":                             "stem",
    "Strength and Conditioning":        "strength-and-conditioning",
    "Super Camp":                       "super-camp",
    "Surfing":                          "surfing",
    "Survival skills":                  "survival-skills",
    "Swimming":                         "swimming",
    "Taekwondo":                        "taekwondo",
    "Technology":                       "technology",
    "Tennis":                           "tennis",
    "Test Preparation":                 "test-preparation",
    "Theatre Arts":                     "theatre-arts",
    "Track and Field":                  "track-and-field",
    "Trampoline":                       "trampoline",
    "Travel":                           "travel",
    "Ultimate Frisbee":                 "ultimate-frisbee",
    "Videography":                      "videography",
    "Video Game Design":                "video-game-design",
    "Visual Arts (multi)":              "visual-arts-multi",
    "Vocal Training / Singing":         "vocal-training-singing",
    "Volleyball":                       "volleyball",
    "Water Sports (multi)":             "water-sports-multi",
    "Waterskiing/Wakeboarding":         "waterskiing-wakeboarding",
    "Web Design":                       "web-design",
    "Web Development":                  "web-development",
    "Weight Loss Program":              "weight-loss-program",
    "Whitewater Rafting":               "whitewater-rafting",
    "Wilderness Out-tripping":          "wilderness-out-tripping",
    "Wilderness Skills":                "wilderness-skills",
    "Woodworking":                      "woodworking",
    "Writing":                          "writing",
    "Yoga":                             "yoga",
    "Zip Line":                         "zip-line",
    "Zoology":                          "zoology",
    # Special needs / medical — no activity tag mapping:
    # ADD/ADHD, Autism Spectrum Disorder, Cancer, Diabetes, Down Syndrome,
    # Dyslexia, Intellectual disability, Physical Disability, Vision loss,
    # Troubled Teens
    # Age brackets — not activity tags:
    # Ages 4 to 6, Ages 7 to 9, Ages 10 to 12, Ages 13 to 15, Ages 16+
}


def parse_webitems(list_options: str) -> list[str]:
    """Extract SQLwebitems values from a list_options string."""
    m = re.search(r'SQLwebitems:\s*(.+?)(?:\s*,\s*SQL|\s*$)', list_options)
    if not m:
        return []
    raw = m.group(1)
    # Each item is comma-separated; strip whitespace from each
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return items


def load_pages_from_excel(xlsx_path: str) -> list[tuple[str, list[str]]]:
    """
    Parse the Excel and return a deduplicated list of (page_url, [tag_slugs]).
    Only pages with at least one mappable SQLwebitems tag are included.
    Deduplicates by (page_url) — keeps first occurrence.
    """
    import pandas as pd
    df = pd.read_excel(xlsx_path)

    seen_urls: set[str] = set()
    pages: list[tuple[str, list[str]]] = []

    for _, row in df.iterrows():
        url = str(row.get("page URL", "") or "").strip()
        opts = str(row.get("list options", "") or "")
        if not url or "SQLwebitems" not in opts:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        items = parse_webitems(opts)
        slugs = [WEBITEMS_TO_SLUG[i] for i in items if i in WEBITEMS_TO_SLUG]
        if slugs:
            pages.append((url, slugs))

    return pages


def fetch_camp_ids(path: str) -> list[int]:
    """Fetch a camps.ca category page and extract camp IDs from links."""
    url = f"https://www.camps.ca{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as e:
        print(f"  FETCH ERROR: {e}")
        return []
    ids = re.findall(r'href=["\']\/[a-z0-9\-]+\/(\d+)["\']', html)
    return list({int(i) for i in ids})


def main():
    import sys
    sys.path.insert(0, "/Users/181lp/Documents/CLAUDE_code/projects/csc")
    from db.connection import get_connection

    dry_run = "--dry-run" in sys.argv
    xlsx = "/Users/181lp/Documents/CLAUDE_code/csc_collaterals/ALL CAMP PAGES CURRENT.xlsx"

    if dry_run:
        print("DRY RUN — no writes\n")

    pages = load_pages_from_excel(xlsx)
    print(f"Loaded {len(pages)} unique activity pages from Excel\n")

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Pre-load tag slug → id map
    cur.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
    slug_to_id = {r["slug"]: r["id"] for r in cur.fetchall()}

    total_ins = total_skp = 0
    results = []

    for path, tag_slugs in pages:
        print(f"Fetching {path} ...", end=" ", flush=True)
        camp_ids = fetch_camp_ids(path)
        if not camp_ids:
            print("0 camps, skip")
            continue

        # Filter to active camps in our DB
        ph = ",".join(["%s"] * len(camp_ids))
        cur.execute(
            f"SELECT id FROM camps WHERE id IN ({ph}) AND status = 1", camp_ids
        )
        db_ids = [r["id"] for r in cur.fetchall()]
        if not db_ids:
            print(f"{len(camp_ids)} on page, 0 in DB, skip")
            continue

        # Get all active program IDs for these camps
        ph2 = ",".join(["%s"] * len(db_ids))
        cur.execute(
            f"SELECT id FROM programs WHERE camp_id IN ({ph2}) AND status = 1", db_ids
        )
        prog_ids = [r["id"] for r in cur.fetchall()]

        tag_ids = [slug_to_id[s] for s in tag_slugs if s in slug_to_id]
        ins = skp = 0
        for pid in prog_ids:
            for tid in tag_ids:
                if dry_run:
                    ins += 1
                else:
                    cur.execute(
                        "INSERT IGNORE INTO program_tags (program_id, tag_id, is_primary) "
                        "VALUES (%s, %s, 0)",
                        (pid, tid),
                    )
                    if cur.rowcount > 0:
                        ins += 1
                    else:
                        skp += 1

        if not dry_run:
            conn.commit()

        total_ins += ins
        total_skp += skp
        results.append((path, len(camp_ids), len(db_ids), ins, skp))
        print(f"{len(camp_ids)} camps ({len(db_ids)} in DB) → +{ins} new tags, {skp} existed")
        time.sleep(0.3)

    cur.close()
    conn.close()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}COMPLETE")
    print(f"Total new tag rows: {total_ins:,}")
    print(f"Already existed:    {total_skp:,}")
    print(f"Pages processed:    {len(results)}")


if __name__ == "__main__":
    main()
