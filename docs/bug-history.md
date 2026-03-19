# CSC Bug Fix History & Recurring Trends

65+ fix commits across the project history. Categorized below by area, with recurring patterns highlighted.

---

## Data Integrity (5 fixes) — recurring pattern: ID/key mismatches

| Commit | Fix |
|--------|-----|
| `8c32c89` | **Cross-camp data corruption** — auto-increment DB IDs collided with legacy CIDs during `--import-all-sessions`, 849 programs under wrong camps. Added `dump_cids` guard. |
| `5e1d61d` | **Override camp pool flooding** — `OR p.camp_id IN (...)` pulled ALL programs at override camps. Restricted to tagged or single-program camps. |
| `71c978e` | **Sync activation criterion** — `sync_from_dump` used `showAnalytics` instead of `status` to determine active camps. |
| `222e35b` | **Gender data** — `programs.gender` not populated from `detailInfo`; 11 girls-only camps had NULL gender. |
| `c717de2` | **Program types** — legacy session data had wrong type mappings; corrected via `fix_program_types.py`. |
| `66dbbd7` | **Broad-page redirect pollution** — `/fashion-camps.php` → `/arts_camps.php` caused 205 arts camps to get `fashion-design` tag. Same for filmmaking (205) and cycling (197). Set broad redirects to `None`; cleaned 606 polluted entries from override JSON. |
| `3534bff` | **Cleanup script mass-deletion** — `cleanup_scraper_tags.py` deleted 30,472 legitimate OurKids activity tags. Script couldn't distinguish scraper from OurKids tags (both `tag_role='activity', is_primary=0`). Restored all tags from `ok_sessions` sitems. |
| `ed9b927` | **Tag provenance** — added `source` column (ourkids/scraper/manual) to `program_tags` + 20K-floor safety gate in `materialize_from_raw.py` to prevent future mass-deletion. |

## Search Relevance (12 fixes) — recurring pattern: stale state bleeding across turns

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
| `3534bff` | **Override representative program** — CSSL override path used `MIN(id)` which surfaced wrong session (e.g. "Budding Architects" for AI search). Changed to `COALESCE` preferring a program with a matching `program_tag`. |

## Session / State Management (6 fixes) — recurring pattern: mutations bypassing QueryState

| Commit | Fix |
|--------|-----|
| `01c8b30` | 3 session pollution bugs from block 3-6 testing. |
| `e3e10d9` | `geo_broaden_province` loop — lat/lon/radius not cleared on province broadening. |
| `641534a` | Disambiguation buttons lost on page reload / reboot. |
| `b3342ee` | History and user bubble lost after disambiguation button click. |
| `7324d0d` | Disambiguator infinite loop — broad parent offered repeatedly. |
| `59bfe62` | Invalid type values + fuzzy affirmative detection broken. |

## LLM / Parser (8 fixes) — recurring pattern: JSON extraction fragility

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

## UI / UX (12 fixes)

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

## Infrastructure / Reliability (5 fixes)

| Commit | Fix |
|--------|-----|
| `68de872` | MySQL pool had no connect timeout — DB blip caused indefinite hang. Added 10s timeout. |
| `eae2bd9` | Anthropic client had no timeout — API stall caused indefinite hang. Added 30s timeout. |
| `7b9f405` | CI missing `PYTHONPATH=.` for `export_camp_tag_overrides`. |
| `6907845` | `ST_Distance_Sphere` not supported on Aiven MySQL — removed from advisor. |
| `a02b5ad` | `review_avg` missing from SELECT — `DISTINCT`/`ORDER BY` crash. |

---

## Recurring Trends

1. **Stale state bleeding** (12 fixes): The #1 recurring issue. Activity switches, geo broadening, and turn-to-turn state carry-over repeatedly caused stale tags/type/gender/dates to persist. Each fix added another merge rule or clear path. **Mitigation:** QueryState + `sync_mirror()` architecture, RC-4 rule, Rule 2b, `clear_activity` signal.

2. **ID/key mismatches** (5 fixes): Legacy data uses different ID schemes (CIDs vs auto-increment, prettyurl vs slug). Assumptions about ID meaning broke sync, links, and queries. **Mitigation:** Always validate IDs against their source; never assume DB IDs correspond to external IDs.

3. **LLM output parsing** (3 fixes): Claude returns JSON with preamble text, varying formats. **Mitigation:** `find('{"ranked"')` + `raw_decode` pattern; never assume clean JSON from LLM.

4. **camps.ca URL format** (3 fixes): Format is `/{prettyurl}/{camp_id}` — prettyurl alone 404s, slug != prettyurl. **Mitigation:** Single source of truth `_camps_url()` in `ui/results_card.py`.

5. **Scraper tag pollution** (4 fixes): Scraper tagged programs/camps too broadly — broad-page redirects, mass-tagging multi-program camps, then a cleanup script that couldn't distinguish scraper from OurKids tags destroyed 30K legitimate rows. **Mitigation:** `source` column on `program_tags` (ourkids/scraper/manual), single-program gate on scraper writes, broad-page redirects set to `None`, 20K-floor safety gate in materialization pipeline.
