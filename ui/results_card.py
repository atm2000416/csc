"""
ui/results_card.py
Renders a single camp program result card in Streamlit.

Visual hierarchy (per spec):
  Line 1 — Program Name      (programs.name)
  Line 2 — Camp Name         (camps.camp_name)
  Line 3 — Context blurb     (programs.mini_description)
  Line 4 — Cost              (programs.cost_from / cost_to)
  Line 5 — Location          (camps.city, camps.province)
"""
import streamlit as st


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
    website = result.get("website", "")

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

        if website:
            st.link_button("View Camp →", website)

        st.markdown("</div>", unsafe_allow_html=True)
