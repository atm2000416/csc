"""
core/intent_parser.py
Intent Parser — wraps Gemini API call.
Loads system prompt from intent_parser_system_prompt.md at startup.
Returns structured IntentResult dataclass.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import google.genai as genai
from google.genai import types
from config import get_secret

# Module-level cache for system prompt
_SYSTEM_PROMPT: str | None = None

# Module-level cache for active tag slugs (fetched once per process)
_ACTIVE_SLUGS: set[str] | None = None


@dataclass
class IntentResult:
    tags: list[str] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)
    age_from: int | None = None
    age_to: int | None = None
    city: str | None = None
    cities: list[str] = field(default_factory=list)
    province: str | None = None
    type: str | None = None
    gender: str | None = None
    cost_max: int | None = None
    cost_sensitive: bool = False
    traits: list[str] = field(default_factory=list)
    is_special_needs: bool = False
    is_virtual: bool = False
    language_immersion: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    lat: float | None = None
    lon: float | None = None
    radius_km: int | None = None
    clear_activity: bool = False
    voice: str = "unknown"
    detected_language: str = "en"
    needs_clarification: list[str] = field(default_factory=list)
    needs_geolocation: bool = False
    ics: float = 0.0
    recognized: bool = False
    raw_query: str = ""
    accepted_suggestion: bool = False


def load_system_prompt() -> str:
    """Load Intent Parser system prompt from file. Cached after first call."""
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        candidates = [
            Path("intent_parser_system_prompt.md"),
            Path(__file__).parent.parent / "intent_parser_system_prompt.md",
        ]
        for path in candidates:
            if path.exists():
                _SYSTEM_PROMPT = path.read_text(encoding="utf-8")
                break
        else:
            raise FileNotFoundError(
                "intent_parser_system_prompt.md not found. "
                "Place it in the project root directory."
            )
    return _SYSTEM_PROMPT


def _get_active_slugs() -> set[str]:
    """Fetch all active tag slugs from DB. Cached for process lifetime."""
    global _ACTIVE_SLUGS
    if _ACTIVE_SLUGS is None:
        try:
            from db.connection import get_connection
            conn = get_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT slug FROM activity_tags WHERE is_active = 1")
            _ACTIVE_SLUGS = {row["slug"] for row in cur.fetchall()}
            cur.close()
            conn.close()
        except Exception:
            # If DB is unreachable, return empty set — validation is skipped gracefully
            _ACTIVE_SLUGS = set()
    return _ACTIVE_SLUGS


def _coerce_parsed(parsed: dict) -> dict:
    """Coerce Gemini JSON output to expected Python types before constructing IntentResult."""
    # List fields — ensure list, never None
    for key in ("tags", "exclude_tags", "cities", "traits", "needs_clarification"):
        val = parsed.get(key)
        if val is None:
            parsed[key] = []
        elif not isinstance(val, list):
            parsed[key] = []

    # Integer fields
    for key in ("age_from", "age_to", "cost_max", "radius_km"):
        val = parsed.get(key)
        if val is not None:
            try:
                parsed[key] = int(val)
            except (TypeError, ValueError):
                parsed[key] = None

    # Float fields
    for key in ("ics", "lat", "lon"):
        val = parsed.get(key)
        if val is not None:
            try:
                parsed[key] = float(val)
            except (TypeError, ValueError):
                parsed[key] = 0.0

    # Boolean fields
    for key in ("recognized", "cost_sensitive", "is_special_needs", "is_virtual",
                "needs_geolocation", "accepted_suggestion", "clear_activity"):
        val = parsed.get(key)
        if val is not None and not isinstance(val, bool):
            parsed[key] = bool(val)

    # String fields
    for key in ("city", "province", "type", "gender", "language_immersion",
                "date_from", "date_to", "voice", "detected_language"):
        val = parsed.get(key)
        if val is not None and not isinstance(val, str):
            parsed[key] = str(val)

    return parsed


def parse_intent(
    user_query: str,
    session_context: dict | None = None,
    fuzzy_hints: dict | None = None,
    current_date: str | None = None,
    model_name: str = "gemini-2.5-flash",
) -> IntentResult:
    """
    Call Gemini to parse user query into structured search parameters.

    Args:
        user_query: Raw user input (any language)
        session_context: Accumulated parameters from prior session turns
        fuzzy_hints: Tag hints from Fuzzy Pre-processor
        current_date: ISO date string for temporal reasoning
        model_name: Gemini model to use

    Returns:
        IntentResult dataclass with all extracted parameters
    """
    system_prompt = load_system_prompt()
    active_slugs = _get_active_slugs()

    context_block = ""
    if session_context and session_context.get("accumulated_params"):
        context_block += f"\nSESSION_CONTEXT: {json.dumps(session_context['accumulated_params'])}"
    if session_context and session_context.get("pending_suggestion"):
        context_block += f"\nPENDING_SUGGESTION: {json.dumps(session_context['pending_suggestion'])}"
    if fuzzy_hints:
        context_block += f"\nFUZZY_HINTS: {json.dumps(fuzzy_hints)}"
    if current_date:
        context_block += f"\nCURRENT_DATE: {current_date}"
    if active_slugs:
        context_block += f"\nVALID_SLUGS: {', '.join(sorted(active_slugs))}"

    user_message = f"{user_query}{context_block}" if context_block else user_query

    try:
        client = genai.Client(api_key=get_secret("GEMINI_API_KEY", ""))
        response = client.models.generate_content(
            model=model_name,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2,
                max_output_tokens=1000,
            ),
        )
        raw = response.text.strip()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Gemini API call failed: %s", exc)
        return IntentResult(raw_query=user_query, ics=0.3, recognized=False)

    # Extract first JSON object regardless of surrounding markdown or thinking text
    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
    if json_match:
        raw = json_match.group(0)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Gemini returned unparseable output — return low-confidence fallback
        return IntentResult(raw_query=user_query, ics=0.3, recognized=False)

    # Validate tags against live DB slugs; strip any hallucinated slugs
    if active_slugs and "tags" in parsed:
        raw_tags = parsed.get("tags") or []
        valid_tags = [t for t in raw_tags if t in active_slugs]
        stripped = [t for t in raw_tags if t not in active_slugs]
        if stripped:
            parsed["_stripped_tags"] = stripped  # preserved for trace only
        parsed["tags"] = valid_tags
        # If model thought it recognised an activity but all tags were hallucinated,
        # only flip recognized=False when there are no other structured params either
        if raw_tags and not valid_tags:
            has_other_params = any(parsed.get(k) for k in (
                "type", "gender", "city", "cities", "province",
                "age_from", "age_to", "cost_max", "traits",
            ))
            if not has_other_params:
                parsed["recognized"] = False

    parsed = _coerce_parsed(parsed)

    valid_fields = IntentResult.__dataclass_fields__
    filtered = {k: v for k, v in parsed.items() if k in valid_fields}
    filtered["raw_query"] = user_query

    return IntentResult(**filtered)
