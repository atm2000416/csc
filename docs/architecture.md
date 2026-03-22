# Camp Search Concierge (CSC) — Architecture Document

**Product:** camps.ca AI Powered Camp Finder
**Version:** 1.0
**Status:** Production
**Last Updated:** 2026-03-17

---

## 1. Executive Summary

The Camp Search Concierge (CSC) is a conversational AI search assistant embedded on camps.ca. It allows parents to describe what they are looking for in natural language — activity type, location, age, cost, dates, and personal values — and returns ranked, personalised camp recommendations from a live MySQL database.

The system is designed around a hybrid architecture: a zero-cost keyword pre-processing layer resolves common terms before any LLM call is made, a structured SQL engine handles all data retrieval (no vector search, no embeddings), and two Claude models provide natural language understanding and result ranking. The design prioritises reliability, deterministic fallback behaviour, and low operational cost.

---

## 2. System Overview

| Attribute | Detail |
|-----------|--------|
| **Deployment** | Streamlit Cloud (auto-deploy on push to `main`) |
| **Database** | Aiven managed MySQL (SSL/TLS, `ca.pem` certificate) |
| **LLM Provider** | Anthropic Claude API |
| **Language** | Python 3.11 |
| **Repository** | github.com/atm2000416/csc |
| **Session Model** | Streamlit `session_state` (server-side, per-user, ephemeral) |

### LLM Model Allocation

| Component | Model | Rationale |
|-----------|-------|-----------|
| Intent Parser | `claude-haiku-4-5-20251001` | Fast, low-cost, reliable structured JSON extraction |
| Reranker | `claude-haiku-4-5-20251001` | Fast, low-cost, semantic scoring at ~600ms |
| Concierge Response | `claude-sonnet-4-6` | Highest conversational quality for user-facing copy |

---

## 3. High-Level Architecture

The system is organised into ten functional layers, each with a distinct responsibility. A user request flows through these layers in sequence. Layers 1–4 run on every typed query; layers 5–8 are conditional based on confidence scores.

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1   User Interaction                                     │
│            Chat input · Sidebar filters · Header buttons        │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 2   Orchestrator (app.py)                                │
│            Entry point · Route dispatcher · Special input paths │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 3   Preprocessing (fuzzy_preprocessor.py)                │
│            Keyword→tag hints · Geo coordinates · Age brackets   │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 4   Language Understanding (intent_parser.py)            │
│            Claude Haiku · Natural language → structured params  │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 5   Session / State Management (session_manager.py)      │
│            QueryState · Multi-turn merge · Provenance tracking  │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 6   Search Engine (cssl.py + casl.py)                    │
│            Dynamic SQL · Tag expansion · Geo proximity          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 7   Routing (decision_matrix.py)                         │
│            ICS × RCS → 4 routes · Zero-results advisor          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 8   Post-Processing (diversity_filter + reranker)        │
│            Camp diversity cap · Claude Haiku semantic reranking  │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 9   Response Generation (concierge_response.py)          │
│            Claude Sonnet · Conversational intro message          │
├─────────────────────────────────────────────────────────────────┤
│  LAYER 10  UI Rendering (ui/)                                   │
│            Result cards · Collapsible sessions · Chat bubbles   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. End-to-End Request Flow

### 4.1 Happy Path (typed query, cache miss)

```
User types query
        │
        ▼
[A] Fuzzy Preprocessor           0ms · no API call
    keyword scan → tag/trait/geo/age hints
        │
        ▼
[B] Intent Parser (Claude Haiku) ~400ms
    natural language → IntentResult dataclass
    VALID_SLUGS guard strips hallucinated tags
        │
        ▼
[C] Session Merge                <1ms
    9 merge rules → QueryState mutated
    accumulated_params rebuilt (mirror)
    sidebar filters applied on top
        │
        ├──[D] Category Disambiguator (optional early exit)
        │      Broad tag detected → offer child buttons → return
        │
        ├──[E] Geolocation check (optional early exit)
        │      "near me" detected → ask for city → return
        │
        ▼
[F] Semantic Cache check
    Cache hit → render cached result → return
    Cache miss → continue
        │
        ▼
[G] CSSL Query (MySQL)           ~50ms
    Dynamic WHERE → program pool (up to 100) + RCS score
        │
        ▼
[H] Decision Matrix
    ICS × RCS → Route (SHOW_RESULTS / BROADEN / CLARIFY)
        │
        ▼
[I] Diversity Filter
    Cap at 2 programs per camp (configurable)
        │
        ▼
[J] Reranker (Claude Haiku)      ~600ms
    Semantic rerank top 20 → top 10
    Generate "Why this fits" blurb per result
        │
        ▼
[K] Concierge Response (Claude Sonnet) ~400ms
    1–2 sentence conversational intro
        │
        ▼
[L] UI Rendering
    render_card() × N camps
    render_extra_sessions() collapsible expander
    _render_bubble() for concierge message
```

**Typical end-to-end latency:** 1.4–1.8 seconds (cache miss, reranker fires)
**Cache hit latency:** <100ms

### 4.2 Special Input Paths (bypass LLM entirely)

| Trigger | Path |
|---------|------|
| User says "yes / sure / show me" | Affirmative path: apply pending geo-broaden, re-run CSSL with existing params |
| User clicks disambiguation button | Apply chosen tags to QueryState, re-run CSSL |
| User clicks "Surprise Me" | Random weighted tag + location → direct CSSL query, no LLM |
| User clicks "Start Over" | Clear all session state, reload |

---

## 5. Component Reference

### 5.1 Fuzzy Preprocessor (`core/fuzzy_preprocessor.py`)

