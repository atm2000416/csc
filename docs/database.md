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
Junction: `program_id` + `tag_id` + `is_primary`

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

### `sessions` table (→ our `programs`)
- `gender` tinyint NOT NULL DEFAULT=0 — legacy default is 0 (coed), not NULL
- `running` tinyint DEFAULT=0 — program active/running flag (not currently filtered by sync)
- `mini_description` varchar(500) — migrated as-is
- `type` varchar(45) — "1"=Day, "2"=Overnight (same as our programs.type)

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

### Normal operation — automated sync (`db/sync_from_source.py`)

Runs every 2 hours via GitHub Actions. Queries OurKids MySQL directly as the read-only
`csc_reader` user. Only processes camps whose session set has actually changed — unchanged
camps are skipped entirely.

```bash
# Dry-run (always safe — reads source, writes nothing)
python3 db/sync_from_source.py --dry-run

# Live sync with deactivations (what GitHub Actions runs)
python3 db/sync_from_source.py --deactivate --skip-ids 422,529,579,1647
```

Requires environment variables (or Streamlit secrets):
`SOURCE_DB_HOST`, `SOURCE_DB_PORT`, `SOURCE_DB_NAME`, `SOURCE_DB_USER`, `SOURCE_DB_PASSWORD`
plus the usual `DB_*` Aiven connection variables.

Manual trigger: GitHub repo → Actions → "Sync OurKids → Aiven" → Run workflow.

### Emergency fallback — dump file sync (`db/sync_from_dump.py`)

Used when the OurKids source DB is unreachable or a schema change needs investigation.
Parses a `.sql` dump file instead of querying live.

```bash
# Standard emergency re-sync
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions --dry-run
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions

# Full sync with deactivations + metadata
python3 db/sync_from_dump.py --dump /path/to/dump.sql --deactivate --update-meta \
  --skip-ids 422,529,579,1647
```

Default dump path: `/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260311.sql`

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
- Camps with IDs not present in the source (manually created location branches)
- Programs for camps whose session set is unchanged (automated sync skips them)
