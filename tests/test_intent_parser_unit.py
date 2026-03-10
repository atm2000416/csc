"""
tests/test_intent_parser_unit.py
Pure unit tests for core/intent_parser.py — no network, no Gemini API required.
Tests _coerce_parsed() and parse_intent() error handling.
"""
import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Mock anthropic before any core imports (required since package may not be installed locally)
sys.modules.setdefault("anthropic", MagicMock())


def test_coerce_parsed_age_string():
    """_coerce_parsed should convert age_from/age_to strings to ints."""
    from core.intent_parser import _coerce_parsed

    parsed = {"age_from": "10", "age_to": "14", "tags": ["hockey"]}
    result = _coerce_parsed(parsed)
    assert result["age_from"] == 10
    assert result["age_to"] == 14
    assert isinstance(result["age_from"], int)
    assert isinstance(result["age_to"], int)


def test_coerce_parsed_null_tags():
    """_coerce_parsed should convert null tags to empty list."""
    from core.intent_parser import _coerce_parsed

    parsed = {"tags": None, "exclude_tags": None, "cities": None, "traits": None}
    result = _coerce_parsed(parsed)
    assert result["tags"] == []
    assert result["exclude_tags"] == []
    assert result["cities"] == []
    assert result["traits"] == []


def test_coerce_parsed_ics_string():
    """_coerce_parsed should convert ics string to float."""
    from core.intent_parser import _coerce_parsed

    parsed = {"ics": "0.8"}
    result = _coerce_parsed(parsed)
    assert result["ics"] == 0.8
    assert isinstance(result["ics"], float)


def test_coerce_parsed_bool_coercion():
    """_coerce_parsed should coerce int-like booleans to proper Python bools."""
    from core.intent_parser import _coerce_parsed

    parsed = {"recognized": 1, "is_special_needs": 0}
    result = _coerce_parsed(parsed)
    assert result["recognized"] is True
    assert result["is_special_needs"] is False


def test_coerce_parsed_invalid_int_becomes_none():
    """_coerce_parsed should set invalid int fields to None rather than crash."""
    from core.intent_parser import _coerce_parsed

    parsed = {"age_from": "not-a-number"}
    result = _coerce_parsed(parsed)
    assert result["age_from"] is None


def test_parse_intent_api_failure():
    """parse_intent should return recognized=False and ics=0.3 when Claude raises."""
    from core.intent_parser import parse_intent

    with patch("core.intent_parser.get_client") as mock_get_client, \
         patch("core.intent_parser._get_active_slugs", return_value=set()):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.messages.create.side_effect = Exception("Network error")

        with patch("core.intent_parser.load_system_prompt", return_value="system prompt"):
            result = parse_intent("hockey camp Toronto")

    assert result.recognized is False
    assert result.ics == 0.3
    assert result.raw_query == "hockey camp Toronto"
