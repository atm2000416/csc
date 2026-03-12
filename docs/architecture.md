# CSC Architecture

## Pipeline (per user turn)

```
User query
  │
  ▼
Fuzzy Preprocessor          keyword → slug hints, geo coords, "near me" flag
  │
  ▼
Intent Parser (Claude Haiku) system prompt + session context + fuzzy hints → IntentResult
  │
  ▼
Session Merge               merge_intent() accumulates params across turns
  │
  ▼
Semantic Cache              param-keyed; skip pipeline on hit
  │
  ▼
CSSL (MySQL)                structured SQL → result pool (up to 100)
  │
  ▼
Decision Matrix             ICS × RCS → 4 routes (see below)
  │
  ├─ SHOW_RESULTS      → Diversity Filter → Reranker → display_results()
  ├─ BROADEN_SEARCH    → Zero Results Advisor → suggestion bubble
  ├─ SHOW_AND_CLARIFY  → show results + soft clarifying question
  └─ CLARIFY_LOOP      → clarification widget, no results shown
  │
  ▼
Concierge Response (Claude Sonnet 4.6)   2-3 sentence narrative + follow-up
```

---

## IntentResult Fields
| Field | Type | Notes |
|---|---|---|
| `tags` | list[str] | activity tag slugs |
| `exclude_tags` | list[str] | negative filter slugs |
| `age_from` / `age_to` | int | child's age range |
| `city` | str | single city |
| `cities` | list[str] | multi-city search |
| `province` | str | e.g. "Ontario" |
| `lat` / `lon` / `radius_km` | float | geo proximity search |
| `type` | str | "Day" or "Overnight" |
| `gender` | str | "Boys"/"Girls"/"Coed" — only when explicitly requested |
| `cost_max` | int | CAD |
| `traits` | list[str] | e.g. "resilience", "interpersonal-skills" |
| `is_special_needs` / `is_virtual` | bool | |
| `language_immersion` | str | e.g. "French" |
| `ics` | float | Intent Confidence Score 0–1 |
| `recognized` | bool | False if query couldn't be mapped |
| `needs_geolocation` | bool | "near me" detected |
| `clear_activity` | bool | signals fresh broad search |

---

## Decision Matrix (ICS × RCS)

```
              RCS ≥ 0.70        RCS < 0.70
ICS ≥ 0.70  SHOW_RESULTS      BROADEN_SEARCH
ICS < 0.70  SHOW_AND_CLARIFY  CLARIFY_LOOP
```

Thresholds configurable via `ICS_HIGH_THRESHOLD` / `RCS_HIGH_THRESHOLD` secrets.

---

## Session Merge Rules (`core/session_manager.py`)
- New non-null values override accumulated params
- `recognized=False` + `ics > 0.3` → clears stale tags/exclude_tags/type
- `clear_activity=True` → clears tags, exclude_tags, type, dates
- Completely different activity (zero tag overlap) → clears stale exclude_tags
- New city named but no coords → clears accumulated lat/lon/radius_km
- Province-only (no city/coords) → clears all location specifics

---

## Pending Suggestion Flow
Zero Results Advisor stores a `pending_suggestion` dict in session:
```python
{"type": "geo_broaden_province", "to_province": "Ontario"}
{"type": "geo_broaden",          "to_city": "Barrie", "to_province": "Ontario"}
```
On next turn, `is_affirmative(user_input)` checks for yes/sure/show/etc.
Affirmative path clears the suggestion and re-runs CSSL with updated params.
For `geo_broaden_province`: clears ALL of city, cities, lat, lon, radius_km, needs_geolocation.

---

## CASL (Semantic Expansion)
`core/casl.py` — fires when CSSL returns 0 results after a direct tag search.
Reads `related_ids` (comma-separated IDs) from `activity_tags` for each slug,
resolves them to slugs, and re-runs CSSL with the expanded tag set.

---

## Category Disambiguator
When a query maps to a broad parent tag (e.g. "sport-multi"), the disambiguator
offers child categories as clickable buttons before running CSSL.
Each broad parent is only offered once per session.

---

## Surprise Me (`ui/surprise_me.py`)
Bypasses LLM pipeline entirely:
1. `pick_tag_with_camps()` — weighted random tag with ≥3 active DB camps
2. `get_surprise_results()` — direct CSSL query, tier-sorted
3. Results stored in `_surprise_direct_results`, triggers `st.rerun()`
4. Triggered via `?action=surprise` header button (HTML link → query param)
