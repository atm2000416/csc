# CSC — Camp Search Concierge
**camps.ca AI Powered Camp Finder**
Streamlit + Aiven MySQL + Claude AI. Auto-deploys to Streamlit Cloud on push to `main`.

---

## Current State (as of 2026-03-17)

- Production on Streamlit Cloud, all features working
- LLM stack fully migrated to Claude (Haiku + Sonnet) — no Gemini references remain
- 852 active camps, 4,605 active programs, 208,133 program_tags, 8,412 future program_dates
- **Raw table import pipeline** — regex ETL replaced with `ok_*` staging tables + SQL materialization
- Gender data now populated from OurKids sessions (2,138 coed + 185 boys + 74 girls)
- 2,287 programs with mini_descriptions (previously lost in regex ETL)
- `db/camp_tag_overrides.json` persists scraped tags through every automated sync cycle
- QA suite: 48/48 intent parser tests passing (requires ANTHROPIC_API_KEY); 121/121 non-API tests passing (incl. 16 tag_role tests); 59/59 fuzzy tests
- **3-tier tagging** — `program_tags.tag_role` (specialty/category/activity) imported from OurKids sitems. CSSL ranks specialty first.
- Parity suite (`tests/parity_suite.py`) measures search quality across 4 layers; fuzzy coverage ~95%+
- Architecture docs: `docs/architecture.md` (full), `docs/database.md`, `docs/testing.md`
- **Automated DB sync LIVE** — OurKids dumps to Google Drive; `sync.yml` loads raw tables + materializes daily 02:00 UTC Mon–Fri

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit ≥ 1.35 |
| Database | Aiven MySQL 8.0 (SSL via `ca.pem` or `DB_SSL_CA_CERT` secret) |
| Data Sync | GitHub Actions (`sync.yml`) — daily 02:00 UTC Mon–Fri, raw table import + SQL materialization |
| Intent Parser | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| Reranker | Claude Haiku 4.5 |
| Concierge | Claude Sonnet 4.6 (`claude-sonnet-4-6`) |
| Language | Python 3.11+ |

---

## Pipeline (per user turn)

```
User query
  │
  ▼
fuzzy_preprocessor.py      keyword→tag hints, geo coords, age brackets — zero API cost
  │
  ▼
intent_parser.py           Claude Haiku → IntentResult (tags, geo, age, type, ICS, …)
  │                        VALID_SLUGS guard strips hallucinated tags post-parse
  ▼
session_manager.py         9-rule merge → QueryState (canonical) → accumulated_params (mirror)
  │
  ├── category_disambiguator.py  (early exit: broad tag → offer child buttons)
  ├── needs_geolocation check    (early exit: ask for city/province)
  │
  ▼
semantic_cache.py          cache hit → return immediately
  │
  ▼
cssl.py                    dynamic MySQL WHERE → result pool (up to 100) + RCS score
  │
  ▼
decision_matrix.py         ICS × RCS → SHOW_RESULTS / BROADEN_SEARCH / SHOW_CLARIFY / CLARIFY_LOOP
  │
  ├── BROADEN_SEARCH → casl.py (semantic expansion via related_ids)
  ├── CLARIFY_LOOP   → clarification_widget.py or zero_results_advisor.py
  │
  ▼
diversity_filter.py        cap at 2 programs per camp (configurable)
  │
  ▼
reranker.py                Claude Haiku → semantic rank + "Why this fits" blurb → top 10
  │
  ▼
concierge_response.py      Claude Sonnet → 2-sentence conversational intro
  │
  ▼
ui/results_card.py         render_card() + render_extra_sessions() collapsible expander
```

---

## Key Files

