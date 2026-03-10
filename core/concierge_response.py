"""
core/concierge_response.py
Concierge Response Generator — produces a short spoken narrative for each
search result set. The concierge acknowledges the request, highlights what
makes the top picks relevant, and offers one natural follow-up.

Claude is tried first; on any failure a template-based response is returned
so the concierge always speaks.
"""
import json
import logging
from core.llm_client import get_client

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
- If the search was broadened (route=BROADEN_SEARCH), acknowledge it briefly and naturally
- Keep it concise: 2–3 sentences total, then the follow-up question on a new line

Return ONLY the response text. No JSON. No markdown headers. No bullet points.
"""


def _template_fallback(results: list[dict], params: dict, route: str) -> str:
    """
    Template-based response used when Gemini is unavailable.
    Always returns a non-empty string.
    """
    top = results[0] if results else {}
    count = len(results)

    tags = params.get("tags") or []
    activity = tags[0].replace("-", " ") if tags else ""

    cities = params.get("cities") or []
    location = (
        params.get("city")
        or (cities[0] if cities else None)
        or params.get("province")
        or ""
    )

    age_from = params.get("age_from")
    age_to = params.get("age_to")
    age_str = ""
    if age_from and age_to:
        age_str = f" for ages {age_from}–{age_to}"
    elif age_from:
        age_str = f" for ages {age_from}+"

    # Opening line
    if route == "BROADEN_SEARCH":
        opener = "I expanded the search to find related programs."
    elif activity and location:
        opener = f"Here are the top {activity} programs in {location}{age_str}."
    elif activity:
        opener = f"Here are the top {activity} programs{age_str}."
    elif location:
        opener = f"Here are camp programs in {location}{age_str}."
    else:
        opener = f"Here are {count} programs that match your search."

    # Highlight top camp
    highlight = ""
    if top.get("camp_name"):
        highlight = f" {top['camp_name']} leads the list."

    # Follow-up offer — suggest the most useful missing dimension
    if not age_from:
        followup = "\n\nWhat age is your child? I can narrow these down further."
    elif not params.get("type"):
        followup = "\n\nWould you prefer day camp or overnight?"
    elif not location:
        followup = "\n\nWhich city or area are you looking in?"
    else:
        followup = "\n\nWould you like to filter by cost, date, or a specific week?"

    return opener + highlight + followup


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
        Markdown string for display. Never returns empty string.
    """
    if not results:
        return ""

    # Build a compact summary of the top results for the prompt
    top_summary = []
    for r in results[:3]:
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

    # Surface gender filter effectiveness so concierge can acknowledge sparse data
    notes = []
    if params.get("gender"):
        all_coed = all(r.get("gender") in (None, 0) for r in results)
        if all_coed:
            notes.append(
                f"Gender filter '{params['gender']}' was applied but all programs "
                "returned are coed (no gender-specific data) — results are the same "
                "as without the filter. Acknowledge this briefly and naturally."
            )

    user_message = (
        f"User query: {raw_query}\n"
        f"Active filters: {json.dumps(active_filters, ensure_ascii=False)}\n"
        f"Total results shown: {len(results)}\n"
        f"Route: {route}\n"
        + (f"Notes: {' '.join(notes)}\n" if notes else "")
        + f"Top results:\n{json.dumps(top_summary, ensure_ascii=False, indent=2)}"
    )

    try:
        client = get_client()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            temperature=0.4,
            max_tokens=200,
        )
        text = response.content[0].text.strip()
        if text:
            return text
        _log.warning("Concierge response: Claude returned empty text, using template")
    except Exception as exc:
        _log.warning("Concierge response: Claude call failed (%s), using template", exc)

    return _template_fallback(results, params, route)
