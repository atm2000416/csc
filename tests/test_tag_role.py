"""
tests/test_tag_role.py
Tests for 3-tier tagging: parse_sitems, parse_activities_field,
insert_sitems_tags, and CSSL tag_role ordering.
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── parse_activities_field ───────────────────────────────────────────────────

from db.sync_from_dump import parse_activities_field


def test_parse_activities_normal():
    """Standard activities field with multiple entries."""
    result = parse_activities_field("[133]2,[81]3,[154]1")
    assert result == [133, 81, 154]


def test_parse_activities_single():
    """Single activity."""
    result = parse_activities_field("[42]1")
    assert result == [42]


def test_parse_activities_empty_string():
    """Empty string returns empty list."""
    assert parse_activities_field("") == []


def test_parse_activities_none():
    """None returns empty list."""
    assert parse_activities_field(None) == []


def test_parse_activities_no_brackets():
    """String without bracket patterns returns empty."""
    assert parse_activities_field("no activities here") == []


def test_parse_activities_mixed():
    """Activities field with extra whitespace / varied priorities."""
    result = parse_activities_field("[10]1, [20]5, [30]2")
    assert result == [10, 20, 30]


# ── parse_sitems ─────────────────────────────────────────────────────────────

from db.sync_from_dump import parse_sitems


def test_parse_sitems_basic():
    """parse_sitems extracts id→slug from sitems INSERT."""
    dump = (
        "INSERT INTO `sitems` VALUES "
        "(1,0,'Health & Fitness',0,6,'specialty','6',0,0,0,6,0,'','#94BB25','Health & Fitness'),"
        "(3,0,'Sports',4,4,'specialty','',0,0,0,0,0,'','','Sports'),"
        "(42,0,'Hockey',1,0,'activity','',0,0,0,0,0,'','','Hockey'),"
        "(999,0,'Unknown Item',1,0,'activity','',0,0,0,0,0,'','','Unknown Item');\n"
    )
    result = parse_sitems(dump)
    assert result[1] == "health-fitness"
    assert result[3] == "sports"
    assert result[42] == "hockey"
    assert 999 not in result  # unmapped item


def test_parse_sitems_empty():
    """No sitems table in dump → empty dict."""
    assert parse_sitems("no sitems here") == {}


def test_parse_sitems_escaped_quotes():
    """Handles escaped single quotes in item names."""
    dump = (
        "INSERT INTO `sitems` VALUES "
        "(172,0,'Arts (multi)',0,0,'specialty','',0,0,0,0,0,'','','Arts (multi)');\n"
    )
    result = parse_sitems(dump)
    assert result[172] == "arts-multi"


# ── WEBITEMS_TO_SLUG completeness ────────────────────────────────────────────

from db.tag_from_campsca_pages import WEBITEMS_TO_SLUG


def test_specialty_mappings_present():
    """All critical specialty-level sitems names are mapped."""
    required = [
        ("Health & Fitness", "health-fitness"),
        ("Education", "education"),
        ("Sports", "sports"),
        ("Arts", "arts"),
        ("Adventure", "adventure"),
        ("Computer (multi)", "computer-multi"),
        ("Sport (multi)", "sport-multi"),
        ("Arts (multi)", "arts-multi"),
        ("Traditional (multi activity)", "traditional"),
        ("Adventure (multi)", "adventure-multi"),
        ("Immersion", "language-immersion"),
        ("Health and Fitness (multi)", "health-fitness-multi"),
    ]
    for name, expected_slug in required:
        assert name in WEBITEMS_TO_SLUG, f"Missing mapping for {name!r}"
        assert WEBITEMS_TO_SLUG[name] == expected_slug


# ── insert_sitems_tags logic ─────────────────────────────────────────────────

def test_insert_sitems_tags_priority():
    """Specialty, category, and activity roles are assigned correctly."""
    from db.sync_from_dump import insert_sitems_tags
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.rowcount = 1  # simulate successful insert

    session = {
        "name": "Hockey Camp",
        "specialty_id": 42,
        "category_id": 3,
        "activity_ids": [81, 133],
    }
    sitems_to_slug = {42: "hockey", 3: "sports", 81: "swimming", 133: "archery"}
    tag_slug_to_id = {"hockey": 100, "sports": 200, "swimming": 300, "archery": 400}

    insert_sitems_tags(cursor, prog_id=1, session=session,
                       sitems_to_slug=sitems_to_slug,
                       tag_slug_to_id=tag_slug_to_id)

    # Should have 4 INSERT calls: specialty + category + 2 activities
    calls = cursor.execute.call_args_list
    insert_calls = [c for c in calls if "INSERT" in str(c)]
    assert len(insert_calls) == 4

    # Check roles in order
    assert "'specialty'" in str(insert_calls[0])
    assert "'category'" in str(insert_calls[1])
    assert "'activity'" in str(insert_calls[2])
    assert "'activity'" in str(insert_calls[3])


def test_insert_sitems_tags_dedup():
    """Same tag_id for specialty and category → only specialty inserted."""
    from db.sync_from_dump import insert_sitems_tags
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.rowcount = 1

    session = {
        "name": "Hockey Camp",
        "specialty_id": 42,
        "category_id": 42,  # same as specialty
        "activity_ids": [],
    }
    sitems_to_slug = {42: "hockey"}
    tag_slug_to_id = {"hockey": 100}

    insert_sitems_tags(cursor, prog_id=1, session=session,
                       sitems_to_slug=sitems_to_slug,
                       tag_slug_to_id=tag_slug_to_id)

    insert_calls = [c for c in cursor.execute.call_args_list if "INSERT" in str(c)]
    assert len(insert_calls) == 1  # only specialty, no duplicate category


def test_insert_sitems_tags_fallback():
    """When no sitems data maps, falls back to keyword inference."""
    from db.sync_from_dump import insert_sitems_tags
    from unittest.mock import MagicMock

    cursor = MagicMock()
    cursor.rowcount = 1

    session = {
        "name": "Hockey Skills Camp",
        "specialty_id": None,
        "category_id": None,
        "activity_ids": [],
    }
    sitems_to_slug = {}
    tag_slug_to_id = {"hockey": 100}

    insert_sitems_tags(cursor, prog_id=1, session=session,
                       sitems_to_slug=sitems_to_slug,
                       tag_slug_to_id=tag_slug_to_id)

    # Should fall back to infer_tags and find "hockey"
    insert_calls = [c for c in cursor.execute.call_args_list if "INSERT" in str(c)]
    assert len(insert_calls) >= 1
    assert "'activity'" in str(insert_calls[0])  # fallback uses activity role


# ── _partition_by_role ───────────────────────────────────────────────────────

from app import _partition_by_role


def test_partition_specialty_vs_activity():
    """Specialty hits separated from activity hits."""
    results = [
        {"camp_id": 1, "_role_match": 0},  # specialty
        {"camp_id": 2, "_role_match": 1},  # category
        {"camp_id": 3, "_role_match": 2},  # activity
        {"camp_id": 4, "_role_match": 2},  # activity
    ]
    spec, act = _partition_by_role(results)
    assert len(spec) == 2
    assert len(act) == 2
    assert all(r["_role_match"] <= 1 for r in spec)
    assert all(r["_role_match"] == 2 for r in act)


def test_partition_no_role_data():
    """Pre-migration data without _role_match → all treated as specialty."""
    results = [
        {"camp_id": 1},
        {"camp_id": 2},
    ]
    spec, act = _partition_by_role(results)
    assert len(spec) == 2
    assert len(act) == 0


def test_partition_empty():
    """Empty results → both empty."""
    spec, act = _partition_by_role([])
    assert spec == []
    assert act == []
