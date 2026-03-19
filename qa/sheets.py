"""
qa/sheets.py
Google Sheets integration for QA Review Agent.
Reads tester findings from Beta1 tab, writes COMMENTS responses to column E.
"""
import json
import os
import sys

import gspread
from google.oauth2 import service_account

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import get_secret
from qa.config import SHEETS_SCOPES, QA_SHEET_ID, QA_TAB_NAME


def _get_credentials() -> service_account.Credentials:
    """Build credentials from GDRIVE_SERVICE_ACCOUNT_JSON secret or local file."""
    # 1. Try env var / Streamlit secret (JSON string)
    sa_json = get_secret("GDRIVE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=SHEETS_SCOPES
        )

    # 2. Try local file (gitignored)
    base = os.path.dirname(os.path.dirname(__file__))
    for candidate in [
        os.path.join(base, "service_account.json"),
        os.path.join(base, "collaterals", "service_account.json"),
    ]:
        if os.path.exists(candidate):
            return service_account.Credentials.from_service_account_file(
                candidate, scopes=SHEETS_SCOPES
            )

    raise RuntimeError(
        "Google service account not found. Either:\n"
        "  - Set GDRIVE_SERVICE_ACCOUNT_JSON env var (JSON string), or\n"
        "  - Place service_account.json in project root (gitignored)"
    )


def get_worksheet(
    sheet_id: str = QA_SHEET_ID, tab_name: str = QA_TAB_NAME
) -> gspread.Worksheet:
    """Open a Google Sheet worksheet by ID and tab name."""
    creds = _get_credentials()
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(sheet_id)
    return spreadsheet.worksheet(tab_name)


def get_all_items(ws: gspread.Worksheet) -> list[dict]:
    """
    Read all rows from the worksheet and return structured dicts.

    Returns list of dicts with keys:
        row (1-indexed), item_id, search_term, chat_response, why_incorrect, comment
    Skips header row (row 1) and rows with no search term in column B.
    """
    all_values = ws.get_all_values()
    items = []
    for i, row in enumerate(all_values):
        if i == 0:
            continue  # skip header
        row_num = i + 1  # 1-indexed
        # Pad short rows
        while len(row) < 5:
            row.append("")
        item_id = row[0].strip()
        search_term = row[1].strip()
        chat_response = row[2].strip()
        why_incorrect = row[3].strip()
        comment = row[4].strip()

        if not search_term:
            continue  # skip pre-numbered but empty rows

        # Skip duplicate header rows (e.g. "Enter Search Term")
        if search_term.lower() == "enter search term" or item_id.lower() == "item":
            continue

        items.append({
            "row": row_num,
            "item_id": item_id,
            "search_term": search_term,
            "chat_response": chat_response,
            "why_incorrect": why_incorrect,
            "comment": comment,
        })
    return items


def get_unreviewed_items(ws: gspread.Worksheet) -> list[dict]:
    """Return only items where column E (comment) is empty."""
    return [item for item in get_all_items(ws) if not item["comment"]]


def write_comment(ws: gspread.Worksheet, row_num: int, comment: str) -> None:
    """Write a comment to column E of the given row."""
    ws.update_cell(row_num, 5, comment)


def get_contact_email(ws: gspread.Worksheet) -> str | None:
    """
    Read contact email from row 1 of the worksheet.
    Checks column B (row 1 is "Contact:" in A, email in B).
    Falls back to checking column A if B is empty.
    """
    try:
        row1 = ws.row_values(1)
        # Check column B first (typical: "Contact:" in A, email in B)
        if len(row1) >= 2 and row1[1] and "@" in row1[1]:
            return row1[1].strip()
        # Fallback: check column A
        if row1 and "@" in row1[0]:
            return row1[0].strip()
        return None
    except Exception:
        return None
