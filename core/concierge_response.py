"""
core/concierge_response.py
Concierge Response Generator — produces a short spoken narrative for each
search result set. The concierge acknowledges the request, highlights what
makes the top picks relevant, and offers one natural follow-up.

Returns a plain markdown string. Returns "" on failure (cards render silently).
"""
import json
import logging
import google.genai as genai
from google.genai import types
from config import get_secret

_log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a warm, knowledgeable camp search concierge helping Canadian parents find \
the right summer camp for their child.

After a search, you produce a SHORT spoken response (2–3 sentences max) that:
1. Acknowledges what was searched for in natural, conversational language
2. Highlights what makes the top 1–2 results a strong match (specialty, location, age fit, tier)
3. Ends with ONE natural follow-up offer — a single question or suggestion that \
   helps the parent refine further

Tone rules:
- Warm and confident, like a trusted local expert — NOT a search engine
- Never start with "Great!" / "Sure!" / "Of course!" or any sycophantic filler
- Never say "I found X results" mechanically — speak about the camps, not the count
- Don't list every result — focus on the standout picks
- If the search was broadened (route=BROADEN), acknowledge it briefly and naturally
- Keep it concise: 2–3 sentences total, then the follow-up question on a new line

Return ONLY the response text. No JSON. No markdown headers. No bullet points.
"""


def generate(
    results: list[dict],
    raw_query: str,
    params: dict,
    route: str = "SHOW_RESULTS",
) -> str:
    """
    Generate a concierge narrative for the current result set.

    Args:
        results:   Final reranked result list (top 10)
        raw_query: Original user query string
        params:    Merged intent/session params dict
        route:     Decision matrix route name (SHOW_RESULTS, BROADEN_SEARCH, etc.)

    Returns:
        Markdown string for display, or "" on failure.
    """
    if not results:
        return ""

    # Build a compact summary of the top results for the prompt
    top = results[:3]
    top_summary = []
    for r in top:
        blurb = r.get("blurb") or r.get("mini_description") or ""
        top_summary.append({
            "camp": r.get("camp_name", ""),
            "program": r.get("name", ""),
            "tier": r.get("tier", ""),
            "city": r.get("city", ""),
            "ages": f"{r.get('age_from', '?')}–{r.get('age_to', '?')}",
            "blurb": blurb[:150],
        })

    # Summarise the active filters for context
    active_filters = {}
    for key in ("tags", "city", "cities", "province", "age_from", "age_to",
                "type", "gender", "cost_max", "language_immersion",
                "is_special_needs", "is_virtual"):
        val = params.get(key)
        if val:
            active_filters[key] = val

    user_message = (
        f"User query: {raw_query}\n"
        f"Active filters: {json.dumps(active_filters, ensure_ascii=False)}\n"
        f"Total results shown: {len(results)}\n"
        f"Route: {route}\n"
        f"Top results:\n{json.dumps(top_summary, ensure_ascii=False, indent=2)}"
    )

    try:
        client = genai.Client(api_key=get_secret("GEMINI_API_KEY", ""))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                temperature=0.4,
                max_output_tokens=200,
            ),
        )
        return response.text.strip()
    except Exception as exc:
        _log.warning("Concierge response generation failed: %s", exc)
        return ""
