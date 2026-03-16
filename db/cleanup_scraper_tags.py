#!/usr/bin/env python3
"""
cleanup_scraper_tags.py — Remove spurious program_tags rows from multi-program camps.

The category-page scraper (tag_from_campsca_pages.py) used to tag ALL programs at a
camp when it found that camp on a camps.ca category page.  For multi-program camps
(e.g. 33 sessions), this meant every session got tagged with every category — polluting
search results with irrelevant sessions.

This script removes non-primary (is_primary=0) program_tags rows for camps that have
more than MAX_PROGRAMS active programs.  Primary tags (is_primary=1, from OurKids data)
are never touched.

Usage:
    python3 db/cleanup_scraper_tags.py --dry-run     # preview deletions
    python3 db/cleanup_scraper_tags.py               # execute deletions
"""
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.connection import get_connection

MAX_PROGRAMS = 5


def main():
    parser = argparse.ArgumentParser(description="Remove scraper-inserted tags from multi-program camps")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no changes")
    parser.add_argument("--threshold", type=int, default=MAX_PROGRAMS,
                        help=f"Program count threshold (default {MAX_PROGRAMS})")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Find camps with more than threshold active programs
    cur.execute("""
        SELECT camp_id, COUNT(*) as prog_count
        FROM programs
        WHERE status = 1
        GROUP BY camp_id
        HAVING COUNT(*) > %s
        ORDER BY prog_count DESC
    """, (args.threshold,))
    multi_camps = cur.fetchall()
    print(f"Found {len(multi_camps)} camps with >{args.threshold} active programs")

    if not multi_camps:
        print("Nothing to clean up.")
        cur.close()
        conn.close()
        return

    # Count non-primary tags for these camps
    camp_ids = [r["camp_id"] for r in multi_camps]
    ph = ",".join(["%s"] * len(camp_ids))
    cur.execute(f"""
        SELECT COUNT(*) as cnt
        FROM program_tags pt
        JOIN programs p ON pt.program_id = p.id
        WHERE p.camp_id IN ({ph})
          AND pt.is_primary = 0
          AND p.status = 1
    """, camp_ids)
    total = cur.fetchone()["cnt"]
    print(f"Non-primary program_tags rows at these camps: {total}")

    # Show sample of what will be deleted
    cur.execute(f"""
        SELECT c.id as camp_id, c.name, COUNT(DISTINCT p.id) as progs,
               COUNT(pt.tag_id) as nonprimary_tags
        FROM program_tags pt
        JOIN programs p ON pt.program_id = p.id
        JOIN camps c ON p.camp_id = c.id
        WHERE p.camp_id IN ({ph})
          AND pt.is_primary = 0
          AND p.status = 1
        GROUP BY c.id, c.name
        ORDER BY nonprimary_tags DESC
        LIMIT 20
    """, camp_ids)
    print("\nTop 20 affected camps:")
    print(f"  {'Camp ID':>7}  {'Programs':>8}  {'Tags to remove':>14}  Name")
    for r in cur.fetchall():
        print(f"  {r['camp_id']:>7}  {r['progs']:>8}  {r['nonprimary_tags']:>14}  {r['name'][:50]}")

    if args.dry_run:
        print(f"\n[DRY RUN] Would delete {total} non-primary program_tags rows")
    else:
        # Delete non-primary tags for multi-program camps
        cur.execute(f"""
            DELETE pt FROM program_tags pt
            JOIN programs p ON pt.program_id = p.id
            WHERE p.camp_id IN ({ph})
              AND pt.is_primary = 0
              AND p.status = 1
        """, camp_ids)
        deleted = cur.rowcount
        conn.commit()
        print(f"\nDeleted {deleted} non-primary program_tags rows")
        print("Run `python3 db/export_camp_tag_overrides.py` to regenerate JSON")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
