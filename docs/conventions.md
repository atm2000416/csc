# CSC Conventions & Gotchas

## Critical Rules

### camps.ca URL Format (DO NOT CHANGE)
**Confirmed working format:** `https://www.camps.ca/{prettyurl}/{camp_id}?{UTM}`
- Example: `https://www.camps.ca/camp-kidstown/2020?utm_source=camps.ca&utm_medium=ai-search&utm_campaign=csc`
- `prettyurl` alone (no ID) -> **404**. The camp ID is required.
- `_camps_url(prettyurl, camp_id)` in `ui/results_card.py` is the single source of truth
- `camp_id` comes from `result.get("camp_id")` (the `camps.id` FK on programs); never use `programs.id`

### Session State
- `st.session_state.session_context["_query_state"]` — canonical `QueryState` instance
- `accumulated_params` in `session_context` is a **derived mirror** — NEVER write directly
- Always mutate `QueryState` methods, then call `sync_mirror()` to rebuild the mirror
- `merge_intent()` handles all 9 merge rules; nothing else should mutate QueryState

### Scraper Tags Are Camp-Level
The scraper and import scripts only write `program_tags` for single-program camps.
Multi-program camps rely on `camp_tag_overrides.json` parallel lookup in CSSL.
This prevents false program-level signals (e.g. basketball session getting a hockey tag
because the camp appears on the hockey page).

---

## Database Conventions

- `get_connection()` returns a pooled MySQL connection — always close **both** cursor AND conn
- `cursor = conn.cursor(dictionary=True)` — rows returned as dicts
- SQL placeholders: `%(name)s` style when passing a dict; `%s` for tuple args
- `resolve_tag_ids(slugs, cursor)` in `cssl.py` converts slug list -> integer DB IDs
- `programs.start_date` / `programs.end_date` — correct column names (NOT `date_from`/`date_to`)
- `camps.status = 1` = active; `camps.status = 0` = inactive/agate (free listing, not on camps.ca)
- `program_tags.tag_role` — ENUM `'specialty'`/`'category'`/`'activity'` (default `'activity'`).
  Derived from OurKids focus levels: `[sitem_id]level` in `ok_sessions.activities` where
  **3** (intense) → `specialty`, **2** (instructional) → `category`, **1** (recreational) → `activity`.
  These levels are set by the camps themselves. CSSL affinity gate: specialty/category pass
  unconditionally; activity is gated by tag count (≤10) or category family (≥2 sibling tags).
  Scraper always inserts as `'activity'`.
- `program_tags.source` — ENUM `'ourkids'`/`'scraper'`/`'manual'` (default `'ourkids'`).
  Any bulk tag cleanup MUST filter `source = 'scraper'`. Never delete `ourkids` rows.
- `ok_*` staging tables must never be queried by the app at runtime

---

## Intent / Tags

- `gender` field: only set when user explicitly asks for a gender-specific camp
  ("my son plays hockey" -> gender=null; "all-girls camp" -> gender="Girls")
- `ics = 0.3` is the hardcoded API-error fallback — do NOT clear stale state on this value
- After parse, any tag not in the live `VALID_SLUGS` set is stripped before `IntentResult` is built
- `taxonomy_mapping.py` is the alias source for fuzzy_preprocessor (~1,900 entries covering full L2/L3 taxonomy); `activity_tags` DB is authoritative
- `sports` bare word -> L1 parent `sports` (triggers category disambiguator); `sport-multi` only via explicit "multi sport" language
- `-multi` parent slugs are excluded from bare-word aliases — they trigger the disambiguator for better UX

---

## UI

- Results card: 4 lines — session name / camp name (tier-coloured) / detail pills / AI rationale
- `render_extra_sessions()` expander populated from `_fetch_all_camp_programs(search_params=...)`
  — applies same tag/age/type/gender filters as CSSL so only relevant sessions appear;
  bypasses reranker top-N cutoff so matching sessions aren't hidden by the reranker limit
- Tier colours: gold `#B8860B`, silver `#707070`, bronze `#8B4513`
- Primary olive: `#8A9A5B`; background: `#F4F7F0`; text: `#2F4F4F`

---

## Known Gotchas

- **Zero results for an activity**: Check `activity_tags` has the slug + `is_active=1`; check `program_tags` has programmes tagged with it; check `taxonomy_mapping.py` FUZZY_ALIASES maps the user's words to that slug; check `camp_tag_overrides.json` has that slug for relevant camps
- **Camp missing from search**: `status=1`? Has programmes? Programmes tagged (via `program_tags` OR `camp_tag_overrides.json`)? Tags match query? Within geo radius? See `docs/architecture.md` section 6 for full diagnosis checklist
- **Reranker JSON error**: `raw.find('{"ranked"')` + `raw_decode` is the extraction pattern — handles preamble text from Claude
- **Stale filters between searches**: RC-4 in `session_manager.py` clears tags/traits/type/gender/age/dates on activity switch. Rule 2b clears stale tags when model is confident but finds zero tags AND zero other params (pure exploration query). Rule 3 fires on `clear_activity=True`.
- **Duplicate programmes from sync**: Run `--dry-run` first; the import is idempotent only if the prior run fully completed
- **Activity tag scraping — URL corruption risk**: dash-format camps.ca URLs (e.g. `/gymnastics-camps.php`) redirect to homepage returning ALL 276 camps — will mass-tag every program incorrectly. Always use underscore `.php` format validated against `sitemap.xml`. `CAMP_PAGE_OVERRIDES` maps all known broken URLs to correct ones; `None` = skip page.
- **Trait fuzzy aliases**: when adding a new trait word (e.g. "resilience"), add both the noun AND adjectival forms separately to `TRAIT_ALIASES` in `taxonomy_mapping.py`
- **Fuzzy preprocessor coverage**: `word_match()` handles plurals via `s?` lookahead. ~220+ bare-word self-mapping aliases cover all L2/L3 slugs. `-multi` parents excluded (disambiguator handles them).
- **Parity suite** (`tests/parity_suite.py`): 4-layer search quality measurement. Use as release guardrail. Layer 1a fuzzy ~95%+, Layer 1b parser 97.8%, Layer 3 retrieval 100%. Run `--with-fuzzy` for quick check, `--with-db` for full retrieval test.
