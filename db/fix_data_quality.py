"""
db/fix_data_quality.py
Fix data quality issues identified by diagnose_multi_location.py.

What this fixes:
  1. Province encoding: QuÃ©bec → Quebec (UTF-8 mojibake)
  2. Province abbreviations: ON/On/ont → Ontario, BC → British Columbia
  3. Province typos: Onatrio, Ontarioooo, Ontario1 → Ontario
  4. City typo: Toront0 → Toronto
  5. Inactive camps that have active programs → status=1

What this does NOT touch:
  - US/international province strings (California, Florida, etc.) — valid foreign locations
  - Inactive camps with zero programs — activating them would show empty pages
  - Missing multi-location records (e.g. Canlan Winnipeg) — need data from old DB

Run:
  source .venv/bin/activate && python3 db/fix_data_quality.py
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection


def run():
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    total_fixed = 0

    # ── 1. Province encoding fix (mojibake) ──────────────────────────────────
    print("=== 1. Province encoding fixes ===")
    encoding_fixes = [
        ("QuÃ©bec",    "Quebec"),
        ("QuÃ©bec ",   "Quebec"),
    ]
    for bad, good in encoding_fixes:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM camps WHERE province = %s", (bad,)
        )
        cnt = cursor.fetchone()["cnt"]
        if cnt:
            cursor.execute(
                "UPDATE camps SET province = %s WHERE province = %s", (good, bad)
            )
            print(f"  Fixed {cnt} camps: {bad!r} → {good!r}")
            total_fixed += cnt
        else:
            print(f"  None found: {bad!r}")

    # ── 2. Province abbreviation normalisation ───────────────────────────────
    print("\n=== 2. Province abbreviation normalisation ===")
    abbrev_fixes = [
        ("ON",       "Ontario"),
        ("On",       "Ontario"),
        ("ont",      "Ontario"),
        ("Ont",      "Ontario"),
        ("BC",       "British Columbia"),
        ("B.C.",     "British Columbia"),
        ("AB",       "Alberta"),
        ("Ab",       "Alberta"),
        ("QC",       "Quebec"),
        ("Qc",       "Quebec"),
        ("MB",       "Manitoba"),
        ("SK",       "Saskatchewan"),
        ("NS",       "Nova Scotia"),
        ("NB",       "New Brunswick"),
        ("NL",       "Newfoundland"),
        ("PE",       "Prince Edward Island"),
    ]
    for bad, good in abbrev_fixes:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM camps WHERE province = %s", (bad,)
        )
        cnt = cursor.fetchone()["cnt"]
        if cnt:
            cursor.execute(
                "UPDATE camps SET province = %s WHERE province = %s", (good, bad)
            )
            print(f"  Fixed {cnt} camps: {bad!r} → {good!r}")
            total_fixed += cnt

    # ── 3. Province typos ────────────────────────────────────────────────────
    print("\n=== 3. Province typos ===")
    typo_fixes = [
        ("Onatrio",    "Ontario"),
        ("Ontarioooo", "Ontario"),
        ("Ontario1",   "Ontario"),
        ("ontario",    "Ontario"),
    ]
    for bad, good in typo_fixes:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM camps WHERE province = %s", (bad,)
        )
        cnt = cursor.fetchone()["cnt"]
        if cnt:
            cursor.execute(
                "UPDATE camps SET province = %s WHERE province = %s", (good, bad)
            )
            print(f"  Fixed {cnt} camps: {bad!r} → {good!r}")
            total_fixed += cnt

    # ── 4. City typos ────────────────────────────────────────────────────────
    print("\n=== 4. City typos ===")
    city_fixes = [
        ("Toront0",   "Toronto"),    # zero not letter O
        ("TORONTO",   "Toronto"),
        ("toronto",   "Toronto"),
        ("MIssissauga", "Mississauga"),
    ]
    for bad, good in city_fixes:
        cursor.execute(
            "SELECT COUNT(*) AS cnt FROM camps WHERE city = %s", (bad,)
        )
        cnt = cursor.fetchone()["cnt"]
        if cnt:
            cursor.execute(
                "UPDATE camps SET city = %s WHERE city = %s", (good, bad)
            )
            print(f"  Fixed {cnt} camps: city {bad!r} → {good!r}")
            total_fixed += cnt

    # ── 5. Activate inactive camps that have active programs ─────────────────
    print("\n=== 5. Activate camps with active programs ===")
    cursor.execute("""
        SELECT c.id, c.camp_name, c.city, c.province,
               COUNT(p.id) AS program_count
        FROM camps c
        JOIN programs p ON p.camp_id = c.id AND p.status = 1
        WHERE c.status = 0
        GROUP BY c.id
        HAVING program_count > 0
    """)
    to_activate = cursor.fetchall()
    for camp in to_activate:
        cursor.execute("UPDATE camps SET status = 1 WHERE id = %s", (camp["id"],))
        print(f"  ACTIVATED id={camp['id']:5d}  {camp['camp_name']!r}  "
              f"({camp['city']}, {camp['province']})  "
              f"— {camp['program_count']} program(s)")
        total_fixed += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n=== Done — {total_fixed} fixes applied ===")
    print("""
Still requires manual data entry from old DB:
  - Canlan Sports Winnipeg location (city=Winnipeg, province=Manitoba)
  - Canlan Sports BC locations x3
  - Canlan Sports Saskatchewan location
  - Any other multi-location brands missing records
Run diagnose_multi_location.py again after data import to verify.
""")


if __name__ == "__main__":
    run()
