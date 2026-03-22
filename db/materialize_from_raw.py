#!/usr/bin/env python3
"""
db/materialize_from_raw.py
Populate CSC tables (camps, programs, program_tags, program_dates) from
ok_* staging tables loaded by load_raw_tables.py.

Replaces the regex-based ETL in sync_from_dump.py with SQL JOINs against
the raw OurKids staging tables.

Usage:
  python db/materialize_from_raw.py --dry-run
  python db/materialize_from_raw.py --skip-ids 422,529,579,1647 --deactivate
"""
import re
import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

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
    'double': 'silver', 'single': 'bronze',
}

INVALID_CITIES = {'.', '', 'virtual', 'international', 'online', 'tbd', 'n/a'}

# OurKids gender → CSC gender mapping
# OurKids: 0=unset, 1=Coed, 2=Girls, 3=Boys
# CSC:     0=Coed, 1=Boys, 2=Girls
_GENDER_MAP = {0: 0, 1: 0, 2: 2, 3: 1}

# OurKids trait IDs → CSC trait IDs (inferred from justification texts)
# OurKids: 1=Responsibility, 2=Independence, 3=Teamwork, 4=Courage,
#          5=Resilience, 6=Interpersonal, 7=Curiosity, 8=Creativity,
#          9=Physicality, 10=Generosity, 11=Tolerance, 12=Religious Faith
_TRAIT_MAP = {
    1: 15,   # Responsibility
    2: 14,   # Independence
    3: 10,   # Teamwork
    4: 13,   # Courage
    5: 11,   # Resilience
    6: 16,   # Interpersonal Skills
    7: 12,   # Curiosity
    8: 17,   # Creativity
    9: 18,   # Physicality
    10: 19,  # Generosity
    11: 20,  # Tolerance
    12: 22,  # Religious Faith
}

# OurKids language_immersion sitem IDs → human-readable language names
_LANG_SITEMS = {192: 'Mandarin', 193: 'French', 198: 'Spanish', 199: 'English', 262: 'German'}

# Session names to skip
_SKIP_PREFIXES = ("new program", "copy of")


def _normalise_province(p):
    p = (p or '').strip()
    return PROVINCE_MAP.get(p, p) if p else None


def _normalise_city(c):
    return c.strip().title() if c else None


def _slugify(text):
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def _ensure_unique_slug(cursor, slug_base):
    slug = slug_base
    counter = 1
    while True:
        cursor.execute("SELECT id FROM camps WHERE slug = %s", (slug,))
        if not cursor.fetchone():
            return slug
        slug = f"{slug_base}-{counter}"
        counter += 1


def _name_related(a, b):
    stop = {"camp", "the", "of", "at", "in", "and", "&", "-", "summer",
            "day", "sports", "inc", "ltd", "school", "schools"}
    a_sig = set(a.lower().split()) - stop
    b_sig = set(b.lower().split()) - stop
    return bool(a_sig & b_sig) if a_sig and b_sig else False


def _check_staging_tables(cursor):
    """Verify ok_* tables exist. Returns list of missing tables."""
    required = ["ok_camps", "ok_sessions", "ok_sitems", "ok_session_date",
                "ok_addresses", "ok_generalInfo"]
    missing = []
    for t in required:
        try:
            cursor.execute(f"SELECT 1 FROM `{t}` LIMIT 1")
            cursor.fetchone()
        except Exception:
            missing.append(t)
    return missing


def _get_columns(cursor, table):
    """Get column names for a staging table."""
    cursor.execute(f"SHOW COLUMNS FROM `{table}`")
    return [r["Field"] for r in cursor.fetchall()]


def _discover_schema(cursor):
    """Discover column names in ok_* tables and print for debugging."""
    for table in ["ok_camps", "ok_sessions", "ok_sitems", "ok_session_date",
                  "ok_addresses", "ok_generalInfo"]:
        try:
            cols = _get_columns(cursor, table)
            print(f"  {table}: {', '.join(cols)}")
        except Exception:
            print(f"  {table}: NOT FOUND")


def _load_webitems_to_slug():
    """Import WEBITEMS_TO_SLUG bridge from tag_from_campsca_pages."""
    from db.tag_from_campsca_pages import WEBITEMS_TO_SLUG
    return {k.lower(): v for k, v in WEBITEMS_TO_SLUG.items()}


def _load_keyword_tagger():
    """Import keyword inference from sync_from_dump (fallback tagger)."""
    from db.sync_from_dump import infer_tags
    return infer_tags


# ── Materialization steps ─────────────────────────────────────────────────────

