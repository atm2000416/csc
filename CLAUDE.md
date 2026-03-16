# CSC — Camp Search Concierge
**camps.ca AI Powered Camp Finder**
Streamlit + Aiven MySQL + Claude AI. Auto-deploys to Streamlit Cloud on push to `main`.

---

## Current State (as of 2026-03-16)

- Production on Streamlit Cloud, all features working
- LLM stack fully migrated to Claude (Haiku + Sonnet) — no Gemini references remain
- 271 camps with full per-session programme records (36 synced in first live run)
- Activity tags backfilled from camps.ca category pages: 728 camps, 10,724+ tags
- `db/camp_tag_overrides.json` persists scraped tags through every automated sync cycle
- QA suite: 48/48 intent parser tests passing (requires ANTHROPIC_API_KEY); 75/75 non-API tests passing
- Architecture docs: `docs/architecture.md` (full), `docs/database.md`, `docs/testing.md`
- **Automated DB sync LIVE** — OurKids dumps to Google Drive; `sync.yml` downloads + syncs daily 02:00 UTC Mon–Fri

### Pending one-time action (run locally before automation takes over)
```bash
python3 db/tag_from_campsca_pages.py        # scrape all 148 pages (~5-10 min)
python3 db/export_camp_tag_overrides.py     # regenerate JSON
git add db/camp_tag_overrides.json && git commit -m "refresh: full sitemap tag coverage"
git push
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit ≥ 1.35 |
| Database | Aiven MySQL 8.0 (SSL via `ca.pem` or `DB_SSL_CA_CERT` secret) |
| Data Sync | GitHub Actions (`sync.yml`) — daily 02:00 UTC Mon–Fri, downloads dump from Google Drive |
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
taxonomy_mapping.py             2,200+ line activity taxonomy: FUZZY_ALIASES, TRAIT_ALIASES,
                                GEO_ALIASES, GEO_COORDS, AGE_ALIASES, TAG_METADATA

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
  sync_from_source.py           **Primary data sync** — queries OurKids MySQL directly (GitHub Actions)
  sync_from_dump.py             **Emergency fallback** — manual sync from SQL dump file
  taxonomy_loader.py            load activity_tags from DB at startup; fallback to taxonomy_mapping

ui/
  results_card.py               render_card() 4-line card + render_extra_sessions() expander
  filter_sidebar.py             sticky filter bar — age / type / cost / province
  surprise_me.py                Surprise Me: random tag → direct CSSL, no LLM
  clarification_widget.py       clarification prompt chips

tests/
  test_intent_parser.py         40-query QA suite — MUST stay 40/40 before every push
  test_query_state.py           30 QueryState invariant tests
  test_intent_parser_unit.py    unit tests for _coerce_parsed(); no API required
  test_reranker.py              reranker unit tests; no API required
  test_session_manager.py       session manager unit tests
  test_cssl.py                  SQL query tests (skips if DB unavailable)
  test_fuzzy.py                 fuzzy preprocessor tests (no DB/API)
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
- `taxonomy_mapping.py` is the alias source for fuzzy_preprocessor; `activity_tags` DB is authoritative

### UI
- Results card: 4 lines — session name / camp name (tier-coloured) / detail pills / AI rationale
- `render_extra_sessions()` expander always populated from `_fetch_all_camp_programs()` (full DB catalog)
  — bypasses reranker top-N cutoff so no sessions are hidden
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

1. **SQL ORDER BY** — gender exact match → type exact match → is_primary tag → tag count ASC → tier (gold first) → review_avg DESC
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
2. `PAGE_SLUG_OVERRIDES` — 96 sitemap-derived pages with specific slugs (ballet→ballet,
   not dance-multi; photography→photography, not arts-multi etc.)
3. `CAMP_PAGE_OVERRIDES` — URL normalisation (dash→underscore broken URLs)

**Parallel lookup in search** (`core/cssl.py`): `_SLUG_TO_CAMP_IDS` (loaded at module
init from `camp_tag_overrides.json`) adds `OR p.camp_id IN (...)` to every tag query —
guaranteeing camps.ca-listed camps appear even if `program_tags` has a gap.

### OurKids programme sync — automated (GitHub Actions)

`db/sync_from_dump.py` runs **daily 02:00 UTC Mon–Fri** via `.github/workflows/sync.yml`.
Workflow: downloads the latest dump from Google Drive → runs sync → exports
`camp_tag_overrides.json` → commits if changed.

**Why Google Drive (not direct DB):** OurKids DBA denied direct MySQL access from GitHub
Actions — firewall is locked to known IPs. OurKids uploads a mysqldump to a shared Google
Drive folder; we pull it via a service account. No firewall changes required on their side.

Manual trigger: GitHub → Actions → "Sync OurKids → Aiven" → Run workflow.

**Google Drive setup:**
- Service account: `youtube-php-api@youtube-bonbon-431918-h7.iam.gserviceaccount.com`
- Drive folder ID: `15EsIGXhGCyHxmrdkGDCjIwcC1wEd6Wzk`
- GitHub secrets: `GDRIVE_SERVICE_ACCOUNT_JSON` (full JSON key), `GDRIVE_FOLDER_ID`
- Download script: `db/download_from_drive.py` — fetches most-recently-modified file in folder

```bash
# Emergency manual run from a local dump file
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions --dry-run
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions \
  --deactivate --skip-ids 422,529,579,1647
```

`--skip-ids` protects manually promoted sub-locations:
`422` Canlan Etobicoke · `529` Canlan Scarborough · `579` Canlan Oakville · `1647` Idea Labs Pickering

---

## Dev Workflow

```bash
# Run locally
streamlit run app.py

# Run all tests (must be green before pushing)
pytest tests/ -v

# Run QA suite only (40/40 required)
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
| `GDRIVE_FOLDER_ID` | — | ✓ | Google Drive folder ID (`15EsIGXhGCyHxmrdkGDCjIwcC1wEd6Wzk`) |
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
- **Duplicate programmes from sync**: Run `--dry-run` first; the import is idempotent only if the prior run fully completed
- **Activity tag scraping — URL corruption risk**: dash-format camps.ca URLs (e.g. `/gymnastics-camps.php`) redirect to homepage returning ALL 276 camps — will mass-tag every program incorrectly. Always use underscore `.php` format validated against `sitemap.xml`. `CAMP_PAGE_OVERRIDES` maps all known broken URLs to correct ones; `None` = skip page. After scraping, run `db/export_camp_tag_overrides.py` to regenerate `camp_tag_overrides.json`.
- **Adding a new category page**: add to `PAGE_SLUG_OVERRIDES` in `tag_from_campsca_pages.py` (path → [slugs]), run the scraper + export, commit JSON. If it's a new main page, also add to `CANONICAL_PAGES`.
- **Trait fuzzy aliases**: when adding a new trait word (e.g. "resilience"), add both the noun AND adjectival forms separately to `TRAIT_ALIASES` in `taxonomy_mapping.py`

---

## Further Reading

| Topic | File |
|-------|------|
| Full pipeline + component reference | `docs/architecture.md` |
| DB schema, column names, sync detail | `docs/database.md` |
| Design system (colours, fonts, spacing) | `docs/design-system.md` |
| QA and testing procedures | `docs/testing.md` |
