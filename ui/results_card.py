"""
ui/results_card.py
Renders a single camp program result card in Streamlit.

Visual hierarchy (per spec):
  Line 1 — Program Name      (programs.name)
  Line 2 — Camp Name         (camps.camp_name)
  Line 3 — Context blurb     (reranker blurb or programs.mini_description)
  Line 4 — Cost              (programs.cost_from / cost_to)
  Line 5 — Location          (camps.city, camps.province)
"""
import streamlit as st


def _camps_url(slug: str, camp_id: int) -> str:
    return f"https://www.camps.ca/{slug}/{camp_id}"


def _normalise_website(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url


_TIER_COLOUR = {
    "gold":   "#B8860B",
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
    tier     = result.get("tier", "bronze")
    tier_col = _TIER_COLOUR.get(tier, _TIER_COLOUR["bronze"])

    program_name = result.get("name") or "Summer Program"
    camp_name    = result.get("camp_name", "")
    city         = result.get("city", "")
    province     = result.get("province", "")
    location     = ", ".join(filter(None, [city, province]))
    cost         = _cost_str(result.get("cost_from"), result.get("cost_to"))
    blurb        = result.get("blurb") or result.get("mini_description") or ""
    website      = result.get("website", "")
    camp_slug    = result.get("slug", "")
    camp_id      = result.get("camp_id")

    card_style = (
        f"border-left: 4px solid {tier_col}; "
        "border-radius: 8px; "
        "background: #ffffff; "
        "padding: 14px 16px 12px 16px; "
        "margin-bottom: 10px; "
        "box-shadow: 0 1px 4px rgba(0,0,0,0.06);"
    )

    with st.container():
        st.markdown(f'<div style="{card_style}">', unsafe_allow_html=True)

        # Line 1 — Program Name
        st.markdown(
            f'<p style="margin:0 0 2px 0; font-family:Montserrat,sans-serif; font-weight:800; '
            f'font-size:1.1rem; color:#1b5e20;">{program_name}</p>',
            unsafe_allow_html=True,
        )

        # Line 2 — Camp Name
        st.markdown(
            f'<p style="margin:0 0 6px 0; font-size:0.95rem; color:{tier_col}; font-weight:600;">'
            f"{camp_name}</p>",
            unsafe_allow_html=True,
        )

        # Line 3 — Context blurb
        if blurb:
            st.markdown(
                f'<p style="margin:0 0 8px 0; font-size:0.88rem; color:#555; font-style:italic;">'
                f"{blurb}</p>",
                unsafe_allow_html=True,
            )

        # Line 4 — Cost
        if cost:
            st.markdown(
                f'<p style="margin:0 0 4px 0; font-size:0.88rem; color:#333;">💰 {cost}</p>',
                unsafe_allow_html=True,
            )

        # Line 5 — Location
        if location:
            st.markdown(
                f'<p style="margin:0 0 10px 0; font-size:0.85rem; color:#666;">📍 {location}</p>',
                unsafe_allow_html=True,
            )

        # Buttons
        btn_cols = st.columns([1, 1, 4])
        with btn_cols[0]:
            if camp_slug and camp_id:
                st.link_button("View on camps.ca →", _camps_url(camp_slug, camp_id))
        if website:
            with btn_cols[1]:
                st.link_button("Camp Website →", _normalise_website(website))

        st.markdown("</div>", unsafe_allow_html=True)
