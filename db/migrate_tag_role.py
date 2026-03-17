#!/usr/bin/env python3
"""
db/migrate_tag_role.py
Idempotent migration: add tag_role ENUM column to program_tags.

Run:
    python3 db/migrate_tag_role.py [--dry-run]

Safe to run multiple times — checks if column already exists.
Default 'activity' preserves existing behavior for all current rows.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

dry_run = "--dry-run" in sys.argv

conn = get_connection()
cursor = conn.cursor(dictionary=True)

# Check if column already exists
cursor.execute(
    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'program_tags' "
    "AND COLUMN_NAME = 'tag_role'"
)
exists = cursor.fetchone()

if exists:
    print("tag_role column already exists — nothing to do.")
else:
    sql = (
        "ALTER TABLE program_tags "
        "ADD COLUMN tag_role ENUM('specialty','category','activity') "
        "NOT NULL DEFAULT 'activity' AFTER is_primary"
    )
    if dry_run:
        print(f"[DRY RUN] Would execute:\n  {sql}")
    else:
        cursor.execute(sql)
        conn.commit()
        print("Added tag_role column to program_tags (default='activity').")

    # Add index for tag_role
    cursor.execute(
        "SELECT INDEX_NAME FROM INFORMATION_SCHEMA.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'program_tags' "
        "AND INDEX_NAME = 'idx_tag_role'"
    )
    idx_exists = cursor.fetchone()
    if not idx_exists and not dry_run:
        cursor.execute("ALTER TABLE program_tags ADD INDEX idx_tag_role (tag_role)")
        conn.commit()
        print("Added idx_tag_role index.")

# Summary
cursor.execute("SELECT tag_role, COUNT(*) as cnt FROM program_tags GROUP BY tag_role")
rows = cursor.fetchall()
print("\nCurrent tag_role distribution:")
for r in rows:
    print(f"  {r['tag_role']}: {r['cnt']:,}")

cursor.close()
conn.close()
