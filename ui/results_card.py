"""
ui/results_card.py
Renders a single camp program result card in Streamlit.
"""
import streamlit as st


_TIER_STYLES = {
    "gold":   "border: 2px solid #FFD700; border-radius: 8px; padding: 12px; margin-bottom: 10px;",
    "silver": "border: 2px solid #C0C0C0; border-radius: 8px; padding: 12px; margin-bottom: 10px;",
    "bronze": "border: 1px solid #CD7F32; border-radius: 8px; padding: 12px; margin-bottom: 10px;",
}

_TIER_BADGE = {
    "gold":   "🥇 GOLD",
    "silver": "🥈 SILVER",
    "bronze": "🥉 BRONZE",
}


def render_card(result: dict):
    """
    Render one result as a styled card.

    Expected result keys:
        camp_name, name, city, province, tier,
        age_from, age_to, type, cost_from, cost_to,
        blurb, website, lgbtq_welcoming, accessibility
    Plus optional 'tags' list of tag name strings.
    """
    tier = result.get("tier", "bronze")
    style = _TIER_STYLES.get(tier, _TIER_STYLES["bronze"])
    badge = _TIER_BADGE.get(tier, "")

    camp_name = result.get("camp_name", "Unknown Camp")
    program_name = result.get("name", "")
    city = result.get("city", "")
    province = result.get("province", "")
    location = ", ".join(filter(None, [city, province]))

    age_from = result.get("age_from")
    age_to = result.get("age_to")
    age_str = f"Ages {age_from}–{age_to}" if age_from is not None and age_to is not None else ""

    prog_type = result.get("type", "")
    cost_from = result.get("cost_from")
    cost_to = result.get("cost_to")
    if cost_from and cost_to:
        cost_str = f"${cost_from}–${cost_to}"
    elif cost_from:
        cost_str = f"From ${cost_from}"
    else:
        cost_str = ""

    line2_parts = [p for p in [program_name, age_str, prog_type, cost_str] if p]
    line2 = " | ".join(line2_parts)

    blurb = result.get("blurb") or result.get("mini_description") or ""

    icons = []
    if result.get("lgbtq_welcoming"):
        icons.append("🏳️‍🌈 LGBTQ+ welcoming")
    if result.get("accessibility"):
        icons.append("♿ Accessible")
    icons_str = "  ".join(icons)

    tags = result.get("tags", [])
    tags_str = "  ".join(f"`{t}`" for t in tags[:8]) if tags else ""

    website = result.get("website", "")

    with st.container():
        st.markdown(f'<div style="{style}">', unsafe_allow_html=True)

        st.markdown(f"**{badge} {camp_name}** — {location}")
        if line2:
            st.markdown(line2)
        if blurb:
            st.markdown(f"_{blurb}_")
        if icons_str:
            st.markdown(icons_str)
        if tags_str:
            st.markdown(tags_str)

        if website:
            st.link_button("View Camp", website)

        st.markdown("</div>", unsafe_allow_html=True)