**Role:** Zero-cost, zero-latency keyword matching layer that runs before any LLM call. Catches common terms, misspellings, aliases, and domain-specific language that Claude might misinterpret or miss.

**Inputs:** Raw user query string

**Outputs:**

| Key | Example | Purpose |
|-----|---------|---------|
| `tag_hints` | `["empowerment"]` | Validated activity tag slugs |
| `trait_hints` | `["courage"]` | Character trait slugs |
| `geo_expansion` | `["Toronto", "Mississauga", …]` | Region name → city list |
| `geo_coords` | `{lat, lon, radius_km}` | Known suburb → GPS coordinates |
| `age_bracket` | `{age_from: 2, age_to: 4}` | Age language → numeric range |
| `needs_geolocation` | `True` | "near me" → ask for location |

**Data source:** `taxonomy_mapping.py` — 5 alias dictionaries, longest-match-first ordering to prevent substring false positives.

**Why this exists:** Prevents Claude from hallucinating tags for common terms that have an exact known mapping. The preprocessor's output is injected into the Claude call as `FUZZY_HINTS`, which the system prompt treats as high-confidence candidates. A camp search for "confidence" reliably returns `empowerment`-tagged camps because the preprocessor catches it before Claude even sees the query.

---

### 5.2 Intent Parser (`core/intent_parser.py`)

**Role:** Convert free-text user queries into a fully structured `IntentResult` dataclass using Claude Haiku.

**Model:** `claude-haiku-4-5-20251001` · Temperature 0.2 · Max tokens 1000

**System prompt:** `intent_parser_system_prompt.md` — contains full activity taxonomy (~200 slugs with aliases), trait taxonomy, ICS scoring guide, JSON output schema, and FUZZY_HINTS enforcement rules.

**Key inputs injected per call:**
- Raw query
- `FUZZY_HINTS` from preprocessor
- `VALID_SLUGS` — live list of all `is_active=1` slugs from `activity_tags` DB table
- Current session context (accumulated params from prior turns)
- Today's date (for date range interpretation)

**Post-parse guard:** Any tag returned by Claude that does not exist in `VALID_SLUGS` is stripped before the `IntentResult` is constructed. If all tags are stripped, `recognized` is set to `False`. This prevents hallucinated slugs from reaching the SQL engine.

**IntentResult fields:**

| Field | Type | Description |
|-------|------|-------------|
| `tags` | `list[str]` | Activity tag slugs (e.g. `["hockey", "skating"]`) |
| `exclude_tags` | `list[str]` | Tags to exclude from results |
| `traits` | `list[str]` | Character trait slugs (e.g. `["teamwork", "resilience"]`) |
| `city` | `str` | Single city name |
| `cities` | `list[str]` | Multi-city search |
| `province` | `str` | Province name |
| `lat` / `lon` / `radius_km` | `float` | GPS proximity search |
| `age_from` / `age_to` | `int` | Child's age range |
| `type` | `str` | `"Day"` / `"Overnight"` / `"Virtual"` |
| `gender` | `str` | `"Boys"` / `"Girls"` — only when explicitly requested |
| `cost_max` | `int` | Maximum cost in CAD |
| `date_from` / `date_to` | `str` | ISO date strings |
| `language_immersion` | `str` | e.g. `"French"` |
| `is_special_needs` | `bool` | Special needs programme filter |
| `is_virtual` | `bool` | Online programme filter |
| `ics` | `float` | Intent Confidence Score 0.0–1.0 |
| `recognized` | `bool` | `False` if query could not be mapped to taxonomy |
| `needs_clarification` | `list[str]` | Dimensions to ask about (age, location, etc.) |
| `needs_geolocation` | `bool` | "Near me" detected — ask user for location |
| `clear_activity` | `bool` | Fresh broad search signal — clear activity params |

---

### 5.3 Session Manager + QueryState (`core/session_manager.py`, `core/query_state.py`)

**Role:** Maintain persistent conversational context across turns. Allow users to refine searches incrementally without re-stating everything each time.

**Architecture:** `QueryState` is the canonical source of truth. The `accumulated_params` flat dict (used by CSSL) is a derived read-only mirror, rebuilt by `sync_mirror()` after every mutation. Code must never write to `accumulated_params` directly.

**Key types:**

| Type | Description |
|------|-------------|
| `QueryState` | All accumulated search state; each field wrapped in `FieldValue` with provenance metadata |
| `FieldValue` | `{value, provenance, turn_set, confidence, source}` |
| `GeoState` | `original_anchor` (never overwritten) · `current_scope` · `broadening_history` |
| `PendingAction` | Typed suggestion awaiting user confirmation (replaces loose dict) |
| `Provenance` | `EXPLICIT` / `INFERRED` / `SYSTEM_BROADENED` / `CARRIED` / `DEFAULT` |

**merge_intent() — 9 rules applied in order:**

| # | Rule | Trigger | Effect |
|---|------|---------|--------|
| 1 | Unrecognised query | `recognized=False` and `ics > 0.3` | Clear stale tags, exclude_tags, type |
| 2 | No taxonomy match | No tags and `0.3 < ics < 0.7` | Clear stale tags, exclude_tags |
| 3 | Fresh search signal | `clear_activity=True` | Clear tags, exclude_tags, type, dates |
| 4 | Activity switch | New tags share zero overlap with prior tags | Clear stale exclude_tags |
| 5 | Apply list fields | Non-empty tags, exclude_tags, traits | Override accumulated values |
| 6 | Apply scalar fields | Non-null type, age, cost, dates, flags | Override accumulated values |
| 7 | Post-switch cleanup | Activity switched + dates/type not re-stated | Strip inherited dates/type |
| 8 | Geo replacement | Any geo field present in intent | `replace_geo()` — resets broadening history |
| 9 | Sync mirror | Always | Rebuild `accumulated_params` from QueryState |

