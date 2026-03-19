# CSC Data Sync

## Overview

Two automated sync pipelines keep CSC data current:

1. **OurKids programme sync** — daily 02:00 UTC Mon–Fri via `sync.yml`
2. **camps.ca category tag refresh** — weekly Sunday 03:00 UTC via `refresh-camp-tags.yml`

Both are GitHub Actions workflows with manual trigger support.

---

## OurKids Programme Sync

**Pipeline: Raw Table Import + SQL Materialization** (replaced regex ETL on 2026-03-17)

`.github/workflows/sync.yml` runs **daily 02:00 UTC Mon–Fri**:
1. `db/download_from_drive.py` — fetches latest dump from Google Drive
2. `db/load_raw_tables.py --dump dump.sql` — imports 8 OurKids tables as `ok_*` staging
3. `db/materialize_from_raw.py --deactivate --skip-ids 422,529,579,1647` — SQL JOINs populate CSC tables
4. `db/import_camp_tag_overrides.py` — re-applies camps.ca scraped tags (single-program camps only)
5. `db/export_camp_tag_overrides.py` — regenerates JSON, commits if changed

Manual trigger: GitHub > Actions > "Sync OurKids > Aiven" > Run workflow.

### Staging Tables

Ephemeral, recreated each sync:
`ok_camps`, `ok_sessions`, `ok_sitems`, `ok_session_date`, `ok_addresses`,
`ok_generalInfo`, `ok_detailInfo`, `ok_extra_locations`

**Important:** `ok_*` tables must never be queried by the app at runtime. They are ephemeral staging data only.

### Improvements Over Legacy Regex ETL

- Gender data now imported (OurKids 1=Coed > CSC 0, 2=Boys > 1, 3=Girls > 2)
- Mini descriptions captured from `ok_sessions.mini_description`
- Sitems tags via SQL JOIN instead of regex field extraction
- All OurKids columns available for inspection via `SELECT * FROM ok_sessions`
- Old regex accidentally filtered by `gender` field (position 7), dropping all non-coed sessions

### Google Drive Setup

**Why Google Drive (not direct DB):** OurKids DBA denied direct MySQL access from GitHub
Actions — firewall is locked to known IPs. OurKids uploads a mysqldump to a shared Google
Drive folder; we pull it via a service account.

- Service account: `youtube-php-api@youtube-bonbon-431918-h7.iam.gserviceaccount.com`
- Drive folder ID: `16xEqbVXQgffZ_7osLEGNBT4iTMsuWHJT`
- GitHub secrets: `GDRIVE_SERVICE_ACCOUNT_JSON` (full JSON key), `GDRIVE_FOLDER_ID`
- Download script: `db/download_from_drive.py` — fetches most-recently-modified file in folder

### OurKids Session Schema

Actual column names in `ok_sessions`:
- `class_name` (not `name`)
- `start`/`end` (not `date_from`/`date_to`)
- `gender` at position 7 (was misidentified as `status` in old regex)
- No real status column — all sessions in the dump are active
- `running` field is unrelated (only 186/12864 have `running=1`)

### Gender Mapping

OurKids uses `0=unset, 1=Coed, 2=Boys, 3=Girls`; CSC uses `0=Coed, 1=Boys, 2=Girls`.
The `_GENDER_MAP` in `materialize_from_raw.py` handles conversion.

### Staging Table Compatibility

- `ok_*` tables require `ENGINE=InnoDB` (Aiven doesn't support MyISAM)
- `SET SESSION sql_mode = ''` required for zero dates in legacy data
- Both handled automatically by `load_raw_tables.py`

### Manual Commands

```bash
# Manual run from a local dump file
python3 db/load_raw_tables.py --dump /path/to/dump.sql [--dry-run]
python3 db/materialize_from_raw.py --deactivate --skip-ids 422,529,579,1647 [--dry-run]
PYTHONPATH=. python3 db/import_camp_tag_overrides.py
PYTHONPATH=. python3 db/export_camp_tag_overrides.py

# Emergency fallback (legacy regex ETL — kept but no longer primary)
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions \
  --deactivate --skip-ids 422,529,579,1647
```

`--skip-ids` protects manually promoted sub-locations:
`422` Canlan Etobicoke, `529` Canlan Scarborough, `579` Canlan Oakville, `1647` Idea Labs Pickering

---

## camps.ca Category Tag Refresh

`db/tag_from_campsca_pages.py` runs **weekly (Sunday 03:00 UTC)** via
`.github/workflows/refresh-camp-tags.yml`. It scrapes all camps.ca category pages,
updates `program_tags` in Aiven (single-program camps only), exports
`camp_tag_overrides.json`, and commits the JSON to `main` if it changed.

Manual trigger: GitHub > Actions > "Refresh camps.ca Category Tags" > Run workflow.

```bash
# Local run (scrapes ~148 pages, ~5-10 min)
python3 db/tag_from_campsca_pages.py [--dry-run]

# After scraping, regenerate the JSON (also runs automatically in CI)
python3 db/export_camp_tag_overrides.py
```

### How Page-to-Slug Mapping Works

1. `CANONICAL_PAGES` in `tag_from_campsca_pages.py` — 57 canonical main pages (replaces
   Excel when running in CI; Excel takes priority locally if found at `CAMP_PAGES_XLSX`)
2. `PAGE_SLUG_OVERRIDES` — 110 sitemap-derived pages with specific slugs (ballet > ballet,
   not dance-multi; photography > photography, not arts-multi etc.)
3. `CAMP_PAGE_OVERRIDES` — URL normalisation (dash > underscore broken URLs)

### Parallel Lookup in Search

`core/cssl.py` loads `_SLUG_TO_CAMP_IDS` from `camp_tag_overrides.json` at module init.
Adds `OR p.camp_id IN (...)` to every tag query — guaranteeing camps.ca-listed camps
appear even if `program_tags` has a gap. For multi-program override camps, the
representative program uses `COALESCE`: prefers a program with a matching `program_tag`,
falls back to lowest ID if none match.

### Scraper Tags: Camp-Level, Not Program-Level

The scraper and import scripts only write `program_tags` for single-program camps.
Multi-program camps rely solely on the `camp_tag_overrides.json` parallel lookup in CSSL.
This prevents false program-level signals (e.g. a basketball session getting a hockey tag
because the camp appears on the hockey page).

### Tag Provenance (`program_tags.source`)

The `source` column tracks where each tag originated:
- **ourkids** — imported from OurKids sitems data (specialty/category/activities fields)
- **scraper** — inserted by `tag_from_campsca_pages.py` or `import_camp_tag_overrides.py`
- **manual** — hand-corrected entries

Any bulk tag cleanup **MUST** filter by `source = 'scraper'`. Never delete `ourkids` rows.
`materialize_from_raw.py` has a safety gate: if `program_tags` count drops below 20K,
the transaction is rolled back and the sync aborts.

### CAMP_PAGE_OVERRIDES: No Broad Redirects

`CAMP_PAGE_OVERRIDES` maps broken URLs to working equivalents. **Never redirect a specific
category page to a broad parent page** (e.g. `/fashion-camps.php` → `/arts_camps.php`).
This causes all camps on the parent page to receive the child category's tags. If no
specific page exists, set the value to `None` to skip the URL entirely.

### Adding a New Category Page

Add to `PAGE_SLUG_OVERRIDES` in `tag_from_campsca_pages.py` (path > [slugs]), run the
scraper + export, commit JSON. If it's a new main page, also add to `CANONICAL_PAGES`.
