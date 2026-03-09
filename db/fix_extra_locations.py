"""
db/fix_extra_locations.py
Auto-creates missing camp location records identified by validate_extra_locations.py.

For each missing location:
  1. Creates a new camp record (inheriting tier/website/description from primary)
  2. Copies the primary camp's active programs + their tags to the new location

Usage:
  # Dry run — see what would be created
  python3 db/fix_extra_locations.py --dry-run

  # Run for all camps
  python3 db/fix_extra_locations.py

  # Run for specific camp IDs only
  python3 db/fix_extra_locations.py --cids 204,295,514

  # Custom dump path
  python3 db/fix_extra_locations.py --dump /path/to/dump.sql
"""
import re
import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

DEFAULT_DUMP = "/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql"

PROVINCE_MAP = {
    'ON': 'Ontario', 'On': 'Ontario', 'ont': 'Ontario',
    'BC': 'British Columbia', 'AB': 'Alberta', 'QC': 'Quebec',
    'MB': 'Manitoba', 'SK': 'Saskatchewan', 'NS': 'Nova Scotia',
    'NB': 'New Brunswick', 'NL': 'Newfoundland', 'PE': 'Prince Edward Island',
}


def normalise_province(p):
    p = p.strip()
    return PROVINCE_MAP.get(p, p) if p else None


def normalise_city(c):
    return c.strip().title() if c else None


