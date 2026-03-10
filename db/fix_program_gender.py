"""
db/fix_program_gender.py

Fix programs.gender from the legacy detailInfo.gender camp-level field.

Old detailInfo.gender codes (confirmed against known camps):
  '1' = Coed / all-gender (default — skip, no update needed)
  '2' = Girls-only  → programs.gender = 2
  '3' = Boys-only   → programs.gender = 1  (verify before applying)

NOTE: sessions.gender uses the SAME codes (1=Coed, 2=Girls, 3=Boys).
We use detailInfo (camp-level) rather than sessions (session-level) because
it's a single authoritative value per camp and easier to parse cleanly.

Only updates programs where gender IS NULL (doesn't overwrite existing data).

Usage:
  source .venv/bin/activate && python3 db/fix_program_gender.py --dry-run
  source .venv/bin/activate && python3 db/fix_program_gender.py
  source .venv/bin/activate && python3 db/fix_program_gender.py --include-boys
"""
import re
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

DEFAULT_DUMP = "/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql"

# Old detailInfo.gender → new programs.gender
# '1' = Coed → skip (None)
# '2' = Girls → 2
# '3' = Boys  → 1
GENDER_MAP = {'2': 2, '3': 1}


def parse_detail_info_gender(content: str) -> dict[int, str]:
    """
    Returns {cid: gender_code_str} for all detailInfo rows.
    gender field is the 12th column in the INSERT.
    Schema: (cid, cap_from, cap_to, cap_period, cost_from, cost_to,
             cost_currency, cost_period, age_from, age_to, age_type, gender, ...)
    """
    m = re.search(
        r"INSERT INTO `detailInfo` VALUES (.*?);\n",
        content, re.DOTALL
    )
    if not m:
        return {}

    result = {}
    rows = re.findall(
        r"\((\d+),\d+,(?:\d+|NULL),\d+,\d+,(?:\d+|NULL),\d+,\d+,"
        r"'[^']*','[^']*',\d+,'([^']*)',",
        m.group(1)
    )
    for cid, gender in rows:
        result[int(cid)] = gender
    return result


def run(dump_path: str, dry_run: bool, include_boys: bool):
    print(f"Reading dump: {dump_path}")
    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    detail_genders = parse_detail_info_gender(content)
    print(f"  Parsed detailInfo.gender for {len(detail_genders)} camps")

    from collections import Counter
    dist = Counter(detail_genders.values())
    print(f"  Distribution: {dict(dist)}")
    print(f"  → '1'=Coed: {dist.get('1',0)}  '2'=Girls: {dist.get('2',0)}  '3'=Boys: {dist.get('3',0)}\n")

    conn = get_connection()
    c = conn.cursor(dictionary=True)

    # Load active programs with gender=NULL
    c.execute("""
        SELECT p.id, p.camp_id, p.name, ca.camp_name
        FROM programs p
        JOIN camps ca ON p.camp_id = ca.id
        WHERE p.status = 1 AND p.gender IS NULL
    """)
    null_progs = {r['camp_id']: r for r in c.fetchall()}
    print(f"Active programs with gender=NULL: {len(null_progs)}")

    updates = []
    for camp_id, prog in null_progs.items():
        old_code = detail_genders.get(camp_id)
        if not old_code:
            continue
        new_gender = GENDER_MAP.get(old_code)
        if new_gender is None:
            continue  # '1' = Coed, skip
        if new_gender == 1 and not include_boys:
            continue  # Skip boys unless --include-boys flag set
        label = "Girls" if new_gender == 2 else "Boys"
        updates.append((prog, new_gender, label, old_code))

    print(f"Programs to update: {len(updates)}")
    from collections import Counter as C
    print("Breakdown:", C(label for _, _, label, _ in updates))
    print()

    for prog, gender_val, label, old_code in updates:
        print(f"  {'[DRY] ' if dry_run else ''}prog={prog['id']} camp={prog['camp_id']} "
              f"detailInfo.gender='{old_code}' → gender={gender_val} ({label})"
              f"  | {prog['camp_name']}")
        if not dry_run:
            c.execute("UPDATE programs SET gender=%s WHERE id=%s",
                      (gender_val, prog["id"]))

    if not dry_run and updates:
        conn.commit()
        print(f"\nDone — {len(updates)} programs updated.")
    elif dry_run:
        print(f"\nDRY RUN — {len(updates)} programs would be updated.")
    else:
        print("\nNothing to update.")

    c.close()
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dump", default=DEFAULT_DUMP)
    parser.add_argument("--include-boys", action="store_true",
                        help="Also update Boys-only programs (gender=3 in dump). "
                             "Review dry-run output carefully before applying.")
    args = parser.parse_args()
    run(args.dump, args.dry_run, args.include_boys)
