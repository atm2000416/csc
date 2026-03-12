"""
core/session_manager.py
Session Manager — manages conversational context across turns.
Uses Streamlit session_state. Zero infrastructure cost.

Phase 1 bridge: QueryState is the canonical source of truth.
accumulated_params and pending_suggestion are derived mirrors — maintained for
backward compat with CSSL and any app.py callers not yet migrated to QueryState.
"""
import streamlit as st
from dataclasses import asdict
from core.intent_parser import IntentResult
from core.query_state import (
    QueryState, GeoScope, PendingAction, PendingActionType, ActionResolution, Provenance,
)


# ---------------------------------------------------------------------------
# Session init
# ---------------------------------------------------------------------------

def init_session() -> None:
    """Initialize session state on first load."""
    if "session_context" not in st.session_state:
        qs = QueryState()
        st.session_state.session_context = {
            "_query_state":    qs,
            "accumulated_params": {},
            "query_history":   [],
            "results_shown":   [],
            "pending_suggestion": None,
            "refinement_count": 0,
            "raw_query":       "",
        }
    # Schema mismatch guard: old pickled session pre-dates QueryState → migrate.
    elif not isinstance(
        st.session_state.session_context.get("_query_state"), QueryState
    ):
        session = st.session_state.session_context
        qs = QueryState.from_flat_dict(
            session.get("accumulated_params", {}),
            turn=session.get("refinement_count", 0),
        )
        session["_query_state"] = qs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def get_query_state() -> QueryState:
    """Return the canonical QueryState for this session."""
    return st.session_state.session_context["_query_state"]


def sync_mirror() -> None:
    """
    Rebuild accumulated_params and pending_suggestion from QueryState.
    These are output-only mirrors. NEVER mutate them directly elsewhere.
    """
    session = st.session_state.session_context
    qs: QueryState = session["_query_state"]

    session["accumulated_params"] = qs.to_cssl_params()

    if qs.pending_action is not None:
        # Minimal legacy-compatible shape for app.py readers.
        session["pending_suggestion"] = {
            "action_id":  qs.pending_action.action_id,
            "type":       qs.pending_action.type.value,
            "parameters": qs.pending_action.parameters,
            "message":    qs.pending_action.message_shown,
        }
    else:
        session["pending_suggestion"] = None


def _build_geo_scope(new: dict) -> GeoScope | None:
    """
    Extract geo keys from a flat intent dict and return a GeoScope.
    Only includes keys that are actually present in the intent.
    Returns None when no geo information is present.

    Coordinate invalidation and province-reset are implicit here:
    lat/lon are only included when the intent actually provided them,
    so a new city name with no lat/lon correctly yields a city-only scope.
    """
    scope: dict = {}
    if new.get("city"):
        scope["city"] = new["city"]
    if new.get("cities"):
        scope["cities"] = new["cities"]
    if new.get("province"):
        scope["province"] = new["province"]
    if new.get("lat") is not None:
        scope["lat"]       = new["lat"]
        scope["lon"]       = new["lon"]
        if new.get("radius_km"):
            scope["radius_km"] = new["radius_km"]
    return scope if scope else None  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Main merge
# ---------------------------------------------------------------------------

