"""
app.py
Camp Search Concierge (CSC) — Streamlit entry point.
Orchestrates the full pipeline: fuzzy preprocessing → intent parsing →
session merge → cache check → CSSL → decision matrix → results.
"""
import datetime
import streamlit as st

from config import get_secret

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Camp Finder | camps.ca",
    page_icon="🏕️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800;900&family=Lato:wght@400;700&display=swap');

/* ── Base ── */
html, body, [class*="css"] {
    font-family: 'Lato', sans-serif;
    color: #333333;
    background-color: #F5F5F5;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Custom topbar (navy) ── */
.camps-topbar {
    background: #336699;
    padding: 0 1.5rem;
    height: 72px;
    width: 100%;
    display: flex;
    align-items: center;
    position: fixed;
    top: 0;
    left: 0;
    z-index: 1000;
    box-shadow: 0 2px 12px rgba(0,0,0,0.15);
}

/* Push content below the fixed header */
.main-content {
    margin-top: 72px;
}
.camps-topbar .logo {
    font-family: 'Nunito', sans-serif;
    font-weight: 900;
    font-size: 1.5rem;
    color: white;
    letter-spacing: -0.3px;
}
.camps-topbar .logo em {
    color: #ffd166;
    font-style: normal;
}
.camps-topbar .badge {
    margin-left: 10px;
    background: rgba(255,255,255,0.2);
    color: white;
    font-family: 'Nunito', sans-serif;
    font-weight: 800;
    font-size: 0.65rem;
    padding: 2px 9px;
    border-radius: 12px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    border: 1px solid rgba(255,255,255,0.3);
}

/* ── Topbar reset button ── */
.topbar-reset {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: rgba(255,255,255,0.15);
    color: white !important;
    font-size: 1.1rem;
    text-decoration: none !important;
    border: 1px solid rgba(255,255,255,0.3);
    cursor: pointer;
    transition: background 0.15s ease;
}
.topbar-reset:hover {
    background: rgba(255,255,255,0.3) !important;
    color: white !important;
    text-decoration: none !important;
}

/* ── Surprise Me chip ── */
.surprise-chip-row {
    text-align: center;
    margin-bottom: 8px;
}
.surprise-chip {
    display: inline-flex;
    align-items: center;
    padding: 6px 16px;
    border-radius: 20px;
    background: #F5F5F5;
    color: #D93600 !important;
    font-family: 'Nunito', sans-serif;
    font-weight: 700;
    font-size: 0.84rem;
    text-decoration: none !important;
    border: 1px solid #CCCCCC;
    cursor: pointer;
    transition: border-color 0.15s ease;
}
.surprise-chip:hover {
    border-color: #D93600 !important;
    text-decoration: none !important;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: white !important;
    border-right: 1px solid #CCCCCC;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-family: 'Nunito', sans-serif;
    font-weight: 800;
    font-size: 0.95rem;
    color: white;
    background: #336699;
    margin: -1rem -1rem 1rem -1rem;
    padding: 0.9rem 1rem;
    border-radius: 0 0 12px 12px;
}
[data-testid="stSidebar"] label {
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    color: #333333 !important;
    font-family: 'Nunito', sans-serif !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="stSidebar"] .stSlider,
[data-testid="stSidebar"] .stSelectbox,
[data-testid="stSidebar"] .stNumberInput {
    margin-bottom: 0.8rem;
}

/* ── Main content area ── */
.main-content {
    max-width: 860px;
    margin: 1.5rem auto 6rem;
    padding: 0 1.2rem;
    margin-top: 88px;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0;
    margin-bottom: 0.4rem;
}

/* ── Chat input — white dock with top border ── */
section[data-testid="stBottom"] {
    background: #FFFFFF !important;
    border-top: 1px solid #CCCCCC !important;
    box-shadow: none !important;
}
section[data-testid="stBottom"] > div,
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}
[data-testid="stChatInput"] textarea {
    border: 2px solid #336699 !important;
    border-radius: 28px !important;
    font-family: 'Lato', sans-serif !important;
    font-size: 0.92rem !important;
    padding: 0.55rem 1.1rem !important;
    background: white !important;
    color: #333333 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #D93600 !important;
    box-shadow: 0 0 0 3px rgba(217,54,0,0.15) !important;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Nunito', sans-serif !important;
    font-weight: 700 !important;
    border-radius: 24px !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 1rem !important;
    border: none !important;
    color: white !important;
    background: #336699 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    background: #2a5580 !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.18) !important;
    transform: translateY(-1px);
}

/* ── Link buttons ── */
.stLinkButton a {
    font-family: 'Nunito', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.78rem !important;
    border-radius: 24px !important;
    background: #336699 !important;
    color: white !important;
    border: none !important;
    padding: 0.3rem 0.9rem !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12) !important;
    transition: all 0.15s ease;
}
.stLinkButton a:hover {
    background: #2a5580 !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.18) !important;
    transform: translateY(-1px);
}

/* ── Result count ── */
.result-count {
    padding: 0 1.4rem;
    font-family: 'Nunito', sans-serif;
    font-size: 0.78rem;
    font-weight: 800;
    color: #336699;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.8rem;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: #336699 !important;
}