```
app.py                          Streamlit entry point + full pipeline orchestration
config.py                       get_secret() — reads Streamlit secrets or os.getenv
intent_parser_system_prompt.md  Claude system prompt (edit to tune extraction behaviour)
taxonomy_mapping.py             2,400+ line activity taxonomy: FUZZY_ALIASES (~1,900 entries),
                                TRAIT_ALIASES, GEO_ALIASES, GEO_COORDS, AGE_ALIASES, TAG_METADATA

core/
  llm_client.py                 get_client() → anthropic.Anthropic (shared by all LLM modules)
  intent_parser.py              Claude Haiku → IntentResult dataclass
  fuzzy_preprocessor.py         keyword→slug hints before Claude call (zero API cost)
  query_state.py                QueryState — canonical source of truth for accumulated intent
  session_manager.py            merge_intent() — 9 merge rules; accumulated_params is derived mirror
  cssl.py                       MySQL search query builder; RCS calculation; date enrichment
  casl.py                       semantic tag expansion via activity_tags.related_ids
  reranker.py                   Claude Haiku reranker + blurb annotation; gold tier boost
  concierge_response.py         Claude Sonnet narrative generator
  decision_matrix.py            ICS × RCS → 4 routes; thresholds configurable via secrets
  zero_results_advisor.py       diagnose why zero results and offer recovery action
  diversity_filter.py           cap results per camp before reranking
  semantic_cache.py             session_state-backed result cache keyed by params + query
  category_disambiguator.py     detect broad parent tag → offer child category picker
  tracer.py                     per-request debug trace accumulated in session_state

db/
  connection.py                 MySQL connection pool (SSL; ca.pem or DB_SSL_CA_CERT secret)
  load_raw_tables.py            **Step 1** — parse dump → DROP + CREATE ok_* staging tables in Aiven
  materialize_from_raw.py       **Step 2** — SQL JOINs → populate CSC tables from ok_* staging
  import_camp_tag_overrides.py  **Step 3** — re-apply camps.ca scraped tags after materialization
  export_camp_tag_overrides.py  **Step 4** — export combined tags to JSON for parallel lookup
  sync_from_dump.py             **Emergency fallback** — legacy regex-based sync from dump file
  sync_from_source.py           Legacy direct-DB sync (superseded by raw table pipeline)
  tag_from_campsca_pages.py     camps.ca category page scraper + WEBITEMS_TO_SLUG bridge
  migrate_tag_role.py           idempotent ALTER TABLE — adds tag_role ENUM to program_tags
  taxonomy_loader.py            load activity_tags from DB at startup; fallback to taxonomy_mapping

ui/
  results_card.py               render_card() 4-line card + render_extra_sessions() expander
  filter_sidebar.py             sticky filter bar — age / type / cost / province
  surprise_me.py                Surprise Me: random tag → direct CSSL, no LLM
  clarification_widget.py       clarification prompt chips

tests/
  test_intent_parser.py         48-query QA suite — MUST stay 48/48 before every push
  test_query_state.py           30 QueryState invariant tests
  test_intent_parser_unit.py    unit tests for _coerce_parsed(); no API required
  test_reranker.py              reranker unit tests; no API required
  test_session_manager.py       session manager unit tests
  test_cssl.py                  SQL query tests (skips if DB unavailable)
  test_fuzzy.py                 59 fuzzy preprocessor tests (plurals, bare-words, taxonomy, natural-language)
  test_tag_role.py              16 tests for 3-tier tagging (parse_sitems, parse_activities, tag_role, partitioning)
  parity_suite.py               4-layer search quality measurement (--with-fuzzy, --with-parser, --with-db)
  qa_queries.py                 test case definitions
```

---

## Conventions

### camps.ca URL format (DO NOT CHANGE)
**Confirmed working format:** `https://www.camps.ca/{prettyurl}/{camp_id}?{UTM}`
- Example: `https://www.camps.ca/camp-kidstown/2020?utm_source=camps.ca&utm_medium=ai-search&utm_campaign=csc`
- `prettyurl` alone (no ID) → **404**. The camp ID is required.
- `_camps_url(prettyurl, camp_id)` in `ui/results_card.py` is the single source of truth — all camps.ca links go through it
- `camp_id` comes from `result.get("camp_id")` (the `camps.id` FK on programs); never use `programs.id`

