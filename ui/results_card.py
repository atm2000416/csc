"""
ui/results_card.py
Renders camp program result cards in Streamlit.

Visual hierarchy (full card):
  Line 1 — Session Information  (programs.name)
  Line 2 — Camp Name            (camps.camp_name, tier-coloured)
  Line 3 — Session Details      (type · ages · location · cost · gender)
  Line 4 — AI Rationale         (reranker blurb explaining why this fits)

When a camp has multiple ranked sessions, the top-ranked session is shown as the
full card; additional sessions from the same camp are collapsed into an expander
below it (render_extra_sessions).
"""
import streamlit as st
from datetime import date as _date


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

_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun",
           "Jul","Aug","Sep","Oct","Nov","Dec"]


def _date_range_str(start, end) -> str:
    """Format a date range as 'Jul 6 – 10' or 'Jul 28 – Aug 1'."""
    if not start:
        return ""
    try:
        s = start if hasattr(start, 'month') else _date.fromisoformat(str(start))
        e = end   if hasattr(end,   'month') else _date.fromisoformat(str(end))   if end else None
    except (ValueError, TypeError):
        return ""
    if e and s.month == e.month:
        return f"{_MONTHS[s.month-1]} {s.day} – {e.day}"
    if e:
        return f"{_MONTHS[s.month-1]} {s.day} – {_MONTHS[e.month-1]} {e.day}"
    return f"{_MONTHS[s.month-1]} {s.day}"


_UTM = "utm_source=camps.ca&utm_medium=ai-search&utm_campaign=csc"


def _camps_url(prettyurl: str, camp_id) -> str:
    return f"https://www.camps.ca/{prettyurl}/{camp_id}?{_UTM}"


def _normalise_website(url: str) -> str:
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{_UTM}"


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
    "display:inline-flex; align-items:center; margin-right:8px; margin-bottom:6px; "
    "padding:10px 16px; border-radius:24px; font-size:0.84rem; font-weight:700; "
    "font-family:Nunito,sans-serif; text-decoration:none; "
    "background:#8A9A5B; color:white; min-height:44px; "
    "box-shadow:3px 3px 8px rgba(117,131,77,0.35);"
)

