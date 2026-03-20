"""
qa/responder.py
Generates human-readable COMMENTS responses for QA tester findings.
Uses Claude Haiku for formatting; falls back to template if API unavailable.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qa.config import RESPONDER_MODEL
from qa.validator import ValidationResult


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("[%Y-%m-%d %H:%M UTC]")


def _template_response(entry: dict, validation: ValidationResult) -> str:
    """Generate a response using templates (no LLM needed)."""
    ts = _timestamp()
    tags_str = ", ".join(validation.intent_tags) if validation.intent_tags else "none detected"

    if validation.issue_type == "UI_UX":
        return f"{ts} Status: UI Feedback Noted. {validation.details} We'll review this with the design team."

    if validation.issue_type == "LINK_ISSUE":
        return f"{ts} Status: Link Issue Confirmed. {validation.details} This will be fixed."

    if validation.issue_type == "EXPECTED_BEHAVIOR" and not validation.is_valid_issue:
        return (
            f"{ts} Status: Working as Expected. "
            f"Your search returned {validation.result_count} results. "
            f"The system matched on: {tags_str}. "
            f"If you expected a specific camp that's missing, please let us know which one."
        )

    # Valid issue — include root cause and what's next
    parts = [ts]

    if validation.is_valid_issue:
        parts.append("Status: Issue Confirmed.")
    else:
        parts.append("Status: Investigating.")

    if validation.root_cause:
        # Strip internal jargon from root cause
        cause = validation.root_cause
        for term in ["CSSL", "CASL", "ICS", "RCS", "FUZZY_ALIAS"]:
            cause = cause.replace(term, "search system")
        parts.append(cause)

    parts.append(
        f"The search returned {validation.result_count} results "
        f"using tags: {tags_str}."
    )

    if validation.missing_camps:
        mc = ", ".join(validation.missing_camps[:3])
        suffix = f" (+{len(validation.missing_camps) - 3} more)" if len(validation.missing_camps) > 3 else ""
        parts.append(f"Missing camps: {mc}{suffix}.")

    parts.append("We're looking into this.")

    return " ".join(parts)


def generate_response(
    entry: dict,
    validation: ValidationResult,
    conversation_history: str = "",
) -> str:
    """
    Generate a COMMENTS response for a QA finding.

    Args:
        entry: The tester's original finding
        validation: Pipeline validation results
        conversation_history: Existing threaded conversation in column E (for follow-ups)

    Tries Claude Haiku for a polished response; falls back to template.
    """
    # For simple cases, use templates directly (saves API calls)
    if validation.issue_type in ("UI_UX", "LINK_ISSUE") and not conversation_history:
        return _template_response(entry, validation)

    # Try LLM for richer responses
    try:
        from core.llm_client import get_client

        client = get_client()

        # Build conversation context for follow-ups
        history_block = ""
        if conversation_history:
            history_block = f"""
CONVERSATION SO FAR (in column E):
{conversation_history}

This is a FOLLOW-UP. The tester has replied to a previous agent response.
Address their specific reply directly. Do not repeat information already covered.
"""

        prompt = f"""You are the QA Review Bot for camps.ca — a camp search engine.
A tester submitted a finding. Write a response for the COMMENTS column.

Your personality: witty, slightly cheeky, but always helpful. Think friendly coworker
who's great at explaining things — not a corporate robot. Light roasting is encouraged
when the system did something dumb, or when the tester's finding is actually correct
behavior. Keep it fun so nobody falls asleep reading QA comments.

TESTER FINDING:
- Search term: "{entry.get('search_term', '')}"
- What they saw: {entry.get('chat_response', '') or '(not provided)'}
- Why they think it's wrong: {entry.get('why_incorrect', '') or '(not provided)'}
{history_block}
VALIDATION RESULTS:
- Issue type: {validation.issue_type}
- Valid issue: {validation.is_valid_issue}
- Root cause: {validation.root_cause or 'N/A'}
- Pipeline results: {validation.result_count} results (ICS={validation.intent_ics:.2f}, RCS={validation.rcs:.2f})
- Tags resolved: {', '.join(validation.intent_tags) or 'none'}
- Missing camps: {', '.join(validation.missing_camps[:5]) or 'none'}
- Details: {validation.details}

RESPONSE FORMAT — always include:

**Status:** Issue Confirmed / Working as Expected / Need More Info / Fixed
Then 2-3 sentences: what happened, why, and what's next.

Example for a valid issue:
"Status: Issue Confirmed. Good catch! Searching 'fashion camps toronto' only returned 2 camps because we were being way too picky about what counts as a 'fashion camp.' Turns out 5 other camps genuinely teach fashion — we were just ignoring them. Fixed now, give it another spin."

Example for expected behavior:
"Status: Working as Expected. I know 15 hockey camps in Ottawa feels like a lot, but hear me out — they all genuinely offer hockey programs. The search nailed both the activity and location. If there's a specific camp you expected to see, drop the name and I'll hunt it down."

Example for a follow-up:
"Status: Fixed. You were right the first time! The missing camps are now showing up after we tweaked the tag matching. Thanks for not letting this one slide."

Rules:
- Keep under 150 words
- Lead with the status — testers want to know immediately if they found something real
- Explain the "why" in plain English — no developer jargon
- Never use acronyms like ICS, RCS, CSSL, or CASL
- If camps are missing, name them (up to 3)
- Acknowledge real issues with humor ("yep, that's on us")
- When behavior is correct, explain it warmly — don't be dismissive
- Match the tester's energy — if they're frustrated, be empathetic first, witty second
- It's OK to compliment a good catch

Respond with ONLY the comment text (no quotes, no prefix)."""

        response = client.messages.create(
            model=RESPONDER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=300,
        )
        comment = response.content[0].text.strip()
        return f"{_timestamp()} {comment}"

    except Exception:
        # Fallback to template
        return _template_response(entry, validation)
