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
    """Build credentials from GDRIVE_SERVICE_ACCOUNT_JSON secret."""
    sa_json = get_secret("GDRIVE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        raise RuntimeError(
            "GDRIVE_SERVICE_ACCOUNT_JSON not set. "
            "Set it in .streamlit/secrets.toml or as an env var."
        )
    info = json.loads(sa_json)
    return service_account.Credentials.from_service_account_info(
        info, scopes=SHEETS_SCOPES
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


def get_tester_email(sheet_id: str, tab_name: str) -> str | None:
    """
    Read tester email from row 1 of a per-tester tab.
    Returns None if tab doesn't exist or row 1 is empty.
    """
    try:
        creds = _get_credentials()
        gc = gspread.authorize(creds)
        spreadsheet = gc.open_by_key(sheet_id)
        ws = spreadsheet.worksheet(tab_name)
        val = ws.cell(1, 1).value
        return val.strip() if val else None
    except Exception:
        return None