---

### 5.4 CSSL — Camp SQL Search Logic (`core/cssl.py`)

**Role:** Translate the accumulated parameter dict into a dynamic MySQL query. The sole data retrieval engine — no vector search, no embeddings.

**Inputs:** `accumulated_params` dict + pool size limit (default 100)

**Outputs:** `(list[dict], rcs: float)` — result pool and Result Confidence Score

**Tag resolution pipeline:**
1. Raw slug list → `expand_via_categories()` — traverses category hierarchy to include child tags (e.g. `"dance-multi"` expands to all dance sub-styles)
2. Expanded slugs → `resolve_tag_ids()` — converts slugs to integer IDs for the SQL `IN (…)` clause
3. Expanded slugs → `resolve_category_family()` — finds the narrowest multi-category parent (e.g., `swimming` → `water-sports-multi` family of 15 tags) for affinity checking
4. Tag IDs → `_has_strong_role_assignments()` — checks if any searched tag has specialty/category assignments globally. Determines whether the affinity gate activates.

**Affinity gate** (filters stray tags on unrelated programs):

| Tag type | Gate logic |
|----------|-----------|
| Has specialty/category roles + multi-parent family | Accept if `tag_role` is specialty/category OR program has ≥2 tags from the same category family |
| Has specialty/category roles + leaf tag (no parent) | Accept if `tag_role` is specialty/category OR program has ≤10 total tags |
| No specialty/category roles globally (e.g., hiking) | Gate skipped — all matches pass |

The `tag_role` values come from OurKids focus levels set by the camps themselves: `3=intense→specialty`, `2=instructional→category`, `1=recreational→activity`. See data-sync.md for the mapping.

**Dynamic WHERE clause — filters applied:**

| Filter | Condition |
|--------|-----------|
| Active only | `p.status = 1 AND c.status = 1` |
| Not expired | `p.end_date IS NULL OR p.end_date >= CURDATE()` |
| Activity tags | `program_tags.tag_id IN (…)` + affinity gate (see above) |
| Excluded tags | `p.id NOT IN (SELECT … WHERE tag_id IN (…))` |
| Geo (GPS) | Haversine formula ≤ `radius_km` |
| Geo (city list) | `c.city IN (…)` |
| Geo (single city) | `c.city = ?` |
| Province | `c.province = ?` |
| Age overlap | `p.age_from ≤ age_to AND p.age_to ≥ age_from` (NULLs treated as accepting any age) |
| Camp type | Maps `"Day"/"Overnight"/"Virtual"` to legacy numeric codes `'1'/'2'/'3'/'4'` |
| Gender | Soft match: exact requested gender OR coed (`gender=0`) OR NULL |
| Cost | `p.cost_from ≤ cost_max` |
| Date range | JOIN `program_dates` with slot overlap check |
| Traits | `program_traits.trait_id IN (…)` — ranking boost only, not a hard filter |
| Special needs | `p.is_special_needs = 1` |
| Virtual | `p.is_virtual = 1` |
| Language | Boost only — `language_immersion` column has 24 programmes; most language camps found via `language-instruction` tag |

**Result Confidence Score (RCS):**

| Pool size | Base RCS | Notes |
|-----------|----------|-------|
| ≥ 20 results | 0.90 | |
| 10–19 results | 0.80 | |
| 5–9 results | 0.70 | |
| 1–4 results | 0.50 | |
| 0 results | 0.00 | |
| Has gold camp | +0.05 | Capped at 1.0 |
| Tags active + < 3 results | −0.20 | Floor 0.30 |
| < 50% age coverage | −0.10 | Floor 0.30 |

---

### 5.5 CASL — Contextual Activity Synonym Lookup (`core/casl.py`)

**Role:** Semantic broadening when CSSL returns too few results. Fired only on the `BROADEN_SEARCH` route.

**Mechanism:** Reads `related_ids` (comma-separated integer IDs) from the `activity_tags` table for each searched slug. Resolves those IDs to slugs, then re-runs CSSL with the expanded tag set. Additional results are appended to the original pool (no duplicates).

**Example:** User searches "sailing" (3 results). CASL reads `related_ids` for `sailing-marine-skills` → resolves to `kayaking-sea-kayaking`, `canoeing`, `water-sports-multi` → re-runs CSSL with all four tags → returns 18 results.

---

### 5.6 Decision Matrix (`core/decision_matrix.py`)

**Role:** Route the search based on two confidence signals — how well the system understood the query (ICS) and how many good results it found (RCS).

**Matrix:**

```
                    RCS ≥ threshold         RCS < threshold
ICS ≥ threshold     SHOW_RESULTS            BROADEN_SEARCH
ICS < threshold     SHOW_AND_CLARIFY        CLARIFY_LOOP
```

| Route | Behaviour |
|-------|-----------|
| `SHOW_RESULTS` | Confident query, good pool. Show results, no friction. |
| `BROADEN_SEARCH` | Confident query, thin pool. Invoke CASL semantic expansion. |
| `SHOW_AND_CLARIFY` | Good pool, vague query. Show results + ask one clarifying question. |
| `CLARIFY_LOOP` | Neither confident. Ask clarifying questions. Show results as fallback if any exist. |

Default thresholds: ICS ≥ 0.70, RCS ≥ 0.70. Both configurable via Streamlit secrets (`ICS_HIGH_THRESHOLD`, `RCS_HIGH_THRESHOLD`).

---

### 5.7 Category Disambiguator (`core/category_disambiguator.py`)

**Role:** Surface a category picker when a query resolves to a broad parent tag, offering the user specific sub-categories before running any search.

