"""
ui/results_card.py
Renders a single camp program result card in Streamlit.

Visual hierarchy:
  Line 1 — Session Information  (programs.name)
  Line 2 — Camp Name            (camps.camp_name, tier-coloured)
  Line 3 — Session Details      (type · ages · location · cost · gender)
  Line 4 — AI Rationale         (reranker blurb explaining why this fits)
"""
import streamlit as st


_TIER_COLOUR = {
    "gold":   "#B8860B",
    "silver": "#707070",
    "bronze": "#8B4513",
}

_TYPE_LABEL = {
    "1":        "Day Camp",
    "Day Camp": "Day Camp",
    "2":        "Overnight",
    "3":        "Day & Overnight",
    "1,3":      "Day & Overnight",
    "4":        "Virtual",
}

_GENDER_LABEL = {1: "Boys", 2: "Girls"}


def _camps_url(slug: str, camp_id: int) -> str:
    return f"https://www.camps.ca/{slug}/{camp_id}"


def _normalise_website(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return "https://" + url


def _cost_str(cost_from, cost_to) -> str:
    if cost_from and cost_to and int(cost_from) != int(cost_to):
        return f"${int(cost_from):,} – ${int(cost_to):,}"
    if cost_from:
        return f"from ${int(cost_from):,}"
    return ""


def _age_str(age_from, age_to) -> str:
    if age_from is not None and age_to is not None:
        return f"Ages {int(age_from)}–{int(age_to)}"
    if age_from is not None:
        return f"Ages {int(age_from)}+"
    return ""


_BTN = (
    "display:inline-block; margin-right:8px; "
    "padding:5px 14px; border-radius:24px; font-size:0.78rem; font-weight:700; "
    "font-family:Nunito,sans-serif; text-decoration:none; "
    "background:#8A9A5B; color:white; "
    "box-shadow:3px 3px 8px rgba(117,131,77,0.35);"
)

_PILL = (
    "display:inline-block; margin:0 5px 0 0; "
    "padding:2px 10px; border-radius:20px; "
    "font-size:0.76rem; font-weight:600; font-family:Nunito,sans-serif; "
    "background:#f0f4e8; color:#4a6040; border:1px solid #d0dbb8;"
)


def render_card(result: dict):
    tier     = result.get("tier", "bronze")
    tier_col = _TIER_COLOUR.get(tier, _TIER_COLOUR["bronze"])

    # ── Field extraction ───────────────────────────────────────────────────────
    session_name = result.get("name") or "Summer Program"
    camp_name    = result.get("camp_name", "")
    city         = result.get("city", "")
    province     = result.get("province", "")
    location     = ", ".join(filter(None, [city, province]))
    cost         = _cost_str(result.get("cost_from"), result.get("cost_to"))
    ages         = _age_str(result.get("age_from"), result.get("age_to"))
    camp_type    = _TYPE_LABEL.get(str(result.get("type", "")), "")
    gender       = _GENDER_LABEL.get(result.get("gender"), "")
    rationale    = result.get("blurb") or ""
    website      = result.get("website", "")
    camp_slug    = result.get("slug", "")
    camp_id      = result.get("camp_id")

    # ── Line 1: Session Information ────────────────────────────────────────────
    line1 = (
        f'<p style="margin:0 0 3px 0; font-family:Nunito,sans-serif; font-weight:800; '
        f'font-size:1.05rem; color:#2F4F4F;">{session_name}</p>'
    )

    # ── Line 2: Camp Name ──────────────────────────────────────────────────────
    line2 = (
        f'<p style="margin:0 0 8px 0; font-size:0.92rem; font-weight:600; '
        f'font-family:Nunito,sans-serif; color:{tier_col};">{camp_name}</p>'
    )

    # ── Line 3: Session Details (pills) ───────────────────────────────────────
    detail_pills = []
    if camp_type:
        detail_pills.append(f'<span style="{_PILL}">🏕 {camp_type}</span>')
    if ages:
        detail_pills.append(f'<span style="{_PILL}">👦 {ages}</span>')
    if location:
        detail_pills.append(f'<span style="{_PILL}">📍 {location}</span>')
    if cost:
        detail_pills.append(f'<span style="{_PILL}">💰 {cost}</span>')
    if gender:
        detail_pills.append(f'<span style="{_PILL}">{gender} only</span>')

    line3 = (
        f'<div style="margin:0 0 8px 0; line-height:1.8;">{"".join(detail_pills)}</div>'
        if detail_pills else ""
    )

    # ── Line 4: AI Rationale ───────────────────────────────────────────────────
    line4 = (
        f'<p style="margin:0 0 10px 0; font-size:0.85rem; color:#4a5f5f; '
        f'font-family:Lato,sans-serif; line-height:1.55;">'
        f'<span style="font-weight:700; color:#8A9A5B;">✨ Why this fits:</span> '
        f'{rationale}</p>'
    ) if rationale else ""

    # ── Buttons ────────────────────────────────────────────────────────────────
    buttons_html = ""
    if camp_slug and camp_id:
        buttons_html += f'<a href="{_camps_url(camp_slug, camp_id)}" target="_blank" style="{_BTN}">View on camps.ca →</a>'
    if website:
        buttons_html += f'<a href="{_normalise_website(website)}" target="_blank" style="{_BTN}">Camp Website →</a>'

    buttons = f'<div style="margin-top:6px;">{buttons_html}</div>' if buttons_html else ""

    # ── Assemble card ──────────────────────────────────────────────────────────
    card_html = (
        f'<div style="padding:0 1.4rem; margin-bottom:10px;">'
        f'<div style="border-left:4px solid {tier_col}; border-radius:12px; '
        f'background:#ffffff; padding:14px 16px 12px 16px; '
        f'box-shadow:0 2px 8px rgba(47,79,79,0.08);">'
        + line1 + line2 + line3 + line4 + buttons
        + "</div></div>"
    )

    st.markdown(card_html, unsafe_allow_html=True)
