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

    if validation.issue_type == "UI_UX":
        return f"{ts} UI feedback noted for review. {validation.details}"

    if validation.issue_type == "EXPECTED_BEHAVIOR" and not validation.is_valid_issue:
        return (
            f"{ts} Working as designed. "
            f"Search returned {validation.result_count} results "
            f"(ICS={validation.intent_ics:.2f}, RCS={validation.rcs:.2f}). "
            f"Tags resolved: {', '.join(validation.intent_tags) or 'none'}."
        )

    if validation.issue_type == "LINK_ISSUE":
        return f"{ts} Link issue confirmed. {validation.details}"

    # Valid issue — include root cause and diagnostics
    parts = [ts]

    if validation.is_valid_issue:
        parts.append("Valid issue.")
    else:
        parts.append("Investigating.")

    if validation.root_cause:
        parts.append(validation.root_cause)

    parts.append(
        f"Pipeline returned {validation.result_count} results "
        f"(ICS={validation.intent_ics:.2f}, RCS={validation.rcs:.2f})."
    )

    if validation.intent_tags:
        parts.append(f"Tags: {', '.join(validation.intent_tags)}.")

    if validation.missing_camps:
        mc = ", ".join(validation.missing_camps[:5])
        suffix = f" (+{len(validation.missing_camps) - 5} more)" if len(validation.missing_camps) > 5 else ""
        parts.append(f"Missing camps: {mc}{suffix}.")

    return " ".join(parts)


def generate_response(entry: dict, validation: ValidationResult) -> str:
    """
    Generate a COMMENTS response for a QA finding.

    Tries Claude Haiku for a polished response; falls back to template.
    """
    # For simple cases, use templates directly (saves API calls)
    if validation.issue_type in ("UI_UX", "LINK_ISSUE"):
        return _template_response(entry, validation)

    # Try LLM for richer responses
    try:
        from core.llm_client import get_client

        client = get_client()

        prompt = f"""You are a QA response bot for a camp search engine (camps.ca).
A tester submitted a finding. Generate a concise, professional response for the COMMENTS column.

TESTER FINDING:
- Search term: {entry.get('search_term', '')}
- What they saw: {entry.get('chat_response', '')}
- Why incorrect: {entry.get('why_incorrect', '')}

VALIDATION RESULTS:
- Issue type: {validation.issue_type}
- Valid issue: {validation.is_valid_issue}
- Root cause: {validation.root_cause or 'N/A'}
- Pipeline results: {validation.result_count} results (ICS={validation.intent_ics:.2f}, RCS={validation.rcs:.2f})
- Tags resolved: {', '.join(validation.intent_tags) or 'none'}
- Missing camps: {', '.join(validation.missing_camps[:5]) or 'none'}
- Details: {validation.details}

RESPONSE CATEGORIES (pick one):
- Issue confirmed: "Valid issue. [root cause]. [what we'll fix]."
- Expected behavior: "Working as designed. [explanation]."
- Clarification needed: "Need more details: [specific question]."
- Already fixed: "Resolved in recent update. Please re-test."
- UI/UX noted: "UI feedback logged for review."

Rules:
- Keep under 200 words
- Be specific about root cause when known
- Include relevant numbers (result count, missing camp count)
- Don't be defensive — acknowledge real issues directly
- Use plain language, no jargon

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
