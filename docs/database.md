# CSC Database

## Connection
Aiven MySQL 8.0. SSL required — CA cert stored as `DB_SSL_CA_CERT` secret (base64).
```python
from db.connection import get_connection
conn = get_connection()
cur = conn.cursor(dictionary=True)
# ... always close both:
cur.close()
conn.close()
```

---

## Key Tables

### `camps`
| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | matches legacy `cid` |
| `camp_name` | VARCHAR(150) | |
| `slug` | VARCHAR(200) UNIQUE | URL slug |
| `tier` | ENUM gold/silver/bronze | |
| `status` | TINYINT | 1=active, 0=inactive |
| `city` / `province` | VARCHAR | |
| `lat` / `lon` | DECIMAL(10,7) | |
| `website` | VARCHAR(200) | |
| `lgbtq_welcoming` / `accessibility` | TINYINT | |
| `prettyurl` | VARCHAR(245) | legacy URL path |

### `programs`
| Column | Type | Notes |
|---|---|---|
| `id` | INT PK | |
| `camp_id` | INT FK→camps | |
| `name` | VARCHAR(300) | |
| `type` | VARCHAR(45) | "1"=Day "2"=Overnight |
| `age_from` / `age_to` | SMALLINT | |
| `cost_from` / `cost_to` | SMALLINT | CAD |
| `gender` | TINYINT | NULL=unknown, 0=Coed, 1=Boys, 2=Girls |
| `status` | TINYINT | 1=active |
| `mini_description` | VARCHAR(500) | shown in results |

### `activity_tags`
| Column | Notes |
|---|---|
| `slug` | unique identifier used everywhere |
| `is_active` | 1=available for search |
| `related_ids` | comma-separated IDs for CASL expansion |
| `aliases` | feeds fuzzy preprocessor |
| `level` | 1=Domain, 2=Category, 3=Sub-activity |

### `program_tags`
Junction: `program_id` + `tag_id` + `is_primary` + `tag_role` (ENUM: specialty/category/activity) + `source` (ENUM: ourkids/scraper/manual)

**`tag_role`** — derived from OurKids focus levels during materialization:

| OurKids focus level | Meaning | tag_role | Set by |
|:---:|---|---|---|
| 3 | Intense | `specialty` | The camp itself |
| 2 | Instructional | `category` | The camp itself |
| 1 | Recreational | `activity` | The camp itself |

The `ok_sessions.activities` field format is `[sitem_id]focus_level`. The focus level is the camp's own declaration of how seriously they offer each activity. The CSSL affinity gate uses `tag_role` to filter noise: `specialty`/`category` tags always pass; `activity` tags are gated by program tag count or category family membership.

**`source`** — distinguishes tag origin:
- **ourkids** — imported from OurKids sitems data via `materialize_from_raw.py` (default)
- **scraper** — inserted by `tag_from_campsca_pages.py` or `import_camp_tag_overrides.py`
- **manual** — manually inserted corrections

Any bulk cleanup must filter by `source = 'scraper'` to avoid deleting OurKids-sourced tags.

### `traits`
12 character traits: resilience, curiosity, courage, independence, responsibility,
interpersonal-skills, creativity, physicality, generosity, tolerance,
self-regulation, religious-faith

---

