"""
core/interaction_logger.py
Non-critical async logging of search interactions to interaction_log table.
Never raises — all errors are silently swallowed.
"""
import json
import uuid
from config import get_secret


def _get_session_id() -> str:
    try:
        import streamlit as st
        if "session_id" not in st.session_state:
            st.session_state["session_id"] = str(uuid.uuid4())
        return st.session_state["session_id"]
    except Exception:
        return str(uuid.uuid4())


def log_search(
    session: dict,
    intent,
    rcs: float,
    result_count: int,
):
    """
    Log a search interaction to interaction_log.

    Args:
        session: session_context dict from session_manager
        intent: IntentResult dataclass
        rcs: Result Confidence Score float
        result_count: Number of results returned
    """
    if get_secret("LOG_INTERACTIONS", "true").lower() != "true":
        return

    try:
        from db.connection import get_connection
        conn = get_connection()
        cursor = conn.cursor()

        session_id = _get_session_id()
        raw_query = getattr(intent, "raw_query", "")
        intent_json = json.dumps({
            k: v for k, v in vars(intent).items()
            if k not in ("raw_query",)
        }, default=str)
        ics = getattr(intent, "ics", 0.0)
        refinement = session.get("refinement_count", 0)

        cursor.execute(
            """
            INSERT INTO interaction_log
                (session_id, raw_query, intent_json, ics, rcs, result_count, refinement)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (session_id, raw_query, intent_json, ics, rcs, result_count, refinement),
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception:
        pass
