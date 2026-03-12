# CSC Testing

## QA Suite
```bash
# Run full 40-query intent parser QA — must pass 40/40 before any push
pytest tests/test_intent_parser.py -v

# Unit tests (reranker, session manager)
pytest tests/test_reranker.py tests/test_session_manager.py -v
```

The QA suite in `tests/test_intent_parser.py` calls Claude live — requires
`ANTHROPIC_API_KEY` set in environment.

---

## Manual Smoke Tests (after significant changes)
Run these conversation flows in the app to verify end-to-end behaviour:

**Block 1 — Basic search**
1. "hockey camps in Toronto for my 10 year old"
   - Expect: hockey tag, Toronto, age 9–11, results shown

**Block 2 — Geo broadening**
1. "skateboarding camps in Etobicoke for a 10 year old boy"
   - Expect: no results → province-wide suggestion
2. "yes"
   - Expect: province-wide results shown (Leaside Volleyball etc.)
3. "focus on Toronto camps"
   - Expect: Toronto-filtered results including Leaside Volleyball Club

**Block 3 — Gender filter**
1. "all-girls overnight camps in Ontario for teenagers"
   - Expect: only programs with `gender=2` shown; Camp Wenonah NOT in results
2. "is Camp Wenonah all-girls?"
   - Expect: concierge says coed (not a camp-gender-specific search)

**Block 4 — Session refinement**
1. "arts camps in Ottawa"
2. "what about overnight?"
   - Expect: adds overnight filter, keeps Ottawa + arts tags
3. "Start Over" (header button)
   - Expect: full session clear, fresh state

**Block 5 — Surprise Me**
1. Click "✨ Surprise Me" header button
   - Expect: stays in same tab, shows gold-tier camps with "You might also love..." heading
   - Expect: no LLM-generated message, direct results

**Block 6 — Affirmative variations**
1. Search something → get province broadening suggestion
2. "show me the 7 camps" — should act as affirmative

---

## Known Failure Modes to Watch
| Symptom | Likely cause | Fix |
|---|---|---|
| Province-wide loop (keeps asking) | lat/lon not cleared on geo_broaden_province | Check `app.py` affirmative handler |
| "which city works best?" loop | Concierge generating city-picker question | Check concierge system prompt |
| Wrong tags for "my son/daughter" | Intent parser setting gender | Check intent_parser_system_prompt.md |
| Reranker returns no blurbs | Claude JSON parse failure | Check `core/reranker.py` raw_decode |
| Surprise Me opens new tab | Missing `target="_self"` on topbar links | Check `app.py` topbar HTML |

---

## Adding New QA Tests
Edit `tests/qa_queries.py`. Each test case:
```python
{
    "query": "...",
    "expect_tags": ["slug1"],           # exact match
    "expect_tags_include": ["slug1"],   # subset match
    "expect_tags_not": ["slug2"],       # must not appear
    "expect_city": "Toronto",
    "expect_age_from": 9,
    "expect_gender": "Girls",          # only for explicit gender camp requests
    "note": "Why this test exists"
}
```