## Gender Field Notes
- `gender=NULL` — data missing; NOT the same as coed
- `gender=0` — coed (also the legacy default — most imported programs have 0, not NULL)
- `gender=1` — boys only
- `gender=2` — girls only
- CSSL filter: only applied when user explicitly requests gender-specific camp
- "my son / my daughter" alone → `gender=null` in intent (child's sex ≠ camp gender filter)

Note: The legacy DB had a separate `gender` table (camp-level gender with age brackets) that
was not migrated. Gender data is therefore sparse and unreliable for filtering.

---

## Legacy Schema Reference (confirmed from MWB + official docs)

### `camps` table — column order (0-indexed INSERT tuple)
| Index | Field | Type | Notes |
|---|---|---|---|
| 0 | `cid` | smallint UNSIGNED | PK → our `id` |
| 1 | `camp_name` | varchar(75) | |
| 4 | `eListingType` | varchar(6) DEFAULT 'bronze' | Tier string: gold/silver/bronze/double/single |
| 5 | `status` | tinyint(1) DEFAULT 0 | **1=live, 0=inactive or agate** |
| 7 | `location` | varchar(50) | City name |
| 8-9 | `Lat`/`Lon` | varchar(100) | Stored as string in legacy |
| 10 | `weight` | int DEFAULT 1 | Member buy-in: 0=unset, 1=bronze, 2=silver, 3=gold |
| 13 | `prettyURL` | varchar(245) | |
| 16 | `showAnalytics` | int DEFAULT 1 | Sales analytics toggle — NOT activation signal |
| 17 | `agate` | tinyint | 0=regular paid listing, non-zero=free/agate listing |

**Tier field**: `eListingType` is authoritative (more current than `weight`).
**Agate camps**: status=0 — free listings on ourkids.net, not camps.ca. Correctly excluded by our filter.

### `sessions` table (→ our `programs`, accessible as `ok_sessions`)
- **`class_name`** varchar — session display name (NOT `name`; column is `class_name` in the dump)
- **`start`/`end`** — date columns (NOT `date_from`/`date_to`)
- **`gender`** tinyint NOT NULL DEFAULT=0 — OurKids encoding: 0=unset, 1=Coed, 2=Girls, 3=Boys. Mapped to CSC: 0=Coed, 1=Boys, 2=Girls via `_GENDER_MAP`. **Critical discovery:** the old regex ETL misidentified position 7 as `status`, accidentally filtering out all non-coed sessions.
- **`running`** tinyint DEFAULT=0 — only 186/12864 sessions have `running=1`. NOT a status field — do not filter by this.
- `mini_description` varchar(500) — migrated as-is
- `type` varchar(45) — "1"=Day, "2"=Overnight (same as our programs.type)
- `specialty` smallint → sitems.id (99% populated), `category` tinyint → sitems.id (71%), `activities` text (`[id]priority,...`)

### `extra_locations` table
- `Lat`/`Lon` stored as `double` (unlike camps table which uses varchar)
- `main_loc` tinyint DEFAULT=0 — 1 = primary location for multi-location brands
- `office` tinyint DEFAULT=0 — 1 = administrative office only, not a camp site
- `admin` tinyint — internal admin flag

### `sitems` table (→ our `activity_tags`)
Legacy activity/tag system. Confirmed mapping:
| Legacy (`sitems`) | Our DB (`activity_tags`) |
|---|---|
| `h1=0` (top-level parent) | `level=1` (Domain) |
| `h2` (category subset) | `level=2` (Category) |
| `h3` (leaf subset) | `level=3` (Sub-activity) |
| `relatives` (comma-sep IDs) | `related_ids` (feeds CASL) |
| `isact=1` | `is_active=1` |

Example hierarchy: "Hip Hop" → h3(Dance multi) → h2(Arts multi) → h1(Arts)

---

## Data Sync

### Normal operation — Raw Table Import + SQL Materialization (daily, automated)

Runs daily 02:00 UTC Mon–Fri via GitHub Actions (`.github/workflows/sync.yml`).
Downloads a mysqldump from Google Drive, imports raw OurKids tables as `ok_*` staging
tables, then materializes CSC tables via SQL JOINs.

```bash
# Step 1: Import raw tables (replay CREATE TABLE + INSERT INTO as ok_*)
python3 db/load_raw_tables.py --dump dump.sql [--dry-run]

# Step 2: Materialize CSC tables from staging (SQL JOINs)
python3 db/materialize_from_raw.py --deactivate --skip-ids 422,529,579,1647 [--dry-run]

# Step 3: Re-apply scraped tags + export JSON
python3 db/import_camp_tag_overrides.py
python3 db/export_camp_tag_overrides.py
```

**Staging tables** (ephemeral, DROP + recreated each sync):
`ok_camps`, `ok_sessions`, `ok_sitems`, `ok_session_date`, `ok_addresses`,
`ok_generalInfo`, `ok_detailInfo`, `ok_extra_locations`

**Key design decisions:**
- `ok_*` tables use `ENGINE=InnoDB` (Aiven doesn't support MyISAM) — converted automatically
- `SET SESSION sql_mode = ''` before loading (legacy data has zero dates `0000-00-00`)
- `ok_sessions` uses `class_name` (not `name`), `start`/`end` (not `date_from`/`date_to`)
- All sessions imported — no `running` or `status` filter (old regex accidentally filtered by gender field)
- Gender mapping: OurKids `1=Coed, 2=Girls, 3=Boys` → CSC `0=Coed, 1=Boys, 2=Girls`

### Emergency fallback — legacy regex sync (`db/sync_from_dump.py`)

Used only when the raw table import approach has issues. Parses individual fields from
dump SQL via regex — less reliable but requires no staging tables.

```bash
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions --dry-run
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions \
  --deactivate --skip-ids 422,529,579,1647
```

### Protected skip-ids (manually promoted sub-locations — never deactivate)
| ID | Camp |
|---|---|
| 422 | Canlan Sports - Etobicoke |
| 529 | Canlan Sports - Scarborough |
| 579 | Canlan Sports - Oakville |
| 1647 | Idea Labs Kids Pickering & Whitby |

### Activation signal
**`status` (field 5/`status` column)** = active/inactive in both legacy and source schemas.
`showAnalytics` (index 16, defaults 1) — sales analytics toggle, not an activation signal.

### What sync does NOT touch
- `activity_tags` — curated manually in Aiven DB
- Camps with IDs not present in the dump (manually created location branches)
- `ok_*` staging tables are ephemeral — only used during sync, never queried by app at runtime
