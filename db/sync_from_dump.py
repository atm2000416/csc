"""
db/sync_from_dump.py
Sync the new CSC database from a fresh SQL dump of the legacy camp directory.

What this syncs:
  1. NEW camps      — cids in dump (active, with city) not present in new DB → INSERT
  2. RE-ACTIVATED   — cids status=0 in new DB, now status=1 in dump → UPDATE status=1
  3. DEACTIVATED    — cids status=1 in new DB, now status=0 in dump → UPDATE status=0
                      (requires --deactivate flag; only touches camps whose ID came from
                       the old DB, not manually-created location branches)
  4. METADATA       — tier/website changes for active camps (--update-meta flag)
  5. LOCATIONS      — new extra_locations not yet in new DB → INSERT

What this does NOT touch:
  - activity_tags / program_tags / categories (curated in new DB)
  - Programs for existing camps (tags/descriptions curated post-migration)
  - Camps added manually in new DB (IDs not present in dump)

Usage:
  # Dry run — see what would change (always do this first)
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --dry-run

  # Apply standard sync (new camps + re-activations + new locations)
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql

  # Also deactivate camps that left the client list
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --deactivate

  # Full sync: new + deactivations + metadata + locations
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --deactivate --update-meta

  # Run only a specific section
  python3 db/sync_from_dump.py --dump /path/to/new_dump.sql --only status
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
    'ON': 'Ontario', 'On': 'Ontario', 'ont': 'Ontario', 'Ont': 'Ontario',
    'ontario': 'Ontario',
    'BC': 'British Columbia', 'B.C.': 'British Columbia',
    'AB': 'Alberta', 'Ab': 'Alberta',
    'QC': 'Quebec', 'Qc': 'Quebec', 'QuÃ©bec': 'Quebec',
    'MB': 'Manitoba', 'SK': 'Saskatchewan', 'NS': 'Nova Scotia',
    'NB': 'New Brunswick', 'NL': 'Newfoundland', 'PE': 'Prince Edward Island',
}

TIER_MAP = {
    'gold': 'gold', 'silver': 'silver', 'bronze': 'bronze',
    'double': 'silver',  # legacy tier name
    'single': 'bronze',
}


def normalise_province(p):
    p = (p or '').strip()
    return PROVINCE_MAP.get(p, p) if p else None


def normalise_city(c):
    return c.strip().title() if c else None


def slugify(text):
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


# ── Dump parsers ──────────────────────────────────────────────────────────────

def _extract_block(content, table):
    """Extract the VALUES block from an INSERT INTO `table` VALUES (...);
    Uses ';\\n' as the terminator — MySQL dumps end each statement with ';\\n'.
    Falls back to greedy match if not found.
    """
    # Primary: match up to semicolon at end of line
    match = re.search(
        rf'INSERT INTO `{table}` VALUES (.*?);\n',
        content, re.DOTALL
    )
    if match:
        return match.group(1)
    # Fallback: greedy to end of file section
    match = re.search(
        rf'INSERT INTO `{table}` VALUES (.*)',
        content, re.DOTALL
    )
    return match.group(1).rstrip(';\n') if match else None


def parse_camps(content):
    """
    Old schema: (cid, camp_name, prefix, listingClass, eListingType, status,
                  mod_date, location, Lat, Lon, weight, filename, usePretty,
                  prettyURL, onlineonly, wentLive, showAnalytics, agate)
    Returns dict: {cid: {camp_name, tier, status, lat, lon}}
    """
    block = _extract_block(content, 'camps')
    if not block:
        raise RuntimeError("camps INSERT not found in dump")

    rows = re.findall(
        r"\((\d+),'((?:[^'\\]|\\.)*)',('(?:[^'\\]|\\.)*'|NULL),'([^']*)',"
        r"'([^']*)',(\d+),'[^']*','[^']*','([^']*?)','([^']*?)',",
        block
    )
    result = {}
    for row in rows:
        cid, camp_name, _, listing_class, e_listing, status, lat, lon = row
        cid = int(cid)
        camp_name = camp_name.replace("\\'", "'")
        tier = TIER_MAP.get(e_listing, 'bronze')
        try:
            lat_f = float(lat) if lat and lat != '0' else None
            lon_f = float(lon) if lon and lon != '0' else None
        except ValueError:
            lat_f = lon_f = None
        result[cid] = {
            'cid': cid,
            'camp_name': camp_name,
            'tier': tier,
            'status': int(status),
            'lat': lat_f,
            'lon': lon_f,
        }
    return result


def parse_addresses(content):
    """
    Old schema: (cid, address, city, province, postal, country, ...)
    Returns dict: {cid: {city, province, postal, address}}
    """
    block = _extract_block(content, 'addresses')
    if not block:
        return {}

    rows = re.findall(
        r"\((\d+),'((?:[^'\\]|\\.)*?)','((?:[^'\\]|\\.)*?)','((?:[^'\\]|\\.)*?)',"
        r"'((?:[^'\\]|\\.)*?)',(\d+)",
        block
    )
    result = {}
    for row in rows:
        cid, address, city, province, postal, _ = row
        cid = int(cid)
        result[cid] = {
            'city': normalise_city(city),
            'province': normalise_province(province),
            'postal': postal.strip(),
            'address': address.strip().replace("\\'", "'"),
        }
    return result


def parse_general_info(content):
    """
    Old schema: (cid, website, director_name|NULL, category, description, ...)
    director_name may be NULL or a quoted string.
    Returns dict: {cid: {website}}
    """
    block = _extract_block(content, 'generalInfo')
    if not block:
        return {}

    # Match: (cid, 'website', NULL|'director',  -> grab cid + website
    # Websites don't contain single quotes so [^']* is safe here
    rows = re.findall(
        r"\((\d+),'([^']*)',(?:NULL|'[^']*'),",
        block
    )
    result = {}
    for cid, website in rows:
        result[int(cid)] = {
            'website': website.strip(),
        }
    return result


def parse_extra_locations(content):
    """Returns dict: {cid: [location_dict, ...]}"""
    block = _extract_block(content, 'extra_locations')
    if not block:
        return {}

    rows = re.findall(
        r'\((\d+),(\d+),(\d+),\'([^\']*)\',([0-9.-]+),([0-9.-]+),'
        r'(\d+),\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',\'([^\']*)\',(\d+)',
        block
    )
    result = defaultdict(list)
    for row in rows:
        el_id, cid, loc_id, postal, lat, lon, admin, address, city, province, country, main_loc = row
        city = normalise_city(city)
        province = normalise_province(province)
        if not city:
            continue
        result[int(cid)].append({
            'city': city, 'province': province,
            'lat': float(lat), 'lon': float(lon),
            'address': address.strip(), 'postal': postal.strip(),
        })
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def name_related(a, b):
    stop = {"camp", "the", "of", "at", "in", "and", "&", "-", "summer",
            "day", "sports", "inc", "ltd", "school", "schools"}
    a_sig = set(a.lower().split()) - stop
    b_sig = set(b.lower().split()) - stop
    return bool(a_sig & b_sig) if a_sig and b_sig else False


def ensure_unique_slug(cursor, slug_base):
    slug = slug_base
    counter = 1
    while True:
        cursor.execute("SELECT id FROM camps WHERE slug = %s", (slug,))
        if not cursor.fetchone():
            return slug
        slug = f"{slug_base}-{counter}"
        counter += 1


# ── Main sync logic ───────────────────────────────────────────────────────────

def run(dump_path, dry_run, only, update_meta, deactivate=False, skip_ids=None):
    print(f"Reading dump: {dump_path}")
    with open(dump_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    dump_camps = parse_camps(content)
    dump_addrs = parse_addresses(content)
    dump_info  = parse_general_info(content)
    dump_locs  = parse_extra_locations(content)

    print(f"  Parsed {len(dump_camps)} camps, {len(dump_addrs)} addresses, "
          f"{len(dump_info)} generalInfo rows, "
          f"{sum(len(v) for v in dump_locs.values())} extra_location rows\n")

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Load all new-DB camps
    cursor.execute("SELECT id, camp_name, city, province, status, tier, website FROM camps")
    new_db_all = {r['id']: r for r in cursor.fetchall()}

    skip_ids = set(skip_ids or [])

    stats = {
        'new_camps': 0,
        'deactivated': 0,
        'reactivated': 0,
        'meta_updated': 0,
        'locations_added': 0,
    }

    # ── 1. Status changes ─────────────────────────────────────────────────────
    if only in (None, 'status', 'all'):
        print("=== Status changes ===")
        changed = 0
        for cid, old in dump_camps.items():
            if cid not in new_db_all:
                continue
            new = new_db_all[cid]
            old_active = old['status'] == 1
            new_active = new['status'] == 1

            if old_active and not new_active:
                # Re-activate: dump says active, new DB says inactive
                print(f"  RE-ACTIVATE id={cid}: {new['camp_name']!r}")
                if not dry_run:
                    cursor.execute("UPDATE camps SET status=1 WHERE id=%s", (cid,))
                stats['reactivated'] += 1
                changed += 1
            elif not old_active and new_active and deactivate:
                # Dump says inactive (camp left client list), new DB still active.
                # Only deactivate camps whose ID came from the old DB (cid in dump).
                # Manually-created location branches (IDs assigned post-migration)
                # won't appear in dump_camps at all, so they're never touched here.
                if cid in skip_ids:
                    print(f"  SKIPPED     id={cid}: {new['camp_name']!r}  (in --skip-ids)")
                    continue
                print(f"  DEACTIVATE  id={cid}: {new['camp_name']!r}")
                if not dry_run:
                    cursor.execute("UPDATE camps SET status=0 WHERE id=%s", (cid,))
                stats['deactivated'] += 1
                changed += 1

        if not changed:
            print("  No status changes.")
        print()

    # ── 2. New camps ──────────────────────────────────────────────────────────
    if only in (None, 'new', 'all'):
        print("=== New camps (in dump, not in new DB) ===")
        added = 0
        for cid, old in sorted(dump_camps.items()):
            if cid in new_db_all:
                continue
            if old['status'] != 1:
                continue  # don't import inactive camps

            addr = dump_addrs.get(cid, {})
            info = dump_info.get(cid, {})
            city = addr.get('city')
            province = addr.get('province')

            if not city:
                continue  # skip camps with no city data

            camp_name = old['camp_name']
            slug = ensure_unique_slug(cursor, slugify(camp_name)) if not dry_run else slugify(camp_name)

            print(f"  NEW id={cid}: {camp_name!r} ({city}, {province})")
            if dry_run:
                added += 1
                continue

            cursor.execute(
                """
                INSERT INTO camps
                    (id, camp_name, slug, tier, status, lat, lon,
                     city, province, country, website, description)
                VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                ON DUPLICATE KEY UPDATE id=id
                """,
                (cid, camp_name, slug, old.get('tier', 'bronze'),
                 old.get('lat'), old.get('lon'),
                 city, province,
                 info.get('website', ''), info.get('description', ''))
            )
            added += 1

        stats['new_camps'] = added
        if not added:
            print("  No new camps.")
        print()

    # ── 3. Metadata updates ───────────────────────────────────────────────────
    if update_meta and only in (None, 'meta', 'all'):
        print("=== Metadata updates (tier/website) ===")
        updated = 0
        for cid, old in dump_camps.items():
            if cid not in new_db_all:
                continue
            new = new_db_all[cid]
            new_tier = TIER_MAP.get(old.get('tier', ''), old.get('tier', 'bronze'))
            info = dump_info.get(cid, {})
            changes = {}
            if new_tier != new.get('tier'):
                changes['tier'] = new_tier
            website = info.get('website', '')
            if website and website != (new.get('website') or ''):
                changes['website'] = website

            if changes:
                desc = ', '.join(f"{k}: {new.get(k)!r}→{v!r}" for k, v in changes.items())
                print(f"  UPDATE id={cid} {new['camp_name']!r}: {desc}")
                if not dry_run:
                    set_clause = ', '.join(f"{k}=%s" for k in changes)
                    cursor.execute(
                        f"UPDATE camps SET {set_clause} WHERE id=%s",
                        list(changes.values()) + [cid]
                    )
                updated += 1

        stats['meta_updated'] = updated
        if not updated:
            print("  No metadata changes.")
        print()

    # ── 4. Extra locations ────────────────────────────────────────────────────
    if only in (None, 'locations', 'all'):
        print("=== Missing extra_locations ===")

        # Build city+province index for all new-DB camps
        cursor.execute("SELECT id, camp_name, city, province, status FROM camps")
        all_camps = cursor.fetchall()
        city_prov_index = defaultdict(list)
        for c in all_camps:
            key = ((c['city'] or '').strip().lower(), (c['province'] or '').strip().lower())
            city_prov_index[key].append(c)

        active_in_new = {r['id']: r for r in all_camps if r['status'] == 1}

        # Build city-only index as fallback (handles empty province in extra_locations)
        city_only_index = defaultdict(list)
        for c in all_camps:
            city_only_index[(c['city'] or '').strip().lower()].append(c)

        # Cities that are not real searchable places
        INVALID_CITIES = {'.', '', 'virtual', 'international', 'online', 'tbd', 'n/a'}

        added_locs = 0
        COMMIT_EVERY = 20  # commit after every N new camps created
        camps_since_commit = 0

        for cid, locs in sorted(dump_locs.items()):
            if cid not in active_in_new:
                continue
            primary = active_in_new[cid]

            for loc in locs:
                # Skip invalid/non-geographic cities
                if (loc['city'] or '.').lower() in INVALID_CITIES:
                    continue

                key = (loc['city'].lower(), (loc['province'] or '').lower())
                # Always merge city+province match with city-only match
                # (handles empty province in dump matching populated province in DB)
                prov_matches = city_prov_index.get(key, [])
                city_matches = city_only_index.get(loc['city'].lower(), [])
                seen_ids = set()
                all_matches = []
                for m in prov_matches + city_matches:
                    if m['id'] not in seen_ids:
                        seen_ids.add(m['id'])
                        all_matches.append(m)
                related = [m for m in all_matches if name_related(primary['camp_name'], m['camp_name'])]
                if related:
                    continue  # already present

                camp_name = f"{primary['camp_name']} - {loc['city']}"
                slug_base = slugify(camp_name)

                if dry_run:
                    print(f"  [DRY] CREATE {camp_name!r} "
                          f"({loc['city']}, {loc['province'] or '?'})")
                    added_locs += 1
                    continue

                slug = ensure_unique_slug(cursor, slug_base)

                # Get master camp details
                cursor.execute("SELECT * FROM camps WHERE id=%s", (cid,))
                master = cursor.fetchone() or primary

                cursor.execute(
                    """
                    INSERT INTO camps
                        (camp_name, slug, tier, status, lat, lon,
                         city, province, country, website, description)
                    VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                    """,
                    (camp_name, slug, master.get('tier', 'bronze'),
                     loc['lat'], loc['lon'],
                     loc['city'], loc['province'],
                     master.get('website'), master.get('description'))
                )
                new_camp_id = cursor.lastrowid
                print(f"  CREATE id={new_camp_id}: {camp_name!r}")

                # Copy programs from primary
                cursor.execute(
                    "SELECT * FROM programs WHERE camp_id=%s AND status=1", (cid,)
                )
                for prog in cursor.fetchall():
                    cursor.execute(
                        """
                        INSERT INTO programs
                            (camp_id, name, type, age_from, age_to, cost_from, cost_to,
                             mini_description, description, status)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,1)
                        """,
                        (new_camp_id, prog['name'], prog['type'],
                         prog.get('age_from'), prog.get('age_to'),
                         prog.get('cost_from'), prog.get('cost_to'),
                         prog.get('mini_description', ''), prog.get('description', ''))
                    )
                    new_prog_id = cursor.lastrowid
                    cursor.execute(
                        "SELECT tag_id FROM program_tags WHERE program_id=%s", (prog['id'],)
                    )
                    for tag_row in cursor.fetchall():
                        cursor.execute(
                            "INSERT INTO program_tags (program_id, tag_id) VALUES (%s,%s)",
                            (new_prog_id, tag_row['tag_id'])
                        )

                added_locs += 1
                camps_since_commit += 1
                # Refresh index so duplicates within same dump don't re-trigger
                city_prov_index[key].append({'id': new_camp_id, 'camp_name': camp_name,
                                              'city': loc['city'], 'province': loc['province'],
                                              'status': 1})
                city_only_index[loc['city'].lower()].append({'id': new_camp_id,
                    'camp_name': camp_name, 'city': loc['city'],
                    'province': loc['province'], 'status': 1})
                # Commit in batches to avoid lock timeouts
                if camps_since_commit >= COMMIT_EVERY:
                    conn.commit()
                    camps_since_commit = 0

        stats['locations_added'] = added_locs
        if not added_locs:
            print("  No missing locations.")
        print()

    # ── Commit & summary ──────────────────────────────────────────────────────
    if not dry_run:
        conn.commit()

    cursor.close()
    conn.close()

    prefix = "DRY RUN — " if dry_run else ""
    print("=" * 60)
    print(f"{prefix}Sync complete")
    print(f"  New camps {'would be ' if dry_run else ''}inserted:       {stats['new_camps']}")
    print(f"  Camps {'would be ' if dry_run else ''}re-activated:       {stats['reactivated']}")
    if deactivate:
        print(f"  Camps {'would be ' if dry_run else ''}deactivated:        {stats['deactivated']}")
    if update_meta:
        print(f"  Metadata {'would be ' if dry_run else ''}updated:        {stats['meta_updated']}")
    print(f"  Locations {'would be ' if dry_run else ''}added:          {stats['locations_added']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync CSC new DB from a legacy SQL dump"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to DB")
    parser.add_argument("--only",
                        choices=["status", "new", "meta", "locations", "all"],
                        default=None,
                        help="Run only a specific sync section")
    parser.add_argument("--update-meta", action="store_true",
                        help="Also update tier/website for existing camps")
    parser.add_argument("--deactivate", action="store_true",
                        help="Deactivate camps whose status is now 0 in the dump "
                             "(i.e. they left the client list). Always dry-run first "
                             "to review the list before applying.")
    parser.add_argument("--skip-ids",
                        help="Comma-separated camp IDs to skip during deactivation "
                             "(e.g. manually-promoted sub-locations: 422,529,579)")
    parser.add_argument("--dump", default=DEFAULT_DUMP,
                        help="Path to SQL dump file")
    args = parser.parse_args()
    skip_ids = set(int(x) for x in args.skip_ids.split(",")) if args.skip_ids else None
    run(args.dump, args.dry_run, args.only, args.update_meta, args.deactivate, skip_ids)
