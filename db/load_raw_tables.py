#!/usr/bin/env python3
"""
db/load_raw_tables.py
Import raw OurKids tables from a mysqldump into Aiven as ok_* staging tables.

Replays CREATE TABLE and INSERT INTO statements from the dump, renaming each
table to ok_<name>.  No field-level parsing — the SQL is executed as-is with
only the table name substituted.

Tables imported:
  camps → ok_camps, sessions → ok_sessions, sitems → ok_sitems,
  session_date → ok_session_date, addresses → ok_addresses,
  generalInfo → ok_generalInfo, detailInfo → ok_detailInfo,
  extra_locations → ok_extra_locations

Usage:
  python db/load_raw_tables.py --dump dump.sql                # load all 8 tables
  python db/load_raw_tables.py --dump dump.sql --dry-run      # parse only
  python db/load_raw_tables.py --dump dump.sql --tables camps,sessions
"""
import re
import sys
import os
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from db.connection import get_connection

TABLES = [
    "camps",
    "sessions",
    "sitems",
    "session_date",
    "addresses",
    "generalInfo",
    "detailInfo",
    "extra_locations",
]


def _find_create_block(content: str, table: str) -> str | None:
    """Extract the full CREATE TABLE statement for `table` from the dump."""
    pattern = re.compile(
        rf"CREATE TABLE `{re.escape(table)}` \(.*?\) ENGINE=\w+[^;]*;",
        re.DOTALL,
    )
    m = pattern.search(content)
    if not m:
        # Try without ENGINE clause (some dumps end differently)
        pattern2 = re.compile(
            rf"CREATE TABLE `{re.escape(table)}` \(.*?\);",
            re.DOTALL,
        )
        m = pattern2.search(content)
    return m.group(0) if m else None


def _find_insert_blocks(content: str, table: str) -> list[str]:
    """Extract all INSERT INTO statements for `table` from the dump."""
    pattern = re.compile(
        rf"INSERT INTO `{re.escape(table)}` VALUES .*?;\n",
        re.DOTALL,
    )
    return [m.group(0) for m in pattern.finditer(content)]


def _rename_table(sql: str, old_name: str, new_name: str) -> str:
    """Replace table name references in SQL."""
    return sql.replace(f"`{old_name}`", f"`{new_name}`")


def _sanitize_create(sql: str) -> str:
    """Make CREATE TABLE compatible with Aiven MySQL (InnoDB only)."""
    # Replace MyISAM with InnoDB
    sql = re.sub(r'ENGINE=MyISAM', 'ENGINE=InnoDB', sql, flags=re.IGNORECASE)
    # Remove FULLTEXT indexes (not supported in older InnoDB or may cause issues)
    sql = re.sub(r',?\s*FULLTEXT\s+KEY\s+`[^`]*`\s*\([^)]*\)', '', sql)
    return sql


def load_table(cursor, content: str, table: str, dry_run: bool) -> dict:
    """Load a single table from dump content into ok_<table>.

    Returns stats dict with keys: create, inserts, rows.
    """
    ok_name = f"ok_{table}"
    stats = {"create": False, "inserts": 0, "rows": 0}

    # 1. Find CREATE TABLE
    create_sql = _find_create_block(content, table)
    if not create_sql:
        print(f"  WARNING: CREATE TABLE `{table}` not found in dump — skipping")
        return stats

    create_sql = _rename_table(create_sql, table, ok_name)
    create_sql = _sanitize_create(create_sql)
    stats["create"] = True

    # 2. Find INSERT blocks
    insert_blocks = _find_insert_blocks(content, table)
    stats["inserts"] = len(insert_blocks)

    if dry_run:
        # Count approximate rows from INSERT blocks
        for block in insert_blocks:
            # Each row is a (...) group in VALUES
            stats["rows"] += block.count("),(") + (1 if "VALUES" in block else 0)
        return stats

    # 3. Execute: DROP → CREATE → INSERTs
    cursor.execute(f"DROP TABLE IF EXISTS `{ok_name}`")
    cursor.execute(create_sql)

    for block in insert_blocks:
        sql = _rename_table(block, table, ok_name).rstrip("\n")
        try:
            cursor.execute(sql)
            stats["rows"] += cursor.rowcount
        except Exception as e:
            print(f"  ERROR inserting into {ok_name}: {e}")
            # Try to continue with remaining blocks
            continue

    return stats


def run(dump_path: str, dry_run: bool, tables: list[str] | None):
    print(f"Reading dump: {dump_path}")
    with open(dump_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    print(f"  Dump size: {len(content):,} bytes\n")

    tables_to_load = tables or TABLES

    if not dry_run:
        conn = get_connection()
        cursor = conn.cursor()
        # Allow zero dates from legacy OurKids dump (Aiven strict mode rejects them)
        cursor.execute("SET SESSION sql_mode = ''")
    else:
        conn = cursor = None

    total_tables = 0
    total_rows = 0

    for table in tables_to_load:
        print(f"{'[DRY] ' if dry_run else ''}Loading {table} → ok_{table}...")
        stats = load_table(cursor, content, table, dry_run)

        if stats["create"]:
            total_tables += 1
            total_rows += stats["rows"]
            print(f"  ✓ {stats['inserts']} INSERT block(s), ~{stats['rows']} rows")
        print()

    if not dry_run and conn:
        conn.commit()
        cursor.close()
        conn.close()

    prefix = "[DRY RUN] " if dry_run else ""
    print("=" * 60)
    print(f"{prefix}Loaded {total_tables}/{len(tables_to_load)} tables, "
          f"~{total_rows:,} total rows")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import raw OurKids tables from dump as ok_* staging tables"
    )
    parser.add_argument("--dump", required=True, help="Path to SQL dump file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Parse only, don't execute SQL")
    parser.add_argument("--tables",
                        help="Comma-separated subset of tables to load "
                             f"(default: all {len(TABLES)})")
    args = parser.parse_args()
    table_list = args.tables.split(",") if args.tables else None
    run(args.dump, args.dry_run, table_list)
