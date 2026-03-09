"""
core/session_manager.py
Session Manager — manages conversational context across turns.
Uses Streamlit session_state. Zero infrastructure cost.
"""
import streamlit as st
from dataclasses import asdict
from core.intent_parser import IntentResult


def init_session():
    """Initialize session state on first load."""
    if "session_context" not in st.session_state:
        st.session_state.session_context = {
            "accumulated_params": {},
            "query_history": [],
            "results_shown": [],
            "pending_suggestion": None,
            "refinement_count": 0,
            "raw_query": "",
        }


def merge_intent(intent: IntentResult) -> dict:
    """
    Merge new intent with accumulated session parameters.
    New non-null/non-empty values override accumulated; session fills gaps.
    Returns merged parameters dict ready for CSSL.
    """
    session = st.session_state.session_context
    acc = session["accumulated_params"].copy()
    new = asdict(intent)

    # When the parser completely failed, don't let stale activity params bleed in
    if not intent.recognized:
        for k in ("tags", "exclude_tags", "type"):
            acc.pop(k, None)

    # RC-4: Clear stale exclude_tags when user switches to a completely different activity
    new_tags = new.get("tags") or []
    acc_tags = acc.get("tags") or []
    if new_tags and acc_tags and not (set(new_tags) & set(acc_tags)):
        acc.pop("exclude_tags", None)

    # Scalars: override on any non-None value (allows setting False, 0, etc.)
    for key in [
        "age_from", "age_to", "cost_max", "is_special_needs", "is_virtual",
        "language_immersion", "city", "province", "type", "gender",
    ]:
        val = new.get(key)
        if val is not None:
            acc[key] = val

    # Lists: override only if non-empty (empty list = "no new info")
    for key in ["tags", "exclude_tags", "cities", "traits"]:
        val = new.get(key)
        if val:
            acc[key] = val

    # Store raw_query immutably
    session["raw_query"] = intent.raw_query
    session["accumulated_params"] = acc
    session["query_history"].append(intent.raw_query)
    session["refinement_count"] += 1

    return acc


def store_suggestion(suggestion: dict):
    """Store a structured suggestion for affirmative acceptance."""
    st.session_state.session_context["pending_suggestion"] = suggestion


def clear_suggestion():
    """Clear pending suggestion after execution."""
    st.session_state.session_context["pending_suggestion"] = None


def store_results(program_ids: list[int]):
    """Track which programs user has seen."""
    shown = st.session_state.session_context["results_shown"]
    shown.extend(p for p in program_ids if p not in shown)
