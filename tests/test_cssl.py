"""
tests/test_cssl.py
Basic SQL query validation tests for CSSL.
Skips gracefully if DB is unavailable.

Usage:
    python -m pytest tests/test_cssl.py -v
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

def db_available() -> bool:
    try:
        from db.connection import get_connection
        conn = get_connection()
        conn.close()
        return True
    except Exception:
        return False


DB_SKIP = pytest.mark.skipif(not db_available(), reason="DB not available")


@DB_SKIP
def test_tag_resolution_by_slug():
    """resolve_tag_ids should return IDs for known slugs."""
    from db.connection import get_connection
    from core.cssl import resolve_tag_ids

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    ids = resolve_tag_ids(["hockey", "soccer"], cursor)
    cursor.close()
    conn.close()

    # Should return at least some IDs if tags are seeded
    assert isinstance(ids, list)
    # All returned values should be ints
    assert all(isinstance(i, int) for i in ids)


@DB_SKIP
def test_tag_resolution_empty():
    """resolve_tag_ids with empty input returns []."""
    from db.connection import get_connection
    from core.cssl import resolve_tag_ids

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    ids = resolve_tag_ids([], cursor)
    cursor.close()
    conn.close()

    assert ids == []


@DB_SKIP
def test_trait_resolution():
    """resolve_trait_ids should return IDs for seeded traits."""
    from db.connection import get_connection
    from core.cssl import resolve_trait_ids

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    ids = resolve_trait_ids(["resilience", "curiosity"], cursor)
    cursor.close()
    conn.close()

    assert isinstance(ids, list)
    assert all(isinstance(i, int) for i in ids)


@DB_SKIP
def test_cssl_query_no_params():
    """CSSL with empty params should return a tuple (list, float)."""
    from core.cssl import query

    results, rcs = query({}, limit=10)
    assert isinstance(results, list)
    assert isinstance(rcs, float)
    assert 0.0 <= rcs <= 1.0


@DB_SKIP
def test_cssl_age_filter():
    """Age overlap filter should only return programs within age range."""
    from core.cssl import query

    params = {"age_from": 8, "age_to": 10}
    results, _ = query(params, limit=20)

    for r in results:
        if r.get("age_from") is not None and r.get("age_to") is not None:
            # Program must overlap with [8, 10]
            assert r["age_from"] <= 10, f"Program age_from {r['age_from']} > query age_to 10"
            assert r["age_to"] >= 8, f"Program age_to {r['age_to']} < query age_from 8"


@DB_SKIP
def test_cssl_gender_filter():
    """Gender filter should only return Coed (0) or matching gender."""
    from core.cssl import query

    params = {"gender": "Girls"}
    results, _ = query(params, limit=20)

    for r in results:
        gender = r.get("gender")
        if gender is not None:
            assert gender in (0, 2), f"Unexpected gender {gender} for Girls filter"


@DB_SKIP
def test_cssl_location_filter():
    """City filter should only return programs from that city."""
    from core.cssl import query

    params = {"city": "Toronto"}
    results, _ = query(params, limit=20)

    for r in results:
        assert r["city"] == "Toronto", f"Got city {r['city']!r} for Toronto filter"


@DB_SKIP
def test_cssl_tier_ordering():
    """Results should be ordered gold > silver > bronze by tier."""
    from core.cssl import query

    results, _ = query({}, limit=50)

    tier_order = {"gold": 0, "silver": 1, "bronze": 2}
    previous_rank = -1
    for r in results:
        tier = r.get("tier", "bronze")
        rank = tier_order.get(tier, 2)
        assert rank >= previous_rank, (
            f"Tier ordering violated: {tier!r} after rank {previous_rank}"
        )
        previous_rank = rank


@DB_SKIP
def test_cssl_calculate_rcs_empty():
    """RCS for empty results should be 0.0."""
    from core.cssl import calculate_rcs

    assert calculate_rcs([], {}, []) == 0.0


@DB_SKIP
def test_cssl_calculate_rcs_many():
    """RCS for 20+ results should be >= 0.90."""
    from core.cssl import calculate_rcs

    fake_results = [{"tier": "bronze"}] * 20
    rcs = calculate_rcs(fake_results, {}, [1, 2])
    assert rcs >= 0.90
