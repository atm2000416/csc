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
- `gender=NULL` — data missing (most programs); NOT the same as coed
- `gender=0` — explicitly coed
- `gender=1` — boys only
- `gender=2` — girls only
- CSSL filter: only applied when user explicitly requests gender-specific camp
- "my son / my daughter" alone → `gender=null` in intent (child's sex ≠ camp gender filter)

---

## Legacy Dump Sync (`db/sync_from_dump.py`)

### Activation signal
**`status` (field 6)** in the legacy camps tuple = active/inactive.
Field 17 is `showAnalytics` (defaults 1) — **not** a membership flag. There is no `is_member` column.

### Workflow
```bash
# 1. Always dry-run first
python3 db/sync_from_dump.py --dump /path/to/dump.sql --dry-run

# 2. Standard sync (new camps + re-activations + locations + program dates)
python3 db/sync_from_dump.py --dump /path/to/dump.sql

# 3. With deactivations (review dry-run output carefully first)
python3 db/sync_from_dump.py --dump /path/to/dump.sql --deactivate --skip-ids 422,529,579,1647

# 4. Full sync including tier/website metadata
python3 db/sync_from_dump.py --dump /path/to/dump.sql --deactivate --update-meta --skip-ids 422,529,579,1647

# 5. Seed programs/tags for newly-active camps with no programs
python3 db/sync_from_dump.py --dump /path/to/dump.sql --seed-programs
```

### Protected skip-ids (manually promoted sub-locations — never deactivate)
| ID | Camp |
|---|---|
| 422 | Canlan Sports - Etobicoke |
| 529 | Canlan Sports - Scarborough |
| 579 | Canlan Sports - Oakville |
| 1647 | Idea Labs Kids Pickering & Whitby |

### What sync does NOT touch
- `activity_tags`, `program_tags` — curated manually in new DB
- Programs/tags for existing active camps
- Camps with IDs above ~2110 (manually created location branches)

### Default dump path
`/Users/181lp/Documents/CLAUDE_code/csc_migration/camp_directory_dump20260205.sql`
