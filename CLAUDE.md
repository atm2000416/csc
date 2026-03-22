# CSC — Camp Search Concierge

**camps.ca AI Powered Camp Finder**
Streamlit + Aiven MySQL + Claude AI. Auto-deploys to Streamlit Cloud on push to `main`.

281 camps, 4,070 programs, 208K tags. Automated daily sync from OurKids via Google Drive.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| UI | Streamlit >= 1.35 |
| Database | Aiven MySQL 8.0 (SSL) |
| Data Sync | GitHub Actions — daily 02:00 UTC Mon-Fri |
| Intent Parser | Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) |
| Reranker | Claude Haiku 4.5 |
| Concierge | Claude Sonnet 4.6 (`claude-sonnet-4-6`) |
| Language | Python 3.11+ |

---

## Pipeline (per user turn)

```
User query
  |
  v
fuzzy_preprocessor.py      keyword->tag hints, geo coords, age brackets (zero API cost)
  |
  v
intent_parser.py           Claude Haiku -> IntentResult (tags, geo, age, type, ICS)
  |                        VALID_SLUGS guard strips hallucinated tags post-parse
  v
session_manager.py         9-rule merge -> QueryState (canonical) -> accumulated_params
  |
  +-- category_disambiguator.py  (early exit: broad tag -> offer child buttons)
  +-- needs_geolocation check    (early exit: ask for city/province)
  |
  v
semantic_cache.py          cache hit -> return immediately
  |
  v
cssl.py                    dynamic MySQL WHERE -> result pool (up to 100) + RCS score
  |
  v
decision_matrix.py         ICS x RCS -> SHOW_RESULTS / BROADEN / CLARIFY / CLARIFY_LOOP
  |
  +-- BROADEN_SEARCH -> casl.py (semantic expansion via related_ids)
  +-- CLARIFY_LOOP   -> clarification_widget.py or zero_results_advisor.py
  |
  v
diversity_filter.py        cap at 2 programs per camp
  |
  v
reranker.py                Claude Haiku -> semantic rank + "Why this fits" blurb -> top 10
  |
  v
concierge_response.py      Claude Sonnet -> 2-sentence conversational intro
  |
  v
ui/results_card.py         render_card() + render_extra_sessions() collapsible expander
```

---

## Key Files

```
app.py                          Streamlit entry point + full pipeline orchestration
config.py                       get_secret() — reads Streamlit secrets or os.getenv
intent_parser_system_prompt.md  Claude system prompt for intent extraction
taxonomy_mapping.py             FUZZY_ALIASES (~1,900), TRAIT_ALIASES, GEO_ALIASES, GEO_COORDS

core/
  llm_client.py                 get_client() -> anthropic.Anthropic
  intent_parser.py              Claude Haiku -> IntentResult dataclass
  fuzzy_preprocessor.py         keyword->slug hints before Claude call
  query_state.py                QueryState — canonical source of truth
  session_manager.py            merge_intent() — 9 merge rules
  cssl.py                       MySQL search query builder + RCS + date enrichment
  casl.py                       semantic tag expansion via related_ids
  reranker.py                   Claude Haiku reranker + blurb annotation
  concierge_response.py         Claude Sonnet narrative generator
  decision_matrix.py            ICS x RCS -> 4 routes
  zero_results_advisor.py       diagnose zero results + offer recovery
  diversity_filter.py           cap results per camp before reranking
  semantic_cache.py             session_state-backed result cache
  category_disambiguator.py     broad parent tag -> child category picker
  tracer.py                     per-request debug trace

db/
  connection.py                 MySQL connection pool (SSL)
  load_raw_tables.py            Step 1 — parse dump -> ok_* staging tables
  materialize_from_raw.py       Step 2 — SQL JOINs -> populate CSC tables
  import_camp_tag_overrides.py  Step 3 — re-apply scraped tags (single-program camps only)
  export_camp_tag_overrides.py  Step 4 — export tags to JSON for parallel lookup
  tag_from_campsca_pages.py     camps.ca category page scraper
  sync_from_dump.py             Emergency fallback — legacy regex ETL

ui/
  results_card.py               render_card() + render_extra_sessions()
  filter_sidebar.py             sticky filter bar
  surprise_me.py                random tag -> direct CSSL, no LLM
  clarification_widget.py       clarification prompt chips

tests/
  test_intent_parser.py         48-query QA suite (requires ANTHROPIC_API_KEY)
  test_query_state.py           30 QueryState invariant tests
  test_fuzzy.py                 59 fuzzy preprocessor tests
  test_tag_role.py              16 tests for 3-tier tagging
  test_reranker.py              reranker unit tests
  test_session_manager.py       session manager unit tests
  test_cssl.py                  SQL query tests (skips if DB unavailable)
  parity_suite.py               4-layer search quality measurement
```