def slugify(text):
    import re as _re
    s = text.lower().strip()
    s = _re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def parse_extra_locations(dump_path):
    with open(dump_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    match = re.search(r'INSERT INTO `extra_locations` VALUES (.*?);', content, re.DOTALL)
    if not match:
        raise RuntimeError("extra_locations INSERT not found in dump")
    rows = re.findall(
        r'\((\d+),(\d+),(\d+),\'([^\']*)\',([0-9.-]+),([0-9.-]+),'
        r'(\d+),\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',(\d+)',
        match.group(1)
    )
    result = defaultdict(list)
    for row in rows:
        el_id, cid, loc_id, postal, lat, lon, admin, address, city, province, country, main_loc = row
        city = normalise_city(city)
        province = normalise_province(province)
        if not city:
            continue
        result[int(cid)].append({
            "city": city, "province": province,
            "lat": float(lat), "lon": float(lon),
            "address": address.strip(), "postal": postal.strip(),
            "main_loc": int(main_loc),
        })
    return result


def name_related(a, b):
    stop = {"camp", "the", "of", "at", "in", "and", "&", "-", "summer",
            "day", "sports", "inc", "ltd", "school", "schools"}
    a_sig = set(a.lower().split()) - stop
    b_sig = set(b.lower().split()) - stop
    return bool(a_sig & b_sig) if a_sig and b_sig else False


def get_missing_locations(cursor, extra_locs, target_cids=None):
    """Return list of (primary_camp, location_dict) that are missing from new DB."""
    cursor.execute("SELECT id, camp_name, city, province, status FROM camps")
    all_camps = cursor.fetchall()

    city_prov_index = defaultdict(list)
    for c in all_camps:
        key = ((c["city"] or "").strip().lower(), (c["province"] or "").strip().lower())
        city_prov_index[key].append(c)

    cursor.execute("SELECT id, camp_name, city, province FROM camps WHERE status = 1")
    active_camps = {r["id"]: r for r in cursor.fetchall()}

    missing = []
    for cid, locations in sorted(extra_locs.items()):
        if cid not in active_camps:
            continue
        if target_cids and cid not in target_cids:
            continue
        primary = active_camps[cid]
        for loc in locations:
            key = (loc["city"].lower(), (loc["province"] or "").lower())
            matches = city_prov_index.get(key, [])
            related = [m for m in matches if name_related(primary["camp_name"], m["camp_name"])]
            if not related:
                missing.append((primary, loc))
    return missing


def copy_programs(cursor, source_camp_id, dest_camp_id, dry_run):
    """Copy all active programs and their tags from source to dest camp."""
    cursor.execute(
        "SELECT * FROM programs WHERE camp_id = %s AND status = 1", (source_camp_id,)
    )
    programs = cursor.fetchall()
    if not programs:
        return 0

    copied = 0
    for prog in programs:
        if dry_run:
            print(f"      [DRY] Would copy program: {prog['name']!r}")
            copied += 1
            continue

        cursor.execute(
            """
            INSERT INTO programs
                (camp_id, name, type, age_from, age_to, cost_from, cost_to,
                 mini_description, description, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """,
            (dest_camp_id, prog["name"], prog["type"],
             prog.get("age_from"), prog.get("age_to"),
             prog.get("cost_from"), prog.get("cost_to"),
             prog.get("mini_description", ""), prog.get("description", ""))
        )
        new_prog_id = cursor.lastrowid

        # Copy program_tags
        cursor.execute(
            "SELECT tag_id FROM program_tags WHERE program_id = %s", (prog["id"],)
        )
        for tag_row in cursor.fetchall():
            cursor.execute(
                "INSERT INTO program_tags (program_id, tag_id) VALUES (%s, %s)",
                (new_prog_id, tag_row["tag_id"])
            )
        copied += 1

    return copied


def run(dump_path, target_cids, dry_run):
    extra_locs = parse_extra_locations(dump_path)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM camps WHERE status = 1")
    primary_camps = {r["id"]: r for r in cursor.fetchall()}

    missing = get_missing_locations(cursor, extra_locs, target_cids)

    print(f"\n{'DRY RUN — ' if dry_run else ''}Found {len(missing)} missing locations\n")
    if not missing:
        print("Nothing to do.")
        cursor.close()
        conn.close()
        return

    camps_created = 0
    programs_copied = 0

    # Group by parent camp for cleaner output
    by_camp = defaultdict(list)
    for primary, loc in missing:
        by_camp[primary["id"]].append((primary, loc))

    for camp_id, items in sorted(by_camp.items()):
        primary = items[0][0]
        master = primary_camps.get(camp_id, primary)
        print(f"Camp: {primary['camp_name']!r} (id={camp_id})")

        for _, loc in items:
            loc_label = f"{loc['city']}, {loc['province'] or '?'}"
            slug_base = slugify(f"{primary['camp_name']}-{loc['city']}")

            # Ensure slug uniqueness
            slug = slug_base
            counter = 1
            while True:
                cursor.execute("SELECT id FROM camps WHERE slug = %s", (slug,))
                if not cursor.fetchone():
                    break
                slug = f"{slug_base}-{counter}"
                counter += 1

            camp_name = f"{primary['camp_name']} - {loc['city']}"

            if dry_run:
                print(f"  [DRY] Would CREATE: {camp_name!r} ({loc_label})")
                print(f"        slug={slug}  lat={loc['lat']:.4f}  lon={loc['lon']:.4f}")
                camps_created += 1
                programs_copied += 1
                continue

            cursor.execute(
                """
                INSERT INTO camps
                    (camp_name, slug, tier, status, lat, lon,
                     city, province, country, website, description)
                VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                """,
                (camp_name, slug, master.get("tier", "bronze"),
                 loc["lat"], loc["lon"],
                 loc["city"], loc["province"],
                 master.get("website"), master.get("description"))
            )
            new_camp_id = cursor.lastrowid
            print(f"  CREATED id={new_camp_id}: {camp_name!r} ({loc_label})")
            camps_created += 1

            n = copy_programs(cursor, camp_id, new_camp_id, dry_run)
            if n:
                print(f"    Copied {n} program(s)")
                programs_copied += n
            else:
                print(f"    WARNING: no programs found to copy from camp id={camp_id}")

        print()

    if not dry_run:
        conn.commit()

    cursor.close()
    conn.close()

    print(f"{'='*50}")
    print(f"{'DRY RUN — ' if dry_run else ''}Done")
    print(f"  Camps {'would be ' if dry_run else ''}created:          {camps_created}")
    print(f"  Programs {'would be ' if dry_run else ''}copied:          {programs_copied}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cids", help="Comma-separated camp IDs to process")
    parser.add_argument("--dump", default=DEFAULT_DUMP)
    args = parser.parse_args()

    target_cids = set(int(c) for c in args.cids.split(",")) if args.cids else None
    run(args.dump, target_cids, args.dry_run)