_PILL = (
    "display:inline-block; margin:0 5px 4px 0; "
    "padding:4px 10px; border-radius:20px; "
    "font-size:0.82rem; font-weight:600; font-family:Nunito,sans-serif; "
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
    prettyurl    = result.get("prettyurl") or result.get("slug", "")

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
    if prettyurl:
        camp_id = result.get("camp_id") or result.get("id", "")
        buttons_html += f'<a href="{_camps_url(prettyurl, camp_id)}" target="_blank" style="{_BTN}">View on camps.ca →</a>'
    if website:
        buttons_html += f'<a href="{_normalise_website(website)}" target="_blank" style="{_BTN}">Camp Website →</a>'

    buttons = f'<div style="margin-top:6px;">{buttons_html}</div>' if buttons_html else ""

    # ── Assemble card ──────────────────────────────────────────────────────────
    card_html = (
        f'<div style="padding:0 0.4rem; margin-bottom:10px;">'
        f'<div style="border-left:4px solid {tier_col}; border-radius:12px; '
        f'background:#ffffff; padding:14px 16px 12px 16px; '
        f'box-shadow:0 2px 8px rgba(47,79,79,0.08);">'
        + line1 + line2 + line3 + line4 + buttons
        + "</div></div>"
    )

    st.markdown(card_html, unsafe_allow_html=True)


# ── Compact row style (used inside the expander) ──────────────────────────────
_ROW_NAME = (
    "font-family:Nunito,sans-serif; font-weight:700; font-size:0.88rem; "
    "color:#2F4F4F; margin:0 0 2px 0;"
)
_ROW_META = (
    "font-family:Lato,sans-serif; font-size:0.78rem; color:#5a7070; margin:0;"
)
_ROW_LINK = (
    "font-size:0.75rem; font-weight:700; font-family:Nunito,sans-serif; "
    "color:#8A9A5B; text-decoration:none; white-space:nowrap;"
)


def render_compact_card(result: dict):
    """
    Render a compact camp card for the "More Camps" section.
    Shows camp name, location, ages, cost, and a one-line description
    with a View button — no session-level detail or blurb.
    """
    tier     = result.get("tier", "bronze")
    tier_col = _TIER_COLOUR.get(tier, _TIER_COLOUR["bronze"])

    camp_name    = result.get("camp_name", "")
    session_name = result.get("name") or "Summer Program"
    city         = result.get("city", "")
    province     = result.get("province", "")
    location     = ", ".join(filter(None, [city, province]))
    cost         = _cost_str(result.get("cost_from"), result.get("cost_to"))
    ages         = _age_str(result.get("age_from"), result.get("age_to"))
    camp_type    = _TYPE_LABEL.get(str(result.get("type", "")), "")
    desc         = (result.get("mini_description") or result.get("description") or "")
    if desc and len(desc) > 120:
        desc = desc[:117].rsplit(" ", 1)[0] + "…"
    prettyurl    = result.get("prettyurl") or result.get("slug", "")
    website      = result.get("website", "")

    # Compact pills
    pills = []
    if camp_type:
        pills.append(f'<span style="{_PILL}">🏕 {camp_type}</span>')
    if ages:
        pills.append(f'<span style="{_PILL}">👦 {ages}</span>')
    if location:
        pills.append(f'<span style="{_PILL}">📍 {location}</span>')
    if cost:
        pills.append(f'<span style="{_PILL}">💰 {cost}</span>')
    pills_html = f'<div style="margin:4px 0 4px 0; line-height:1.8;">{"".join(pills)}</div>' if pills else ""

    # Link
    link_html = ""
    if prettyurl:
        camp_id = result.get("camp_id") or result.get("id", "")
        link_html = (
            f'<a href="{_camps_url(prettyurl, camp_id)}" target="_blank" '
            f'style="{_ROW_LINK} font-size:0.82rem;">View on camps.ca →</a>'
        )

    desc_html = (
        f'<p style="margin:0; font-size:0.84rem; color:#4a5f5f; '
        f'font-family:Lato,sans-serif; line-height:1.4;">{desc}</p>'
    ) if desc else ""

    card_html = (
        f'<div style="padding:0 0.4rem; margin-bottom:6px;">'
        f'<div style="border-left:3px solid {tier_col}; border-radius:10px; '
        f'background:#ffffff; padding:10px 14px 8px 14px; '
        f'box-shadow:0 1px 4px rgba(47,79,79,0.06);">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
        f'  <div style="flex:1; min-width:0;">'
        f'    <p style="margin:0 0 1px 0; font-family:Nunito,sans-serif; font-weight:800; '
        f'    font-size:0.95rem; color:#2F4F4F;">{camp_name}</p>'
        f'    <p style="margin:0 0 4px 0; font-size:0.82rem; font-weight:600; '
        f'    font-family:Nunito,sans-serif; color:{tier_col};">{session_name}</p>'
        f'  </div>'
        f'  <div style="padding-top:4px; flex-shrink:0;">{link_html}</div>'
        f'</div>'
        + pills_html + desc_html
        + '</div></div>'
    )

    st.markdown(card_html, unsafe_allow_html=True)


def render_extra_sessions(extra: list[dict], camp_name: str, tier: str) -> None:
    """
    Render an expander below the primary card listing additional ranked sessions
    from the same camp in a compact format.

    extra      — list of result dicts (same shape as render_card input)
    camp_name  — displayed in the expander label
    tier       — used for the accent colour on session names
    """
    if not extra:
        return

    n      = len(extra)
    label  = f"{'1 more session' if n == 1 else f'{n} more sessions'} at {camp_name}"
    tier_col = _TIER_COLOUR.get(tier, _TIER_COLOUR["bronze"])

    # Pull the expander flush against the card above it
    st.markdown(
        '<style>.extra-session-expander{margin-top:-14px !important;}</style>',
        unsafe_allow_html=True,
    )

    with st.expander(label, expanded=False):
        rows_html = []
        for r in extra:
            name      = r.get("name") or "Session"
            ages      = _age_str(r.get("age_from"), r.get("age_to"))
            cost      = _cost_str(r.get("cost_from"), r.get("cost_to"))
            camp_type = _TYPE_LABEL.get(str(r.get("type", "")), "")
            # Prefer program_dates upcoming entries, fall back to program start/end
            pdates    = r.get("program_dates") or []
            if pdates:
                first = pdates[0]
                date_s = _date_range_str(first.get("start_date"), first.get("end_date"))
            else:
                date_s = _date_range_str(r.get("start_date"), r.get("end_date"))

            meta_parts = [p for p in [camp_type, ages, cost, date_s] if p]
            meta_str   = "  ·  ".join(meta_parts)

            prettyurl = r.get("prettyurl") or r.get("slug", "")
            link_html = ""
            if prettyurl:
                camp_id = r.get("camp_id") or r.get("id", "")
                link_html = (
                    f'<a href="{_camps_url(prettyurl, camp_id)}" target="_blank" '
                    f'style="{_ROW_LINK}">View →</a>'
                )

            rows_html.append(
                f'<div style="display:flex; justify-content:space-between; '
                f'align-items:flex-start; padding:8px 0; '
                f'border-bottom:1px solid #eef1e8;">'
                f'  <div style="flex:1; min-width:0; padding-right:12px;">'
                f'    <p style="{_ROW_NAME} color:{tier_col};">{name}</p>'
                f'    <p style="{_ROW_META}">{meta_str}</p>'
                f'  </div>'
                f'  <div style="padding-top:2px;">{link_html}</div>'
                f'</div>'
            )

        # Remove bottom border from last row
        all_rows = "".join(rows_html)
        st.markdown(
            f'<div style="padding:0 4px;">{all_rows}</div>',
            unsafe_allow_html=True,
        )
