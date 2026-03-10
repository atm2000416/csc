"""
ui/results_card.py
Renders a single camp program result card in Streamlit.

Visual hierarchy (per spec):
  Line 1 — Program Name      (programs.name)
  Line 2 — Camp Name         (camps.camp_name)
  Line 3 — Context blurb     (programs.mini_description)
  Line 4 — Cost              (programs.cost_from / cost_to)
  Line 5 — Location          (camps.city, camps.province)
  Line 6 — Schedule slots    (program_dates, if available)
"""
import streamlit as st
from datetime import date


def _camps_url(slug: str, camp_id: int) -> str:
    """Generate the camps.ca listing URL for a camp."""
    return f"https://www.camps.ca/{slug}/{camp_id}"


def _normalise_website(url: str) -> str:
    """Ensure external website URL has an https:// scheme."""
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url


_TIER_COLOUR = {
    "gold":   "#B8860B",   # dark gold
    "silver": "#808080",
    "bronze": "#8B4513",
}


def _cost_str(cost_from, cost_to) -> str:
    if cost_from and cost_to:
        return f"${int(cost_from):,} – ${int(cost_to):,}"
    if cost_from:
        return f"From ${int(cost_from):,}"
    return ""


_MONTH_ABBR = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _format_slot(start_str: str, end_str: str) -> str:
    """Format a date range compactly: 'Jul 7–11' or 'Jun 30–Jul 4'."""
    try:
        s = date.fromisoformat(start_str)
        e = date.fromisoformat(end_str)
    except (ValueError, TypeError):
        return ""
    sm, em = _MONTH_ABBR[s.month], _MONTH_ABBR[e.month]
    if s.month == e.month:
        return f"{sm} {s.day}–{e.day}"
    return f"{sm} {s.day}–{em} {e.day}"


def _render_schedule(program_dates: list) -> None:
    """Render weekly slot pills + before/after care badges."""
    if not program_dates:
        return

    today = date.today()
    future = [pd for pd in program_dates
              if date.fromisoformat(str(pd["end_date"])) >= today]
    if not future:
        return

    # Sort by start_date
    future.sort(key=lambda x: x["start_date"])

    slot_labels = [_format_slot(str(pd["start_date"]), str(pd["end_date"]))
                   for pd in future]
    # Show up to 6 slots, collapse the rest
    MAX_SHOW = 6
    shown = slot_labels[:MAX_SHOW]
    hidden = len(slot_labels) - MAX_SHOW

    slots_str = "  ·  ".join(shown)
    if hidden > 0:
        slots_str += f"  +{hidden} more"

    # Before/after care — show badge if ANY slot offers it
    care_parts = []
    if any(pd.get("before_care") for pd in future):
        care_parts.append("🌅 Before care")
    if any(pd.get("after_care") for pd in future):
        care_parts.append("🌇 After care")

    schedule_html = (
        '<p style="margin:0 0 4px 0; font-size:0.83rem; color:#1a6e2e;">'
        f"📅 {slots_str}</p>"
    )
    st.markdown(schedule_html, unsafe_allow_html=True)

    if care_parts:
        care_html = (
            '<p style="margin:0 0 4px 0; font-size:0.80rem; color:#555;">'
            + "  ·  ".join(care_parts)
            + "</p>"
        )
        st.markdown(care_html, unsafe_allow_html=True)


def render_card(result: dict):
    """
    Render one result as a styled card.

    Expected result keys:
        camp_name, name, city, province, tier,
        age_from, age_to, type, cost_from, cost_to,
        mini_description, blurb, website,
        lgbtq_welcoming, accessibility
    Plus optional 'tags' list of tag name strings.
    """
    tier      = result.get("tier", "bronze")
    tier_col  = _TIER_COLOUR.get(tier, _TIER_COLOUR["bronze"])

    program_name = result.get("name") or "Summer Program"
    camp_name    = result.get("camp_name", "")
    city         = result.get("city", "")
    province     = result.get("province", "")
    location     = ", ".join(filter(None, [city, province]))

    cost  = _cost_str(result.get("cost_from"), result.get("cost_to"))
    blurb = result.get("blurb") or result.get("mini_description") or ""

    age_from = result.get("age_from")
    age_to   = result.get("age_to")
    age_str  = f"Ages {age_from}–{age_to}" if age_from is not None and age_to is not None else ""

    prog_type = result.get("type", "")

    icons = []
    if result.get("lgbtq_welcoming"):
        icons.append("🏳️‍🌈 LGBTQ+")
    if result.get("accessibility"):
        icons.append("♿ Accessible")

    tags = result.get("tags", [])
    program_dates = result.get("program_dates", [])
    website = result.get("website", "")
    camp_slug = result.get("slug", "")
    camp_id = result.get("camp_id")

    # ── Card container ────────────────────────────────────────────────────────
    card_style = (
        f"border-left: 4px solid {tier_col}; "
        "border-radius: 6px; "
        "background: #FAFAFA; "
        "padding: 14px 16px 10px 16px; "
        "margin-bottom: 12px;"
    )

    with st.container():
        st.markdown(f'<div style="{card_style}">', unsafe_allow_html=True)

        # Line 1 — Program Name (primary heading)
        st.markdown(f"### {program_name}")

        # Line 2 — Camp Name (secondary, with tier colour)
        camp_html = (
            f'<p style="margin:0 0 6px 0; font-size:0.95rem; color:{tier_col}; font-weight:600;">'
            f"{camp_name}</p>"
        )
        st.markdown(camp_html, unsafe_allow_html=True)

        # Line 3 — Context blurb
        if blurb:
            st.markdown(
                f'<p style="margin:0 0 8px 0; font-size:0.88rem; color:#555; font-style:italic;">'
                f"{blurb}</p>",
                unsafe_allow_html=True,
            )

        # Line 4 — Cost  (+ age range + type as secondary detail)
        meta_parts = [p for p in [cost, age_str, prog_type] if p]
        if meta_parts:
            meta_html = (
                '<p style="margin:0 0 4px 0; font-size:0.88rem; color:#333;">'
                + "  ·  ".join(meta_parts)
                + "</p>"
            )
            st.markdown(meta_html, unsafe_allow_html=True)

        # Line 5 — Location
        if location:
            st.markdown(
                f'<p style="margin:0 0 8px 0; font-size:0.85rem; color:#666;">📍 {location}</p>',
                unsafe_allow_html=True,
            )

        # Line 6 — Schedule slots
        _render_schedule(program_dates)

        # Icons + tags (supplementary)
        if icons:
            st.markdown(
                '<p style="margin:0 0 4px 0; font-size:0.82rem;">'
                + "  ".join(icons) + "</p>",
                unsafe_allow_html=True,
            )
        if tags:
            tags_str = "  ".join(f"`{t}`" for t in tags[:8])
            st.markdown(tags_str)

        btn_cols = st.columns([1, 1, 4])
        with btn_cols[0]:
            if camp_slug and camp_id:
                st.link_button("View on camps.ca →", _camps_url(camp_slug, camp_id))
        if website:
            with btn_cols[1]:
                st.link_button("Camp Website →", _normalise_website(website))

        st.markdown("</div>", unsafe_allow_html=True)
