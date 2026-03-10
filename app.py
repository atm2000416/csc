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
    page_title="Camp Search Concierge",
    page_icon="",
    layout="wide",
)

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
from ui.filter_sidebar import render_filters
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
    st.markdown(f"**{len(results)} result(s) found**")
    for result in results:
        render_card(result)


def _speak(message: str):
    """Render a concierge narrative in the assistant chat bubble."""
    if message:
        with st.chat_message("assistant"):
            st.markdown(message)


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

    st.title("Camp Search Concierge")
    st.caption("Find the perfect summer camp for your child.")

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

    # Sidebar filters
    sidebar_filters = render_filters()

    # Surprise Me button
    def on_surprise_search(query: str):
        st.session_state["_pending_query"] = query

    col1, col2 = st.columns([4, 1])
    with col2:
        render_surprise_me(on_surprise_search)

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

    # Handle surprise query injection
    if st.session_state.get("_pending_query") and not user_input:
        user_input = st.session_state.pop("_pending_query")
        st.session_state["_surprise_results_heading"] = True
        st.session_state["_input_path"] = st.session_state.pop("_input_path_pending", "surprise_me")
        # Keep location from prior session but clear activity/filter params
        prior = st.session_state.session_context.get("accumulated_params", {})
        st.session_state.session_context["accumulated_params"] = {
            k: v for k, v in prior.items() if k in ("city", "cities", "province")
        }
        st.session_state.session_context["pending_suggestion"] = None
    else:
        st.session_state.pop("_surprise_results_heading", None)

    if not user_input:
        # Show prior results if available
        prior = st.session_state.get("_last_results")
        if prior:
            display_results(prior)
        return

    session = st.session_state.session_context

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
    # and there are meaningful child options to offer the user
    broad_parent = get_broad_parent(merged_params.get("tags", []))
    if broad_parent:
        options = get_viable_children(broad_parent)
        if len(options) >= 2:
            record("category_disambiguator", {
                "parent": broad_parent,
                "options": [o["slug"] for o in options],
            })
            render_trace()
            _render_category_picker(broad_parent, options, merged_params, user_input)
            return

    # Geolocation needed but no location in params — ask the user
    if intent.needs_geolocation and not merged_params.get("city") and not merged_params.get("province"):
        record("output", {"route": "NEEDS_GEOLOCATION"})
        render_trace()
        with st.chat_message("assistant"):
            st.markdown(
                "I'd love to find camps near you! Which city or province are you in?"
            )
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
        user_lat=merged_params.get("lat"),
        user_lon=merged_params.get("lon"),
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
    with st.chat_message("assistant"):
        st.markdown(msg)
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

    with st.chat_message("assistant"):
        st.markdown(
            f"**{parent_name}** covers a lot of ground! "
            f"Which area interests you most?"
        )
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
