#!/usr/bin/env python3
"""
db/export_camp_tag_overrides.py

Exports the current program_tags that were scraped from camps.ca activity pages
into db/camp_tag_overrides.json — a camp_id → [tag_slug, ...] mapping.

This file is read by sync_from_source.py after keyword inference so that
camps.ca-derived tags survive every sync cycle.

Run after tag_from_campsca_pages.py:
    python3 db/export_camp_tag_overrides.py
"""
import json
import os

from db.connection import get_connection

OUTPUT = os.path.join(os.path.dirname(__file__), "camp_tag_overrides.json")

conn = get_connection()
cur = conn.cursor(dictionary=True)

cur.execute("""
    SELECT p.camp_id, GROUP_CONCAT(DISTINCT ats.slug ORDER BY ats.slug) as slugs
    FROM program_tags pt
    JOIN programs p ON p.id = pt.program_id
    JOIN activity_tags ats ON ats.id = pt.tag_id AND ats.is_active = 1
    WHERE p.status = 1
    GROUP BY p.camp_id
""")

mapping = {}
for row in cur.fetchall():
    mapping[str(row["camp_id"])] = row["slugs"].split(",")

cur.close()
conn.close()

with open(OUTPUT, "w") as f:
    json.dump(mapping, f, indent=2)

print(f"Exported {len(mapping)} camps → {OUTPUT}")