**Trigger:** `get_broad_parent(tags)` returns a slug when the tag list contains a single broad parent (e.g. `"music-multi"`, `"sport-multi"`, `"arts-multi"`).

**Flow:**
1. Detect broad parent in `merged_params.tags`
2. `get_viable_children(parent)` — fetch child tags with ≥ 1 active camp
3. Render clickable buttons (each carries `{slug, emoji, display_label}`)
4. User click stores choice in `_disambiguation_choice` → bypasses LLM on next render cycle
5. Each broad parent offered **at most once per session** to prevent infinite disambiguation loops

---

### 5.8 Diversity Filter (`core/diversity_filter.py`)

**Role:** Prevent any single camp from dominating the result list by capping the number of programs shown per camp before reranking.

**Algorithm:** Single pass over the SQL-ordered pool. Programs within the per-camp cap go to a `diverse` list; overflow goes to a separate `overflow` list. Returns `diverse + overflow` — overflow is never discarded, only deferred.

**Default cap:** 2 programs per camp (`DIVERSITY_MAX_PER_CAMP` secret, configurable).

**Why this matters:** A camp with 50 programs and strong tag overlap could fill the entire top-10 without this filter. The diversity cap ensures a variety of different camps is always represented in the first screen of results.

---

### 5.9 Reranker (`core/reranker.py`)

**Role:** Apply semantic relevance scoring to the diversity-filtered pool and generate a personalised one-sentence rationale ("Why this fits") for each result.

**Model:** `claude-haiku-4-5-20251001` · Temperature 0.1 · Max tokens 3000

**Skip conditions:**
- Pool size ≤ 15 (configurable) AND ICS ≥ 0.80 → skip Claude call, use SQL order, assign `rerank_score = 1.0`
- Pool ≤ 3 candidates → skip (not worth latency)

**When the reranker fires:**

1. Takes top 20 programs from the diversity-filtered pool
2. Sends a compact representation to Claude: `{id, camp, program, tier, city, ages, desc[:200]}`
3. Claude returns `{"ranked": [{id, score, blurb}]}` — JSON only, no preamble
4. Scores are applied back to result dicts
5. A **gold tier boost** is applied post-Claude: if `tier == "gold"` and `score ≥ 0.70`, multiply score by 1.05 (capped at 1.0). This nudges gold camps above silver camps of equal relevance without overriding clearly more relevant results.
6. Results are sorted by `rerank_score` descending; top 10 returned

**Fallback on API error:** SQL order is preserved; `rerank_score = 0.5`; blurb set to `mini_description`.

**Bilingual support:** The prompt instructs Claude to write blurbs in the same language as the user's query. Camp names remain in English; blurb prose matches French or English as appropriate.

---

### 5.10 Concierge Response Generator (`core/concierge_response.py`)

**Role:** Generate a short, warm, conversational intro message that frames the results for the user.

**Model:** `claude-sonnet-4-6` · Temperature 0.4 · Max tokens 200

**Route-aware tone:**

| Route | Tone |
|-------|------|
| `SHOW_RESULTS` | Confident and direct — "Great news, I found 7 hockey camps in Toronto…" |
| `BROADEN_SEARCH` | Acknowledges widening — "I broadened the search a little and found…" |
| `SHOW_AND_CLARIFY` | Shows results but invites refinement — "Here are some options, but tell me more about…" |

**Fallback:** Template string on API error.

---

### 5.11 Semantic Cache (`core/semantic_cache.py`)

**Role:** Skip the entire pipeline (CSSL + reranker + concierge) on repeated or near-identical queries within a session.

**Key:** Hash of `accumulated_params + raw_query`
**Store:** Streamlit `session_state` (per-user, cleared on browser close)
**Payload:** `{results, concierge_message}`

A cache hit replays the stored response in <100ms. Cache misses continue through the full pipeline.

---

### 5.12 Zero Results Advisor (`core/zero_results_advisor.py`)

**Role:** When all routes fail to produce usable results, diagnose why and offer a specific recovery action.

**Critical design rule:** The advisor must apply **all the same filters as CSSL** (type, gender, cost, age, language_immersion, is_special_needs, is_virtual). If the advisor counts programmes without a filter that CSSL applies, it will suggest broadening that cannot help — creating an **endless loop** (advisor suggests city → CSSL gets 0 → advisor suggests province → CSSL gets 0 → repeat).

**Two diagnostic paths:**

1. **Tag-based path** (`tag_ids` non-empty): Queries for programmes matching the tags with all CSSL filters applied, grouped by city. Used when the user asked for a specific activity.
2. **Geo-only path** (`tag_ids` empty): Checks whether ANY camps exist in the searched city/province with all filters applied. Used when the user provided location/age/gender but no activity.

**Failure types and responses:**

| Type | Cause | Response |
|------|-------|---------|
| `geo_broaden_specific` | Activity exists in another city in the same province | "No results in [city], but I found N programmes in [nearby city]. Want me to show those?" |
| `geo_broaden_province` | City has no camps at all | "We don't have camps in [city] yet, but there are N programmes across [province]" |
| `no_supply` | Activity/filter combination has zero results anywhere | "We don't currently have [X] camps in our directory" — names the blocking filter (e.g., "French-immersion camps") |
| `no_tags` (with geo) | No activity identified but camps exist in area | "I found camps in [city], what type of camp interests you?" |
| `no_tags` (no geo) | Nothing useful extracted | "Could not identify the activity requested" |

Recovery actions are stored as `PendingAction` in `QueryState`. If the user says "yes" on the next turn, the action is applied and CSSL is re-run without going through the LLM again.

---

## 6. Ranking Logic

