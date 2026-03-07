"""
core/intent_parser.py
Intent Parser — wraps Gemini API call.
Loads system prompt from intent_parser_system_prompt.md at startup.
Returns structured IntentResult dataclass.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import google.generativeai as genai

# Module-level cache for system prompt
_SYSTEM_PROMPT: str | None = None


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
        # Search for the prompt file relative to the project root
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


def parse_intent(
    user_query: str,
    session_context: dict | None = None,
    fuzzy_hints: dict | None = None,
    current_date: str | None = None,
    model_name: str = "gemini-1.5-flash",
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

    # Build context block appended to user message
    context_block = ""
    if session_context and session_context.get("accumulated_params"):
        context_block += f"\nSESSION_CONTEXT: {json.dumps(session_context['accumulated_params'])}"
    if session_context and session_context.get("pending_suggestion"):
        context_block += f"\nPENDING_SUGGESTION: {json.dumps(session_context['pending_suggestion'])}"
    if fuzzy_hints:
        context_block += f"\nFUZZY_HINTS: {json.dumps(fuzzy_hints)}"
    if current_date:
        context_block += f"\nCURRENT_DATE: {current_date}"

    user_message = f"{user_query}{context_block}" if context_block else user_query

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_prompt,
    )

    response = model.generate_content(
        user_message,
        generation_config={"temperature": 0.1, "max_output_tokens": 1000},
    )

    raw = response.text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    parsed = json.loads(raw)

    # Filter to only known fields and inject raw_query
    valid_fields = IntentResult.__dataclass_fields__
    filtered = {k: v for k, v in parsed.items() if k in valid_fields}
    filtered["raw_query"] = user_query

    return IntentResult(**filtered)