---

## Critical Rules

1. **camps.ca URL**: Program deep link `/{prettyurl}/{camp_id}/session/{ourkids_session_id}`, fallback `/{prettyurl}/{camp_id}` — prettyurl alone 404s. Single source of truth: `_camps_url()` in `ui/results_card.py`. See `docs/conventions.md`.

2. **Session state**: `accumulated_params` is a derived mirror — NEVER write directly. Mutate `QueryState`, then `sync_mirror()`. Only `merge_intent()` should mutate QueryState.

3. **Scraper tags are camp-level**: Scraper/import only write `program_tags` for single-program camps. Multi-program camps use `camp_tag_overrides.json` parallel lookup in CSSL. See `docs/data-sync.md`.

4. **`program_tags.source` column**: `ourkids` (OurKids sitems), `scraper` (camps.ca pages), `manual`. Any bulk cleanup of tags MUST filter by `source = 'scraper'` — never delete `ourkids` rows. Safety gate in `materialize_from_raw.py` aborts if tag count drops below 20K.

5. **`program_tags.tag_role` from OurKids focus levels**: `ok_sessions.activities` format is `[sitem_id]level` where level is the camp's own declaration: `3=intense→specialty`, `2=instructional→category`, `1=recreational→activity`. These are set by the camps themselves, not OurKids. The CSSL affinity gate uses tag_role to filter noise — see docs/architecture.md.

6. **`ics = 0.3`** is the API-error fallback — do NOT clear stale state on this value.

7. **`ok_*` staging tables** must never be queried by the app at runtime.

---

## Decision Matrix

```
                RCS >= 0.70          RCS < 0.70
ICS >= 0.70    SHOW_RESULTS         BROADEN_SEARCH  (invoke CASL)
ICS < 0.70    SHOW_AND_CLARIFY     CLARIFY_LOOP
```

Thresholds: `ICS_HIGH_THRESHOLD` / `RCS_HIGH_THRESHOLD` secrets (default 0.70 each).

## Ranking Order (4 stages)

1. **SQL ORDER BY** — gender match -> type match -> tag_role (specialty > category > activity) -> tag count ASC -> tier (gold first) -> review_avg DESC. **Affinity gate** filters before ranking: tag must be specialty/category, OR program has ≤10 tags, OR ≥2 tags from the same category family. Tags without any specialty/category assignments globally (e.g., hiking) skip the gate.
2. **Diversity filter** — cap at 2 programs per camp
3. **Claude reranker** — semantic score 0-1; gold boost x1.05 if score >= 0.70; top 10
4. **Display grouping** — group by camp_id; top session = full card; rest = filtered expander

---

## Dev Workflow

```bash
streamlit run app.py                              # Run locally
pytest tests/ -v                                  # All tests (must pass before push)
pytest tests/test_intent_parser.py -v             # QA suite (48/48 required)
git push origin main                              # Deploy (auto-deploys on push)
```

---

## Secrets

| Secret | Streamlit | Actions | Purpose |
|--------|:-:|:-:|---------|
| `ANTHROPIC_API_KEY` | x | | Claude API |
| `DB_HOST/PORT/NAME/USER/PASSWORD` | x | x | Aiven MySQL |
| `DB_SSL_CA_CERT` | x | x | Aiven CA cert (PEM string) |
| `GDRIVE_SERVICE_ACCOUNT_JSON` | | x | Google service account |
| `GDRIVE_FOLDER_ID` | | x | Google Drive folder |
| `ICS_HIGH_THRESHOLD` | x | | Decision matrix ICS cutoff (0.70) |
| `RCS_HIGH_THRESHOLD` | x | | Decision matrix RCS cutoff (0.70) |
| `RERANKER_THRESHOLD` | x | | Pool size for reranker (15) |
| `DIVERSITY_MAX_PER_CAMP` | x | | Max per camp (2) |
| `RESULTS_POOL_SIZE` | x | | CSSL pool limit (100) |

---

## Detailed Documentation

| Topic | File |
|-------|------|
| Full pipeline + component reference | `docs/architecture.md` |
| DB schema, column names, constraints | `docs/database.md` |
| All conventions, gotchas, patterns | `docs/conventions.md` |
| Data sync pipeline + OurKids schema | `docs/data-sync.md` |
| Design system (colours, fonts) | `docs/design-system.md` |
| QA and testing procedures | `docs/testing.md` |
| Bug fix history + recurring trends | `docs/bug-history.md` |