### Database
- `get_connection()` returns a pooled MySQL connection — always close **both** cursor AND conn
- `cursor = conn.cursor(dictionary=True)` — rows returned as dicts
- SQL placeholders: `%(name)s` style when passing a dict; `%s` for tuple args
- `resolve_tag_ids(slugs, cursor)` in `cssl.py` converts slug list → integer DB IDs
- `programs.start_date` / `programs.end_date` — correct column names (NOT `date_from`/`date_to`)
- `camps.status = 1` = active; `camps.status = 0` = inactive/agate (free listing, not on camps.ca)
- `program_tags.tag_role` — ENUM `'specialty'`/`'category'`/`'activity'` (default `'activity'`).
  Imported from OurKids sitems 3-tier model. CSSL ranks specialty > category > activity via `_role_match`.
  Migration: `python3 db/migrate_tag_role.py`. Scraper always inserts as `'activity'`.

### Session State
- `st.session_state.session_context["_query_state"]` — canonical `QueryState` instance
- `accumulated_params` in `session_context` is a **derived mirror** — NEVER write directly
- Always mutate `QueryState` methods, then call `sync_mirror()` to rebuild the mirror
- `merge_intent()` handles all 9 merge rules; nothing else should mutate QueryState

### Intent / Tags
- `gender` field: only set when user explicitly asks for a gender-specific camp
  ("my son plays hockey" → gender=null; "all-girls camp" → gender="Girls")
- `ics = 0.3` is the hardcoded API-error fallback — do NOT clear stale state on this value
- After parse, any tag not in the live `VALID_SLUGS` set is stripped before `IntentResult` is built
- `taxonomy_mapping.py` is the alias source for fuzzy_preprocessor (~1,900 entries covering full L2/L3 taxonomy); `activity_tags` DB is authoritative
- `sports` bare word → L1 parent `sports` (triggers category disambiguator); `sport-multi` only via explicit "multi sport" language
- `-multi` parent slugs are excluded from bare-word aliases — they trigger the disambiguator for better UX

### UI
- Results card: 4 lines — session name / camp name (tier-coloured) / detail pills / AI rationale
- `render_extra_sessions()` expander populated from `_fetch_all_camp_programs(search_params=...)`
  — applies same tag/age/type/gender filters as CSSL so only relevant sessions appear;
  bypasses reranker top-N cutoff so matching sessions aren't hidden by the reranker limit
- Tier colours: gold `#B8860B`, silver `#707070`, bronze `#8B4513`
- Primary olive: `#8A9A5B`; background: `#F4F7F0`; text: `#2F4F4F`

---

## Decision Matrix

```
                RCS ≥ 0.70          RCS < 0.70
ICS ≥ 0.70    SHOW_RESULTS         BROADEN_SEARCH  (invoke CASL)
ICS < 0.70    SHOW_AND_CLARIFY     CLARIFY_LOOP
```

Thresholds: `ICS_HIGH_THRESHOLD` / `RCS_HIGH_THRESHOLD` secrets (default 0.70 each).

---

## Ranking Order (4 stages)

1. **SQL ORDER BY** — gender exact match → type exact match → tag_role (specialty=0 > category=1 > activity=2) → tag count ASC → tier (gold first) → review_avg DESC
2. **Diversity filter** — cap at 2 programs per camp (`DIVERSITY_MAX_PER_CAMP`)
3. **Claude reranker** — semantic relevance score 0–1; gold boost ×1.05 if score ≥ 0.70; top 10 returned
4. **Display grouping** — group by camp_id preserving rank; top session = full card; rest = expander

---

## Data Sync Workflow

### camps.ca category tag refresh — automated (GitHub Actions)

`db/tag_from_campsca_pages.py` runs **weekly (Sunday 03:00 UTC)** via
`.github/workflows/refresh-camp-tags.yml`. It scrapes all camps.ca category pages,
updates `program_tags` in Aiven, exports `camp_tag_overrides.json`, and commits the
JSON to `main` if it changed.

Manual trigger: GitHub → Actions → "Refresh camps.ca Category Tags" → Run workflow.

```bash
# Local run (scrapes ~148 pages, ~5-10 min)
python3 db/tag_from_campsca_pages.py [--dry-run]

# After scraping, regenerate the JSON (also runs automatically in CI)
python3 db/export_camp_tag_overrides.py
```

