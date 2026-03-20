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

        prompt = f"""You are a QA response bot for a camp search engine (camps.ca).
A tester submitted a finding. Generate a clear, helpful response for the COMMENTS column.
The tester is NOT a developer — explain things in plain language they can understand.

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

RESPONSE FORMAT — use this structure:

**Status:** One of: Issue Confirmed / Working as Expected / Need More Info / Fixed
**What happened:** 1-2 sentences explaining what the search did and why.
**What's next:** What we're doing about it (if issue), or why the results are correct (if expected).

Example for a valid issue:
"Status: Issue Confirmed. When you searched 'fashion camps toronto', the system found the right tag (fashion-design) but only returned 2 specialty camps. 5 other camps that offer fashion at the instructional level were being filtered out by our tag matching rules. We've updated the search logic to include these camps — please re-test."

Example for expected behavior:
"Status: Working as Expected. Your search for 'hockey camps ottawa' returned 15 camps. The system correctly identified hockey as the activity and Ottawa as the location. The camps shown all offer hockey programs. If you expected a specific camp that's missing, please let us know which one."

Rules:
- Keep under 150 words
- Lead with the status so the tester knows immediately if action is needed
- Explain the "why" — don't just say "working as designed" without explaining what the system did
- If results are correct, briefly explain what tags/location the system used
- If there's a real issue, say what the root cause is in plain terms
- Never use acronyms like ICS, RCS, CSSL, or CASL — the tester won't know these
- If camps are missing, name them (up to 3)
- Don't be defensive — acknowledge real issues directly

Respond with ONLY the comment text (no quotes, no prefix)."""

        response = client.messages.create(
            model=RESPONDER_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=300,
        )
        comment = response.content[0].text.strip()
        return f"{_timestamp()} {comment}"

    except Exception:
        # Fallback to template
        return _template_response(entry, validation)
