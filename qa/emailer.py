"""
qa/emailer.py
Gmail API notifications for QA review results.
Uses the existing Google service account with domain-wide delegation.
Gracefully degrades if Gmail API is not configured.
"""
import base64
import json
import logging
import os
import sys
from email.mime.text import MIMEText

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config import get_secret

logger = logging.getLogger(__name__)

# Gmail API scopes — requires domain-wide delegation in Google Workspace admin
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SENDER_EMAIL = get_secret("QA_SENDER_EMAIL", "")


def _get_gmail_service(sender_email: str):
    """Build Gmail API service with delegated credentials."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    sa_json = get_secret("GDRIVE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        return None

    try:
        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=GMAIL_SCOPES
        )
        # Domain-wide delegation: impersonate the sender
        delegated = creds.with_subject(sender_email)
        return build("gmail", "v1", credentials=delegated, cache_discovery=False)
    except Exception as e:
        logger.warning("Failed to build Gmail service: %s", e)
        return None


def send_notification(
    to_email: str, item_id: str, summary: str, sender_email: str = ""
) -> bool:
    """
    Send a QA review notification email.

    Returns True if sent, False if skipped/failed.
    Gracefully degrades if Gmail is not configured.
    """
    sender = sender_email or SENDER_EMAIL
    if not sender:
        logger.info("No sender email configured — skipping email notification")
        return False

    if not to_email:
        logger.info("No recipient email — skipping notification for item %s", item_id)
        return False

    service = _get_gmail_service(sender)
    if not service:
        logger.warning(
            "Gmail API not available — skipping email for item %s. "
            "Ensure domain-wide delegation is configured for the service account.",
            item_id,
        )
        return False

    try:
        message = MIMEText(
            f"QA Review Agent has reviewed item #{item_id}:\n\n{summary}\n\n"
            f"View the full spreadsheet for details.",
            "plain",
        )
        message["to"] = to_email
        message["from"] = sender
        message["subject"] = f"CSC QA Review — Item #{item_id}"

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()

        logger.info("Email sent to %s for item %s", to_email, item_id)
        return True

    except Exception as e:
        logger.warning("Failed to send email for item %s: %s", item_id, e)
        return False