def materialize_camps(cursor, dry_run, skip_ids, deactivate):
    """Sync camps table from ok_camps + ok_addresses + ok_generalInfo."""
    stats = {"new": 0, "updated": 0, "reactivated": 0, "deactivated": 0}

    # Load dump data from staging tables separately (avoids column name assumptions in JOINs)
    cursor.execute("SELECT * FROM ok_camps")
    raw_camps = {r["cid"]: r for r in cursor.fetchall()}

    cursor.execute("SELECT * FROM ok_addresses")
    raw_addrs = {r["cid"]: r for r in cursor.fetchall()}

    try:
        cursor.execute("SELECT * FROM ok_generalInfo")
        raw_info = {r["cid"]: r for r in cursor.fetchall()}
    except Exception:
        raw_info = {}

    # Merge into unified rows
    dump_rows = {}
    for cid, c in raw_camps.items():
        addr = raw_addrs.get(cid, {})
        info = raw_info.get(cid, {})
        dump_rows[cid] = {**c, **{f"addr_{k}": v for k, v in addr.items()},
                          **{f"info_{k}": v for k, v in info.items()}}

    # Load existing CSC camps
    cursor.execute("SELECT id, camp_name, city, province, status, tier, website FROM camps")
    csc_camps = {r["id"]: r for r in cursor.fetchall()}

    dump_cids = set(dump_rows.keys())

    print("=== Camp sync ===")

    for cid, d in sorted(dump_rows.items()):
        tier = TIER_MAP.get(d.get("eListingType") or "", "bronze")
        city = _normalise_city(d.get("addr_city"))
        province = _normalise_province(d.get("addr_province"))
        dump_active = int(d.get("status", 0)) == 1

        try:
            lat_raw = d.get("Lat")
            lon_raw = d.get("Lon")
            lat = float(lat_raw) if lat_raw and str(lat_raw) != "0" else None
            lon = float(lon_raw) if lon_raw and str(lon_raw) != "0" else None
        except (ValueError, TypeError):
            lat = lon = None

        prettyurl = d.get("prettyURL") or None
        website = (d.get("info_website") or "").strip()
        camp_name = d.get("camp_name", "")

        if cid in csc_camps:
            existing = csc_camps[cid]
            csc_active = existing["status"] == 1

            # Status changes
            if dump_active and not csc_active:
                print(f"  RE-ACTIVATE id={cid}: {camp_name!r}")
                if not dry_run:
                    cursor.execute("UPDATE camps SET status=1 WHERE id=%s", (cid,))
                stats["reactivated"] += 1
            elif not dump_active and csc_active and deactivate:
                if cid in skip_ids:
                    print(f"  SKIPPED     id={cid}: {camp_name!r}  (in --skip-ids)")
                    continue
                print(f"  DEACTIVATE  id={cid}: {camp_name!r}")
                if not dry_run:
                    cursor.execute("UPDATE camps SET status=0 WHERE id=%s", (cid,))
                stats["deactivated"] += 1

            # Metadata updates for active camps
            if dump_active:
                changes = {}
                if tier != existing.get("tier"):
                    changes["tier"] = tier
                if website and website != (existing.get("website") or ""):
                    changes["website"] = website
                if prettyurl and prettyurl != (existing.get("prettyurl") or ""):
                    changes["prettyurl"] = prettyurl
                if city and city != (existing.get("city") or ""):
                    changes["city"] = city
                if province and province != (existing.get("province") or ""):
                    changes["province"] = province
                if lat is not None:
                    changes["lat"] = lat
                if lon is not None:
                    changes["lon"] = lon

                if changes and not dry_run:
                    set_clause = ", ".join(f"{k}=%s" for k in changes)
                    cursor.execute(
                        f"UPDATE camps SET {set_clause} WHERE id=%s",
                        list(changes.values()) + [cid]
                    )
                if changes:
                    stats["updated"] += 1
        else:
            # New camp
            if not dump_active:
                continue
            if not city:
                continue  # skip camps with no city data

            slug = (_ensure_unique_slug(cursor, _slugify(camp_name))
                    if not dry_run else _slugify(camp_name))

            print(f"  NEW id={cid}: {camp_name!r} ({city}, {province})")
            if not dry_run:
                cursor.execute(
                    """INSERT INTO camps
                       (id, camp_name, slug, tier, status, lat, lon,
                        city, province, country, website, prettyurl)
                       VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                       ON DUPLICATE KEY UPDATE id=id""",
                    (cid, camp_name, slug, tier, lat, lon,
                     city, province, website, prettyurl)
                )
            stats["new"] += 1

    print(f"  New: {stats['new']}, Updated: {stats['updated']}, "
          f"Reactivated: {stats['reactivated']}, Deactivated: {stats['deactivated']}")
    print()
    return dump_cids


