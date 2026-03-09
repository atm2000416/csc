"""
db/fix_program_types.py

Fix programs.type which was incorrectly stored during migration.

The old DB had a sessions.type field per session:
  1 = Day Camp
  2 = Overnight / Residential
  3 = Day + Overnight (both)
  4 = Virtual / Online
  5 = Other (treated as Day)

The migration collapsed all sessions to one program per camp and
used the camp-level generalInfo.main_category instead of the actual
session type, resulting in nearly all programs being typed 'Day Camp'.

This script fixes that using three sources in priority order:
  1. sessions table — most accurate; per-session data
  2. generalInfo.main_category — camp-level fallback (1=Day, 2=Residential)
  3. Parent camp inheritance — for location branches (e.g. "Camp X - Ottawa"
     inherits the corrected type of "Camp X")

Also normalises the 'Day Camp' string → '1' for consistency.

Usage:
  # Dry run — see what would change
  source .venv/bin/activate && python3 db/fix_program_types.py --dry-run

  # Apply
  source .venv/bin/activate && python3 db/fix_program_types.py
"""
import re
import sys
import os
import argparse
from collections import defaultdict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

DEFAULT_DUMP = "/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql"

# DB type codes (what we store in programs.type)
DAY       = "1"
OVERNIGHT = "2"
BOTH      = "3"
VIRTUAL   = "4"


def parse_session_types(content) -> dict[int, str]:
    """
    Return {cid: type_code} derived from the sessions table.
    If a camp has mixed day+overnight sessions → '3' (Both).
    """
    match = re.search(r"INSERT INTO `sessions` VALUES (.*?);\n", content, re.DOTALL)
    if not match:
        return {}

    rows = re.findall(r"\((\d+),(\d+),'(?:[^'\\]|\\.)*?','(\d+)',", match.group(1))
    session_types: dict[int, set] = defaultdict(set)
    for _, cid, stype in rows:
        session_types[int(cid)].add(int(stype))

    result = {}
    for cid, types in session_types.items():
        core = types & {1, 2, 3}
        if not core:
            continue
        has_day   = bool(core & {1, 3})
        has_night = bool(core & {2, 3})
        if has_day and has_night:
            result[cid] = BOTH
        elif has_night:
            result[cid] = OVERNIGHT
        else:
            result[cid] = DAY
    return result


def parse_gi_category(content) -> dict[int, str]:
    """
    Return {cid: type_code} from generalInfo.main_category.
    main_category: 1=Day, 2=Residential/Overnight.
    """
    match = re.search(r"INSERT INTO `generalInfo` VALUES (.*?);\n", content, re.DOTALL)
    if not match:
        return {}

    rows = re.findall(r"\((\d+),'[^']*',(?:NULL|'[^']*'),(\d+),", match.group(1))
    result = {}
    for cid, cat in rows:
        cat = int(cat)
        if cat == 2:
            result[int(cid)] = OVERNIGHT
        elif cat == 1:
            result[int(cid)] = DAY
    return result


def derive_type(camp_id: int, session_map: dict, gi_map: dict) -> str | None:
    """Priority: sessions > generalInfo. Returns None if no data."""
    return session_map.get(camp_id) or gi_map.get(camp_id)


def strip_city_suffix(camp_name: str) -> str:
    """
    'Camp X - Ottawa'  →  'Camp X'
    Returns the name unchanged if no ' - ' separator found.
    """
    idx = camp_name.rfind(" - ")
    return camp_name[:idx].strip() if idx > 0 else camp_name


def run(dump_path: str, dry_run: bool):
    print(f"Reading dump: {dump_path}")
    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    session_map = parse_session_types(content)
    gi_map      = parse_gi_category(content)
    print(f"  {len(session_map)} cids from sessions, {len(gi_map)} cids from generalInfo")

    conn = get_connection()
    c = conn.cursor(dictionary=True)

    # Load all camps (id → camp_name, type will be derived separately)
    c.execute("SELECT id, camp_name FROM camps WHERE status=1")
    all_camps = {r["id"]: r["camp_name"] for r in c.fetchall()}

    # Build name→camp_id index for parent lookup
    name_to_ids: dict[str, list[int]] = defaultdict(list)
    for cid, name in all_camps.items():
        name_to_ids[name.strip().lower()].append(cid)

    # Step 1: compute the corrected type for every active camp
    # Priority: session → gi → parent inheritance
    camp_type: dict[int, str | None] = {}
    for camp_id, camp_name in all_camps.items():
        t = derive_type(camp_id, session_map, gi_map)
        if t is None:
            # Try parent inheritance via "Name - City" pattern
            parent_name = strip_city_suffix(camp_name)
            if parent_name != camp_name:
                for pid in name_to_ids.get(parent_name.lower(), []):
                    t = derive_type(pid, session_map, gi_map)
                    if t:
                        break
        camp_type[camp_id] = t

    # Step 2: load all active programs and compute needed changes
    c.execute("SELECT id, camp_id, name, type FROM programs WHERE status=1")
    programs = c.fetchall()

    # Current type → normalised type code
    _NORMALISE = {
        "Day Camp": DAY,
        "Day":      DAY,
        "day camp": DAY,
    }

    updates = []
    for prog in programs:
        current = prog["type"] or ""
        # Get authoritative type from dump data
        new_type = camp_type.get(prog["camp_id"])

        if new_type:
            if new_type != current:
                updates.append((prog["id"], prog["camp_id"], prog["name"], current, new_type))
        elif current in _NORMALISE:
            # No dump data — just normalise string to code
            normalised = _NORMALISE[current]
            if normalised != current:
                updates.append((prog["id"], prog["camp_id"], prog["name"], current, normalised))

    print(f"\n{'DRY RUN — ' if dry_run else ''}Programs to update: {len(updates)} / {len(programs)}")

    # Count breakdown
    from collections import Counter
    breakdown = Counter(new for _, _, _, _, new in updates)
    print(f"  Breakdown of new types: {dict(breakdown)}")

    # Sample
    print("\nSample changes:")
    for pid, cid, name, old, new in updates[:15]:
        print(f"  prog={pid} camp={cid}: {old!r}→{new!r}  {name!r}")

    if dry_run or not updates:
        c.close()
        conn.close()
        return

    # Apply in batches
    batch = 0
    for pid, cid, name, old, new in updates:
        c.execute("UPDATE programs SET type=%s WHERE id=%s", (new, pid))
        batch += 1
        if batch % 100 == 0:
            conn.commit()
            print(f"  ... committed {batch}")

    conn.commit()
    c.close()
    conn.close()
    print(f"\nDone — {len(updates)} programs updated.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dump", default=DEFAULT_DUMP)
    args = parser.parse_args()
    run(args.dump, args.dry_run)
