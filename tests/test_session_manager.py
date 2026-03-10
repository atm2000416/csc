"""
tests/test_session_manager.py
Unit tests for core/session_manager.py — no DB or network required.
"""
import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock anthropic and streamlit before any core imports
sys.modules.setdefault("anthropic", MagicMock())

# We'll inject a fresh st mock per test via importlib
import importlib


class _FakeSessionState:
    """Mimics st.session_state attribute access with dict-like storage."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __contains__(self, key):
        return hasattr(self, key)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)


def _run_with_st(accumulated_params, intent_kwargs):
    """Helper: run merge_intent with a mocked st.session_state."""
    from core.intent_parser import IntentResult

    session_context = {
        "accumulated_params": dict(accumulated_params),
        "query_history": [],
        "results_shown": [],
        "pending_suggestion": None,
        "refinement_count": 0,
        "raw_query": "",
    }

    mock_st = MagicMock()
    mock_st.session_state = _FakeSessionState(session_context=session_context)

    # Patch streamlit in the session_manager module
    sys.modules["streamlit"] = mock_st
    import core.session_manager as sm
    importlib.reload(sm)

    defaults = dict(
        tags=[], exclude_tags=[], age_from=None, age_to=None,
        city=None, cities=[], province=None, type=None, gender=None,
        cost_max=None, cost_sensitive=False, traits=[], is_special_needs=False,
        is_virtual=False, language_immersion=None, voice="unknown",
        detected_language="en", needs_clarification=[], needs_geolocation=False,
        ics=0.8, recognized=True, raw_query="test", accepted_suggestion=False,
    )
    defaults.update(intent_kwargs)
    intent = IntentResult(**defaults)

    result = sm.merge_intent(intent)
    return result


def test_merge_intent_reset_special_needs():
    """is_special_needs=False in new intent should clear existing True in session."""
    result = _run_with_st(
        accumulated_params={"is_special_needs": True, "tags": ["hockey"]},
        intent_kwargs={"is_special_needs": False, "tags": ["hockey"]},
    )
    assert result.get("is_special_needs") is False, (
        f"Expected is_special_needs=False, got {result.get('is_special_needs')!r}"
    )


def test_merge_intent_age_zero():
    """age_from=0 in new intent should not be ignored (falsy but valid)."""
    result = _run_with_st(
        accumulated_params={"age_from": 10},
        intent_kwargs={"age_from": 0, "age_to": 5},
    )
    assert result.get("age_from") == 0, (
        f"Expected age_from=0, got {result.get('age_from')!r}"
    )


def test_merge_intent_empty_list_does_not_override():
    """Empty tags list from new intent should NOT clear existing accumulated tags."""
    result = _run_with_st(
        accumulated_params={"tags": ["hockey"], "city": "Toronto"},
        intent_kwargs={"tags": [], "city": "Toronto"},
    )
    assert result.get("tags") == ["hockey"], (
        f"Expected tags=['hockey'] preserved, got {result.get('tags')!r}"
    )


def test_merge_intent_is_virtual_false():
    """is_virtual=False should override existing True."""
    result = _run_with_st(
        accumulated_params={"is_virtual": True},
        intent_kwargs={"is_virtual": False},
    )
    assert result.get("is_virtual") is False, (
        f"Expected is_virtual=False, got {result.get('is_virtual')!r}"
    )