**How page→slug mapping works:**
1. `CANONICAL_PAGES` in `tag_from_campsca_pages.py` — 57 canonical main pages (replaces
   Excel when running in CI; Excel takes priority locally if found at `CAMP_PAGES_XLSX`)
2. `PAGE_SLUG_OVERRIDES` — 110 sitemap-derived pages with specific slugs (ballet→ballet,
   not dance-multi; photography→photography, not arts-multi etc.)
3. `CAMP_PAGE_OVERRIDES` — URL normalisation (dash→underscore broken URLs)

**Parallel lookup in search** (`core/cssl.py`): `_SLUG_TO_CAMP_IDS` (loaded at module
init from `camp_tag_overrides.json`) adds `OR p.camp_id IN (...)` to every tag query —
guaranteeing camps.ca-listed camps appear even if `program_tags` has a gap.
For multi-program override camps, one representative program (lowest ID) is included
to avoid pool flooding.  Scraper/import scripts only write `program_tags` for
single-program camps; multi-program camps rely solely on the override parallel lookup.

### OurKids programme sync — automated (GitHub Actions)

**Pipeline: Raw Table Import + SQL Materialization** (replaced regex ETL on 2026-03-17)

`.github/workflows/sync.yml` runs **daily 02:00 UTC Mon–Fri**:
1. `db/download_from_drive.py` — fetches latest dump from Google Drive
2. `db/load_raw_tables.py --dump dump.sql` — imports 8 OurKids tables as `ok_*` staging
3. `db/materialize_from_raw.py --deactivate --skip-ids 422,529,579,1647` — SQL JOINs populate CSC tables
4. `db/import_camp_tag_overrides.py` — re-applies camps.ca scraped tags
5. `db/export_camp_tag_overrides.py` — regenerates JSON, commits if changed

**Staging tables loaded** (ephemeral, recreated each sync):
`ok_camps`, `ok_sessions`, `ok_sitems`, `ok_session_date`, `ok_addresses`,
`ok_generalInfo`, `ok_detailInfo`, `ok_extra_locations`

**Key improvements over regex ETL:**
- Gender data now imported (OurKids 1=Coed→CSC 0, 2=Boys→1, 3=Girls→2)
- Mini descriptions captured from `ok_sessions.mini_description`
- Sitems tags via SQL JOIN instead of regex field extraction
- All OurKids columns available for inspection via `SELECT * FROM ok_sessions`
- Old regex accidentally filtered by `gender` field (position 7), dropping all non-coed sessions

**Why Google Drive (not direct DB):** OurKids DBA denied direct MySQL access from GitHub
Actions — firewall is locked to known IPs. OurKids uploads a mysqldump to a shared Google
Drive folder; we pull it via a service account. No firewall changes required on their side.

Manual trigger: GitHub → Actions → "Sync OurKids → Aiven" → Run workflow.

**Google Drive setup:**
- Service account: `youtube-php-api@youtube-bonbon-431918-h7.iam.gserviceaccount.com`
- Drive folder ID: `16xEqbVXQgffZ_7osLEGNBT4iTMsuWHJT`
- GitHub secrets: `GDRIVE_SERVICE_ACCOUNT_JSON` (full JSON key), `GDRIVE_FOLDER_ID`
- Download script: `db/download_from_drive.py` — fetches most-recently-modified file in folder

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
`422` Canlan Etobicoke · `529` Canlan Scarborough · `579` Canlan Oakville · `1647` Idea Labs Pickering

**OurKids session schema (actual column names in ok_sessions):**
`class_name` (not name), `start`/`end` (not date_from/date_to), `gender` at position 7
(was misidentified as `status` in old regex — position 7 is gender, not status).
No real status column — all sessions in the dump are active. `running` field is unrelated.

---

## Dev Workflow

```bash
# Run locally
streamlit run app.py

# Run all tests (must be green before pushing)
pytest tests/ -v

# Run QA suite only (48/48 required)
pytest tests/test_intent_parser.py -v

# Deploy — Streamlit Cloud auto-deploys on push
git push origin main
```

---