A camp's position in the final result list is determined by four sequential stages. Each stage operates on the output of the previous one.

### Stage 1 — Eligibility Gate (CSSL WHERE clause)

A program cannot appear at all unless every hard filter passes. There are no partial matches — a program is either in the pool or excluded entirely.

Critical eligibility conditions: active status (program and camp), not expired, tag match, geo match, age overlap, type, gender soft-match, cost cap, date overlap, traits.

### Stage 2 — SQL Sort (CSSL ORDER BY)

Programs that pass the gate are sorted by five keys in strict priority order:

| Priority | Signal | When Active | Detail |
|----------|--------|-------------|--------|
| 1 | Gender exact match | User requested gender-specific camp | Exact gender programs first; coed and null follow |
| 2 | Type exact match | User specified Day or Overnight | Pure type beats combined type (e.g. "Day only" beats "Day & Overnight" for a Day search) |
| 3a | `tag_role` match | Tag search active | specialty (0) > category (1) > activity (2). Roles derived from OurKids focus levels: 3=intense→specialty, 2=instructional→category, 1=recreational→activity |
| 3b | Tag count (ASC) | Tag search active | Fewer total tags = more specialised = sorted higher. A dedicated soccer camp beats a multi-sport camp for a soccer search |
| 4 | Tier (gold > silver > bronze) | Always | Within any tied group from rules 1–3 |
| 5 | Review average (DESC) | Always | Final tiebreaker |

### Stage 3 — Diversity Cap (Diversity Filter)

Before reranking, the pool is capped at 2 programs per camp (configurable). This prevents a single camp from flooding the top results. Programs beyond the cap are deferred to an overflow list — not discarded — and remain available in the per-camp expander.

### Stage 4 — Semantic Rerank (Claude Haiku)

The final and most powerful ranking signal. Claude evaluates semantic fit between the user's query and each program's description, generating a relevance score from 0.0 to 1.0. This can completely invert the SQL order.

A small gold tier boost (+5%) is applied post-Claude for gold-tier camps scoring ≥ 0.70. This nudges but never overrides a clearly more relevant non-gold result.

**The SQL order is a seed, not the final answer. Claude's reranker determines display position.**

### Stage 5 — Display Grouping

The 10 reranked programs are grouped by `camp_id` for display, preserving rank order. The highest-ranked program for each camp becomes the primary result card. All other programs from the same camp collapse into a "more sessions" expander below it, supplemented by a direct DB query (`_fetch_all_camp_programs`) that retrieves the full session catalog regardless of reranker cutoffs.

**Ranking Signal Summary:**

| Signal | Stage | Weight |
|--------|-------|--------|
| Gender exact match | SQL | Hard priority — slot 1 |
| Type exact match | SQL | Hard priority — slot 2 |
| `tag_role` (specialty > category > activity) | SQL | Specialist boost — slot 3a |
| Tag count (fewer = better) | SQL | Specialist boost — slot 3b |
| Tier (gold/silver/bronze) | SQL + reranker | SQL slot 4 + 5% post-rerank boost |
| Review average | SQL | Tiebreaker — slot 5 |
| Semantic relevance score | Claude Haiku | Final reorder, 0.0–1.0 |
| Gold boost | Post-Claude | ×1.05 if gold AND score ≥ 0.70 |

---

## 7. Data Architecture

### 7.1 Database Schema (Key Tables)

| Table | Key Columns | Purpose |
|-------|-------------|---------|
| `camps` | `id, camp_name, tier, city, province, lat, lon, slug, website, status, review_avg` | Camp master record |
| `programs` | `id, camp_id, name, type, age_from, age_to, cost_from, cost_to, gender, is_special_needs, is_virtual, is_family, before_care, after_care, language_immersion, mini_description, description, start_date, end_date, status` | Individual programme / session offering |
| `program_dates` | `program_id, start_date, end_date` | Scheduled date slots per programme |
| `activity_tags` | `id, slug, is_active, related_ids` | Taxonomy of activities; `related_ids` powers CASL |
| `program_tags` | `program_id, tag_id, is_primary, tag_role, source` | Many-to-many; `is_primary` marks core activity; `tag_role` = specialty/category/activity; `source` = ourkids/scraper/manual |
| `traits` | `id, name, slug` | 12 character traits (Teamwork, Resilience, Creativity, etc.) |
| `program_traits` | `program_id, trait_id, justification` | Many-to-many trait assignments with camp-authored justification text |
| `categories` | `slug, filter_activity_tags, is_active` | Hierarchical tag expansion for CSSL |

### 7.2 Taxonomy Mapping (`taxonomy_mapping.py`)

A static Python module (no DB dependency) providing all alias lookups used by the fuzzy preprocessor and intent parser:

| Dictionary | Entries | Maps |
|-----------|---------|------|
| `FUZZY_ALIASES` | 1000+ | keyword → `[tag_slug, …]` |
| `TRAIT_ALIASES` | 200+ | keyword → `[trait_slug, …]` |
| `GEO_ALIASES` | 150+ | region name → `[city_list]` or `None` |
| `GEO_COORDS` | 80+ | suburb name → `{lat, lon, radius_km}` |
| `AGE_ALIASES` | 30+ | age label → `{age_from, age_to}` |
| `TAG_METADATA` | 200+ | slug → `{display, level, domain, aliases}` |

### 7.3 Data Sync

Programme data is sourced from OurKids via a mysqldump file on Google Drive, imported as raw staging tables, then materialized into CSC tables via SQL JOINs.

#### Automated sync (`.github/workflows/sync.yml`)

A GitHub Actions workflow runs **daily 02:00 UTC Mon–Fri** and on demand. The pipeline has five steps:

