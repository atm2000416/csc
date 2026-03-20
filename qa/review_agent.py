#!/usr/bin/env python3
"""
qa/review_agent.py
QA Review Agent — automated validation of tester findings from Google Sheets.

Usage:
    python -m qa.review_agent                    # Review all unreviewed items
    python -m qa.review_agent --item 3           # Review specific item
    python -m qa.review_agent --dry-run          # Validate without writing to sheet
    python -m qa.review_agent --force            # Re-review all items (ignore existing comments)
    python -m qa.review_agent --item 1 --test-email user@example.com
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qa.config import QA_SHEET_ID, QA_TAB_NAME
from qa.sheets import get_worksheet, get_all_items, get_unreviewed_items, append_comment, write_comment, get_contact_email
from qa.validator import validate_finding
from qa.responder import generate_response
from qa.emailer import send_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("qa.review_agent")


def run(
    item_filter: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    test_email: str | None = None,
    tab: str | None = None,
) -> list[dict]:
    """
    Main review loop.

    Args:
        item_filter: Specific item ID to review (None = all)
        dry_run: If True, validate but don't write to sheet
        force: If True, re-review items that already have comments
        test_email: Override email for testing
        tab: Specific tab name (default: Beta1)

    Returns:
        List of {item_id, issue_type, response} dicts for processed items
    """
    tab_name = tab or QA_TAB_NAME
    logger.info("Connecting to Google Sheets (tab: %s)...", tab_name)
    ws = get_worksheet(QA_SHEET_ID, tab_name)

    if force:
        items = get_all_items(ws)
    else:
        items = get_unreviewed_items(ws)

    if item_filter:
        items = [i for i in items if str(i["item_id"]) == str(item_filter)]
        if not items:
            logger.warning("Item %s not found or has no search term", item_filter)
            return []

    # Read contact email from tab
    contact_email = get_contact_email(ws)
    if contact_email:
        logger.info("Contact email: %s", contact_email)

    logger.info("Found %d item(s) to review", len(items))
    processed = []

    for item in items:
        item_id = item["item_id"]
        search_term = item["search_term"]
        is_followup = item.get("is_followup", False)
        existing_comment = item.get("comment", "")

        if is_followup:
            logger.info("--- Item %s: '%s' [FOLLOW-UP] ---", item_id, search_term)
        else:
            logger.info("--- Item %s: '%s' ---", item_id, search_term)

        # Validate
        try:
            validation = validate_finding(item)
        except Exception as e:
            logger.error("Validation failed for item %s: %s", item_id, e)
            continue

        logger.info(
            "  Type: %s | Valid: %s | Results: %d | ICS: %.2f | RCS: %.2f",
            validation.issue_type,
            validation.is_valid_issue,
            validation.result_count,
            validation.intent_ics,
            validation.rcs,
        )
        if validation.root_cause:
            logger.info("  Root cause: %s", validation.root_cause)

        # Generate response (pass conversation history for follow-ups)
        try:
            response = generate_response(
                item,
                validation,
                conversation_history=existing_comment if is_followup else "",
            )
        except Exception as e:
            logger.error("Response generation failed for item %s: %s", item_id, e)
            continue

        logger.info("  Response: %s", response[:120] + "..." if len(response) > 120 else response)

        # Write to sheet — append for threaded conversation
        if not dry_run:
            try:
                append_comment(ws, item["row"], response, existing=existing_comment)
                logger.info("  Written to row %d, column E", item["row"])
            except Exception as e:
                logger.error("Failed to write comment for item %s: %s", item_id, e)
        else:
            logger.info("  [DRY RUN] Would write to row %d, column E", item["row"])

        # Email notification
        email = test_email or contact_email
        if not dry_run and email:
            send_notification(email, item_id, response)

        processed.append({
            "item_id": item_id,
            "issue_type": validation.issue_type,
            "is_valid_issue": validation.is_valid_issue,
            "is_followup": is_followup,
            "response": response,
        })

    logger.info("Processed %d item(s)", len(processed))
    return processed


def main():
    parser = argparse.ArgumentParser(
        description="QA Review Agent — validate tester findings"
    )
    parser.add_argument(
        "--item", type=str, default=None, help="Review a specific item ID"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without writing to Google Sheets",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-review all items (ignore existing comments)",
    )
    parser.add_argument(
        "--tab",
        type=str,
        default=None,
        help="Tab name to process (default: Beta1). Use --tab ALL for all tester tabs.",
    )
    parser.add_argument(
        "--test-email",
        type=str,
        default=None,
        help="Send test notification to this email",
    )
    args = parser.parse_args()

    # Process single tab or all tester tabs
    ALL_TABS = ["Beta1", "JIM", "DEBBIE", "ANJELICA", "MICHAEL"]

    if args.tab and args.tab.upper() == "ALL":
        tabs_to_run = ALL_TABS
    else:
        tabs_to_run = [args.tab] if args.tab else [QA_TAB_NAME]

    results = []
    for tab in tabs_to_run:
        tab_results = run(
            item_filter=args.item,
            dry_run=args.dry_run,
            force=args.force,
            test_email=args.test_email,
            tab=tab,
        )
        for r in tab_results:
            r["tab"] = tab
        results.extend(tab_results)

    # Summary
    if results:
        print(f"\n{'='*60}")
        print(f"QA Review Summary: {len(results)} item(s) processed")
        print(f"{'='*60}")
        for r in results:
            status = "VALID" if r["is_valid_issue"] else "OK"
            followup = " (follow-up)" if r.get("is_followup") else ""
            tab_label = f"[{r.get('tab', '')}] " if r.get("tab") else ""
            print(f"  {tab_label}Item {r['item_id']}: [{status}] {r['issue_type']}{followup}")
        print()


if __name__ == "__main__":
    main()
