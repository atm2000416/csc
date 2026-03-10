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
    color: #2F4F4F;
    background-color: #F4F7F0;
}
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Custom topbar (frosted glass) ── */
.camps-topbar {
    background: rgba(138,154,91,0.88);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    padding: 0 1.5rem;
    height: 72px;
    display: flex;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 1000;
    box-shadow: 0 2px 12px rgba(47,79,79,0.15);
    margin-bottom: 0;
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
    background: rgba(255,255,255,0.25);
    color: white;
    font-family: 'Nunito', sans-serif;
    font-weight: 800;
    font-size: 0.65rem;
    padding: 2px 9px;
    border-radius: 12px;
    letter-spacing: 0.3px;
    text-transform: uppercase;
    border: 1px solid rgba(255,255,255,0.4);
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: white !important;
    border-right: 1px solid #d8e4d0;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-family: 'Nunito', sans-serif;
    font-weight: 800;
    font-size: 0.95rem;
    color: white;
    background: #8A9A5B;
    margin: -1rem -1rem 1rem -1rem;
    padding: 0.9rem 1rem;
    border-radius: 0 0 12px 12px;
}
[data-testid="stSidebar"] label {
    font-size: 0.82rem !important;
    font-weight: 700 !important;
    color: #2F4F4F !important;
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
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: transparent;
    border: none;
    box-shadow: none;
    padding: 0;
    margin-bottom: 0.4rem;
}

/* ── Chat input ── */
[data-testid="stChatInput"] textarea {
    border: 2px solid #c5d4a0 !important;
    border-radius: 28px !important;
    font-family: 'Lato', sans-serif !important;
    font-size: 0.92rem !important;
    padding: 0.55rem 1.1rem !important;
    background: white !important;
    color: #2F4F4F !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: #8A9A5B !important;
    box-shadow: 0 0 0 3px rgba(138,154,91,0.18) !important;
}

/* ── Buttons (claymorphism) ── */
.stButton > button {
    font-family: 'Nunito', sans-serif !important;
    font-weight: 700 !important;
    border-radius: 24px !important;
    font-size: 0.85rem !important;
    padding: 0.4rem 1rem !important;
    border: none !important;
    color: white !important;
    background: #8A9A5B !important;
    box-shadow: 4px 4px 10px #75834d, -3px -3px 8px #9fb169, inset 2px 2px 6px rgba(255,255,255,0.4) !important;
    transition: all 0.15s ease;
}
.stButton > button:hover {
    background: #7a8a4b !important;
    box-shadow: 3px 3px 8px #75834d, -2px -2px 6px #9fb169, inset 2px 2px 6px rgba(255,255,255,0.4) !important;
    transform: translateY(-1px);
}

/* ── Link buttons (camps.ca / Camp Website) ── */
.stLinkButton a {
    font-family: 'Nunito', sans-serif !important;
    font-weight: 700 !important;
    font-size: 0.78rem !important;
    border-radius: 24px !important;
    background: #8A9A5B !important;
    color: white !important;
    border: none !important;
    padding: 0.3rem 0.9rem !important;
    box-shadow: 3px 3px 8px rgba(117,131,77,0.35) !important;
    transition: all 0.15s ease;
}
.stLinkButton a:hover {
    background: #7a8a4b !important;
    box-shadow: 4px 4px 12px rgba(117,131,77,0.45) !important;
    transform: translateY(-1px);
}

/* ── Result count ── */
.result-count {
    padding: 0 1.4rem;
    font-family: 'Nunito', sans-serif;
    font-size: 0.78rem;
    font-weight: 800;
    color: #8A9A5B;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 0.8rem;
}

/* ── Spinner ── */
.stSpinner > div {
    border-top-color: #8A9A5B !important;
}

/* ── Selectbox / inputs ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    border: 1.5px solid #c5d4a0 !important;
    border-radius: 10px !important;
    font-size: 0.88rem !important;
}

/* ── Sticky filter bar ── */
[data-testid="stExpander"] {
    position: sticky;
    top: 72px;
    z-index: 900;
    background: white;
    border-bottom: 1px solid #d8e4d0;
    box-shadow: 0 2px 8px rgba(47,79,79,0.06);
}