/* ── Selectbox / inputs ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    border: 1.5px solid #CCCCCC !important;
    border-radius: 10px !important;
    font-size: 0.88rem !important;
}

/* ── Sticky filter bar ── */
[data-testid="stExpander"] {
    position: sticky;
    top: 72px;
    z-index: 900;
    margin-top: 0;
    background: white;
    border-bottom: 1px solid #CCCCCC;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

/* ── Previous searches ── */
.prev-search {
    font-family: 'Lato', sans-serif;
    font-size: 0.82rem;
    color: #555555;
    margin: 0 1.4rem 8px;
    cursor: pointer;
}
.prev-search summary {
    list-style: none;
}
.prev-search summary::-webkit-details-marker {
    display: none;
}

/* ── Dividers ── */
hr { border-color: #CCCCCC !important; margin: 0.8rem 0 !important; }

/* ── Mobile — tablet (≤768px) ── */
@media (max-width: 768px) {
    .camps-topbar {
        padding: 0 0.75rem;
        height: 60px;
    }
    .camps-topbar .logo {
        font-size: 1.25rem;
    }
    .camps-topbar .badge {
        display: none;
    }
    .main-content {
        padding: 0 0.6rem;
        margin-top: 76px;
    }
    [data-testid="stExpander"] {
        top: 60px !important;
    }
    /* Larger touch targets for link buttons */
    .stLinkButton a {
        padding: 0.55rem 1rem !important;
        font-size: 0.84rem !important;
        min-height: 44px !important;
        display: inline-flex !important;
        align-items: center !important;
    }
    /* Larger touch targets for st.buttons */
    .stButton > button {
        padding: 0.55rem 1.1rem !important;
        min-height: 44px !important;
    }
    /* Chat input larger tap target */
    [data-testid="stChatInput"] textarea {
        font-size: 1rem !important;
        padding: 0.7rem 1.1rem !important;
    }
}

/* ── Mobile — phone (≤480px) ── */
@media (max-width: 480px) {
    .camps-topbar .logo {
        font-size: 1.15rem;
    }
    .main-content {
        padding: 0 0.4rem;
    }
    /* Full-width chat bubbles */
    [data-testid="stChatMessage"] > div {
        max-width: 92% !important;
    }
    /* Reduce card outer padding */
    .result-count {
        padding: 0 0.5rem;
    }
}
</style>
""", unsafe_allow_html=True)

# ── Imports (after page config) ───────────────────────────────────────────────
from core.session_manager import (
    init_session, merge_intent, store_suggestion, clear_suggestion, store_results,
    get_query_state, sync_mirror,
)
from core.fuzzy_preprocessor import preprocess
from core.intent_parser import parse_intent
from core.cssl import query as cssl_query
from core.decision_matrix import decide, Route
from core.diversity_filter import apply as diversity_filter
from core.reranker import rerank
from core.semantic_cache import build_cache_key, get_cached, set_cache
from core.interaction_logger import log_search
from core.casl import expand as casl_expand
from core.zero_results_advisor import diagnose
from core.tracer import init_trace, record, render_trace
from core.category_disambiguator import get_broad_parent, get_viable_children
from core.concierge_response import generate as generate_concierge_response
from ui.results_card import render_card, render_compact_card, render_extra_sessions
from ui.filter_sidebar import render_filters, get_filter_values
from ui.clarification_widget import render_clarification
from ui.surprise_me import render_surprise_me  # noqa: F401 — kept for compat


# ── DB health check ───────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _check_db() -> tuple[bool, str]:
    try:
        from db.connection import get_connection
        conn = get_connection()
        cursor = conn.cursor(buffered=True)
        cursor.execute("SELECT 1")
        cursor.fetchall()
        cursor.close()
        conn.close()
        return True, ""
    except Exception as e:
        return False, str(e)


@st.cache_resource(show_spinner=False)
def _check_camps_table() -> bool:
    try:
        from db.connection import get_connection
        conn = get_connection()
        cursor = conn.cursor(buffered=True)
        cursor.execute("SELECT 1 FROM camps LIMIT 1")
        cursor.fetchall()
        cursor.close()
        conn.close()
        return True
    except Exception:
        return False


# ── Result processing ─────────────────────────────────────────────────────────
def process_results(results: list[dict], raw_query: str, intent_params: dict) -> list[dict]:
    """
    Tiered ranking pipeline:
      1. Diversity filter → 1 best program per camp
      2. Rerank all camps via Claude
      3. Gold camps: ALL shown (they paid for visibility)
      4. Silver/Bronze: only those scoring above the gold cohort average
         (silver > gold_avg, bronze > gold_avg + 0.05)
      5. Return two lists via a '_tier_section' field:
         'recommended' = gold + exceptional silver/bronze
         'more'        = remaining silver/bronze that cleared threshold
    """
    # Step 1: 1 program per camp for reranking
    diverse = diversity_filter(results, max_per_camp=1)

    # Step 2: Rerank all camps (up to 75 for broad queries)
    reranked = rerank(diverse, raw_query, intent_params, top_n=len(diverse))

    # Step 3: Separate by tier
    gold   = [r for r in reranked if r.get("tier") == "gold"]
    silver = [r for r in reranked if r.get("tier") == "silver"]
    bronze = [r for r in reranked if r.get("tier") == "bronze"]

    # Step 4: Calculate gold average score → threshold for silver/bronze
    gold_scores = [r.get("rerank_score", 0.0) for r in gold]
    gold_avg = sum(gold_scores) / len(gold_scores) if gold_scores else 0.5

    silver_threshold = gold_avg           # silver must beat gold average
    bronze_threshold = gold_avg + 0.05    # bronze must clearly outperform

    silver_in = [r for r in silver if r.get("rerank_score", 0.0) > silver_threshold]
    bronze_in = [r for r in bronze if r.get("rerank_score", 0.0) > bronze_threshold]

    # Step 5: Page 1 cap of 15 — gold first, then fill with silver/bronze
    PAGE_1_CAP = 15

    gold.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    silver_in.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
    bronze_in.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

    # Gold gets priority slots, silver/bronze fill remaining up to cap
    recommended = []
    more = []

    if len(gold) <= PAGE_1_CAP:
        # All gold fit on page 1 — fill remaining slots with best silver/bronze
        recommended = list(gold)
        remaining = PAGE_1_CAP - len(gold)
        # Merge silver + bronze by score for the fill slots
        fill_pool = sorted(silver_in + bronze_in,
                           key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        recommended.extend(fill_pool[:remaining])
        more = fill_pool[remaining:]
    else:
        # More gold than cap — top 15 gold on page 1, rest overflow
        recommended = gold[:PAGE_1_CAP]
        more = gold[PAGE_1_CAP:] + silver_in + bronze_in
        more.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

    for r in recommended:
        r["_tier_section"] = "recommended"
    for r in more:
        r["_tier_section"] = "more"

    return recommended + more


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_all_camp_programs(camp_id: int, exclude_program_id: int, camp_name: str,
                             search_params: dict | None = None) -> list[dict]:
    """
    Return active, non-expired programs for a camp that match the current search
    criteria, excluding the one already shown as the primary card and the generic
    placeholder (name=camp name).

    Applies tag, age, and type filters from search_params so only relevant
    sessions appear in the expander.
    """
    try:
        from db.connection import get_connection
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)

        conditions = [
            "p.camp_id = %s", "p.status = 1", "p.id != %s",
            "p.name != %s",
            "(p.end_date IS NULL OR p.end_date >= CURDATE())"
        ]
        args: list = [camp_id, exclude_program_id, camp_name]
        joins = ["JOIN camps c ON c.id = p.camp_id"]

        if search_params:
            # Tag filter — only show sessions tagged with the searched activity
            from core.cssl import resolve_tag_ids, expand_via_categories
            expanded = expand_via_categories(search_params.get("tags", []), cursor)
            tag_ids = resolve_tag_ids(expanded, cursor)
            if tag_ids:
                ph = ", ".join(["%s"] * len(tag_ids))
                conditions.append(
                    f"EXISTS (SELECT 1 FROM program_tags WHERE program_id = p.id "
                    f"AND tag_id IN ({ph}))"
                )
                args.extend(tag_ids)

            # Age overlap filter
            if (search_params.get("age_from") is not None
                    and search_params.get("age_to") is not None):
                conditions.append(
                    "(p.age_from IS NULL OR p.age_from <= %s) AND "
                    "(p.age_to IS NULL OR p.age_to >= %s)"
                )
                args.extend([search_params["age_to"], search_params["age_from"]])

            # Type filter
            _TYPE_MAP = {
                "Day":       "(FIND_IN_SET('1', p.type) OR p.type = 'Day Camp' OR p.type IS NULL)",
                "Overnight": "FIND_IN_SET('2', p.type)",
                "Both":      "(FIND_IN_SET('1', p.type) AND FIND_IN_SET('2', p.type))",
                "Virtual":   "FIND_IN_SET('4', p.type)",
            }
            if search_params.get("type") and search_params["type"] in _TYPE_MAP:
                conditions.append(_TYPE_MAP[search_params["type"]])

            # Gender filter
            _GENDER_MAP = {"Boys": 1, "Girls": 2}
            if (search_params.get("gender")
                    and search_params["gender"] in _GENDER_MAP):
                gval = _GENDER_MAP[search_params["gender"]]
                conditions.append(
                    "(p.gender = %s OR p.gender IS NULL OR p.gender = 0)"
                )
                args.append(gval)

        where = " AND ".join(conditions)
        joins_str = " ".join(joins)
        cursor.execute(
            f"SELECT p.id, p.name, p.type, p.age_from, p.age_to, "
            f"       p.cost_from, p.cost_to, p.start_date, p.end_date, "
            f"       p.ourkids_session_id, "
            f"       c.camp_name, c.tier, c.city, c.province, c.slug, c.prettyurl, c.website, "
            f"       p.camp_id "
            f"FROM programs p "
            f"{joins_str} "
            f"WHERE {where} "
            f"ORDER BY p.name",
            tuple(args)
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception:
        return []


def _partition_by_role(results: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Split CSSL results into specialty/category hits vs activity-only hits.
    _role_match: 0=specialty, 1=category, 2=activity, 3=no match (or missing).
    """
    specialty_hits = [r for r in results if r.get("_role_match") is not None
                      and r["_role_match"] <= 1]
    activity_hits  = [r for r in results if r.get("_role_match") is not None
                      and r["_role_match"] == 2]
    # If no role data (pre-migration), treat all as specialty
    if not specialty_hits and not activity_hits:
        return results, []
    return specialty_hits, activity_hits


def _maybe_offer_more_camps(pool: list[dict], final: list[dict],
                            raw_query: str, merged_params: dict,
                            activity_overflow: list[dict] | None = None) -> None:
    """
    If the CSSL pool contained more unique camps than we displayed,
    offer to show them via a conversational prompt.
    Called after display_results() for any route that shows results.

    activity_overflow: if provided, these are activity-role matches that were
    held back because enough specialty matches were available.
    """
    shown_camp_ids = {r.get("camp_id") for r in final}

    # Combine regular overflow with activity-role overflow
    overflow = [r for r in pool if r.get("camp_id") not in shown_camp_ids]
    if activity_overflow:
        activity_extra = [r for r in activity_overflow
                          if r.get("camp_id") not in shown_camp_ids]
        overflow = overflow + activity_extra

    n_more = len({r.get("camp_id") for r in overflow})
    if n_more <= 0:
        return
    tags = merged_params.get("tags", [])
    tag_label = tags[0].replace("-multi", "").replace("-", " ") if tags else "this activity"

    # If we held back activity matches, mention it specifically
    if activity_overflow:
        n_activity = len({r.get("camp_id") for r in activity_overflow
                          if r.get("camp_id") not in shown_camp_ids})
        if n_activity > 0:
            st.session_state["_more_camps_pool"]   = overflow
            st.session_state["_more_camps_query"]  = raw_query
            st.session_state["_more_camps_params"] = merged_params
            _speak(
                f"I also found **{n_activity} more camp{'s' if n_activity != 1 else ''}** "
                f"that offer {tag_label} as an activity. Would you like to see them?"
            )
            return

    st.session_state["_more_camps_pool"]   = overflow
    st.session_state["_more_camps_query"]  = raw_query
    st.session_state["_more_camps_params"] = merged_params
    _speak(
        f"I also found **{n_more} more camp{'s' if n_more != 1 else ''}** "
        f"with {tag_label} sessions. Would you like to see them?"
    )


def _save_to_search_history(query_label: str, count: int):
    """Push current results summary onto search history before overwriting."""
    if not query_label:
        return
    history = st.session_state.setdefault("_search_history", [])
    history.append({"query": query_label, "count": count})


def _render_search_history():
    """Render collapsed previous search summaries."""
    history = st.session_state.get("_search_history", [])
    if not history:
        return
    items = []
    for entry in reversed(history):
        items.append(
            f'<span style="color:#555555;">&#9656; Previous: '
            f'\'{entry["query"]}\' — {entry["count"]} results</span><br>'
        )
    st.markdown(
        f'<details class="prev-search"><summary style="color:#555555; '
        f'font-size:0.82rem; cursor:pointer;">&#9656; Previous searches '
        f'({len(history)})</summary>'
        f'<div style="padding:4px 0 4px 12px; font-size:0.8rem;">'
        f'{"".join(items)}</div></details>',
        unsafe_allow_html=True,
    )


def display_results(results: list[dict], search_params: dict | None = None,
                    is_new_search: bool = False):
    if not results:
        st.info("No camps found matching your search. Try adjusting your filters.")
        return

    # Save prior results to history before displaying new ones
    if is_new_search:
        prev_label = st.session_state.get("_last_query_label")
        prev_results = st.session_state.get("_last_results")
        if prev_label and prev_results:
            _save_to_search_history(prev_label, len(prev_results))

    # Resolve search_params: explicit arg > session state > None (unfiltered)
    if search_params is None:
        search_params = st.session_state.get("_last_search_params")

    # Render previous searches if any
    _render_search_history()

    # Split into recommended vs more by _tier_section tag
    recommended = [r for r in results if r.get("_tier_section") == "recommended"]
    more        = [r for r in results if r.get("_tier_section") == "more"]

    # Fallback: if no _tier_section tags (e.g. cached results), show all as recommended
    if not recommended and not more:
        recommended = results

    n_recommended = len(recommended)
    count_label = f'{n_recommended} camp{"s" if n_recommended != 1 else ""} found'

    # Scroll anchor — user sees top of results first
    st.markdown('<div id="results-top"></div>', unsafe_allow_html=True)
    st.markdown(f'<p class="result-count">{count_label}</p>', unsafe_allow_html=True)
    render_filters()

    # ── Section 1: Recommended Camps (full cards) ────────────────────────────
    for r in recommended:
        render_card(r)

        # Show extra sessions from the same camp
        camp_id   = r.get("camp_id")
        camp_name = r.get("camp_name", "")
        db_extras = _fetch_all_camp_programs(camp_id, r.get("id", -1), camp_name,
                                             search_params=search_params)
        if db_extras:
            render_extra_sessions(db_extras, camp_name, r.get("tier", "bronze"))

    # ── Section 2: More Camps That Match (collapsed expander) ───────────────
    if more:
        n_more = len(more)
        label = f"Show {n_more} more camp{'s' if n_more != 1 else ''} that match"
        with st.expander(label, expanded=False):
            for r in more:
                render_compact_card(r)

    # Scroll to top of results
    import streamlit.components.v1 as components
    components.html(
        '<script>var el=document.getElementById("results-top");'
        'if(el){el.scrollIntoView({behavior:"smooth"});}</script>',
        height=0,
    )


_BUBBLE_BASE = (
    "padding:12px 16px; max-width:75%; "
    "font-family:'Lato',sans-serif; font-size:0.95rem; line-height:1.55;"
)

_BUBBLE_ROW = "padding:0 1.4rem;"


_AVATAR_BASE = (
    "width:34px; height:34px; border-radius:50%; flex-shrink:0; "
    "display:flex; align-items:center; justify-content:center; "
    "font-size:17px; align-self:flex-end;"
)
_AVATAR_AI   = f"{_AVATAR_BASE} background:#336699;"
_AVATAR_USER = f"{_AVATAR_BASE} background:#336699;"


def _render_bubble(message: str, role: str):
    """Low-level bubble renderer — does not touch session state."""
    if not message:
        return
    if role == "assistant":
        st.markdown(
            f'<div style="display:flex; align-items:flex-end; gap:8px; '
            f'justify-content:flex-start; margin:0 0 0.8rem 0; {_BUBBLE_ROW}">'
            f'<div style="{_AVATAR_AI}">🏕</div>'
            f'<div style="background:#FFFFFF; color:#333333; '
            f'border-radius:18px 18px 18px 4px; box-shadow:0 1px 6px rgba(47,79,79,0.10); {_BUBBLE_BASE}">'
            f'{message}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="display:flex; align-items:flex-end; gap:8px; '
            f'justify-content:flex-end; margin:0 0 0.8rem 0; {_BUBBLE_ROW}">'
            f'<div style="background:#336699; color:white; '
            f'border-radius:18px 18px 4px 18px; {_BUBBLE_BASE}">'
            f'{message}</div>'
            f'<div style="{_AVATAR_USER}; color:white; font-size:13px; '
            f'font-family:Nunito,sans-serif; font-weight:800;">You</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _render_history():
    """Re-render all stored conversation messages."""
    for msg in st.session_state.get("_messages", []):
        _render_bubble(msg["content"], msg["role"])


def _speak(message: str):
    """Append CSC response to history and render it."""
    if message:
        st.session_state.setdefault("_messages", []).append(
            {"role": "assistant", "content": message}
        )
        _render_bubble(message, "assistant")


def _show_user_bubble(message: str):
    """Append user message to history and render it."""
    if message:
        st.session_state.setdefault("_messages", []).append(
            {"role": "user", "content": message}
        )
        _render_bubble(message, "user")


# ── Affirmative suggestion check ──────────────────────────────────────────────
_AFFIRMATIVE_WORDS = {"yes", "sure", "ok", "okay", "yeah", "yep", "please",
                      "go ahead", "show me", "show", "do it", "absolutely", "sounds good"}

def is_affirmative(text: str) -> bool:
    """Match affirmative responses even when extra words follow (e.g. 'yes, show them')."""
    normalized = text.strip().lower().rstrip(".,!")
    if normalized in _AFFIRMATIVE_WORDS:
        return True
    # Match if the first word is an affirmative (e.g. "yes please", "yes, show them")
    first_word = normalized.split()[0].rstrip(",.!") if normalized else ""
    if first_word in {"yes", "sure", "okay", "yeah", "yep"}:
        return True
    # Match show-intent phrases (e.g. "show me the 7 camps", "show them", "show me")
    if normalized.startswith("show"):
        return True
    return False


# ── Main app ──────────────────────────────────────────────────────────────────
def main():
    # Handle header button actions (HTML links pass ?action=... as query params)
    _action = st.query_params.get("action", "")
    if _action == "reset":
        st.query_params.clear()
        st.session_state.clear()
        st.rerun()
    if _action == "surprise":
        st.query_params.clear()
        from ui.surprise_me import run_surprise
        run_surprise()
        st.rerun()

    init_session()

    # Branded topbar with reset icon
    st.markdown("""
    <div class="camps-topbar">
        <span class="logo">camps<em>.ca</em></span>
        <span class="badge">AI Concierge</span>
        <div style="margin-left:auto; display:flex; align-items:center;">
            <a href="?action=reset" target="_self" class="topbar-reset" title="Start over">↺</a>
        </div>
    </div>
    <div class="main-content">
    """, unsafe_allow_html=True)

    # DB health check on first load
    db_ok, db_err = _check_db()
    if not db_ok:
        st.error(
            f"Database connection failed: {db_err}\n\n"
            "Check your secrets configuration and ensure the Aiven CA certificate is set."
        )
        st.stop()

    camps_ready = _check_camps_table()
    if not camps_ready:
        st.warning(
            "The database schema has not been initialized yet. "
            "Run `mysql ... < db/schema.sql` to set up the tables, "
            "then `python db/seed_tags.py` to seed activity tags."
        )

    # Read current filter values (widgets rendered later, inside display_results)
    sidebar_filters = get_filter_values()

    # "You might also love..." heading (shown after a Surprise Me result)
    if st.session_state.get("_surprise_results_heading"):
        st.markdown("### You might also love...")

    # Surprise Me chip — show when no results are displayed
    if not st.session_state.get("_last_results"):
        st.markdown(
            '<div class="surprise-chip-row">'
            '<a href="?action=surprise" target="_self" class="surprise-chip">'
            '✨ Surprise Me</a></div>',
            unsafe_allow_html=True,
        )

    # Chat input
    user_input = st.chat_input("Describe what you're looking for (e.g. hockey camp Toronto for my 10 year old)")

    # Handle category disambiguation button choice (no new chat input needed)
    if st.session_state.get("_disambiguation_choice") and not user_input:
        choice = st.session_state.pop("_disambiguation_choice")
        st.session_state.pop("_pending_category_picker", None)
        init_trace()
        # Persist chosen tags into QueryState so next typed turn inherits them.
        qs = get_query_state()
        qs.apply_inferred_update("tags", choice["params"]["tags"], source="category_disambiguation")
        sync_mirror()
        record("input", {"raw_query": choice["raw_query"], "path": "disambiguation",
                         "source": "category_disambiguation"})
        _render_history()
        _show_user_bubble(choice.get("label", choice["raw_query"]))
        _run_search(choice["params"], choice["raw_query"],
                    st.session_state.session_context, sidebar_filters)
        return

    # Handle direct surprise results (bypasses LLM pipeline entirely)
    if st.session_state.get("_surprise_direct_results") is not None and not user_input:
        surprise_results = st.session_state.pop("_surprise_direct_results")
        query_label      = st.session_state.pop("_surprise_query_label", "Surprise camps")
        st.session_state.pop("_disambiguated_tags", None)
        clear_suggestion()
        _render_history()
        _show_user_bubble(query_label)
        if surprise_results:
            st.session_state["_last_query_label"] = query_label
            st.session_state["_last_results"] = surprise_results
            display_results(surprise_results, is_new_search=True)
        else:
            _speak("I couldn't find camps for that combination — try searching manually!")
        return

    # Handle surprise query injection (legacy path — kept for safety)
    if st.session_state.get("_pending_query") and not user_input:
        user_input = st.session_state.pop("_pending_query")
        st.session_state["_surprise_results_heading"] = True
        st.session_state["_input_path"] = st.session_state.pop("_input_path_pending", "surprise_me")
        st.session_state.pop("_disambiguated_tags", None)  # fresh disambiguator on surprise
        # Keep location from prior session but clear all activity/filter params.
        qs = get_query_state()
        _prior_scope = {k: v for k, v in qs.geo.current_scope.items()
                        if k in ("city", "cities", "province")}
        qs.start_new_search()
        if _prior_scope:
            qs.replace_geo(_prior_scope)  # type: ignore[arg-type]
        sync_mirror()
    else:
        st.session_state.pop("_surprise_results_heading", None)

    if not user_input:
        messages = st.session_state.get("_messages", [])
        prior    = st.session_state.get("_last_results")
        if messages or prior:
            _render_history()
            if prior:
                display_results(prior)
            # Re-render disambiguation buttons if the user hasn't picked yet
            _render_pending_picker()
        else:
            st.markdown(
                '<p style="color:#78909c; font-size:0.92rem; margin-top:2rem; text-align:center;">'
                '🏕️ Tell me what you\'re looking for and I\'ll find the best camps for your child.'
                '</p>',
                unsafe_allow_html=True,
            )
        return

    session = st.session_state.session_context
    st.session_state.pop("_pending_category_picker", None)

    # Render prior conversation history, then show + store current user message
    _render_history()
    _show_user_bubble(user_input)

    # Show-more camps: user said yes to a previous "X more camps" offer
    if st.session_state.get("_more_camps_pool") and is_affirmative(user_input):
        overflow_pool   = st.session_state.pop("_more_camps_pool")
        overflow_query  = st.session_state.pop("_more_camps_query", user_input)
        overflow_params = st.session_state.pop("_more_camps_params", {})
        init_trace()
        with st.spinner("Finding more matches…"):
            more_final = process_results(overflow_pool, overflow_query, overflow_params)
        n_shown = len({r.get("camp_id") for r in more_final})
        _speak(f"Here are {n_shown} more camp{'s' if n_shown != 1 else ''}:")
        st.session_state["_last_query_label"] = overflow_query
        display_results(more_final, search_params=overflow_params, is_new_search=True)
        st.session_state["_last_results"] = more_final
        st.session_state["_last_search_params"] = overflow_params
        return

    # Affirmative suggestion check (geo-broaden)
    pending = session.get("pending_suggestion")
    if pending and is_affirmative(user_input):
        qs = get_query_state()
        init_trace()
        # Apply geo mutation before clearing the action so broaden_geo() can read it.
        _pa = qs.pending_action
        if _pa is not None and _pa.type.value in (
            "geo_broaden", "geo_broaden_province", "geo_broaden_radius"
        ):
            qs.broaden_geo(_pa)
        _p = _pa.parameters if _pa else {}
        record("input", {
            "raw_query": user_input,
            "path": "affirmative",
            "suggestion_type": pending.get("type"),
            "suggestion_detail": _p.get("to_city") or _p.get("to_province"),
            "sidebar_filters": sidebar_filters,
        })
        # clear_suggestion() resolves the pending_action and syncs mirrors.
        clear_suggestion()
        merged_params = dict(session["accumulated_params"])
        merged_params.update(sidebar_filters)
        record("merged_params", {"params": merged_params})
        _run_search(merged_params, user_input, session, sidebar_filters)
        return

    clear_suggestion()

    init_trace()
    input_path = st.session_state.pop("_input_path", "typed")
    input_record: dict = {"raw_query": user_input, "path": input_path,
                          "sidebar_filters": sidebar_filters}
    if input_path == "surprise_me":
        input_record["surprise_tag"] = st.session_state.pop("_surprise_tag", None)
        input_record["surprise_province"] = st.session_state.pop("_surprise_province", None)
    record("input", input_record)

    # Fuzzy preprocessing
    fuzzy_hints = preprocess(user_input)
    record("fuzzy_preprocessor", {"hints": fuzzy_hints})

    # Intent parsing
    with st.spinner("Thinking..."):
        intent = parse_intent(
            user_input,
            session_context=session,
            fuzzy_hints=fuzzy_hints,
            current_date=datetime.date.today().isoformat(),
        )

    # Inject geo coordinates from fuzzy hints directly — bypasses Claude API for
    # reliable lat/lon resolution without hallucination risk.
    if fuzzy_hints.get("geo_coords") and intent.lat is None:
        gc = fuzzy_hints["geo_coords"]
        intent.lat = gc["lat"]
        intent.lon = gc["lon"]
        intent.radius_km = gc["radius_km"]

    record("intent_parser", {
        "tags": intent.tags,
        "exclude_tags": intent.exclude_tags,
        "city": intent.city,
        "cities": intent.cities,
        "province": intent.province,
        "age_from": intent.age_from,
        "age_to": intent.age_to,
        "type": intent.type,
        "gender": intent.gender,
        "cost_max": intent.cost_max,
        "traits": intent.traits,
        "is_special_needs": intent.is_special_needs,
        "is_virtual": intent.is_virtual,
        "language_immersion": intent.language_immersion,
        "date_from": intent.date_from,
        "date_to": intent.date_to,
        "lat": intent.lat,
        "lon": intent.lon,
        "radius_km": intent.radius_km,
        "ics": intent.ics,
        "needs_clarification": intent.needs_clarification,
        "recognized": intent.recognized,
    })

    # Merge with session
    merged_params = merge_intent(intent, fuzzy_hints=fuzzy_hints)

    # Apply sidebar filters (override intent with explicit UI filters)
    merged_params.update(sidebar_filters)
    record("merged_params", {"params": merged_params})

    # Category disambiguation — fires when a single broad parent tag was found
    # and there are meaningful child options to offer the user.
    # Guard: only offer once per broad parent per session — prevents infinite loop
    # when the user types refinements without clicking a disambiguation button.
    _disambiguated = st.session_state.get("_disambiguated_tags", set())
    broad_parent = get_broad_parent(merged_params.get("tags", []))
    if broad_parent and broad_parent not in _disambiguated:
        options = get_viable_children(broad_parent)
        if len(options) >= 2:
            st.session_state["_disambiguated_tags"] = _disambiguated | {broad_parent}
            record("category_disambiguator", {
                "parent": broad_parent,
                "options": [o["slug"] for o in options],
            })
            render_trace()
            _render_category_picker(broad_parent, options, merged_params, user_input)
            return

    # Geolocation needed — always ask regardless of stale session location.
    # "near me" means the user's physical location, not a prior session city.
    if intent.needs_geolocation:
        record("output", {"route": "NEEDS_GEOLOCATION"})
        render_trace()
        _speak("I'd love to find camps near you! Which city or province are you in?")
        return

    _run_search(merged_params, user_input, session, sidebar_filters, intent=intent)


def _run_search(merged_params: dict, raw_query: str, session: dict, sidebar_filters: dict, intent=None):
    # Clear any stale "show more" state from the previous search turn.
    st.session_state.pop("_more_camps_pool", None)
    pool_size = int(get_secret("RESULTS_POOL_SIZE", "500"))

    # Semantic cache check
    cache_key = build_cache_key({**merged_params, "_q": raw_query})
    cached = get_cached(cache_key)
    if cached:
        record("cache", {"hit": True, "result_count": len(cached["results"])})
        render_trace()
        _speak(cached.get("concierge_message", ""))
        st.session_state["_last_query_label"] = raw_query
        display_results(cached["results"], search_params=merged_params, is_new_search=True)
        st.session_state["_last_results"] = cached["results"]
        st.session_state["_last_search_params"] = merged_params
        return

    record("cache", {"hit": False})

    # CSSL query
    with st.spinner("Searching camps..."):
        results, rcs = cssl_query(merged_params, limit=pool_size)

    record("cssl", {
        "pool_size": pool_size,
        "results_returned": len(results),
        "rcs": rcs,
        "sample_camps": [r.get("camp_name") for r in results[:5]],
    })

    # Virtual fallback: is_virtual=True is a hard filter; many programmes aren't
    # flagged virtual in the DB even when they offer online options.  If the filter
    # caused zero results, retry without it and surface a note to the user.
    virtual_fallback_used = False
    if not results and merged_params.get("is_virtual"):
        merged_params = {**merged_params, "is_virtual": False}
        with st.spinner("Searching camps..."):
            results, rcs = cssl_query(merged_params, limit=pool_size)
        if results:
            virtual_fallback_used = True
            record("cssl_virtual_fallback", {
                "results_returned": len(results), "rcs": rcs,
                "note": "is_virtual filter dropped — no programmes flagged virtual",
            })

    _virtual_note = (
        "_Note: I couldn't find programmes specifically flagged as online, "
        "but here are some that may offer virtual or hybrid sessions._\n\n"
    ) if virtual_fallback_used else ""

    # Partition results by tag_role: specialty/category hits vs activity-only.
    # Always prioritize specialty/category hits; backfill with activity hits
    # only when there aren't enough focused camps to fill the display.
    specialty_hits, activity_hits = _partition_by_role(results)
    n_specialty_camps = len({r.get("camp_id") for r in specialty_hits})
    _activity_overflow = None
    if specialty_hits and activity_hits:
        if n_specialty_camps >= 10:
            # Enough specialty camps — hold back activity-only for "see more"
            _activity_overflow = activity_hits
            results = specialty_hits
        else:
            # Not enough specialty camps to fill display — prepend them,
            # then backfill with activity hits so specialty always ranks first.
            results = specialty_hits + activity_hits
        record("role_partition", {
            "specialty_camps": n_specialty_camps,
            "activity_held_back": len(activity_hits) if _activity_overflow else 0,
        })

    ics = getattr(intent, "ics", 1.0) if intent else 1.0
    if intent:
        merged_params["ics"] = intent.ics
    decision = decide(
        ics=ics,
        rcs=rcs,
        needs_clarification=getattr(intent, "needs_clarification", []) if intent else [],
    )
    record("decision_matrix", {"ics": ics, "rcs": rcs, "route": decision.route.name})

    # Route handlers
    if decision.route == Route.SHOW_RESULTS:
        with st.spinner("Finding the best matches…"):
            final = process_results(results, raw_query, merged_params)
            msg = generate_concierge_response(final, raw_query, merged_params, "SHOW_RESULTS", ics=ics, needs_clarification=getattr(intent, "needs_clarification", []) if intent else [])
        record("output", {"route": "SHOW_RESULTS", "final_count": len(final),
                          "top_camps": [r.get("camp_name") for r in final],
                          "concierge_msg": msg[:200]})
        render_trace()
        _speak(_virtual_note + msg)
        st.session_state["_last_query_label"] = raw_query
        display_results(final, search_params=merged_params, is_new_search=True)
        _maybe_offer_more_camps(results, final, raw_query, merged_params,
                                activity_overflow=_activity_overflow)
        st.session_state["_last_results"] = final
        st.session_state["_last_search_params"] = merged_params
        set_cache(cache_key, {"results": final, "concierge_message": msg})
        store_results([r["id"] for r in final])
        if intent:
            log_search(session, intent, rcs, len(final))

    elif decision.route == Route.BROADEN_SEARCH:
        expanded = casl_expand(merged_params, limit=pool_size)
        result_ids = {r["id"] for r in results}
        all_results = results + [r for r in expanded if r["id"] not in result_ids]
        record("casl_expand", {
            "input_tags": merged_params.get("tags", []),
            "expanded_count": len(expanded),
            "casl_sample": [r.get("camp_name") for r in expanded[:5]],
            "combined_count": len(all_results),
        })
        if all_results:
            with st.spinner("Finding the best matches…"):
                final = process_results(all_results, raw_query, merged_params)
                max_score = max((r.get("rerank_score", 0.0) for r in final), default=0.0)
                if max_score < 0.45 and not results:
                    diag = _diagnose_zero_results(merged_params)
                    record("output", {"route": "ZERO_RESULTS", "reason": "casl_low_relevance",
                                      "advisor_type": diag.get("type")})
                    render_trace()
                    _show_zero_results(diag)
                    return
                msg = generate_concierge_response(final, raw_query, merged_params, "BROADEN_SEARCH", ics=ics, needs_clarification=getattr(intent, "needs_clarification", []) if intent else [])
            record("output", {"route": "BROADEN_SEARCH", "final_count": len(final),
                               "top_camps": [r.get("camp_name") for r in final],
                               "concierge_msg": msg[:200]})
            render_trace()
            _speak(_virtual_note + msg)
            st.session_state["_last_query_label"] = raw_query
            display_results(final, search_params=merged_params, is_new_search=True)
            _maybe_offer_more_camps(all_results, final, raw_query, merged_params,
                                    activity_overflow=_activity_overflow)
            st.session_state["_last_results"] = final
            st.session_state["_last_search_params"] = merged_params
            set_cache(cache_key, {"results": final, "concierge_message": msg})
            store_results([r["id"] for r in final])
            if intent:
                log_search(session, intent, rcs, len(final))
        else:
            diag = _diagnose_zero_results(merged_params)
            record("output", {"route": "ZERO_RESULTS", "advisor_type": diag.get("type")})
            render_trace()
            _show_zero_results(diag)

    elif decision.route == Route.SHOW_CLARIFY:
        with st.spinner("Finding the best matches…"):
            final = process_results(results, raw_query, merged_params)
            msg = generate_concierge_response(final, raw_query, merged_params, "SHOW_CLARIFY", ics=ics, needs_clarification=getattr(intent, "needs_clarification", []) if intent else [])
        record("output", {"route": "SHOW_CLARIFY", "final_count": len(final),
                          "clarification_dims": decision.clarification_dimensions,
                          "concierge_msg": msg[:200]})
        render_trace()
        _speak(_virtual_note + msg)
        st.session_state["_last_query_label"] = raw_query
        display_results(final, search_params=merged_params, is_new_search=True)
        _maybe_offer_more_camps(results, final, raw_query, merged_params,
                                activity_overflow=_activity_overflow)
        st.session_state["_last_results"] = final
        st.session_state["_last_search_params"] = merged_params
        render_clarification(decision.clarification_dimensions)
        if intent:
            log_search(session, intent, rcs, len(final))

    elif decision.route == Route.CLARIFY_LOOP:
        clarify_final_count = 0
        clarify_msg = ""
        zero_diag = None
        if results:
            with st.spinner("Finding the best matches…"):
                final = process_results(results, raw_query, merged_params)
                clarify_final_count = len(final)
                clarify_msg = generate_concierge_response(final, raw_query, merged_params, "SHOW_CLARIFY", ics=ics, needs_clarification=getattr(intent, "needs_clarification", []) if intent else [])
        elif not decision.clarification_dimensions:
            # No results and no clarification dims — pre-diagnose before render_trace
            zero_diag = _diagnose_zero_results(merged_params)
        record("output", {"route": "CLARIFY_LOOP", "final_count": clarify_final_count,
                          "clarification_dims": decision.clarification_dimensions,
                          "concierge_msg": clarify_msg[:200] if clarify_msg else "",
                          "advisor_type": zero_diag.get("type") if zero_diag else None})
        render_trace()
        if results:
            _speak(_virtual_note + clarify_msg)
            st.session_state["_last_query_label"] = raw_query
            display_results(final, search_params=merged_params, is_new_search=True)
            st.session_state["_last_results"] = final
            st.session_state["_last_search_params"] = merged_params
            if intent:
                log_search(session, intent, rcs, clarify_final_count)
        if decision.clarification_dimensions:
            render_clarification(decision.clarification_dimensions)
        elif zero_diag:
            _show_zero_results(zero_diag)

    # Handle clarification answer
    answer = st.session_state.pop("_clarification_answer", None)
    if answer:
        st.session_state["_pending_query"] = answer
        st.session_state["_input_path_pending"] = "clarification"
        st.rerun()


def _diagnose_zero_results(merged_params: dict) -> dict:
    """
    Run zero-results diagnosis and record the advisor step.
    Must be called BEFORE render_trace() so the record appears in the debug panel.
    Returns the diagnosis dict for display by _show_zero_results().
    """
    from core.cssl import resolve_tag_ids
    from db.connection import get_connection

    tag_ids = []
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        tag_ids = resolve_tag_ids(merged_params.get("tags", []), cursor)
        cursor.close()
        conn.close()
    except Exception:
        pass

    # When lat/lon was used, city is None — use first entry from cities list
    # so the advisor says "near Etobicoke" instead of "in Ontario".
    searched_city = merged_params.get("city") or (
        (merged_params.get("cities") or [None])[0]
    )
    diagnosis = diagnose(
        tag_ids=tag_ids,
        searched_city=searched_city,
        searched_province=merged_params.get("province"),
        program_type=merged_params.get("type"),
        date_from=merged_params.get("date_from"),
        date_to=merged_params.get("date_to"),
        is_virtual=bool(merged_params.get("is_virtual")),
        age_from=merged_params.get("age_from"),
        age_to=merged_params.get("age_to"),
        user_lat=merged_params.get("lat"),
        user_lon=merged_params.get("lon"),
        language_immersion=merged_params.get("language_immersion"),
        gender=merged_params.get("gender"),
        cost_max=merged_params.get("cost_max"),
        is_special_needs=bool(merged_params.get("is_special_needs")),
    )

    ps = diagnosis.get("pending_suggestion") or {}
    record("advisor", {
        "diagnosis_type": diagnosis.get("type", "unknown"),
        "message": diagnosis.get("message", "")[:200],
        "suggestion_type": ps.get("type"),
        "suggestion_city": ps.get("to_city") or ps.get("to_province"),
    })
    return diagnosis


def _show_zero_results(diagnosis: dict):
    """Display zero-results message and store pending suggestion."""
    msg = diagnosis.get("message", "No camps found matching your search.")
    _speak(msg)
    if diagnosis.get("pending_suggestion"):
        store_suggestion(diagnosis["pending_suggestion"])


def _render_category_picker(parent_slug: str, options: list[dict],
                             merged_params: dict, raw_query: str):
    """
    Concierge disambiguation: show child category buttons so the user can
    narrow down before a search runs.  Stores the confirmed params in session
    state and reruns so _run_search executes on the next pass.
    """
    # Derive a readable parent name from the slug
    parent_name = parent_slug.replace("-multi", "").replace("-", " ").title()

    _speak(f"**{parent_name}** covers a lot of ground! Which area interests you most?")

    # Persist picker config so buttons survive page refresh / reboot
    st.session_state["_pending_category_picker"] = {
        "parent_slug": parent_slug,
        "options": options[:4],
        "merged_params": merged_params,
        "raw_query": raw_query,
    }
    _render_pending_picker()


def _render_pending_picker():
    """Re-render disambiguation buttons from persisted session state (survives page reload)."""
    picker = st.session_state.get("_pending_category_picker")
    if not picker:
        return
    parent_slug = picker["parent_slug"]
    options     = picker["options"]
    merged_params = picker["merged_params"]
    raw_query   = picker["raw_query"]
    parent_name = parent_slug.replace("-multi", "").replace("-", " ").title()

    btn_labels = [opt["name"] for opt in options] + [f"All {parent_name}"]
    btn_slugs  = [opt["slug"] for opt in options] + [None]

    cols = st.columns(len(btn_labels))
    for col, label, slug in zip(cols, btn_labels, btn_slugs):
        if col.button(label, key=f"disambig_{slug or 'all'}"):
            chosen_tags = [slug] if slug else merged_params.get("tags", [parent_slug])
            st.session_state["_disambiguation_choice"] = {
                "params": {**merged_params, "tags": chosen_tags},
                "raw_query": raw_query,
                "label": label,
            }
            st.rerun()


if __name__ == "__main__":
    main()
