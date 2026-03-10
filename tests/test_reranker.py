"""
tests/test_reranker.py
Unit tests for core/reranker.py — no network required.
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock anthropic before any core imports
sys.modules.setdefault("anthropic", MagicMock())


def _make_result(program_id: int, tier: str = "bronze") -> dict:
    return {
        "id": program_id,
        "camp_id": 1,
        "name": f"Program {program_id}",
        "camp_name": "Test Camp",
        "tier": tier,
        "city": "Toronto",
        "age_from": 8,
        "age_to": 14,
        "mini_description": "A great camp program.",
        "description": "Full description.",
    }


def _secret_side_effect(key, default=""):
    if key == "RERANKER_THRESHOLD":
        return "15"
    return "fake-key"


def test_gold_bonus_applied_once():
    """Gold bonus should be applied exactly once (in code, not also in prompt)."""
    from core.reranker import rerank

    results = [_make_result(i, tier="gold" if i == 1 else "bronze") for i in range(1, 21)]
    raw_score = 0.80
    mock_ranked = [
        {"id": i, "score": raw_score if i == 1 else 0.50, "blurb": "blurb"}
        for i in range(1, 21)
    ]

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps({"ranked": mock_ranked}, indent=2))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("core.reranker.get_secret", side_effect=_secret_side_effect), \
         patch("core.reranker.get_client", return_value=mock_client):
        final = rerank(results, "hockey camp", {}, top_n=10)

    gold_result = next((r for r in final if r["id"] == 1), None)
    assert gold_result is not None, "Gold program should appear in results"
    expected = round(raw_score * 1.05, 4)  # applied once
    assert gold_result["rerank_score"] == expected, (
        f"Expected {expected} (1× bonus), got {gold_result['rerank_score']}"
    )


def test_reranker_fires_on_low_ics():
    """Reranker should fire when ICS < 0.80, even with few results."""
    from core.reranker import _should_rerank

    with patch("core.reranker.get_secret", side_effect=_secret_side_effect):
        assert _should_rerank([{}] * 5, 0.50) is True


def test_reranker_skips_on_high_ics_small_pool():
    """Reranker should NOT fire when ICS >= 0.80 and result count <= threshold."""
    from core.reranker import _should_rerank

    with patch("core.reranker.get_secret", side_effect=_secret_side_effect):
        assert _should_rerank([{}] * 10, 0.90) is False


def test_reranker_fallback_score_is_half():
    """When Gemini fails, fallback rerank_score should be 0.5, not 1.0."""
    from core.reranker import rerank

    results = [_make_result(i) for i in range(1, 20)]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API down")

    with patch("core.reranker.get_secret", side_effect=_secret_side_effect), \
         patch("core.reranker.get_client", return_value=mock_client):
        final = rerank(results, "hockey camp", {"ics": 0.50}, top_n=10)

    for r in final:
        assert r["rerank_score"] == 0.5, f"Expected fallback score 0.5, got {r['rerank_score']}"
