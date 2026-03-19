"""
qa/config.py
QA Review Agent configuration — secrets, sheet IDs, scopes.
"""
import os
import sys

# Add project root to path so we can import config.get_secret
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import get_secret

# Google Sheets
QA_SHEET_ID = get_secret(
    "QA_SHEET_ID", "1wygU8YeqvqXOoJonU5iWguFjVu_MOJ7Q4NzW-xtrXBQ"
)
QA_TAB_NAME = "Beta1"

# Google API scopes needed for Sheets read/write
SHEETS_SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Claude model for response generation
RESPONDER_MODEL = "claude-haiku-4-5-20251001"
