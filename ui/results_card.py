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


_TIER_COLOUR = {
    "gold":   "#B8860B",
    "silver": "#808080",
    "bronze": "#8B4513",
}


def _camps_url(slug: str, camp_id: int) -> str:
    return f"https://www.camps.ca/{slug}/{camp_id}"


def _normalise_website(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url


def _cost_str(cost_from, cost_to) -> str:
    if cost_from and cost_to:
        return f"${int(cost_from):,} – ${int(cost_to):,}"
    if cost_from:
        return f"From ${int(cost_from):,}"
    return ""


_BTN = (
    "display:inline-block; margin-right:8px; "
    "padding:5px 14px; border-radius:20px; font-size:0.78rem; font-weight:700; "
    "font-family:Montserrat,sans-serif; text-decoration:none; "
    "background:linear-gradient(135deg,#2e7d32,#388e3c); color:white; "
    "box-shadow:0 2px 6px rgba(46,125,50,0.25);"
)


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

    # ── Build buttons HTML ─────────────────────────────────────────────────────
    buttons_html = ""
    if camp_slug and camp_id:
        buttons_html += f'<a href="{_camps_url(camp_slug, camp_id)}" target="_blank" style="{_BTN}">View on camps.ca →</a>'
    if website:
        buttons_html += f'<a href="{_normalise_website(website)}" target="_blank" style="{_BTN}">Camp Website →</a>'

    # ── Build card lines ───────────────────────────────────────────────────────
    lines = []

    # Line 1 — Program Name
    lines.append(
        f'<p style="margin:0 0 2px 0; font-family:Montserrat,sans-serif; font-weight:800; '
        f'font-size:1.05rem; color:#1b5e20;">{program_name}</p>'
    )

    # Line 2 — Camp Name
    lines.append(
        f'<p style="margin:0 0 6px 0; font-size:0.92rem; color:{tier_col}; font-weight:600;">'
        f'{camp_name}</p>'
    )

    # Line 3 — Blurb
    if blurb:
        lines.append(
            f'<p style="margin:0 0 7px 0; font-size:0.86rem; color:#555; font-style:italic;">'
            f'{blurb}</p>'
        )

    # Line 4 — Cost
    if cost:
        lines.append(
            f'<p style="margin:0 0 4px 0; font-size:0.86rem; color:#333;">💰 {cost}</p>'
        )

    # Line 5 — Location
    if location:
        lines.append(
            f'<p style="margin:0 0 10px 0; font-size:0.84rem; color:#666;">📍 {location}</p>'
        )

    # Buttons
    if buttons_html:
        lines.append(f'<div style="margin-top:4px;">{buttons_html}</div>')

    card_html = (
        f'<div style="border-left:4px solid {tier_col}; border-radius:8px; '
        f'background:#ffffff; padding:14px 16px 12px 16px; margin-bottom:10px; '
        f'box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
        + "".join(lines)
        + "</div>"
    )

    st.markdown(card_html, unsafe_allow_html=True)