## Secrets (Streamlit Cloud)

| Secret | Streamlit Cloud | GitHub Actions | Purpose |
|--------|:--------------:|:--------------:|---------|
| `ANTHROPIC_API_KEY` | ✓ | — | Claude API |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | ✓ | ✓ | Aiven MySQL |
| `DB_SSL_CA_CERT` | ✓ | ✓ | Aiven CA certificate (full PEM string) |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | — | ✓ | Google service account JSON key (full contents) |
| `GDRIVE_FOLDER_ID` | — | ✓ | Google Drive folder ID (`16xEqbVXQgffZ_7osLEGNBT4iTMsuWHJT`) |
| `ICS_HIGH_THRESHOLD` | ✓ | — | Decision matrix ICS cutoff (default `0.70`) |
| `RCS_HIGH_THRESHOLD` | ✓ | — | Decision matrix RCS cutoff (default `0.70`) |
| `RERANKER_THRESHOLD` | ✓ | — | Pool size above which reranker fires (default `15`) |
| `DIVERSITY_MAX_PER_CAMP` | ✓ | — | Max programmes per camp before diversity filter (default `2`) |
| `RESULTS_POOL_SIZE` | ✓ | — | CSSL pool limit (default `100`) |
| `LOG_INTERACTIONS` | ✓ | — | Enable interaction logging to DB (default `true`) |

See `secrets.toml.example` for a template.

---

## Known Patterns & Gotchas

