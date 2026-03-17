#!/usr/bin/env python3
"""
db/import_camp_tag_overrides.py

Re-applies camps.ca-scraped tags from db/camp_tag_overrides.json into
program_tags.  This ensures scraper-sourced tags survive the nightly
OurKids dump sync, which deletes and re-creates programs (and their tags).

Uses INSERT IGNORE so it's safe to run repeatedly — existing rows
(e.g. sitems-sourced specialty/category tags) are never overwritten.

Run after sync_from_dump.py:
    PYTHONPATH=. python db/import_camp_tag_overrides.py [--dry-run]
"""
import json
import os
import sys

from db.connection import get_connection

OVERRIDES = os.path.join(os.path.dirname(__file__), "camp_tag_overrides.json")


def main():
    dry_run = "--dry-run" in sys.argv

    with open(OVERRIDES) as f:
        mapping = json.load(f)  # {camp_id_str: [slug, ...]}

    conn = get_connection()
    cur = conn.cursor(dictionary=True)

    # Build slug → tag_id lookup
    cur.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
    slug_to_id = {r["slug"]: r["id"] for r in cur.fetchall()}

    # Build camp_id → [program_id] lookup for active programs
    cur.execute("SELECT id, camp_id FROM programs WHERE status = 1")
    camp_to_progs: dict[int, list[int]] = {}
    for r in cur.fetchall():
        camp_to_progs.setdefault(r["camp_id"], []).append(r["id"])

    total_ins = 0
    total_skip = 0

    for camp_id_str, slugs in mapping.items():
        camp_id = int(camp_id_str)
        prog_ids = camp_to_progs.get(camp_id, [])
        if not prog_ids:
            continue

        tag_ids = [slug_to_id[s] for s in slugs if s in slug_to_id]
        if not tag_ids:
            continue

        pairs = [(pid, tid) for pid in prog_ids for tid in tag_ids]

        if dry_run:
            total_ins += len(pairs)
            continue

        chunk_size = 500
        for i in range(0, len(pairs), chunk_size):
            chunk = pairs[i : i + chunk_size]
            placeholders = ",".join(["(%s,%s,0,'activity')"] * len(chunk))
            flat = [v for pair in chunk for v in pair]
            cur.execute(
                f"INSERT IGNORE INTO program_tags (program_id, tag_id, is_primary, tag_role) "
                f"VALUES {placeholders}",
                flat,
            )
            total_ins += cur.rowcount
            total_skip += len(chunk) - cur.rowcount

    if not dry_run:
        conn.commit()

    cur.close()
    conn.close()

    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Re-applied overrides: +{total_ins} new tags, {total_skip} already existed")


if __name__ == "__main__":
    main()