```
Google Drive dump.sql
  │
  ▼
db/download_from_drive.py       fetch latest dump from Google Drive
  │
  ▼
db/load_raw_tables.py           replay CREATE TABLE + INSERT → ok_* staging tables
  │
  ▼
ok_camps, ok_sessions,          raw OurKids tables (ephemeral, recreated each sync)
ok_sitems, ok_session_date,
ok_addresses, ok_generalInfo,
ok_detailInfo, ok_extra_locations
  │
  ▼
db/materialize_from_raw.py      SQL JOINs → populate CSC tables (camps, programs,
  │                             program_tags with tag_role, program_dates)
  ▼
db/import_camp_tag_overrides.py → db/export_camp_tag_overrides.py → commit if changed
```

**Why Google Drive (not direct DB):** OurKids DBA denied direct MySQL access from GitHub Actions — firewall locked to known IPs. OurKids uploads a mysqldump to a shared Google Drive folder; we pull it via a service account.

Operations performed on every run:

| Operation | Effect |
|-----------|--------|
| Load raw tables | DROP + CREATE `ok_*` staging tables from dump SQL (MyISAM→InnoDB, zero-date mode) |
| Upsert active camps | INSERT new, UPDATE tier/meta/prettyurl for existing from `ok_camps` |
| Sync programs | DELETE + reinsert all programs from `ok_sessions` (all sessions imported, no status filter) |
| Sync program_tags | 4-source tagging: specialty, specialty2, category, activities with **focus level mapping** (`[ID]level` → tag_role), keyword fallback |
| Sync program_traits | `ok_sessions.trait1/trait2` → `program_traits` via `_TRAIT_MAP` with justification text |
| Sync program_dates | Refresh future date rows from `ok_session_date` |
| Sync locations | Multi-location camps via `ok_extra_locations` |
| Deactivate departed | `--deactivate` flag: status=0 for camps in Aiven but not in dump |

#### Field-by-field materialization from `ok_sessions` → `programs`

The following table documents every field materialized from OurKids' `ok_sessions` staging table into the CSC `programs` table. This mapping is the contract between the OurKids data model and CSC — any new platform connecting to CSC must provide equivalent fields.

| ok_sessions column | CSC programs column | Transform | Coverage |
|--------------------|--------------------|-----------|---------:|
| `class_name` | `name` | Direct copy (NOT `name` — OurKids uses `class_name`) | 100% |
| `type` | `type` | Direct copy: `'1'`=Day, `'2'`=Overnight, `'4'`=Virtual, comma-separated for multiple | 100% |
| `gender` | `gender` | `_GENDER_MAP`: OurKids `0=unset,1=Coed,2=Girls,3=Boys` → CSC `0=Coed,1=Boys,2=Girls` | 98% |
| `age_from` / `age_to` | `age_from` / `age_to` | Direct copy | 100% |
| `cost_from` / `cost_to` | `cost_from` / `cost_to` | Direct copy | 97% |
| `start` / `end` | `start_date` / `end_date` | Rename; zero dates (`0000-00-00`) → NULL | 98% |
| `mini_description` | `mini_description` | Truncated to 500 chars | 100% |
| `description` | `description` | Direct copy (HTML text, full programme description) | 93% |
| `isspecialneeds` | `is_special_needs` | `'1'` → 1, else 0 | 100% |
| `isvirtual` | `is_virtual` | `1/'1'` → 1, else 0 | 100% |
| `isfamily` | `is_family` | `1/'1'` → 1, else 0 | 3% |
| `before_care` | `before_care` | `1/'1'` → 1, else 0 | 14% |
| `after_care` | `after_care` | `1/'1'` → 1, else 0 | 15% |
| `language_immersion` | `language_immersion` | Decoded from sitem ID encoding (e.g. `'193+283'` → `'French'`) via `_LANG_SITEMS`. Only non-English languages stored. | 2.5% raw → 24 programmes |

#### Tag resolution pipeline

`ok_sessions` provides four tag sources, resolved in priority order:

```
ok_sessions.specialty     → ok_sitems.item → WEBITEMS_TO_SLUG → program_tags (tag_role='specialty')
ok_sessions.category      → ok_sitems.item → WEBITEMS_TO_SLUG → program_tags (tag_role='category')
ok_sessions.specialty2    → ok_sitems.item → WEBITEMS_TO_SLUG → program_tags (tag_role='category')
ok_sessions.activities    → [sitem_id]focus_level → tag_role mapping → program_tags
                            focus_level: 3=intense→specialty, 2=instructional→category, 1=recreational→activity
```

`specialty2` was added in March 2026 — a second specialty sitem declared by 22% of sessions. It adds ~500 additional tags, primarily in STEM, arts-crafts, technology, and nature categories.

Keyword inference (`infer_tags()`) is the fallback for sessions with no sitems data.

All tag sources write to `program_tags` with a `source` column: `ourkids` (from sitems), `scraper` (from camps.ca pages), `manual`. The 20K-floor safety gate in `materialize_from_raw.py` aborts if total tag count drops below 20,000.

#### Trait materialization

`ok_sessions.trait1` and `trait2` are OurKids trait IDs (1–12) that identify character development outcomes the camp associates with each programme. These map to the CSC `traits` table (IDs 10–22) via `_TRAIT_MAP`:

| OurKids ID | Trait | CSC ID |
|:---:|-------|:---:|
| 1 | Responsibility | 15 |
| 2 | Independence | 14 |
| 3 | Teamwork | 10 |
| 4 | Courage | 13 |
| 5 | Resilience | 11 |
| 6 | Interpersonal Skills | 16 |
| 7 | Curiosity | 12 |
| 8 | Creativity | 17 |
| 9 | Physicality | 18 |
| 10 | Generosity | 19 |
| 11 | Tolerance | 20 |
| 12 | Religious Faith | 22 |