/* ── Dividers ── */
hr { border-color: #d8e4d0 !important; margin: 0.8rem 0 !important; }
</style>
""", unsafe_allow_html=True)

# ── Imports (after page config) ───────────────────────────────────────────────
from core.session_manager import init_session, merge_intent, store_suggestion, clear_suggestion, store_results
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
from ui.results_card import render_card
from ui.filter_sidebar import render_filters, get_filter_values
from ui.clarification_widget import render_clarification
from ui.surprise_me import render_surprise_me


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
    max_per_camp = int(get_secret("DIVERSITY_MAX_PER_CAMP", "2"))
    diverse = diversity_filter(results, max_per_camp=max_per_camp)
    return rerank(diverse, raw_query, intent_params, top_n=10)


def display_results(results: list[dict]):
    if not results:
        st.info("No camps found matching your search. Try adjusting your filters.")
        return
    st.markdown(f'<p class="result-count">{len(results)} result{"s" if len(results) != 1 else ""} found</p>',
                unsafe_allow_html=True)
    render_filters()
    for result in results:
        render_card(result)


_BUBBLE_BASE = (
    "padding:12px 16px; max-width:75%; "
    "font-family:'Lato',sans-serif; font-size:0.95rem; line-height:1.55;"
)

_BUBBLE_ROW = "padding:0 1.4rem;"


def _render_bubble(message: str, role: str):
    """Low-level bubble renderer — does not touch session state."""
    if not message:
        return
    if role == "assistant":
        st.markdown(
            f'<div style="display:flex; justify-content:flex-start; margin:0 0 0.8rem 0; {_BUBBLE_ROW}">'
            f'<div style="background:#FFFFFF; color:#2F4F4F; '
            f'border-radius:18px 18px 18px 4px; box-shadow:0 1px 6px rgba(47,79,79,0.10); {_BUBBLE_BASE}">'
            f'{message}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div style="display:flex; justify-content:flex-end; margin:0 0 0.8rem 0; {_BUBBLE_ROW}">'
            f'<div style="background:#8A9A5B; color:white; '
            f'border-radius:18px 18px 4px 18px; {_BUBBLE_BASE}">'
            f'{message}</div></div>',
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
    return first_word in {"yes", "sure", "okay", "yeah", "yep"}


# ── Main app ──────────────────────────────────────────────────────────────────
def main():
    init_session()

    # Branded topbar
    st.markdown("""
    <div class="camps-topbar">
        <span class="logo">camps<em>.ca</em></span>
        <span class="badge">Camp Finder</span>
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

    # Surprise Me button
    def on_surprise_search(query: str):
        st.session_state["_pending_query"] = query

    col1, col2, col3 = st.columns([4, 1, 1])
    with col2:
        render_surprise_me(on_surprise_search)
    with col3:
        if st.button("Start Over", key="reset_btn", help="Clear all searches and start fresh"):
            st.session_state.clear()
            st.rerun()

    # Chat input
    user_input = st.chat_input("Describe what you're looking for (e.g. hockey camp Toronto for my 10 year old)")

    # Handle category disambiguation button choice (no new chat input needed)
    if st.session_state.get("_disambiguation_choice") and not user_input:
        choice = st.session_state.pop("_disambiguation_choice")
        init_trace()
        # Persist chosen params into session so next typed turn inherits them
        st.session_state.session_context["accumulated_params"] = dict(choice["params"])
        record("input", {"raw_query": choice["raw_query"], "path": "disambiguation",
                         "source": "category_disambiguation"})
        _run_search(choice["params"], choice["raw_query"],
                    st.session_state.session_context, sidebar_filters)
        return

    # Handle direct surprise results (bypasses LLM pipeline entirely)
    if st.session_state.get("_surprise_direct_results") is not None and not user_input:
        surprise_results = st.session_state.pop("_surprise_direct_results")
        query_label      = st.session_state.pop("_surprise_query_label", "Surprise camps")
        st.session_state.pop("_disambiguated_tags", None)
        st.session_state.session_context["pending_suggestion"] = None
        _render_history()
        _show_user_bubble(query_label)
        if surprise_results:
            st.session_state["_last_results"] = surprise_results
            display_results(surprise_results)
        else:
            _speak("I couldn't find camps for that combination — try searching manually!")
        return

    # Handle surprise query injection (legacy path — kept for safety)
    if st.session_state.get("_pending_query") and not user_input:
        user_input = st.session_state.pop("_pending_query")
        st.session_state["_surprise_results_heading"] = True
        st.session_state["_input_path"] = st.session_state.pop("_input_path_pending", "surprise_me")
        st.session_state.pop("_disambiguated_tags", None)  # fresh disambiguator on surprise
        # Keep location from prior session but clear activity/filter params
        prior = st.session_state.session_context.get("accumulated_params", {})
        st.session_state.session_context["accumulated_params"] = {
            k: v for k, v in prior.items() if k in ("city", "cities", "province")
        }
        st.session_state.session_context["pending_suggestion"] = None
    else:
        st.session_state.pop("_surprise_results_heading", None)

    if not user_input:
        messages = st.session_state.get("_messages", [])
        prior    = st.session_state.get("_last_results")
        if messages or prior:
            _render_history()
            if prior:
                display_results(prior)
        else:
            st.markdown(
                '<p style="color:#78909c; font-size:0.92rem; margin-top:2rem; text-align:center;">'
                '🏕️ Tell me what you\'re looking for and I\'ll find the best camps for your child.'
                '</p>',
                unsafe_allow_html=True,
            )
        return

    session = st.session_state.session_context

    # Render prior conversation history, then show + store current user message
    _render_history()
    _show_user_bubble(user_input)

    # Affirmative suggestion check
    pending = session.get("pending_suggestion")
    if pending and is_affirmative(user_input):
        init_trace()
        merged_params = dict(session["accumulated_params"])
        if pending.get("type") == "geo_broaden":
            merged_params["city"] = pending["to_city"]
            merged_params["province"] = pending["to_province"]
        elif pending.get("type") == "geo_broaden_province":
            merged_params.pop("city", None)
            merged_params["province"] = pending["to_province"]
        # Write accepted params back to session so next typed turn inherits them
        session["accumulated_params"] = merged_params
        record("input", {
            "raw_query": user_input,
            "path": "affirmative",
            "suggestion_type": pending.get("type"),
            "suggestion_detail": pending.get("to_city") or pending.get("to_province"),
            "params_after": merged_params,
            "sidebar_filters": sidebar_filters,
        })
        clear_suggestion()
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

    # Inject geo coordinates from fuzzy hints directly — bypasses Gemini for
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
    merged_params = merge_intent(intent)

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
    pool_size = int(get_secret("RESULTS_POOL_SIZE", "100"))

    # Semantic cache check
    cache_key = build_cache_key({**merged_params, "_q": raw_query})
    cached = get_cached(cache_key)
    if cached:
        record("cache", {"hit": True, "result_count": len(cached["results"])})
        render_trace()
        _speak(cached.get("concierge_message", ""))
        display_results(cached["results"])
        st.session_state["_last_results"] = cached["results"]
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
        final = process_results(results, raw_query, merged_params)
        msg = generate_concierge_response(final, raw_query, merged_params, "SHOW_RESULTS")
        record("output", {"route": "SHOW_RESULTS", "final_count": len(final),
                          "top_camps": [r.get("camp_name") for r in final],
                          "concierge_msg": msg[:200]})
        render_trace()
        _speak(msg)
        display_results(final)
        st.session_state["_last_results"] = final
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
            final = process_results(all_results, raw_query, merged_params)
            max_score = max((r.get("rerank_score", 0.0) for r in final), default=0.0)
            if max_score < 0.45 and not results:
                diag = _diagnose_zero_results(merged_params)
                record("output", {"route": "ZERO_RESULTS", "reason": "casl_low_relevance",
                                  "advisor_type": diag.get("type")})
                render_trace()
                _show_zero_results(diag)
                return
            msg = generate_concierge_response(final, raw_query, merged_params, "BROADEN_SEARCH")
            record("output", {"route": "BROADEN_SEARCH", "final_count": len(final),
                               "top_camps": [r.get("camp_name") for r in final],
                               "concierge_msg": msg[:200]})
            render_trace()
            _speak(msg)
            display_results(final)
            st.session_state["_last_results"] = final
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
        final = process_results(results, raw_query, merged_params)
        msg = generate_concierge_response(final, raw_query, merged_params, "SHOW_CLARIFY")
        record("output", {"route": "SHOW_CLARIFY", "final_count": len(final),
                          "clarification_dims": decision.clarification_dimensions,
                          "concierge_msg": msg[:200]})
        render_trace()
        _speak(msg)
        display_results(final)
        st.session_state["_last_results"] = final
        render_clarification(decision.clarification_dimensions)
        if intent:
            log_search(session, intent, rcs, len(final))

    elif decision.route == Route.CLARIFY_LOOP:
        clarify_final_count = 0
        clarify_msg = ""
        zero_diag = None
        if results:
            final = process_results(results, raw_query, merged_params)
            clarify_final_count = len(final)
            clarify_msg = generate_concierge_response(final, raw_query, merged_params, "SHOW_CLARIFY")
        elif not decision.clarification_dimensions:
            # No results and no clarification dims — pre-diagnose before render_trace
            zero_diag = _diagnose_zero_results(merged_params)
        record("output", {"route": "CLARIFY_LOOP", "final_count": clarify_final_count,
                          "clarification_dims": decision.clarification_dimensions,
                          "concierge_msg": clarify_msg[:200] if clarify_msg else "",
                          "advisor_type": zero_diag.get("type") if zero_diag else None})
        render_trace()
        if results:
            _speak(clarify_msg)
            display_results(final)
            st.session_state["_last_results"] = final
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

    diagnosis = diagnose(
        tag_ids=tag_ids,
        searched_city=merged_params.get("city"),
        searched_province=merged_params.get("province"),
        program_type=merged_params.get("type"),
        date_from=merged_params.get("date_from"),
        date_to=merged_params.get("date_to"),
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
    # Build button row: up to 4 child options + an "All" fallback
    display_options = options[:4]
    btn_labels = [opt["name"] for opt in display_options] + [f"All {parent_name}"]
    btn_slugs  = [opt["slug"] for opt in display_options] + [None]  # None = keep parent

    cols = st.columns(len(btn_labels))
    for col, label, slug in zip(cols, btn_labels, btn_slugs):
        if col.button(label, key=f"disambig_{slug or 'all'}"):
            chosen_tags = [slug] if slug else merged_params.get("tags", [parent_slug])
            st.session_state["_disambiguation_choice"] = {
                "params": {**merged_params, "tags": chosen_tags},
                "raw_query": raw_query,
            }
            st.rerun()


if __name__ == "__main__":
    main()