def merge_intent(intent: IntentResult) -> dict:
    """
    Merge new intent into the accumulated QueryState.
    All state changes go through QueryState mutation methods.
    Returns the derived flat dict (to_cssl_params()) for backward compat.
    """
    session  = st.session_state.session_context
    qs: QueryState = session["_query_state"]
    new = asdict(intent)

    # Advance monotonic turn counter before any mutations.
    qs.turn += 1
    qs.expire_pending_action_if_stale()

    # ------------------------------------------------------------------
    # Clear rules — before new values are applied.
    # ------------------------------------------------------------------

    # Rule 1: intent parser genuinely failed to understand query (not API error).
    # Clear stale activity so it doesn't bleed into an unrelated search.
    # ics=0.3 is the hardcoded API-failure fallback — do not clear on that.
    if not intent.recognized and intent.ics > 0.3:
        for f in ("tags", "exclude_tags", "type"):
            if getattr(qs, f) is not None:
                qs.clear_field(f)

    # Rule 2: model recognised query but found no taxonomy match at medium-low
    # confidence → the user searched something we can't map. Clear stale tags.
    if not intent.tags and 0.3 < intent.ics < 0.7:
        for f in ("tags", "exclude_tags"):
            if getattr(qs, f) is not None:
                qs.clear_field(f)

    # Rule 3: explicit fresh-search signal — clear activity and dates, keep geo.
    if intent.clear_activity:
        qs.clear_activity()

    # ------------------------------------------------------------------
    # Activity-switch detection (RC-4) — must read acc_tags BEFORE
    # applying new tags so comparison is against the prior state.
    # ------------------------------------------------------------------
    new_tags = new.get("tags") or []
    acc_tags = qs.tags.value if qs.tags is not None else []
    activity_switched = bool(
        new_tags and acc_tags and not (set(new_tags) & set(acc_tags))
    )
    if activity_switched:
        if qs.exclude_tags is not None:
            qs.clear_field("exclude_tags")

    # ------------------------------------------------------------------
    # Apply new list fields.
    # Lists: override only if non-empty (empty = "no new info").
    # ------------------------------------------------------------------
    for key in ("tags", "exclude_tags", "traits"):
        val = new.get(key)
        if val:
            qs.apply_inferred_update(key, val)

    # ------------------------------------------------------------------
    # Apply new scalar fields (non-geo).
    # Scalars: override on any non-None value (allows False, 0, etc.)
    # is_special_needs and is_virtual default to False in IntentResult,
    # so a False here actively clears a prior True — matching legacy behavior.
    # ------------------------------------------------------------------
    for key in ("type", "gender", "language_immersion",
                "age_from", "age_to", "cost_max",
                "date_from", "date_to",
                "is_special_needs", "is_virtual"):
        val = new.get(key)
        if val is not None:
            qs.apply_inferred_update(key, val)

    # ------------------------------------------------------------------
    # RC-4 post-merge: if the activity switched, strip any type/dates
    # that the scalar merge re-inherited from session context.
    # Guard: only strip if the model did NOT explicitly state them.
    # ------------------------------------------------------------------
    if activity_switched:
        if new.get("date_from") is None and qs.date_from is not None:
            qs.clear_field("date_from")
        if new.get("date_to") is None and qs.date_to is not None:
            qs.clear_field("date_to")
        if new.get("type") is None and qs.type is not None:
            qs.clear_field("type")

    # ------------------------------------------------------------------
    # Geography — build a GeoScope from intent and call replace_geo()
    # if any geo field is present in this turn's intent.
    # replace_geo() handles anchor update + broadening_history reset.
    # Coordinate invalidation and province-reset are implicit: only keys
    # actually present in the intent appear in the scope.
    # ------------------------------------------------------------------
    geo_scope = _build_geo_scope(new)
    if geo_scope is not None:
        qs.replace_geo(geo_scope)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Session bookkeeping.
    # ------------------------------------------------------------------
    session["raw_query"] = intent.raw_query
    session["query_history"].append(intent.raw_query)
    session["refinement_count"] += 1

    sync_mirror()
    return session["accumulated_params"]


# ---------------------------------------------------------------------------
# Suggestion helpers — backward compat wrappers around PendingAction.
# ---------------------------------------------------------------------------

def store_suggestion(suggestion: dict) -> None:
    """
    Create a PendingAction from a legacy suggestion dict and store it.
    Phase 1 bridge: converts the loose dict to a typed PendingAction.
    """
    qs = get_query_state()

    action_type_str = suggestion.get("type", "")
    try:
        action_type = PendingActionType(action_type_str)
    except ValueError:
        action_type = PendingActionType.ADD_FILTER  # safe default

    action = PendingAction(
        type=action_type,
        parameters=suggestion.get("parameters") or suggestion,
        suggested_at_turn=qs.turn,
        message_shown=suggestion.get("message", ""),
        expires_after_turn=qs.turn + 2,
    )
    qs.set_pending_action(action)
    sync_mirror()


def clear_suggestion() -> None:
    """Clear pending action/suggestion after execution."""
    qs = get_query_state()
    if qs.pending_action is not None:
        qs.clear_pending_action(ActionResolution.ACCEPT)
    sync_mirror()


# ---------------------------------------------------------------------------
# Results tracking
# ---------------------------------------------------------------------------

def store_results(program_ids: list[int]) -> None:
    """Track which programs the user has seen."""
    shown = st.session_state.session_context["results_shown"]
    shown.extend(p for p in program_ids if p not in shown)
