"""
core/reranker.py
Reranker — uses Claude to reorder and annotate results for relevance.
Fires when result pool is large or intent confidence is low.
"""
import json
import logging
from core.llm_client import get_client
from config import get_secret

_log = logging.getLogger(__name__)


def _should_rerank(results: list[dict], intent_ics: float) -> bool:
    threshold = int(get_secret("RERANKER_THRESHOLD", "15"))
    return len(results) > threshold or intent_ics < 0.80


def rerank(
    results: list[dict],
    raw_query: str,
    intent_params: dict,
    top_n: int = 10,
) -> list[dict]:
    """
    Rerank and annotate results using Claude.

    Args:
        results: List of program dicts from CSSL
        raw_query: Original user query string
        intent_params: Merged intent/session params dict
        top_n: Number of results to return

    Returns:
        Top top_n results with 'blurb' and 'rerank_score' fields added.
    """
    if not results:
        return []

    intent_ics = float(intent_params.get("ics", 1.0))

    if not _should_rerank(results, intent_ics):
        for r in results[:top_n]:
            if "blurb" not in r:
                r["blurb"] = r.get("mini_description", "")
            if "rerank_score" not in r:
                r["rerank_score"] = 1.0
        return results[:top_n]

    candidates = results[:20]

    if len(candidates) <= 3:
        for r in candidates:
            r["blurb"] = r.get("mini_description", "")
            r["rerank_score"] = 1.0
        return candidates

    compact = []
    for r in candidates:
        role = r.get("_role_match")
        role_label = {0: "specialty", 1: "category", 2: "activity"}.get(role, "unknown")
        entry = {
            "id": r["id"],
            "camp": r.get("camp_name", ""),
            "program": r.get("name", ""),
            "tier": r.get("tier", "bronze"),
            "city": r.get("city", ""),
            "ages": f"{r.get('age_from', '?')}-{r.get('age_to', '?')}",
            "desc": (r.get("mini_description") or r.get("description") or "")[:200],
            "focus": role_label,
        }
        compact.append(entry)

    prompt = (
        f"User query: {raw_query}\n\n"
        f"Rank these camp programs by relevance to the query. "
        f"Each program has a 'focus' field: 'specialty' means the activity is the camp's "
        f"primary focus, 'category' means it's a significant offering, 'activity' means "
        f"it's one of many activities. Strongly prefer specialty and category programs "
        f"over activity-level ones.\n"
        f"For each program, write a 'blurb': 1-2 sentences describing why the CAMP "
        f"(not a specific program's theme or title) matches the user's query. "
        f"Use direct, confident, factual language. "
        f"Do not reference internal program names, session themes, or specific week titles. "
        f"Do not use hedging phrases like 'sounds like', 'might be', or 'could be'.\n"
        f"IMPORTANT: Write each blurb in the same language as the user's query. "
        f"Camp names stay in English but the blurb text must match the user's language.\n"
        f"Return JSON only: {{\"ranked\": [{{\"id\": int, \"score\": float, \"blurb\": str}}]}}\n"
        f"Programs:\n{json.dumps(compact, ensure_ascii=False)}"
    )

    try:
        client = get_client()
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=3000,
        )
        raw = response.content[0].text.strip()
        # Find the first { and parse from there — handles both compact {"ranked":...}
        # and pretty-printed {\n  "ranked":...} output from Claude.
        start = raw.find('{')
        if start == -1:
            raise ValueError("No JSON object found in reranker response")
        parsed = json.JSONDecoder().raw_decode(raw, start)[0]
        ranked_data = parsed.get("ranked", [])
    except Exception as exc:
        _log.warning("Reranker Claude call failed: %s", exc)
        for r in results[:top_n]:
            r.setdefault("blurb", r.get("mini_description", ""))
            r.setdefault("rerank_score", 0.5)
        return results[:top_n]

    id_to_rank = {item["id"]: item for item in ranked_data}
    id_to_result = {r["id"]: r for r in candidates}

    reranked = []
    for item in ranked_data[:top_n]:
        result = id_to_result.get(item["id"])
        if result is None:
            continue
        result = dict(result)
        result["blurb"] = item.get("blurb", result.get("mini_description", ""))
        score = float(item.get("score", 0.0))
        if result.get("tier") == "gold" and score >= 0.70:
            score = min(1.0, score * 1.05)
        result["rerank_score"] = round(score, 4)
        reranked.append(result)

    seen_ids = {r["id"] for r in reranked}
    for r in candidates:
        if r["id"] not in seen_ids and len(reranked) < top_n:
            r = dict(r)
            r.setdefault("blurb", r.get("mini_description", ""))
            r.setdefault("rerank_score", 0.0)
            reranked.append(r)

    reranked.sort(key=lambda x: x["rerank_score"], reverse=True)
    return reranked[:top_n]
