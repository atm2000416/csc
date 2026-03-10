"""
db/migrate_program_dates.py

One-time (and re-runnable) migration to populate the program_dates table
from the legacy SQL dump's session_date table.

How the linkage works:
  session_date.seid  →  programs.id
  (The migration preserved the old sessions.id as the new programs.id
   for programs that existed in the dump at migration time.)

What gets imported:
  - Only rows where seid matches an active programs.id
  - Only rows with end_date >= today (future/current sessions only)
  - cost_from/cost_to, before_care, after_care per slot

Usage:
  source .venv/bin/activate && python3 db/migrate_program_dates.py --dry-run
  source .venv/bin/activate && python3 db/migrate_program_dates.py
"""
import re
import sys
import os
import argparse
from datetime import date

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

DEFAULT_DUMP = "/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql"


def parse_session_dates(content: str) -> list[dict]:
    """
    Parse all session_date rows from dump.
    Schema: (id, cid, seid, start, end, cost_from, cost_to, location,
             timestamp, loc, period, start_time, end_time,
             before_care, before_start, before_fee, after_care, ...)
    """
    blocks = re.findall(
        r"INSERT INTO `session_date` VALUES (.*?);\n",
        content, re.DOTALL
    )
    rows = []
    for block in blocks:
        matches = re.findall(
            r"\((\d+),(\d+),(\d+),"           # id, cid, seid
            r"'(\d{4}-\d{2}-\d{2})',"         # start
            r"'(\d{4}-\d{2}-\d{2})',"         # end
            r"(\d+),(\d+),"                    # cost_from, cost_to
            r"\d+,'[^']*',\d+,\d+,"           # location, timestamp, loc, period
            r"'[^']*','[^']*',"               # start_time, end_time
            r"(\d+),"                          # before_care
            r"'[^']*',\d+,"                   # before_start, before_fee
            r"(\d+),",                         # after_care
            block
        )
        for m in matches:
            rows.append({
                "seid":        int(m[2]),
                "start_date":  m[3],
                "end_date":    m[4],
                "cost_from":   int(m[5]) or None,
                "cost_to":     int(m[6]) or None,
                "before_care": int(m[7]),
                "after_care":  int(m[8]),
            })
    return rows


def run(dump_path: str, dry_run: bool, cutoff: str | None = None):
    today = cutoff or str(date.today())
    print(f"Reading dump: {dump_path}")
    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    all_rows = parse_session_dates(content)
    print(f"  Parsed {len(all_rows):,} session_date rows total")

    # Filter to future/current dates only
    future_rows = [r for r in all_rows if r["end_date"] >= today]
    print(f"  {len(future_rows):,} rows with end_date >= {today}")

    conn = get_connection()
    c = conn.cursor(dictionary=True)

    # Load active program IDs
    c.execute("SELECT id FROM programs WHERE status=1")
    active_ids = {r["id"] for r in c.fetchall()}
    print(f"  {len(active_ids)} active programs in new DB")

    # Match: seid → program_id
    matched = [r for r in future_rows if r["seid"] in active_ids]
    print(f"  {len(matched)} rows matched to active programs\n")

    if not matched:
        print("Nothing to import.")
        c.close(); conn.close()
        return

    # Group by program_id for reporting
    from collections import defaultdict
    by_prog = defaultdict(list)
    for r in matched:
        by_prog[r["seid"]].append(r)
    print(f"  Covers {len(by_prog)} unique programs")

    print("\nSample (first 10 programs):")
    for pid, slots in list(by_prog.items())[:10]:
        dates_str = "  ".join(f"{s['start_date']}→{s['end_date']}" for s in slots[:3])
        care = " [care]" if any(s["before_care"] or s["after_care"] for s in slots) else ""
        print(f"  prog={pid}: {len(slots)} slot(s)  {dates_str}{care}")

    prefix = "DRY RUN — " if dry_run else ""
    print(f"\n{prefix}Will import {len(matched)} program_date rows "
          f"across {len(by_prog)} programs.")

    if dry_run:
        c.close(); conn.close()
        return

    # Clear existing future program_dates (idempotent re-run)
    c.execute(
        "DELETE FROM program_dates WHERE end_date >= %s "
        "AND program_id IN (%s)" % (
            "%s",
            ",".join(str(pid) for pid in by_prog)
        ),
        (today,)
    )
    deleted = c.rowcount
    if deleted:
        print(f"Cleared {deleted} existing future rows (re-run).")

    # Insert matched rows
    inserted = 0
    for r in matched:
        c.execute(
            """
            INSERT IGNORE INTO program_dates
                (program_id, start_date, end_date, cost_from, cost_to,
                 before_care, after_care)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (r["seid"], r["start_date"], r["end_date"],
             r["cost_from"], r["cost_to"],
             r["before_care"], r["after_care"])
        )
        inserted += 1
        if inserted % 100 == 0:
            conn.commit()

    conn.commit()
    c.close(); conn.close()
    print(f"Done — {inserted} program_date rows inserted.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dump", default=DEFAULT_DUMP)
    parser.add_argument("--cutoff", default=None,
                        help="Only import rows with end_date >= this date (YYYY-MM-DD). "
                             "Defaults to today.")
    args = parser.parse_args()
    run(args.dump, args.dry_run, args.cutoff)