def materialize_programs(cursor, conn, dry_run, dump_cids, force=False):
    """Replace programs for all active camps using ok_sessions.

    Args:
        force: If True, skip change-detection and re-sync all camps
               (rebuilds tags from sitems data even if session names haven't changed).
    """
    stats = {"camps_synced": 0, "camps_skipped": 0, "camps_unchanged": 0,
             "programs_inserted": 0, "tags_inserted": 0, "traits_inserted": 0}

    # Load WEBITEMS bridge
    name_to_slug = _load_webitems_to_slug()
    infer_tags = _load_keyword_tagger()

    # Build sitems id → slug lookup from ok_sitems
    # Column is `item` in OurKids schema (not `item_name`)
    cursor.execute("SELECT * FROM ok_sitems")
    sitems_to_slug = {}
    for r in cursor.fetchall():
        item_name = r.get("item") or r.get("item_name") or r.get("name") or ""
        slug = name_to_slug.get(item_name.strip().lower())
        if slug:
            sitems_to_slug[r["id"]] = slug

    print(f"  Sitems→slug mappings: {len(sitems_to_slug)}")

    # Load active tag slug → id
    cursor.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
    tag_slug_to_id = {r["slug"]: r["id"] for r in cursor.fetchall()}

    # Load all active camps
    cursor.execute("SELECT id, camp_name FROM camps WHERE status = 1")
    active_camps = {r["id"]: r["camp_name"] for r in cursor.fetchall()}

    # Only process camps whose ID is a known CID in the dump (same safety as before)
    safe_camps = {k: v for k, v in active_camps.items() if k in dump_cids}
    skipped_branches = len(active_camps) - len(safe_camps)
    if skipped_branches:
        print(f"  Skipping {skipped_branches} camps (auto-increment location branches)")

    # Load all sessions from ok_sessions
    # OurKids schema: class_name (not name), start/end (not date_from/date_to)
    # No real status column — all sessions in the dump are active
    cursor.execute("SELECT * FROM ok_sessions")
    sessions_by_camp = defaultdict(list)
    for r in cursor.fetchall():
        cid = r.get("cid")
        if cid not in safe_camps:
            continue
        name = (r.get("class_name") or r.get("name") or "").strip().replace("\\'", "'")
        if not name:
            continue
        name_lower = name.lower()
        if any(name_lower.startswith(p) for p in _SKIP_PREFIXES):
            continue
        # Normalize field names for downstream use
        r["_cid"] = cid
        r["_name"] = name
        sessions_by_camp[cid].append(r)

    # Deduplicate by cleaned name per camp
    for cid in list(sessions_by_camp.keys()):
        seen = {}
        deduped = []
        for s in sessions_by_camp[cid]:
            clean_key = re.sub(r'\s+', ' ', s["_name"].strip().lower())
            if clean_key not in seen:
                seen[clean_key] = True
                deduped.append(s)
        sessions_by_camp[cid] = deduped

    total_sessions = sum(len(v) for v in sessions_by_camp.values())
    camps_with = len(sessions_by_camp)
    camps_without = len(safe_camps) - camps_with
    print(f"  {camps_with} camps with sessions, {camps_without} without, "
          f"{total_sessions} total session records")
    print()

    # Load existing program names for change detection
    cursor.execute(
        "SELECT camp_id, GROUP_CONCAT(name ORDER BY name SEPARATOR '|||') as names "
        "FROM programs WHERE status = 1 GROUP BY camp_id"
    )
    existing_names = {
        r["camp_id"]: set(r["names"].split("|||"))
        for r in cursor.fetchall()
    }

    print("=== Program sync ===")

    for camp_id in sorted(safe_camps):
        sessions = sessions_by_camp.get(camp_id)
        if not sessions:
            stats["camps_skipped"] += 1
            continue

        dump_name_set = {s["_name"] for s in sessions}
        db_name_set = existing_names.get(camp_id, set())
        new_names = dump_name_set - db_name_set
        gone_names = db_name_set - dump_name_set

        if not new_names and not gone_names and not force:
            stats["camps_unchanged"] += 1
            continue

        camp_name = safe_camps[camp_id]
        print(f"  {'[DRY] ' if dry_run else ''}SYNC id={camp_id}: {camp_name!r}  "
              f"+{len(new_names)} new  -{len(gone_names)} removed  "
              f"(total → {len(sessions)})")

        if dry_run:
            stats["camps_synced"] += 1
            continue

        # Delete existing programs + tags + dates
        cursor.execute(
            "SELECT id FROM programs WHERE camp_id = %s AND status = 1",
            (camp_id,)
        )
        old_ids = [r["id"] for r in cursor.fetchall()]
        if old_ids:
            id_list = ",".join(str(x) for x in old_ids)
            cursor.execute(f"DELETE FROM program_tags   WHERE program_id IN ({id_list})")
            cursor.execute(f"DELETE FROM program_traits WHERE program_id IN ({id_list})")
            cursor.execute(f"DELETE FROM program_dates  WHERE program_id IN ({id_list})")
            cursor.execute(f"DELETE FROM programs       WHERE id          IN ({id_list})")

        # Prepare all programs and their tags in memory first, then batch insert
        program_rows = []
        session_tags = []
        session_traits = []

        for s in sessions:
            name = s["_name"]
            session_type = s.get("type") or None

            date_from = s.get("start") or s.get("date_from")
            date_to = s.get("end") or s.get("date_to")
            if str(date_from) == "0000-00-00":
                date_from = None
            if str(date_to) == "0000-00-00":
                date_to = None

            gender_val = s.get("gender")
            try:
                gender = _GENDER_MAP.get(int(gender_val), 0) if gender_val is not None else 0
            except (ValueError, TypeError):
                gender = 0
            mini_desc = (str(s.get("mini_description") or ""))[:500]
            description = s.get("description") or None

            is_special_needs = 1 if str(s.get("isspecialneeds", "")).strip() == "1" else 0
            is_virtual = 1 if s.get("isvirtual") in (1, "1") else 0
            is_family = 1 if s.get("isfamily") in (1, "1") else 0
            before_care = 1 if s.get("before_care") in (1, "1") else 0
            after_care = 1 if s.get("after_care") in (1, "1") else 0

            # Decode language_immersion: "193+283" → "French"
            lang_immersion = None
            li_raw = str(s.get("language_immersion") or "")
            if li_raw and li_raw != "0":
                for part in re.split(r'[+,]', li_raw):
                    try:
                        lang_name = _LANG_SITEMS.get(int(part))
                        if lang_name and lang_name != "English":
                            lang_immersion = lang_name
                            break
                    except (ValueError, TypeError):
                        pass

            age_from = s.get("age_from")
            age_to = s.get("age_to")
            cost_from = s.get("cost_from")
            cost_to = s.get("cost_to")

            # Collect traits for this session
            session_trait_ids = []
            for trait_field in ("trait1", "trait2"):
                raw = s.get(trait_field)
                if raw:
                    try:
                        csc_trait = _TRAIT_MAP.get(int(raw))
                        if csc_trait and csc_trait not in session_trait_ids:
                            session_trait_ids.append(csc_trait)
                    except (ValueError, TypeError):
                        pass
            justification1 = s.get("justification1") or None
            justification2 = s.get("justification2") or None
            session_justifications = [justification1, justification2]

            program_rows.append((
                camp_id, name, session_type,
                age_from or None, age_to or None,
                cost_from or None, cost_to or None,
                date_from, date_to,
                gender, mini_desc, description,
                is_special_needs, is_virtual, is_family,
                before_care, after_care,
                lang_immersion, s.get("id")
            ))
            session_traits.append((session_trait_ids, session_justifications))

            # Resolve tags for this session
            tags = []
            seen_tag_ids = set()

            spec_id = s.get("specialty")
            if spec_id:
                try:
                    slug = sitems_to_slug.get(int(spec_id))
                except (ValueError, TypeError):
                    slug = None
                if slug:
                    tag_id = tag_slug_to_id.get(slug)
                    if tag_id and tag_id not in seen_tag_ids:
                        tags.append((tag_id, 1, 'specialty'))
                        seen_tag_ids.add(tag_id)

            cat_id = s.get("category")
            if cat_id:
                try:
                    slug = sitems_to_slug.get(int(cat_id))
                except (ValueError, TypeError):
                    slug = None
                if slug:
                    tag_id = tag_slug_to_id.get(slug)
                    if tag_id and tag_id not in seen_tag_ids:
                        tags.append((tag_id, 0, 'category'))
                        seen_tag_ids.add(tag_id)

            spec2_id = s.get("specialty2")
            if spec2_id:
                try:
                    slug = sitems_to_slug.get(int(spec2_id))
                except (ValueError, TypeError):
                    slug = None
                if slug:
                    tag_id = tag_slug_to_id.get(slug)
                    if tag_id and tag_id not in seen_tag_ids:
                        tags.append((tag_id, 0, 'category'))
                        seen_tag_ids.add(tag_id)

            # Parse activities with focus level: [sitem_id]level
            # Level 1=recreational, 2=instructional, 3=intense
            # Map to tag_role: 3→specialty, 2→category, 1→activity
            _LEVEL_TO_ROLE = {'3': 'specialty', '2': 'category', '1': 'activity'}
            activities_raw = s.get("activities") or ""
            for act_id_str, level_str in re.findall(r'\[(\d+)\](\d+)', str(activities_raw)):
                act_id = int(act_id_str)
                slug = sitems_to_slug.get(act_id)
                if slug:
                    tag_id = tag_slug_to_id.get(slug)
                    role = _LEVEL_TO_ROLE.get(level_str, 'activity')
                    if tag_id and tag_id not in seen_tag_ids:
                        tags.append((tag_id, 0, role))
                        seen_tag_ids.add(tag_id)

            if not seen_tag_ids:
                for slug in sorted(infer_tags([name], tag_slug_to_id)):
                    tag_id = tag_slug_to_id.get(slug)
                    if tag_id:
                        tags.append((tag_id, 0, 'activity'))

            session_tags.append(tags)

        # Batch insert programs
        cursor.executemany(
            """INSERT INTO programs
               (camp_id, name, type, age_from, age_to,
                cost_from, cost_to, start_date, end_date,
                gender, mini_description, description,
                is_special_needs, is_virtual, is_family,
                before_care, after_care,
                language_immersion, ourkids_session_id, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)""",
            program_rows
        )
        # Get the auto-increment IDs for the batch
        first_id = cursor.lastrowid
        prog_ids = list(range(first_id, first_id + len(program_rows)))
        stats["programs_inserted"] += len(program_rows)

        # Batch insert tags
        tag_rows = []
        for prog_id, tags in zip(prog_ids, session_tags):
            for tag_id, is_primary, tag_role in tags:
                tag_rows.append((prog_id, tag_id, is_primary, tag_role))

        if tag_rows:
            cursor.executemany(
                "INSERT IGNORE INTO program_tags "
                "(program_id, tag_id, is_primary, tag_role) "
                "VALUES (%s, %s, %s, %s)",
                tag_rows
            )
            stats["tags_inserted"] += cursor.rowcount

        # Batch insert traits
        trait_rows = []
        for prog_id, (trait_ids, justifications) in zip(prog_ids, session_traits):
            for i, tid in enumerate(trait_ids):
                j = justifications[i] if i < len(justifications) else None
                # Skip stub justifications
                if j and j.strip() in (".", ""):
                    j = None
                trait_rows.append((prog_id, tid, (j or "")[:500] if j else None))

        if trait_rows:
            cursor.executemany(
                "INSERT IGNORE INTO program_traits "
                "(program_id, trait_id, justification) "
                "VALUES (%s, %s, %s)",
                trait_rows
            )
            stats["traits_inserted"] += cursor.rowcount

        stats["camps_synced"] += 1
        if stats["camps_synced"] % 25 == 0:
            conn.commit()

    if not dry_run and stats["camps_synced"] % 25 != 0:
        conn.commit()

    print()
    print(f"  Camps synced: {stats['camps_synced']}, "
          f"Unchanged: {stats['camps_unchanged']}, "
          f"Skipped (no sessions): {stats['camps_skipped']}")
    print(f"  Programs inserted: {stats['programs_inserted']}, "
          f"Tags inserted: {stats['tags_inserted']}, "
          f"Traits inserted: {stats['traits_inserted']}")
    print()
    return stats


