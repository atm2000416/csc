"""
core/tracer.py
Search trace logger for testing and debugging.
Records key pipeline steps into st.session_state["_trace"].
Rendered as a collapsible panel via render_trace().
"""
import time
import streamlit as st


def init_trace():
    """Call at the start of each search to reset the trace."""
    st.session_state["_trace"] = {
        "started_at": time.time(),
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


def render_trace():
    """Render the trace log as a collapsible expander. No-op if no trace."""
    trace = st.session_state.get("_trace")
    if not trace or not trace.get("steps"):
        return

    total = round(time.time() - trace["started_at"], 3)
    with st.expander(f"🔍 Debug Trace ({total}s)", expanded=False):
        for entry in trace["steps"]:
            step = entry.pop("step")
            elapsed = entry.pop("elapsed_s")
            st.markdown(f"**`[{elapsed}s]` {step}**")
            if entry:
                st.json(entry, expanded=False)
            entry["step"] = step        # restore (non-destructive)
            entry["elapsed_s"] = elapsed
