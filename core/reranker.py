"""
core/reranker.py
Reranker — uses Gemini to reorder and annotate results for relevance.
Fires when result pool is large or intent confidence is low.
"""
import json
import logging
import re
import google.genai as genai
from google.genai import types
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
    Rerank and annotate results using Gemini.

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
        compact.append({
            "id": r["id"],
            "camp": r.get("camp_name", ""),
            "program": r.get("name", ""),
            "tier": r.get("tier", "bronze"),
            "city": r.get("city", ""),
            "ages": f"{r.get('age_from', '?')}-{r.get('age_to', '?')}",
            "desc": (r.get("mini_description") or r.get("description") or "")[:200],
        })

    prompt = (
        f"User query: {raw_query}\n\n"
        f"Rank these camp programs by relevance to the query. Preserve specificity.\n"
        f"For each program, write a 'blurb': 1-2 sentences describing why the CAMP "
        f"(not a specific program's theme or title) matches the user's query. "
        f"Use direct, confident, factual language. "
        f"Do not reference internal program names, session themes, or specific week titles. "
        f"Do not use hedging phrases like 'sounds like', 'might be', or 'could be'.\n"
        f"Return JSON only: {{\"ranked\": [{{\"id\": int, \"score\": float, \"blurb\": str}}]}}\n"
        f"Programs:\n{json.dumps(compact, ensure_ascii=False)}"
    )

    try:
        client = genai.Client(api_key=get_secret("GEMINI_API_KEY", ""))
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=1500),
        )
        raw = response.text.strip()
        # Extract first JSON object — handles markdown fences and thinking preamble
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object found in reranker response")
        ranked_data = json.loads(json_match.group(0)).get("ranked", [])
    except Exception as exc:
        _log.warning("Reranker Gemini call failed: %s", exc)
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
