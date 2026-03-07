"""
tests/test_fuzzy.py
Tests for the Fuzzy Pre-processor.
No DB or API required — pure Python.

Usage:
    python -m pytest tests/test_fuzzy.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.fuzzy_preprocessor import preprocess


# ── Activity alias tests ─────────────────────────────────────────────────────

def test_skating_includes_figure_skating():
    result = preprocess("skating camps in Hamilton")
    assert "figure-skating" in result.get("tag_hints", []), (
        f"Expected figure-skating in tag_hints, got {result.get('tag_hints')}"
    )


def test_skating_includes_ice_skating():
    result = preprocess("skating camps")
    assert "ice-skating" in result.get("tag_hints", []) or \
           "figure-skating" in result.get("tag_hints", []), (
        f"Expected ice-skating or figure-skating in tag_hints"
    )


def test_skateboard_maps_to_skateboarding():
    result = preprocess("skateboard camp for teens")
    assert "skateboarding" in result.get("tag_hints", []), (
        f"Expected skateboarding in tag_hints, got {result.get('tag_hints')}"
    )


def test_sk8_maps_to_skateboarding():
    result = preprocess("sk8 camp")
    assert "skateboarding" in result.get("tag_hints", [])


def test_horses_maps_to_equestrian():
    result = preprocess("horses camp for my daughter")
    assert "horseback-riding-equestrian" in result.get("tag_hints", []), (
        f"Expected horseback-riding-equestrian, got {result.get('tag_hints')}"
    )


def test_coding_maps_to_programming():
    result = preprocess("coding camp for kids")
    assert "programming-multi" in result.get("tag_hints", []), (
        f"Expected programming-multi, got {result.get('tag_hints')}"
    )


def test_code_maps_to_programming():
    result = preprocess("learn to code")
    assert "programming-multi" in result.get("tag_hints", [])


def test_robots_maps_to_robotics():
    result = preprocess("robots and technology camp")
    assert "robotics" in result.get("tag_hints", [])


def test_hockey_camp_maps_to_hockey():
    result = preprocess("hockey camp in Toronto")
    assert "hockey" in result.get("tag_hints", [])


def test_swimming_maps_correctly():
    result = preprocess("swimming camp for kids")
    assert "swimming" in result.get("tag_hints", [])


def test_dance_maps_to_dance_multi():
    result = preprocess("dance camp this summer")
    assert "dance-multi" in result.get("tag_hints", [])


def test_ballet_maps_to_ballet():
    result = preprocess("ballet camps in Toronto")
    assert "ballet" in result.get("tag_hints", [])


def test_soccer_camp_maps_to_soccer():
    result = preprocess("soccer camp in Mississauga")
    assert "soccer" in result.get("tag_hints", [])


# ── Geo expansion tests ──────────────────────────────────────────────────────

def test_gta_geo_expansion():
    result = preprocess("hockey camps in the GTA")
    geo = result.get("geo_expansion", [])
    assert "Toronto" in geo, f"Expected Toronto in geo_expansion, got {geo}"
    assert "Mississauga" in geo, f"Expected Mississauga in geo_expansion, got {geo}"


def test_cottage_country_expansion():
    result = preprocess("camps in cottage country")
    geo = result.get("geo_expansion", [])
    assert "Muskoka" in geo or "Haliburton" in geo, (
        f"Expected Muskoka/Haliburton in geo_expansion, got {geo}"
    )


def test_near_me_sets_geolocation():
    result = preprocess("camps near me")
    assert result.get("needs_geolocation") is True, (
        f"Expected needs_geolocation=True, got {result}"
    )


def test_downtown_sets_geolocation():
    result = preprocess("dance camp downtown")
    assert result.get("needs_geolocation") is True


# ── Age bracket tests ────────────────────────────────────────────────────────

def test_tweens_age_bracket():
    result = preprocess("camps for tweens")
    bracket = result.get("age_bracket")
    assert bracket is not None, "Expected age_bracket for 'tweens'"
    assert bracket.get("age_from") == 10
    assert bracket.get("age_to") == 12


def test_toddler_age_bracket():
    result = preprocess("toddler programs")
    bracket = result.get("age_bracket")
    assert bracket is not None
    assert bracket.get("age_from") == 2


def test_teen_age_bracket():
    result = preprocess("camps for teens")
    bracket = result.get("age_bracket")
    assert bracket is not None
    assert bracket.get("age_from") == 13


def test_teenager_age_bracket():
    result = preprocess("teenager summer camp")
    bracket = result.get("age_bracket")
    assert bracket is not None
    assert bracket.get("age_from") == 13


def test_high_school_age_bracket():
    result = preprocess("high school summer program")
    bracket = result.get("age_bracket")
    assert bracket is not None
    assert bracket.get("age_from") == 14


# ── Trait hint tests ─────────────────────────────────────────────────────────

def test_shy_maps_to_interpersonal_skills():
    result = preprocess("camp for my shy daughter")
    assert "interpersonal-skills" in result.get("trait_hints", [])


def test_make_friends_maps_to_interpersonal():
    result = preprocess("camp to make friends")
    assert "interpersonal-skills" in result.get("trait_hints", [])


def test_resilience_maps_correctly():
    result = preprocess("build resilience at summer camp")
    assert "resilience" in result.get("trait_hints", [])


def test_christian_maps_to_religious_faith():
    result = preprocess("Christian overnight camp")
    assert "religious-faith" in result.get("trait_hints", [])


# ── Empty / edge case tests ──────────────────────────────────────────────────

def test_empty_query_returns_empty():
    result = preprocess("")
    assert result == {} or all(not v for v in result.values())


def test_no_match_returns_empty():
    result = preprocess("xyzzy frobble glorp")
    assert result == {} or all(not v for v in result.values())


def test_returns_only_nonempty_keys():
    result = preprocess("something random camp")
    for key, val in result.items():
        assert val, f"Key {key!r} has falsy value {val!r} — should be omitted"


def test_no_duplicate_tag_hints():
    result = preprocess("ice skating skating camps")
    hints = result.get("tag_hints", [])
    assert len(hints) == len(set(hints)), f"Duplicate tag_hints: {hints}"


def test_longest_match_priority_figure_skating():
    """'figure skating camp' should map to figure-skating, not skateboarding."""
    result = preprocess("figure skating camp for beginners")
    hints = result.get("tag_hints", [])
    assert "figure-skating" in hints, f"Expected figure-skating, got {hints}"
    assert "skateboarding" not in hints, f"skateboarding should not be in {hints}"
