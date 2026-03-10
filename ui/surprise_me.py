"""
ui/surprise_me.py
"Surprise Me" button that generates a random camp search.
"""
import random
import streamlit as st

# Only provinces with meaningful camp data in our DB
_PROVINCES = [
    "Ontario", "Ontario", "Ontario",  # weighted — ~85% of inventory
    "British Columbia", "Quebec", "Alberta",
]


def _get_random_tag() -> str | None:
    """Pick a random active activity tag slug from the DB."""
    try:
        from db.connection import get_connection
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT slug FROM activity_tags WHERE is_active = 1 AND level = 3 "
            "ORDER BY RAND() LIMIT 1"
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return row["slug"] if row else None
    except Exception:
        return None


def render_surprise_me(on_search_callback):
    """
    Render the Surprise Me button. Calls on_search_callback(query_str) on click.

    Args:
        on_search_callback: callable(query: str) that triggers the search pipeline
    """
    if st.button("Surprise Me!", key="surprise_me_btn"):
        tag = _get_random_tag()
        province = random.choice(_PROVINCES)

        if tag:
            query = f"{tag} camps in {province}"
        else:
            query = f"summer camps in {province}"

        st.session_state["_surprise_query"] = query
        st.session_state["_surprise_tag"] = tag
        st.session_state["_surprise_province"] = province
        st.session_state["_input_path_pending"] = "surprise_me"
        on_search_callback(query)

    if st.session_state.get("_surprise_results_heading"):
        st.markdown("### You might also love...")
