"""
db/validate_extra_locations.py

Validates all active camps in the new DB against extra_locations in the
SQL dump. Reports which additional locations are missing or inactive.

This is the generalised version of the Canlan fix — runs across all 198
camps that have extra_locations in the old DB.

Usage:
  source .venv/bin/activate && python3 db/validate_extra_locations.py [dump_path]

Default dump path: /Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql
"""
import re
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection
from collections import defaultdict

DUMP_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql"
)

PROVINCE_MAP = {
    '': None, ' ': None, 'ON': 'Ontario', 'On': 'Ontario', 'ont': 'Ontario',
    'Ont': 'Ontario', 'ontario': 'Ontario', 'BC': 'British Columbia',
    'B.C.': 'British Columbia', 'AB': 'Alberta', 'QC': 'Quebec',
    'MB': 'Manitoba', 'SK': 'Saskatchewan', 'NS': 'Nova Scotia',
    'NB': 'New Brunswick', 'NL': 'Newfoundland', 'PE': 'Prince Edward Island',
}


def normalise_province(p: str) -> str:
    p = p.strip()
    return PROVINCE_MAP.get(p, p)


def normalise_city(c: str) -> str:
    return c.strip().title()


def parse_extra_locations(dump_path: str) -> dict[int, list[dict]]:
    """
    Parse extra_locations INSERT from dump.
    Returns dict: {cid: [location_dict, ...]}
    """
    print(f"Reading dump: {dump_path}")
    with open(dump_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    match = re.search(r'INSERT INTO `extra_locations` VALUES (.*?);', content, re.DOTALL)
    if not match:
        raise RuntimeError("extra_locations INSERT not found in dump")

    # Schema: id, cid, locations, postal, Lat, Lon, admin, address, city, province, country, main_loc, ...
    rows = re.findall(
        r'\((\d+),(\d+),(\d+),\'([^\']*)\',([0-9.-]+),([0-9.-]+),'
        r'(\d+),\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',(\d+)',
        match.group(1)
    )

    result: dict[int, list[dict]] = defaultdict(list)
    for row in rows:
        el_id, cid, loc_id, postal, lat, lon, admin, address, city, province, country, main_loc = row
        cid = int(cid)
        city = normalise_city(city)
        province = normalise_province(province)
        if not city:
            continue
        result[cid].append({
            "el_id":    int(el_id),
            "cid":      cid,
            "loc_id":   int(loc_id),
            "postal":   postal,
            "lat":      float(lat),
            "lon":      float(lon),
            "admin":    int(admin),
            "address":  address.strip(),
            "city":     city,
            "province": province,
            "main_loc": int(main_loc),
        })

    print(f"Parsed {sum(len(v) for v in result.values())} extra_location rows "
          f"for {len(result)} camps")
    return result


def run():
    extra_locs = parse_extra_locations(DUMP_PATH)

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Load all active camps from new DB, keyed by id
    cursor.execute("""
        SELECT id, camp_name, city, province, status
        FROM camps WHERE status = 1
    """)
    active_camps = {r["id"]: r for r in cursor.fetchall()}

    # Load ALL camps (any status) for city/province lookup
    cursor.execute("SELECT id, camp_name, city, province, status FROM camps")
    all_camps_list = cursor.fetchall()

    # Build index: (city_lower, province_lower) → list of camp rows
    city_prov_index: dict[tuple, list] = defaultdict(list)
    for c in all_camps_list:
        key = (
            (c["city"] or "").strip().lower(),
            (c["province"] or "").strip().lower(),
        )
        city_prov_index[key].append(c)

    print(f"\nActive camps in new DB: {len(active_camps)}")
    print(f"Checking {len(extra_locs)} cids from extra_locations...\n")

    missing_locations = []    # (camp_name, cid, location)
    inactive_locations = []   # (camp_name, cid, location, existing_camp_id)
    ok_locations = []         # already active

    for cid, locations in sorted(extra_locs.items()):
        # Only process if this camp is active in the new DB
        if cid not in active_camps:
            continue

        camp = active_camps[cid]

        for loc in locations:
            if not loc["city"]:
                continue

            city_key = loc["city"].lower()
            prov_key = (loc["province"] or "").lower()
            key = (city_key, prov_key)

            matches = city_prov_index.get(key, [])

            # Only count a match if the camp name is related to the same brand
            def name_related(a: str, b: str) -> bool:
                a_words = set(a.lower().split())
                b_words = set(b.lower().split())
                stop = {"camp", "the", "of", "at", "in", "and", "&", "-", "summer",
                        "day", "sports", "inc", "ltd"}
                a_sig = a_words - stop
                b_sig = b_words - stop
                return bool(a_sig & b_sig) if a_sig and b_sig else False

            related_matches = [m for m in matches if name_related(camp["camp_name"], m["camp_name"])]

            if not related_matches:
                # No related camp record for this city — truly missing
                missing_locations.append((camp, cid, loc))
            else:
                active_matches = [m for m in related_matches if m["status"] == 1]
                if active_matches:
                    ok_locations.append((camp, cid, loc, active_matches[0]))
                else:
                    # Related record exists but inactive
                    inactive_locations.append((camp, cid, loc, related_matches[0]))

    cursor.close()
    conn.close()

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"{'='*70}")
    print(f"EXTRA LOCATIONS VALIDATION REPORT")
    print(f"{'='*70}")
    print(f"  Locations already active:  {len(ok_locations)}")
    print(f"  Locations INACTIVE:        {len(inactive_locations)}")
    print(f"  Locations MISSING:         {len(missing_locations)}")
    print()

    if inactive_locations:
        print(f"── INACTIVE LOCATIONS (exist in DB but status=0) ──────────────────")
        for camp, cid, loc, existing in inactive_locations:
            print(f"  Camp: {camp['camp_name']!r} (id={cid})")
            print(f"    Location: {loc['city']}, {loc['province']}  "
                  f"lat={loc['lat']:.4f} lon={loc['lon']:.4f}")
            print(f"    Existing DB record: id={existing['id']}  "
                  f"{existing['camp_name']!r}  status={existing['status']}")
            print()

    if missing_locations:
        print(f"── MISSING LOCATIONS (not in DB at all) ───────────────────────────")
        # Group by parent camp
        by_camp: dict = defaultdict(list)
        for camp, cid, loc in missing_locations:
            by_camp[(cid, camp["camp_name"])].append(loc)

        for (cid, camp_name), locs in sorted(by_camp.items()):
            print(f"  Camp: {camp_name!r} (id={cid})")
            for loc in locs:
                print(f"    MISSING: {loc['city']}, {loc['province']}  "
                      f"| {loc['address']}  postal={loc['postal']}")
            print()

    print(f"{'='*70}")
    print(f"SUMMARY: {len(missing_locations)} missing + "
          f"{len(inactive_locations)} inactive locations across "
          f"{len(set(c['id'] for c,_,_ in missing_locations) | set(c['id'] for c,_,_,_ in inactive_locations))} "
          f"camps need attention.")
    print(f"{'='*70}")


if __name__ == "__main__":
    run()
