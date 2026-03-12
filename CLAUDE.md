# CSC — Camp Search Concierge
OurKids.net natural-language camp finder. Streamlit + MySQL + Claude AI.
Deploys automatically to Streamlit Cloud on every push to `main`.

---

## Tech Stack
| Layer | Technology |
|---|---|
| UI | Streamlit ≥1.35 |
| DB | Aiven MySQL 8.0 (SSL) |
| AI | Claude Haiku 4.5 (intent, rerank) + Claude Sonnet 4.6 (concierge) |
| Language | Python 3.11+ |

---

## Key Files
```
app.py                          # Streamlit entry point + pipeline orchestration
config.py                       # get_secret() — reads Streamlit secrets or .env
intent_parser_system_prompt.md  # Claude system prompt (edit to tune extraction)

core/
  llm_client.py         # get_client() → anthropic.Anthropic
  intent_parser.py      # Claude Haiku → IntentResult dataclass
  fuzzy_preprocessor.py # keyword→slug hints (no API call)
  session_manager.py    # merge_intent(), accumulated_params
  cssl.py               # MySQL search query builder
  casl.py               # semantic tag expansion via related_ids
  reranker.py           # Claude Haiku reranker + blurb writer
  concierge_response.py # Claude Sonnet 4.6 narrative generator
  decision_matrix.py    # ICS × RCS routing (4 routes)
  zero_results_advisor.py # proximity diagnostic when RCS=0
  diversity_filter.py   # max N results per camp
  semantic_cache.py     # param-keyed result cache

db/
  connection.py         # MySQL connection pool
  sync_from_dump.py     # sync new DB from legacy OurKids dump

ui/
  results_card.py       # camp result card renderer
  filter_sidebar.py     # age / type / cost / location filters
  surprise_me.py        # Surprise Me feature (direct CSSL, no LLM)
  clarification_widget.py

tests/
  test_intent_parser.py # 40-query QA suite — must stay 40/40
  qa_queries.py         # test case definitions
```

---

## Conventions
- `get_connection()` returns pooled MySQL conn — always close cursor AND conn
- `cursor(dictionary=True)` — rows as dicts
- SQL placeholders: `%(name)s` style (not `%s`) when passing dicts
- `resolve_tag_ids(slugs, cursor)` in `cssl.py` converts slug → DB IDs
- Session: `st.session_state.session_context["accumulated_params"]`
- **gender** field: only set when user explicitly asks for gender-specific camp; "my son/daughter" alone → `null`
- **status=1** in legacy dump = active camp (field 6); field 17 = `showAnalytics` (not membership)

---

## Dev Workflow
```bash
# Run locally
streamlit run app.py

# Run QA suite (must pass 40/40 before pushing)
pytest tests/test_intent_parser.py -v

# Deploy — auto-deploys on push
git push origin main

# Sync from a new OurKids dump
python3 db/sync_from_dump.py --dump /path/to/dump.sql --dry-run
python3 db/sync_from_dump.py --dump /path/to/dump.sql
```

---

## Secrets (Streamlit Cloud)
`ANTHROPIC_API_KEY`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
`DB_SSL_CA_CERT` (base64 CA cert), `RESULTS_POOL_SIZE`, `RERANKER_THRESHOLD`,
`DIVERSITY_MAX_PER_CAMP`

---

## Further Reading
| Topic | File |
|---|---|
| Pipeline & routing logic | [docs/architecture.md](docs/architecture.md) |
| DB schema & sync workflow | [docs/database.md](docs/database.md) |
| Soft Sage design system | [docs/design-system.md](docs/design-system.md) |
| QA & testing procedures | [docs/testing.md](docs/testing.md) |
