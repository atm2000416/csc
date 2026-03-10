"""
ui/surprise_me.py
"Surprise Me" button — picks a random activity tag that has active camps in the
directory, queries CSSL directly (no LLM pipeline), and returns results with gold
tier camps first.
"""
import random
import streamlit as st

# Only provinces with meaningful camp data in our DB
_PROVINCES = [
    "Ontario", "Ontario", "Ontario",  # weighted — ~85% of inventory
    "British Columbia", "Quebec", "Alberta",
]

# Human-readable label for a tag slug shown in the user bubble
def _slug_to_label(slug: str) -> str:
    return slug.replace("-", " ").title()


def _pick_tag_with_camps() -> str | None:
    """
    Pick a random active tag slug that has at least 3 active camps in the DB.
    Weighted: tags with more gold/silver camps are slightly more likely to be chosen.
    Returns None on DB failure.
    """
    try:
        from db.connection import get_connection
        conn = get_connection()
        cur = conn.cursor(dictionary=True)
        # Pull up to 50 eligible tags at random; pick one weighted by tier richness
        cur.execute("""
            SELECT at.slug,
                   SUM(CASE WHEN c.tier = 'gold'   THEN 3
                            WHEN c.tier = 'silver' THEN 2
                            ELSE 1 END) AS weight
            FROM activity_tags at
            JOIN program_tags pt ON pt.tag_id = at.id
            JOIN programs p      ON pt.program_id = p.id AND p.status = 1
            JOIN camps c         ON p.camp_id = c.id     AND c.status = 1
            WHERE at.is_active = 1
            GROUP BY at.id
            HAVING COUNT(DISTINCT c.id) >= 3
            ORDER BY RAND()
            LIMIT 50
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        if not rows:
            return None
        # Weighted random choice (cast Decimal weights to float)
        weights = [float(r["weight"]) for r in rows]
        total = sum(weights)
        r = random.uniform(0, total)
        cumulative = 0.0
        for row, w in zip(rows, weights):
            cumulative += w
            if r <= cumulative:
                return row["slug"]
        return rows[-1]["slug"]
    except Exception:
        return None


def get_surprise_results(tag_slug: str, province: str | None, top_n: int = 10):
    """
    Query CSSL directly for camps tagged with tag_slug, optionally filtered by
    province. Returns (results list, rcs float). Results are already tier-sorted
    (gold first) by CSSL.
    """
    try:
        from core.cssl import query as cssl_query
        params = {"tags": [tag_slug]}
        if province:
            params["province"] = province
        results, rcs = cssl_query(params, limit=top_n)
        # CSSL already orders by tier score; enforce strictly in case of ties
        tier_order = {"gold": 0, "silver": 1, "bronze": 2}
        results.sort(key=lambda r: tier_order.get(r.get("tier", "bronze"), 2))
        return results[:top_n], rcs
    except Exception:
        return [], 0.0


def render_surprise_me(on_search_callback):
    """
    Render the Surprise Me button. On click, picks a tag with active DB camps,
    runs a direct CSSL query (bypassing the LLM pipeline), and stores results in
    session state for display by app.py.

    on_search_callback is kept for API compatibility but is not called.
    """
    if st.button("Surprise Me!", key="surprise_me_btn"):
        tag_slug = _pick_tag_with_camps()
        province = random.choice(_PROVINCES)

        if tag_slug:
            results, _ = get_surprise_results(tag_slug, province)
            # If no results for that province, retry without province filter
            if not results:
                results, _ = get_surprise_results(tag_slug, None)
                province = None
        else:
            results = []

        label = _slug_to_label(tag_slug) if tag_slug else "Summer"
        if province:
            display_query = f"{label} camps in {province}"
        else:
            display_query = f"{label} camps"

        st.session_state["_surprise_direct_results"] = results
        st.session_state["_surprise_query_label"]    = display_query
        st.session_state["_surprise_tag"]            = tag_slug
        st.session_state["_surprise_province"]       = province
        st.session_state["_input_path_pending"]      = "surprise_me"
        st.session_state["_surprise_results_heading"] = True
        st.rerun()

    if st.session_state.get("_surprise_results_heading"):
        st.markdown("### You might also love...")
