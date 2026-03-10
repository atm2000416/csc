"""
core/tracer.py
Search trace logger for testing and debugging.

Accumulates every pipeline turn in st.session_state["_session_trace"].
Rendered as a collapsible panel with:
 - per-step breakdown for the current turn
 - full session JSON (all turns) in a copy-pasteable code block
"""
import json
import time
import streamlit as st


def init_trace():
    """
    Call at the start of each new search turn.
    Archives the previous turn into _session_trace, then resets _trace.
    """
    # Archive the completed previous turn (if any)
    prev = st.session_state.get("_trace")
    if prev and prev.get("steps"):
        if "_session_trace" not in st.session_state:
            st.session_state["_session_trace"] = []
        st.session_state["_session_trace"].append(prev)

    st.session_state["_trace"] = {
        "turn": len(st.session_state.get("_session_trace", [])) + 1,
        "started_at": time.time(),
        "started_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "steps": [],
    }


def record(step: str, data: dict):
    """Append a named step with arbitrary data to the current trace."""
    if "_trace" not in st.session_state:
        return
    elapsed = round(time.time() - st.session_state["_trace"]["started_at"], 3)
    st.session_state["_trace"]["steps"].append({
        "step": step,
        "elapsed_s": elapsed,
        **data,
    })


def _serialisable(obj):
    """Make trace data safe for json.dumps (handles datetime, sets, etc.)."""
    if isinstance(obj, dict):
        return {k: _serialisable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialisable(i) for i in obj]
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def render_trace():
    """
    Render the debug panel.

    Shows:
      - Current turn steps (collapsible per-step JSON)
      - Full session dump (all turns) as copy-pasteable JSON code block
    """
    trace = st.session_state.get("_trace")
    if not trace or not trace.get("steps"):
        return

    # Snapshot current turn with final elapsed time
    total = round(time.time() - trace["started_at"], 3)
    current_turn = {**trace, "total_elapsed_s": total}

    # Build full session view: past turns + current turn
    past_turns = st.session_state.get("_session_trace", [])
    all_turns = past_turns + [current_turn]

    label = (
        f"🔍 Debug — Turn {current_turn['turn']} ({total}s)"
        + (f"  |  Session: {len(all_turns)} turn(s)" if len(all_turns) > 1 else "")
    )

    with st.expander(label, expanded=True):

        # ── Current turn step-by-step ─────────────────────────────────────────
        st.markdown("### Current turn")
        for entry in trace["steps"]:
            # work on a copy so we don't mutate session state
            e = dict(entry)
            step    = e.pop("step")
            elapsed = e.pop("elapsed_s")
            st.markdown(f"**`[{elapsed}s]` {step}**")
            if e:
                st.json(_serialisable(e), expanded=False)

        # ── Full session copy/paste dump ──────────────────────────────────────
        st.divider()
        st.markdown("### Full session trace (copy/paste)")

        dump = []
        for turn in all_turns:
            t = dict(turn)
            t.pop("started_at", None)   # epoch float — not useful to humans
            dump.append(_serialisable(t))

        st.code(json.dumps(dump, indent=2), language="json")

        # ── Quick summary table ───────────────────────────────────────────────
        if len(all_turns) > 1:
            st.divider()
            st.markdown("### Session summary")
            rows = []
            for t in all_turns:
                inp  = next((s for s in t["steps"] if s["step"] == "input"),  {})
                ip   = next((s for s in t["steps"] if s["step"] == "intent_parser"), {})
                cssl = next((s for s in t["steps"] if s["step"] == "cssl"),   {})
                out  = next((s for s in t["steps"] if s["step"] == "output"),  {})
                rows.append({
                    "Turn":    t.get("turn", "?"),
                    "Path":    inp.get("path", "typed"),
                    "Query":   inp.get("raw_query", "")[:50],
                    "Tags":    ", ".join(ip.get("tags", [])),
                    "ICS":     ip.get("ics") or None,
                    "Results": out.get("final_count", cssl.get("results_returned", "")),
                    "RCS":     cssl.get("rcs", ""),
                    "Route":   out.get("route", ""),
                })
            st.dataframe(rows, use_container_width=True)
