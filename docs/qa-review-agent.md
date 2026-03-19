# QA Review Agent

Automated validation of tester feedback from the QA spreadsheet.

---

## What It Does

The QA Review Agent reads tester findings from a shared Google Sheet, reproduces each search through the live CSC pipeline, compares results against camps.ca category pages, classifies the issue, generates a response, and writes it back to the sheet.

**In plain English:** a tester types "soccer camps mississauga" and says "results are wrong." The agent runs that same search against the live database, checks what camps.ca shows for soccer, figures out what's missing and why, then writes a diagnosis back to the spreadsheet.

---

## Spreadsheet Layout

**Sheet ID:** `1wygU8YeqvqXOoJonU5iWguFjVu_MOJ7Q4NzW-xtrXBQ`
**Tab:** Beta1

| Row | Content |
|-----|---------|
| 1 | Contact email (col A = "Contact:", col B = email address) |
| 2 | Column headers |
| 3+ | Tester entries |

| Column | Header | Purpose |
|--------|--------|---------|
| A | Item | Item number |
| B | Enter Search Term | What the tester searched for |
| C | What was the Chat response | What CSC returned |
| D | Why was it incorrect | Tester's explanation of the problem |
| E | Comments | **Agent writes here** — automated response |

The agent skips rows where column B is empty (pre-numbered but unused) and rows where column E already has a response (unless `--force` is used).

---

## How to Run

### Prerequisites

1. **Google Sheet shared** with the service account email (the one in `GDRIVE_SERVICE_ACCOUNT_JSON`)
2. **Google Sheets API enabled** on the Google Cloud project ([console link](https://console.developers.google.com/apis/api/sheets.googleapis.com/overview))
3. **Credentials** — one of:
   - `GDRIVE_SERVICE_ACCOUNT_JSON` env var (JSON string) — used in GitHub Actions
   - `service_account.json` file in project root (gitignored) — used for local dev
4. **Database access** — DB_HOST/PORT/NAME/USER/PASSWORD env vars (or .streamlit/secrets.toml)
5. **Anthropic API key** — `ANTHROPIC_API_KEY` env var

### Local (command line)

```bash
# Export DB credentials (from secrets.toml)
eval "$(grep '^DB_HOST\|^DB_PORT\|^DB_NAME\|^DB_USER\|^DB_PASSWORD' .streamlit/secrets.toml \
  | sed 's/ *= */=/' | sed 's/^/export /')"

# Source API key (if in bash_profile)
source ~/.bash_profile

# Review all unreviewed items
PYTHONPATH=. python3 -m qa.review_agent

# Dry run — validate only, don't write to sheet
PYTHONPATH=. python3 -m qa.review_agent --dry-run

# Review a specific item
PYTHONPATH=. python3 -m qa.review_agent --item 3

# Re-review everything (overwrite existing comments)
PYTHONPATH=. python3 -m qa.review_agent --force

# Dry run a single item
PYTHONPATH=. python3 -m qa.review_agent --item 1 --dry-run
```

### GitHub Actions

Go to **Actions > QA Review Agent > Run workflow**. Optional inputs:

| Input | Default | Description |
|-------|---------|-------------|
| item | (blank) | Specific item ID, or blank for all unreviewed |
| dry_run | false | Validate only, no sheet writes |
| force | false | Re-review items that already have comments |

---

## What the Agent Does for Each Item

```
1. Read tester entry (search term, complaint, expected results)
      |
2. Strip prefixes ("SEARCH: soccer" → "soccer")
      |
3. Is it UI/UX feedback? (starts with "UI:", mentions accordion/buttons/layout)
      |── Yes → write "UI feedback noted for review" → done
      |
4. Run fuzzy preprocessor → tag hints
      |
5. Run intent parser (Claude Haiku) → tags, location, age, type
      |
6. Run CSSL query → results + RCS score
      |
7. Extract camps.ca URL from tester complaint (if any)
      |── e.g. "camps.ca/animal-camps.php" → slug "animals"
      |── Look up which camps are tagged with that slug
      |── Compare: expected camps vs. actual pipeline results
      |
8. Classify the issue:
      |── SEARCH_QUALITY  — wrong/missing results
      |── DATA_QUALITY    — tag coverage gaps
      |── UI_UX           — display/interaction feedback
      |── LINK_ISSUE      — broken URLs
      |── EXPECTED_BEHAVIOR — system working correctly
      |
9. Generate response (Claude Haiku or template fallback)
      |
10. Write response to column E with timestamp
```

---

## Issue Classifications

| Type | Meaning | Example |
|------|---------|---------|
| **SEARCH_QUALITY** | Pipeline returns wrong or missing results | "soccer camps" returns 14 but camps.ca shows 200 |
| **DATA_QUALITY** | Tag gaps — some camps not tagged properly | 5 cheerleading camps on camps.ca page missing from program_tags |
| **UI_UX** | Display or interaction feedback, not a search issue | "Accordion links should go to session profile" |
| **LINK_ISSUE** | Broken camps.ca URLs | Link goes to homepage instead of camp profile |
| **EXPECTED_BEHAVIOR** | System is working correctly, tester expectation mismatch | Search returns good results but tester expected a different set |

---

## Response Categories

The agent writes one of these response types to column E:

- **Issue confirmed:** "Valid issue. [root cause]. [what needs fixing]."
- **Expected behavior:** "Working as designed. [explanation with numbers]."
- **Clarification needed:** "Need more details: [specific question]."
- **Already fixed:** "Resolved in recent update. Please re-test."
- **UI/UX noted:** "UI feedback logged for review."

Every response includes a UTC timestamp prefix: `[2026-03-19 19:10 UTC]`

---

## File Structure

```
qa/
  __init__.py          # Package marker
  config.py            # Sheet ID, API scopes, model config
  sheets.py            # Google Sheets read/write (gspread)
  validator.py         # Reproduce searches, cross-reference camps.ca, classify
  responder.py         # Generate response text (Claude Haiku + template fallback)
  emailer.py           # Email notifications (not yet configured)
  review_agent.py      # CLI entry point + orchestrator
```

---

## Email Notifications (Not Yet Active)

The agent reads a contact email from row 1 of the Beta1 tab and can send per-item email notifications. This requires either:

- **Gmail SMTP + App Password** (works with @gmail.com) — preferred, simple setup
- **Gmail API + Workspace delegation** (requires paid Google Workspace)
- **Slack webhook** — alternative if team uses Slack

Currently the agent logs "No sender email configured — skipping" and the sheet write is the only output. Email setup is documented separately when ready.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `GDRIVE_SERVICE_ACCOUNT_JSON not set` | Export the env var or place `service_account.json` in project root |
| `Google Sheets API has not been used in project` | Enable Sheets API in Google Cloud Console |
| `PermissionError` on sheet access | Share the Google Sheet with the service account email |
| `Connection refused` on DB | Export DB_HOST/PORT/NAME/USER/PASSWORD from secrets.toml |
| All items classified as UI_UX | Check if tester is putting feedback in the search term column |
| Zero results for a valid search | Check FUZZY_ALIASES and program_tags for the relevant slug |

---

## Adding New QA Tabs

The agent currently processes the **Beta1** tab only. To add per-tester tabs:

1. Each tester tab should have the same column structure (A–E)
2. Row 1 should contain the tester's contact email
3. Update `QA_TAB_NAME` in `qa/config.py` or add a `--tab` CLI flag

---

## Dependencies

- `gspread>=6.0.0` (added to requirements.txt)
- `google-auth` (already installed)
- All existing CSC dependencies (anthropic, mysql-connector-python)