Each trait comes with a `justification` field (from `ok_sessions.justification1/justification2`) — a camp-authored explanation of how the programme develops that trait (e.g., *"Campers learn the art of group living and independent problem-solving"*). Stub justifications (`.` or empty) are stored as NULL.

**Coverage:** ~3,999 programme-trait assignments across 30% of active sessions. Most common: Creativity (847), Curiosity (605), Interpersonal Skills (603).

#### Language immersion decoding

`ok_sessions.language_immersion` stores encoded sitem ID pairs (e.g., `'193+283'` = French + Immersion, `'199+284'` = English + ESL). The `_LANG_SITEMS` map decodes the language component:

| Sitem ID | Language |
|:---:|----------|
| 192 | Mandarin |
| 193 | French |
| 198 | Spanish |
| 199 | English |
| 262 | German |
| 283 | (Immersion modifier) |
| 284 | (Second-language support modifier) |

Only non-English languages are stored in `programs.language_immersion`. Result: 20 French, 2 Spanish, 2 German programmes. The `language-instruction` activity tag provides broader coverage (308 programmes) and is the primary search mechanism for language queries.

**Gender mapping:** OurKids `0=unset, 1=Coed, 2=Girls, 3=Boys` → CSC `0=Coed, 1=Boys, 2=Girls` via `_GENDER_MAP`. The old regex ETL accidentally filtered by the gender field (position 7), dropping all non-coed sessions.

#### Adapting to other OurKids platforms

The materialization pipeline is designed to be reusable for other verticals OurKids manages (e.g., tutoring, private schools). The key integration points:

1. **`load_raw_tables.py`** — platform-agnostic; imports any mysqldump as `ok_*` staging tables. No field assumptions.
2. **`materialize_from_raw.py`** — platform-specific; the field mapping table above is the contract. A new platform needs:
   - A session/programme table with at minimum: name, type, age range, cost, dates, description
   - A sitems/taxonomy table for tag resolution (or equivalent tagging system)
   - The `WEBITEMS_TO_SLUG` bridge mapping platform-specific activity IDs → CSC activity tag slugs
   - Gender, trait, and language mappings if the platform uses different encoding schemes
3. **`_GENDER_MAP`, `_TRAIT_MAP`, `_LANG_SITEMS`** — encoding-specific lookup tables. Each platform may use different integer codes for the same concepts. These maps must be verified against real data (e.g., find a known boys-only listing and confirm its raw gender code).
4. **`WEBITEMS_TO_SLUG`** in `tag_from_campsca_pages.py` — bridges platform-specific sitem IDs to CSC's unified tag slugs. Currently 188 mappings for camps. A new platform would need its own bridge table or extend the existing one.
5. **Safety gates** — the 20K-floor tag count check prevents bulk data corruption. Adjust the threshold per platform based on expected tag volume.

**What stays constant across platforms:** The search pipeline (CSSL, CASL, decision matrix, reranker, concierge) is platform-agnostic. It operates on `programs`, `program_tags`, `program_traits`, and `camps` — the canonical CSC schema. Only the materialization layer changes per platform.

**Protected IDs** (never deactivated): `422` Canlan Etobicoke · `529` Canlan Scarborough · `579` Canlan Oakville · `1647` Idea Labs Pickering.

Manual trigger: GitHub repo → Actions tab → "Sync OurKids → Aiven" → Run workflow.

#### Emergency fallback (`db/sync_from_dump.py`)

The legacy regex-based sync script is kept for emergency use. It parses individual fields from dump SQL via regex — less reliable than the raw table import approach but requires no staging tables.

```bash
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions --dry-run
python3 db/sync_from_dump.py --dump /path/to/dump.sql --import-all-sessions \
  --deactivate --skip-ids 422,529,579,1647
```

---

## 8. UI Architecture

### 8.1 Result Card Layout (`ui/results_card.py`)

Each result is rendered as a four-line card:

```
Line 1  Session name         Bold, dark (#2F4F4F) — the specific programme name
Line 2  Camp name            Tier-coloured (gold/silver/bronze) — the camp brand
Line 3  Detail pills         🏕 Type · 👦 Ages · 📍 Location · 💰 Cost · Gender
Line 4  AI rationale         ✨ Why this fits: [Claude-generated blurb]
        ─────────────────────────────────────────────
        [View on camps.ca →]   [Camp Website →]
```

### 8.2 Collapsible Session Expander

When a camp has more than one programme, additional sessions are collapsed beneath the primary card in a `st.expander` labelled "N more sessions at [Camp Name]". Each row shows: session name (tier-coloured), type · ages · cost · date range, and a direct "View →" link.

The expander is always populated with the **full programme catalog** from the database (`_fetch_all_camp_programs`, cached 5 minutes), not just the programmes that survived the reranker's top-N cutoff. This ensures no sessions are hidden from the user.

### 8.3 Chat Interface

- **AI bubble:** Left-aligned, white background, olive avatar circle (🏕)
- **User bubble:** Right-aligned, olive background, "You" avatar circle
- Avatars are anchored at the bottom of each message (`align-self: flex-end`) to create a visual tail-to-avatar connection consistent with messaging conventions

### 8.4 Sidebar Filters

A sticky filter bar renders inside the results area with controls for age range, maximum cost, camp type, and province. Filter values are applied at merge time on top of all intent-parsed values. Sidebar filters always override Claude's extracted parameters.

---

## 9. Confidence Score Reference

### ICS — Intent Confidence Score

Produced by Claude during intent parsing. Reflects how clearly the query mapped to the taxonomy.

