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

    # Override with new non-null values
    for key in [
        "tags", "exclude_tags", "age_from", "age_to", "city", "cities",
        "province", "type", "gender", "cost_max", "traits",
        "is_special_needs", "is_virtual", "language_immersion",
    ]:
        if new.get(key):
            acc[key] = new[key]

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
