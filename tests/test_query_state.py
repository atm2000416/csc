"""
tests/test_query_state.py
Invariant tests for QueryState.
These are architectural contracts — if any fail, the build fails.
"""
import pytest
from core.query_state import (
    QueryState, GeoState, GeoScope, FieldValue, PendingAction,
    Provenance, PendingActionType, ActionResolution,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_geo_action(type_=PendingActionType.GEO_BROADEN_PROVINCE,
                     to_province="Ontario") -> PendingAction:
    return PendingAction(
        type=type_,
        parameters={"to_province": to_province},
        suggested_at_turn=0,
    )

def _make_scope(city="Toronto", province="Ontario") -> GeoScope:
    return {"city": city, "province": province}  # type: ignore


# ---------------------------------------------------------------------------
# Invariant: turn never decreases
# ---------------------------------------------------------------------------

def test_turn_never_decreases():
    qs = QueryState()
    qs.turn = 5
    qs.start_new_search()
    assert qs.turn == 5, "start_new_search() must not reset turn"


def test_start_new_search_does_not_reset_turn():
    qs = QueryState()
    for i in range(1, 6):
        qs.turn = i
    qs.start_new_search()
    assert qs.turn == 5


# ---------------------------------------------------------------------------
# Invariant: search_id changes only on start_new_search()
# ---------------------------------------------------------------------------

def test_search_id_stable_across_mutations():
    qs = QueryState()
    sid = qs.search_id
    qs.turn = 1
    qs.apply_inferred_update("type", "Day")
    qs.apply_inferred_update("age_from", 8)
    assert qs.search_id == sid, "search_id must not change on normal mutations"


def test_search_id_changes_on_start_new_search():
    qs = QueryState()
    sid = qs.search_id
    qs.start_new_search()
    assert qs.search_id != sid, "start_new_search() must mint a new search_id"


def test_search_id_changes_only_on_start_new_search():
    qs = QueryState()
    sid = qs.search_id
    qs.replace_geo(_make_scope())
    qs.apply_inferred_update("tags", ["hockey"])
    assert qs.search_id == sid
    qs.start_new_search()
    assert qs.search_id != sid


# ---------------------------------------------------------------------------
# Invariant: broaden_geo() never mutates original_anchor
# ---------------------------------------------------------------------------

def test_broaden_geo_never_mutates_original_anchor():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    original = dict(qs.geo.original_anchor)

    qs.turn = 2
    action = _make_geo_action(PendingActionType.GEO_BROADEN_PROVINCE, "Ontario")
    qs.broaden_geo(action)

    assert qs.geo.original_anchor["city"] == "Toronto", \
        "broaden_geo() must not overwrite original_anchor"
    assert dict(qs.geo.original_anchor) == original


def test_broaden_geo_updates_current_scope():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    qs.turn = 2
    action = _make_geo_action(PendingActionType.GEO_BROADEN_PROVINCE, "Ontario")
    qs.broaden_geo(action)

    assert qs.geo.current_scope.get("city") is None
    assert qs.geo.current_scope.get("province") == "Ontario"


def test_broaden_geo_appends_to_history():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    assert len(qs.geo.broadening_history) == 0

    qs.turn = 2
    qs.broaden_geo(_make_geo_action())
    assert len(qs.geo.broadening_history) == 1


# ---------------------------------------------------------------------------
# Invariant: replace_geo() always resets broadening_history
# ---------------------------------------------------------------------------

def test_replace_geo_resets_broadening_history():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    qs.turn = 2
    qs.broaden_geo(_make_geo_action())
    assert len(qs.geo.broadening_history) == 1

    qs.turn = 3
    qs.replace_geo(_make_scope("Ottawa", "Ontario"))
    assert len(qs.geo.broadening_history) == 0, \
        "replace_geo() must always reset broadening_history"


def test_replace_geo_replaces_anchor():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    assert qs.geo.original_anchor["city"] == "Toronto"

    qs.turn = 2
    qs.replace_geo(_make_scope("Ottawa", "Ontario"))
    assert qs.geo.original_anchor["city"] == "Ottawa", \
        "replace_geo() must update original_anchor"


# ---------------------------------------------------------------------------
# Invariant: pending_action cleared after ACCEPT and REJECT
# ---------------------------------------------------------------------------

def test_pending_action_cleared_after_accept():
    qs = QueryState()
    qs.turn = 1
    action = _make_geo_action()
    qs.set_pending_action(action)
    assert qs.pending_action is not None

    qs.clear_pending_action(ActionResolution.ACCEPT)
    assert qs.pending_action is None, \
        "pending_action must be None after ACCEPT"


def test_pending_action_cleared_after_reject():
    qs = QueryState()
    qs.turn = 1
    qs.set_pending_action(_make_geo_action())
    qs.clear_pending_action(ActionResolution.REJECT)
    assert qs.pending_action is None, \
        "pending_action must be None after REJECT"


def test_pending_action_resolution_recorded():
    qs = QueryState()
    qs.turn = 1
    action = _make_geo_action()
    action_id = action.action_id
    qs.set_pending_action(action)
    # Resolution is stored on the action before clearing
    qs.pending_action.resolution = ActionResolution.ACCEPT
    assert qs.pending_action.resolution == ActionResolution.ACCEPT


# ---------------------------------------------------------------------------
# Invariant: accumulated_params (to_cssl_params) regenerated from QueryState
# ---------------------------------------------------------------------------

def test_to_cssl_params_reflects_current_state():
    qs = QueryState()
    qs.turn = 1
    qs.apply_inferred_update("tags", ["hockey"])
    qs.replace_geo(_make_scope("Toronto", "Ontario"))

    params = qs.to_cssl_params()
    assert params["tags"] == ["hockey"]
    assert params["city"] == "Toronto"
    assert params["province"] == "Ontario"


def test_to_cssl_params_updates_after_broadening():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    qs.turn = 2
    qs.broaden_geo(_make_geo_action(PendingActionType.GEO_BROADEN_PROVINCE, "Ontario"))

    params = qs.to_cssl_params()
    assert "city" not in params
    assert params["province"] == "Ontario"


def test_to_cssl_params_clears_after_clear_activity():
    qs = QueryState()
    qs.turn = 1
    qs.apply_inferred_update("tags", ["hockey"])
    qs.apply_inferred_update("type", "Day")
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    qs.clear_activity()

    params = qs.to_cssl_params()
    assert "tags" not in params
    assert "type" not in params
    assert params.get("city") == "Toronto", "geo preserved after clear_activity()"


def test_to_cssl_params_does_not_emit_none_geo_keys():
    qs = QueryState()
    params = qs.to_cssl_params()
    for geo_key in ("lat", "lon", "radius_km", "city", "cities", "province"):
        assert geo_key not in params, f"{geo_key} should not appear when not set"


# ---------------------------------------------------------------------------
# Geo anchor semantics
# ---------------------------------------------------------------------------

def test_original_anchor_set_on_first_replace_geo():
    qs = QueryState()
    assert qs.geo.original_anchor is None

    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    assert qs.geo.original_anchor is not None
    assert qs.geo.original_anchor["city"] == "Toronto"


def test_original_anchor_records_turn():
    qs = QueryState()
    qs.turn = 3
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    assert qs.geo.original_anchor["turn"] == 3


def test_original_anchor_cleared_by_start_new_search():
    qs = QueryState()
    qs.turn = 1
    qs.replace_geo(_make_scope("Toronto", "Ontario"))
    qs.start_new_search()
    assert qs.geo.original_anchor is None, \
        "start_new_search() must clear original_anchor"


# ---------------------------------------------------------------------------
# from_flat_dict round-trip
# ---------------------------------------------------------------------------

def test_from_flat_dict_basic():
    d = {
        "tags": ["hockey"],
        "city": "Toronto",
        "province": "Ontario",
        "age_from": 8,
        "age_to": 12,
        "type": "Day",
    }
    qs = QueryState.from_flat_dict(d, turn=3)

    assert qs.tags.value == ["hockey"]
    assert qs.tags.provenance == Provenance.CARRIED
    assert qs.age_from.value == 8
    assert qs.geo.current_scope["city"] == "Toronto"
    assert qs.geo.original_anchor["city"] == "Toronto"
    assert qs.turn == 3


def test_from_flat_dict_to_cssl_params_roundtrip():
    d = {
        "tags": ["soccer"],
        "city": "Ottawa",
        "province": "Ontario",
        "age_from": 10,
        "age_to": 14,
    }
    qs = QueryState.from_flat_dict(d, turn=1)
    result = qs.to_cssl_params()

    assert result["tags"] == ["soccer"]
    assert result["city"] == "Ottawa"
    assert result["age_from"] == 10


def test_from_flat_dict_empty():
    qs = QueryState.from_flat_dict({})
    assert qs.tags is None
    assert qs.geo.original_anchor is None
    params = qs.to_cssl_params()
    assert params == {}


# ---------------------------------------------------------------------------
# Pending action expiry
# ---------------------------------------------------------------------------

def test_pending_action_expires():
    qs = QueryState()
    qs.turn = 1
    action = PendingAction(
        type=PendingActionType.GEO_BROADEN_PROVINCE,
        parameters={"to_province": "Ontario"},
        suggested_at_turn=1,
        expires_after_turn=2,
    )
    qs.set_pending_action(action)
    qs.turn = 3
    qs.expire_pending_action_if_stale()
    assert qs.pending_action is None, "pending_action must be cleared after expiry"


def test_pending_action_not_expired_within_window():
    qs = QueryState()
    qs.turn = 1
    action = PendingAction(
        type=PendingActionType.GEO_BROADEN_PROVINCE,
        parameters={"to_province": "Ontario"},
        suggested_at_turn=1,
        expires_after_turn=3,
    )
    qs.set_pending_action(action)
    qs.turn = 2
    qs.expire_pending_action_if_stale()
    assert qs.pending_action is not None


# ---------------------------------------------------------------------------
# Mutation audit trail
# ---------------------------------------------------------------------------

def test_audit_trail_records_mutations():
    qs = QueryState()
    qs.turn = 1
    qs.apply_inferred_update("tags", ["hockey"])
    qs.replace_geo(_make_scope("Toronto", "Ontario"))

    log = qs.get_audit_log()
    methods = [e["method"] for e in log]
    assert "apply_inferred_update" in methods
    assert "replace_geo" in methods


def test_audit_trail_capped_at_50():
    qs = QueryState()
    for i in range(60):
        qs.turn = i
        qs.apply_inferred_update("tags", [f"tag_{i}"])

    assert len(qs.get_audit_log()) <= 50


def test_audit_trail_not_in_cssl_params():
    qs = QueryState()
    qs.apply_inferred_update("tags", ["arts"])
    params = qs.to_cssl_params()
    assert "_audit" not in params


# ---------------------------------------------------------------------------
# clear_activity preserves geo
# ---------------------------------------------------------------------------

def test_clear_activity_preserves_geo():
    qs = QueryState()
    qs.turn = 1
    qs.apply_inferred_update("tags", ["hockey"])
    qs.apply_inferred_update("type", "Overnight")
    qs.apply_inferred_update("date_from", "2026-07-01")
    qs.replace_geo(_make_scope("Toronto", "Ontario"))

    qs.clear_activity()

    assert qs.tags is None
    assert qs.type is None
    assert qs.date_from is None
    assert qs.geo.current_scope["city"] == "Toronto"


# ---------------------------------------------------------------------------
# start_new_search clears everything except turn
# ---------------------------------------------------------------------------

def test_start_new_search_clears_fields():
    qs = QueryState()
    qs.turn = 3
    qs.apply_inferred_update("tags", ["hockey"])
    qs.apply_inferred_update("age_from", 10)
    qs.replace_geo(_make_scope("Toronto", "Ontario"))

    qs.turn = 5
    qs.start_new_search()

    assert qs.tags is None
    assert qs.age_from is None
    assert qs.geo.original_anchor is None
    assert qs.geo.current_scope == {} or qs.geo.current_scope == GeoState().current_scope
    assert qs.turn == 5