| Range | Meaning |
|-------|---------|
| 0.90–1.00 | Clear, unambiguous query with strong taxonomy match |
| 0.70–0.89 | Good query, most parameters clear, minor ambiguity |
| 0.50–0.69 | Partial extraction, key parameters missing or uncertain |
| 0.30–0.49 | Vague query, few parameters extracted |
| 0.10–0.29 | Minimal extractable content |
| 0.00–0.09 | Nothing useful extracted |

Note: `ics = 0.3` is the hardcoded fallback value returned on API error. The session merge rules do not clear stale state on an API-error fallback.

### RCS — Result Confidence Score

Computed by CSSL from the result pool. Reflects how many and how good the matches were.

| Condition | RCS |
|-----------|-----|
| ≥ 20 results | 0.90 |
| 10–19 results | 0.80 |
| 5–9 results | 0.70 |
| 1–4 results | 0.50 |
| 0 results | 0.00 |
| At least one gold camp | +0.05 |
| Tags active + < 3 results | −0.20 (floor 0.30) |
| < 50% age coverage | −0.10 (floor 0.30) |

---

## 10. Observability

### Debug Trace Panel (`core/tracer.py`)

A collapsible developer panel rendered inside the UI records each pipeline stage's inputs and outputs:

| Stage recorded | Key fields |
|---------------|-----------|
| Input | raw_query, input_path, sidebar_filters |
| Fuzzy preprocessor | tag_hints, trait_hints, geo_expansion |
| Intent parser | all IntentResult fields, ics |
| Merged params | full accumulated_params dict |
| Category disambiguator | broad parent detected, child options |
| Cache | hit/miss, result count |
| CSSL | pool_size, results_returned, rcs, sample camps |
| Decision matrix | ics, rcs, route |
| CASL expand | input_tags, expanded_count, combined_count |
| Output | route, final_count, top camps, concierge message preview |

### Interaction Logger (`core/interaction_logger.py`)

Logs each completed search to a DB table for analytics: session ID, raw query, resolved tags, city, result count, RCS, timestamp.

---

## 11. Infrastructure & Deployment

| Component | Technology | Notes |
|-----------|-----------|-------|
| Application server | Streamlit Cloud | Auto-deploys on push to `main` branch |
| Database | Aiven managed MySQL | SSL/TLS connection; CA cert via `DB_SSL_CA_CERT` Streamlit secret |
| LLM API | Anthropic Claude | API key via `ANTHROPIC_API_KEY` Streamlit secret |
| Data sync | GitHub Actions | Runs `db/sync_from_source.py` every 2 hours; also manually triggerable |
| Session storage | Streamlit `session_state` | Server-side, ephemeral, per-user, no external store |
| Semantic cache | `session_state` | Per-session only; cleared on page reload |

### Secrets Reference

Secrets are stored in two places: **Streamlit Cloud** (for the live app) and **GitHub Actions** (for the automated sync). The Aiven DB secrets must be present in both.

| Secret | Streamlit Cloud | GitHub Actions | Purpose |
|--------|:--------------:|:--------------:|---------|
| `ANTHROPIC_API_KEY` | ✓ | — | Claude API authentication |
| `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` | ✓ | ✓ | Aiven MySQL connection |
| `DB_SSL_CA_CERT` | ✓ | ✓ | Aiven CA certificate (PEM string) |
| `SOURCE_DB_HOST` | — | ✓ | OurKids MySQL hostname/IP |
| `SOURCE_DB_PORT` | — | ✓ | OurKids MySQL port (default 3306) |
| `SOURCE_DB_NAME` | — | ✓ | OurKids database name |
| `SOURCE_DB_USER` | — | ✓ | `csc_reader` (read-only) |
| `SOURCE_DB_PASSWORD` | — | ✓ | csc_reader password |
| `ICS_HIGH_THRESHOLD` | ✓ | — | Decision matrix ICS threshold (default `0.70`) |
| `RCS_HIGH_THRESHOLD` | ✓ | — | Decision matrix RCS threshold (default `0.70`) |
| `RERANKER_THRESHOLD` | ✓ | — | Pool size above which reranker fires (default `15`) |
| `DIVERSITY_MAX_PER_CAMP` | ✓ | — | Max programmes per camp before diversity filter (default `2`) |
| `RESULTS_POOL_SIZE` | ✓ | — | CSSL pool limit (default `100`) |

---

## 12. Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| SQL-only retrieval (no vector search) | Deterministic, auditable, zero embedding infrastructure cost. Tag-based matching is semantically meaningful in this domain and sufficient for the query volume. |
| Fuzzy preprocessor before LLM | Eliminates hallucination risk for known high-frequency terms. Zero latency, zero cost. Claude is reserved for genuine ambiguity. |
| VALID_SLUGS guard on intent parser output | Prevents Claude from inventing tag names that silently produce empty results. Strips at parse time, not query time. |
| QueryState with provenance tracking | Enables future features (explanation of why a filter was applied, user-visible session summary, smarter conflict resolution) without changing the merge interface. |
| accumulated_params as derived mirror | Allows the session layer to be refactored independently of CSSL. CSSL receives a flat dict; QueryState can evolve its internal model freely. |
| Gold tier boost applied post-Claude | Keeps Claude's ranking unbiased during the API call. The business boost is a transparent, auditable post-processing step, not baked into the prompt. |
| Full DB catalog in expander | The reranker's top-N cutoff is a display concern, not a data concern. Every session a camp offers is always visible to the user. |
| Affirmative detection bypasses LLM | "Yes" to a geo-broadening suggestion should never trigger a new intent parse. Eliminates a class of regression where Claude re-interprets the word "yes" as a new query. |