- **Zero results for an activity**: Check `activity_tags` has the slug + `is_active=1`; check `program_tags` has programmes tagged with it; check `taxonomy_mapping.py` FUZZY_ALIASES maps the user's words to that slug; check `camp_tag_overrides.json` has that slug for relevant camps
- **Camp missing from search**: `status=1`? Has programmes? Programmes tagged (via `program_tags` OR `camp_tag_overrides.json`)? Tags match query? Within geo radius? See `docs/architecture.md` §6 for full diagnosis checklist
- **Reranker JSON error**: `raw.find('{"ranked"')` + `raw_decode` is the extraction pattern — handles preamble text from Claude
- **Session state after refactor**: `accumulated_params` is a mirror — if a bug shows stale values, the root cause is always a mutation that bypassed `QueryState` + `sync_mirror()`
- **Stale filters between searches**: RC-4 in `session_manager.py` clears tags/traits/type/gender/age/dates on activity switch. Rule 2b clears stale tags when model is confident but finds zero tags AND zero other params (pure exploration query). Rule 3 fires on `clear_activity=True`.
- **Scraper tags are camp-level, not program-level**: The scraper and import scripts only write `program_tags` for single-program camps. Multi-program camps rely on `camp_tag_overrides.json` parallel lookup in CSSL. This prevents false program-level signals (e.g. a basketball session getting a hockey tag because the camp appears on the hockey page).
- **Duplicate programmes from sync**: Run `--dry-run` first; the import is idempotent only if the prior run fully completed
- **OurKids session column names**: `ok_sessions` uses `class_name` (not `name`), `start`/`end` (not `date_from`/`date_to`). Position 7 in the dump is `gender`, not `status` — the old regex misidentified this, accidentally filtering out all non-coed sessions. No real status column; all sessions in the dump are active. `running` field is unrelated (only 186/12864 have `running=1`).
- **OurKids gender mapping**: OurKids uses `0=unset, 1=Coed, 2=Boys, 3=Girls`; CSC uses `0=Coed, 1=Boys, 2=Girls`. The `_GENDER_MAP` in `materialize_from_raw.py` handles conversion.
- **Staging table compatibility**: `ok_*` tables require `ENGINE=InnoDB` (Aiven doesn't support MyISAM) and `SET SESSION sql_mode = ''` (zero dates in legacy data). Both handled automatically by `load_raw_tables.py`.
- **Activity tag scraping — URL corruption risk**: dash-format camps.ca URLs (e.g. `/gymnastics-camps.php`) redirect to homepage returning ALL 276 camps — will mass-tag every program incorrectly. Always use underscore `.php` format validated against `sitemap.xml`. `CAMP_PAGE_OVERRIDES` maps all known broken URLs to correct ones; `None` = skip page. After scraping, run `db/export_camp_tag_overrides.py` to regenerate `camp_tag_overrides.json`.
- **Adding a new category page**: add to `PAGE_SLUG_OVERRIDES` in `tag_from_campsca_pages.py` (path → [slugs]), run the scraper + export, commit JSON. If it's a new main page, also add to `CANONICAL_PAGES`.
- **Trait fuzzy aliases**: when adding a new trait word (e.g. "resilience"), add both the noun AND adjectival forms separately to `TRAIT_ALIASES` in `taxonomy_mapping.py`
- **Fuzzy preprocessor coverage**: `word_match()` handles plurals via `s?` lookahead. ~220+ bare-word self-mapping aliases cover all L2/L3 slugs. `-multi` parents excluded (disambiguator handles them). Natural variants included where slug form is awkward (e.g. "ai" → ai-artificial-intelligence, "drums" → percussion)
- **Parity suite** (`tests/parity_suite.py`): 4-layer search quality measurement. Use as release guardrail. Layer 1a fuzzy ~95%+, Layer 1b parser 97.8%, Layer 3 retrieval 100%. Run `--with-fuzzy` for quick check, `--with-db` for full retrieval test

---

## Bug Fixes & Trends

61 fix commits across the project history. Categorized below by area, with recurring patterns highlighted.

### Data Integrity (5 fixes) — **recurring pattern: ID/key mismatches**
| Commit | Fix |
|--------|-----|
| `8c32c89` | **Cross-camp data corruption** — auto-increment DB IDs collided with legacy CIDs during `--import-all-sessions`, 849 programs under wrong camps. Added `dump_cids` guard. |
| `5e1d61d` | **Override camp pool flooding** — `OR p.camp_id IN (...)` pulled ALL programs at override camps. Restricted to tagged or single-program camps. |
| `71c978e` | **Sync activation criterion** — `sync_from_dump` used `showAnalytics` instead of `status` to determine active camps. |
| `222e35b` | **Gender data** — `programs.gender` not populated from `detailInfo`; 11 girls-only camps had NULL gender. |
| `c717de2` | **Program types** — legacy session data had wrong type mappings; corrected via `fix_program_types.py`. |

### Search Relevance (12 fixes) — **recurring pattern: stale state bleeding across turns**
| Commit | Fix |
|--------|-----|
| `873a1e4` | `sports` mapped to `sport-multi` (L2 child) instead of `sports` (L1 parent). |
| `e6f1c64` | Zero-results advisor age filter wrong + `financial-literacy` tag not backfilled. |
| `395c329` | "Across Canada" treated as geo filter instead of national scope. |
| `d3d734c` | Virtual fallback broken + gender bleeding on activity switch + advisor `is_virtual` filter wrong. |
| `4b63436` | `clear_activity` signal not preventing stale tags from bleeding into new searches. |
| `7ad9ff0` | Type/dates re-inherited on activity switch when they shouldn't be. |
| `ab4f360` | RC-4 date clearing didn't survive scalar merge + `clear_activity` didn't clear type/dates. |
| `d8c5ab8` | Stale city persisted when user broadened to province level. |
| `0805de7` | CASL (broadening) returned low-relevance results — added quality gate. |
| `8559579` | Exact gender/type match ranked same as soft-match coed results. |
| `32b91ce` | Type + gender search returning 0 results — three separate SQL bugs. |
| `1fe108a` | Gender filter not strict enough — NULL programs included in all-girls/all-boys searches. |

### Session / State Management (6 fixes) — **recurring pattern: mutations bypassing QueryState**
| Commit | Fix |
|--------|-----|
| `01c8b30` | 3 session pollution bugs from block 3-6 testing. |
| `e3e10d9` | `geo_broaden_province` loop — lat/lon/radius not cleared on province broadening. |
| `641534a` | Disambiguation buttons lost on page reload / reboot. |
| `b3342ee` | History and user bubble lost after disambiguation button click. |
| `7324d0d` | Disambiguator infinite loop — broad parent offered repeatedly. |
| `59bfe62` | Invalid type values + fuzzy affirmative detection broken. |

### LLM / Parser (8 fixes) — **recurring pattern: JSON extraction fragility**
| Commit | Fix |
|--------|-----|
| `145a9cb` | QA suite failures — intent parser wrong on city, virtual, ESL, confidence. |
| `51b7f87` | Reranker JSON extraction — Claude preamble text before JSON. Used `find('{')`. |
| `7fb8099` | Reranker JSON — anchored on `{"ranked"` + `raw_decode` for robustness. |
| `72d4dee` | Reranker blurb — camp-level descriptions, removed hedging language. |
| `2931e51` | Concierge asked "which city?" when results already shown. |
| `ae99bc7` | Concierge didn't acknowledge gender filter no-op for coed results. |
| `b06cafc` | Concierge silent when Gemini failed — added template fallback. |
| `9177e26` | Intent system prompt — puppy/animals rule and activity-reset signal. |

### UI / UX (12 fixes)
| Commit | Fix |
|--------|-----|
| `ca7f28c` | Camp ID missing from camps.ca links — `/{prettyurl}` alone 404s. |
| `11367f9` | camps.ca links using `/{slug}/{id}` instead of `/{prettyurl}/{id}`. |
| `4f9ad19` | Listing links still pointing to ourkids.net instead of camps.ca. |
| `237c6eb` | Expander only showed reranker subset, not all camp sessions. |
| `6098420` | No spinner between CSSL and reranker/concierge phases. |
| `d185a92` | Header didn't float on scroll. |
| `b543e2d` | Topbar links opened new tab instead of navigating in-place. |
| `9bed896` | Chat input had rectangular frame; column widths wrong. |
| `7f45803` | Content touched browser edges — needed horizontal padding. |
| `9e11669` | Result card rendered as multiple HTML blocks instead of one. |
| `57958ca` | Indentation error in `_render_category_picker` after refactor. |
| `0e5be70` | Assistant messages not rendering as iMessage blue bubbles. |

### Infrastructure / Reliability (5 fixes)
| Commit | Fix |
|--------|-----|
| `68de872` | MySQL pool had no connect timeout — DB blip caused indefinite hang. Added 10s timeout. |
| `eae2bd9` | Anthropic client had no timeout — API stall caused indefinite hang. Added 30s timeout. |
| `7b9f405` | CI missing `PYTHONPATH=.` for `export_camp_tag_overrides`. |
| `6907845` | `ST_Distance_Sphere` not supported on Aiven MySQL — removed from advisor. |
| `a02b5ad` | `review_avg` missing from SELECT — `DISTINCT`/`ORDER BY` crash. |

### Recurring Trends

1. **Stale state bleeding** (12 fixes): The #1 recurring issue. Activity switches, geo broadening, and turn-to-turn state carry-over repeatedly caused stale tags/type/gender/dates to persist. Each fix added another merge rule or clear path. **Mitigation:** QueryState + `sync_mirror()` architecture, RC-4 rule, Rule 2b, `clear_activity` signal.

2. **ID/key mismatches** (5 fixes): Legacy data uses different ID schemes (CIDs vs auto-increment, prettyurl vs slug). Assumptions about ID meaning broke sync, links, and queries. **Mitigation:** Always validate IDs against their source; never assume DB IDs correspond to external IDs.

3. **LLM output parsing** (3 fixes): Claude returns JSON with preamble text, varying formats. **Mitigation:** `find('{"ranked"')` + `raw_decode` pattern; never assume clean JSON from LLM.

4. **camps.ca URL format** (3 fixes): Format is `/{prettyurl}/{camp_id}` — prettyurl alone 404s, slug != prettyurl. **Mitigation:** Single source of truth `_camps_url()` in `ui/results_card.py`.

---

## Further Reading

| Topic | File |
|-------|------|
| Full pipeline + component reference | `docs/architecture.md` |
| DB schema, column names, sync detail | `docs/database.md` |
| Design system (colours, fonts, spacing) | `docs/design-system.md` |
| QA and testing procedures | `docs/testing.md` |