def materialize_dates(cursor, conn, dry_run):
    """Refresh program_dates from ok_session_date."""
    from datetime import date as _date
    today = str(_date.today())
    stats = {"inserted": 0}

    print("=== Program dates ===")

    # Check if ok_session_date exists
    try:
        cursor.execute("SELECT 1 FROM ok_session_date LIMIT 1")
        cursor.fetchone()
    except Exception:
        print("  WARNING: ok_session_date not found — skipping dates")
        return stats

    # Get active program IDs
    cursor.execute("SELECT id FROM programs WHERE status=1")
    active_prog_ids = {r["id"] for r in cursor.fetchall()}

    # Load future session_date rows from staging.
    # ok_session_date.seid = session ID in OurKids; this matches programs.id
    # because we just recreated programs with matching IDs... except we didn't.
    # The sessions in ok_sessions have their own seid.  Programs got new
    # auto-increment IDs.  We need to join via camp_id + session name.

    # Build program lookup: (camp_id, clean_name) → program_id
    cursor.execute("SELECT id, camp_id, name FROM programs WHERE status=1")
    prog_lookup = {}
    for r in cursor.fetchall():
        key = (r["camp_id"], re.sub(r'\s+', ' ', (r["name"] or "").strip().lower()))
        prog_lookup[key] = r["id"]

    # Build session id → (camp_id, clean_name) from ok_sessions
    cursor.execute("SELECT * FROM ok_sessions")
    seid_to_key = {}
    for r in cursor.fetchall():
        name = r.get("class_name") or r.get("name") or ""
        key = (r["cid"], re.sub(r'\s+', ' ', name.strip().lower()))
        seid_to_key[r["id"]] = key

    # Load future dates from staging
    # session_date schema: (id, cid, seid, start_date, end_date, cost_from, cost_to, ...)
    cursor.execute("SELECT * FROM ok_session_date")
    all_date_rows = cursor.fetchall()

    # Filter to future rows (column is `end` in OurKids, not `end_date`)
    date_rows = [r for r in all_date_rows
                 if str(r.get("end") or r.get("end_date") or "") >= today]

    matched = []
    for r in date_rows:
        key = seid_to_key.get(r.get("seid"))
        if not key:
            continue
        prog_id = prog_lookup.get(key)
        if not prog_id:
            continue
        matched.append((prog_id, r))

    # Group by program
    by_prog = defaultdict(list)
    for prog_id, r in matched:
        by_prog[prog_id].append(r)

    print(f"  {len(matched)} future session_date rows across {len(by_prog)} programs")

    if not dry_run and by_prog:
        # Clear existing future rows for matched programs, then re-insert
        prog_id_list = ",".join(str(pid) for pid in by_prog)
        cursor.execute(
            f"DELETE FROM program_dates WHERE end_date >= %s "
            f"AND program_id IN ({prog_id_list})",
            (today,)
        )
        inserted = 0
        for prog_id, rows in by_prog.items():
            for r in rows:
                sd_start = r.get("start") or r.get("start_date")
                sd_end = r.get("end") or r.get("end_date")
                cursor.execute(
                    """INSERT IGNORE INTO program_dates
                       (program_id, start_date, end_date, cost_from, cost_to,
                        before_care, after_care)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                    (prog_id, sd_start, sd_end,
                     r.get("cost_from"), r.get("cost_to"),
                     r.get("before_care", 0), r.get("after_care", 0))
                )
                inserted += 1
                if inserted % 100 == 0:
                    conn.commit()
        stats["inserted"] = inserted
    elif dry_run:
        stats["inserted"] = len(matched)

    print(f"  {'[DRY] ' if dry_run else ''}Dates inserted: {stats['inserted']}")
    print()
    return stats


def materialize_locations(cursor, conn, dry_run, dump_cids):
    """Create location-branch camps from ok_extra_locations."""
    stats = {"added": 0}

    print("=== Extra locations ===")

    # Check if ok_extra_locations exists
    try:
        cursor.execute("SELECT 1 FROM ok_extra_locations LIMIT 1")
        cursor.fetchone()
    except Exception:
        print("  ok_extra_locations not found — skipping")
        return stats

    # Load extra locations from staging
    cursor.execute("SELECT * FROM ok_extra_locations")
    dump_locs = defaultdict(list)
    for r in cursor.fetchall():
        city = _normalise_city(r.get("city"))
        province = _normalise_province(r.get("province"))
        if not city or city.lower() in INVALID_CITIES:
            continue
        try:
            lat = float(r.get("Lat") or r.get("lat")) if (r.get("Lat") or r.get("lat")) else None
            lon = float(r.get("Lon") or r.get("lon")) if (r.get("Lon") or r.get("lon")) else None
        except (ValueError, TypeError):
            lat = lon = None
        dump_locs[r.get("cid")].append({
            "city": city, "province": province,
            "lat": lat, "lon": lon,
            "address": (r.get("address") or "").strip(),
            "postal": (r.get("postal") or "").strip(),
        })

    # Build city+province index for all camps
    cursor.execute("SELECT id, camp_name, city, province, status FROM camps")
    all_camps = cursor.fetchall()
    city_prov_index = defaultdict(list)
    city_only_index = defaultdict(list)
    for c in all_camps:
        key = ((c["city"] or "").strip().lower(), (c["province"] or "").strip().lower())
        city_prov_index[key].append(c)
        city_only_index[(c["city"] or "").strip().lower()].append(c)

    active_in_new = {r["id"]: r for r in all_camps if r["status"] == 1}

    added = 0
    commits = 0
    for cid, locs in sorted(dump_locs.items()):
        if cid not in active_in_new:
            continue
        primary = active_in_new[cid]

        for loc in locs:
            key = (loc["city"].lower(), (loc["province"] or "").lower())
            prov_matches = city_prov_index.get(key, [])
            city_matches = city_only_index.get(loc["city"].lower(), [])
            seen_ids = set()
            all_matches = []
            for m in prov_matches + city_matches:
                if m["id"] not in seen_ids:
                    seen_ids.add(m["id"])
                    all_matches.append(m)
            related = [m for m in all_matches
                       if _name_related(primary["camp_name"], m["camp_name"])]
            if related:
                continue

            camp_name = f"{primary['camp_name']} - {loc['city']}"
            slug_base = _slugify(camp_name)

            if dry_run:
                print(f"  [DRY] CREATE {camp_name!r} ({loc['city']}, {loc['province'] or '?'})")
                added += 1
                continue

            slug = _ensure_unique_slug(cursor, slug_base)

            cursor.execute("SELECT * FROM camps WHERE id=%s", (cid,))
            master = cursor.fetchone() or primary

            cursor.execute(
                """INSERT INTO camps
                   (camp_name, slug, tier, status, lat, lon,
                    city, province, country, website, description)
                   VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 1, %s, %s)
                   ON DUPLICATE KEY UPDATE id=id""",
                (camp_name, slug, master.get("tier", "bronze"),
                 loc["lat"], loc["lon"],
                 loc["city"], loc["province"],
                 master.get("website"), master.get("description"))
            )
            new_camp_id = cursor.lastrowid
            print(f"  CREATE id={new_camp_id}: {camp_name!r}")

            # Copy programs from primary
            cursor.execute(
                "SELECT * FROM programs WHERE camp_id=%s AND status=1", (cid,)
            )
            for prog in cursor.fetchall():
                cursor.execute(
                    """INSERT INTO programs
                       (camp_id, name, type, age_from, age_to, cost_from, cost_to,
                        mini_description, description, ourkids_session_id, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1)""",
                    (new_camp_id, prog["name"], prog["type"],
                     prog.get("age_from"), prog.get("age_to"),
                     prog.get("cost_from"), prog.get("cost_to"),
                     prog.get("mini_description", ""), prog.get("description", ""),
                     prog.get("ourkids_session_id"))
                )
                new_prog_id = cursor.lastrowid
                cursor.execute(
                    "SELECT tag_id, is_primary, tag_role FROM program_tags WHERE program_id=%s",
                    (prog["id"],)
                )
                for tag_row in cursor.fetchall():
                    cursor.execute(
                        "INSERT IGNORE INTO program_tags "
                        "(program_id, tag_id, is_primary, tag_role) "
                        "VALUES (%s,%s,%s,%s)",
                        (new_prog_id, tag_row["tag_id"],
                         tag_row["is_primary"], tag_row["tag_role"])
                    )

            added += 1
            commits += 1
            # Refresh indexes
            city_prov_index[key].append({
                "id": new_camp_id, "camp_name": camp_name,
                "city": loc["city"], "province": loc["province"], "status": 1})
            city_only_index[loc["city"].lower()].append({
                "id": new_camp_id, "camp_name": camp_name,
                "city": loc["city"], "province": loc["province"], "status": 1})

            if commits >= 20:
                conn.commit()
                commits = 0

    if not dry_run and commits > 0:
        conn.commit()

    stats["added"] = added
    if not added:
        print("  No missing locations.")
    print()
    return stats


def backfill_branch_tags(cursor, conn, dry_run):
    """Backfill tags for location-branch programs that have zero tags.

    Location branches are camps created by materialize_locations() with
    auto-increment IDs (not in ok_camps).  Their programs are copies of the
    parent camp's programs, but if the parent had no tags at copy time, the
    branches ended up tagless — invisible to search.

    This step finds each tagless branch program, matches it to the parent
    camp's program by name, and copies the parent's program_tags.
    """
    stats = {"branches_fixed": 0, "tags_copied": 0}

    print("=== Branch tag backfill ===")

    # Find location-branch camps with tagless programs.
    # Branch camps have names like "Camp X - City" and IDs not in ok_camps.
    cursor.execute("""
        SELECT c.id as branch_id, c.camp_name
        FROM camps c
        WHERE c.status = 1
        AND c.id NOT IN (SELECT cid FROM ok_camps)
        AND EXISTS (
            SELECT 1 FROM programs p
            WHERE p.camp_id = c.id AND p.status = 1
            AND NOT EXISTS (SELECT 1 FROM program_tags pt WHERE pt.program_id = p.id)
        )
    """)
    branches = cursor.fetchall()

    if not branches:
        print("  No tagless branches found.")
        print()
        return stats

    print(f"  Found {len(branches)} branches with tagless programs")

    # Build parent lookup: branch camp_name = "Parent Name - City"
    # → find parent by matching the name prefix
    cursor.execute("SELECT id, camp_name FROM camps WHERE status = 1")
    all_camps = {r["id"]: r["camp_name"] for r in cursor.fetchall()}

    # Also build a name → id index for parent matching
    name_to_ids = {}
    for cid, cname in all_camps.items():
        name_to_ids.setdefault(cname.strip().lower(), []).append(cid)

    for branch in branches:
        branch_id = branch["branch_id"]
        branch_name = branch["camp_name"]

        # Extract parent name: "Camp X - City" → "Camp X"
        # Try splitting on " - " from the right (city is the last segment)
        parts = branch_name.rsplit(" - ", 1)
        if len(parts) < 2:
            continue
        parent_name = parts[0].strip()

        # Find parent camp
        parent_ids = name_to_ids.get(parent_name.lower(), [])
        if not parent_ids:
            continue
        parent_id = parent_ids[0]  # primary parent

        # Get tagless programs in this branch
        cursor.execute("""
            SELECT p.id, p.name FROM programs p
            WHERE p.camp_id = %s AND p.status = 1
            AND NOT EXISTS (SELECT 1 FROM program_tags pt WHERE pt.program_id = p.id)
        """, (branch_id,))
        tagless_progs = cursor.fetchall()

        if not tagless_progs:
            continue

        # Get parent's programs with tags, indexed by name
        cursor.execute("""
            SELECT p.id, p.name FROM programs p
            WHERE p.camp_id = %s AND p.status = 1
            AND EXISTS (SELECT 1 FROM program_tags pt WHERE pt.program_id = p.id)
        """, (parent_id,))
        parent_progs = {r["name"].strip().lower(): r["id"] for r in cursor.fetchall()}

        if not parent_progs:
            continue

        copied_for_branch = 0
        for prog in tagless_progs:
            # Match by exact name
            parent_prog_id = parent_progs.get(prog["name"].strip().lower())

            # Fallback: match by name prefix (branch prog might have city suffix)
            if not parent_prog_id:
                prog_name_lower = prog["name"].strip().lower()
                for pname, pid in parent_progs.items():
                    if pname.startswith(prog_name_lower) or prog_name_lower.startswith(pname):
                        parent_prog_id = pid
                        break

            # Last resort: if branch has exactly 1 program and parent has programs,
            # copy tags from the parent's first program
            if not parent_prog_id and len(tagless_progs) == 1 and parent_progs:
                parent_prog_id = next(iter(parent_progs.values()))

            if not parent_prog_id:
                continue

            # Copy tags from parent program to branch program
            cursor.execute(
                "SELECT tag_id, is_primary, tag_role, source "
                "FROM program_tags WHERE program_id = %s",
                (parent_prog_id,)
            )
            tags = cursor.fetchall()
            if not tags:
                continue

            if not dry_run:
                for t in tags:
                    cursor.execute(
                        "INSERT IGNORE INTO program_tags "
                        "(program_id, tag_id, is_primary, tag_role, source) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (prog["id"], t["tag_id"], t["is_primary"],
                         t["tag_role"], t.get("source", "ourkids"))
                    )
                    stats["tags_copied"] += cursor.rowcount

            copied_for_branch += len(tags)

        if copied_for_branch > 0:
            stats["branches_fixed"] += 1
            print(f"  {'[DRY] ' if dry_run else ''}"
                  f"BACKFILL id={branch_id}: {branch_name!r} "
                  f"(+{copied_for_branch} tags from parent {parent_id})")

    if not dry_run and stats["tags_copied"]:
        conn.commit()

    print(f"\n  Branches fixed: {stats['branches_fixed']}, "
          f"Tags copied: {stats['tags_copied']}")
    print()
    return stats


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dry_run, skip_ids, deactivate, force=False):
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Verify staging tables exist
    missing = _check_staging_tables(cursor)
    if missing:
        print(f"ERROR: Missing staging tables: {', '.join(missing)}")
        print("Run load_raw_tables.py first.")
        cursor.close()
        conn.close()
        sys.exit(1)

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Materializing CSC tables from ok_* staging tables\n")

    print("Staging table schemas:")
    _discover_schema(cursor)
    print()

    # Step 1: Camps
    dump_cids = materialize_camps(cursor, dry_run, skip_ids, deactivate)

    # Step 2: Programs + tags
    prog_stats = materialize_programs(cursor, conn, dry_run, dump_cids, force=force)

    # Step 3: Dates
    date_stats = materialize_dates(cursor, conn, dry_run)

    # Step 4: Extra locations
    loc_stats = materialize_locations(cursor, conn, dry_run, dump_cids)

    # Step 5: Backfill tags for existing location branches
    branch_stats = backfill_branch_tags(cursor, conn, dry_run)

    if not dry_run:
        # Safety gate: verify tag count hasn't dropped catastrophically.
        # This catches bugs in cleanup scripts, bad dump data, or code regressions
        # that would silently delete legitimate program_tags rows.
        cursor.execute("SELECT COUNT(*) as cnt FROM program_tags")
        tag_count = cursor.fetchone()["cnt"]
        TAG_FLOOR = 20_000  # absolute minimum — current baseline is ~35K
        if tag_count < TAG_FLOOR:
            print(f"\n*** SAFETY GATE FAILED ***")
            print(f"program_tags count ({tag_count:,}) is below floor ({TAG_FLOOR:,})")
            print("Rolling back to prevent tag loss. Investigate before re-running.")
            conn.rollback()
            cursor.close()
            conn.close()
            sys.exit(1)

        conn.commit()

    cursor.close()
    conn.close()

    print("=" * 60)
    print(f"{prefix}Materialization complete")
    print(f"  Programs inserted:  {prog_stats['programs_inserted']}")
    print(f"  Tags inserted:      {prog_stats['tags_inserted']}")
    print(f"  Traits inserted:    {prog_stats['traits_inserted']}")
    print(f"  Dates inserted:     {date_stats['inserted']}")
    print(f"  Locations added:    {loc_stats['added']}")
    print(f"  Branch tags copied: {branch_stats['tags_copied']}")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Materialize CSC tables from ok_* staging tables"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to DB")
    parser.add_argument("--deactivate", action="store_true",
                        help="Deactivate camps whose status=0 in staging data")
    parser.add_argument("--skip-ids",
                        help="Comma-separated camp IDs to skip during deactivation "
                             "(e.g. 422,529,579,1647)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-sync all camps (skip change-detection, "
                             "rebuild tags from sitems data)")
    args = parser.parse_args()
    skip_ids = set(int(x) for x in args.skip_ids.split(",")) if args.skip_ids else set()
    run(args.dry_run, skip_ids, args.deactivate, force=args.force)
