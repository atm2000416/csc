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


_UTM_SEARCH = "utm_source=camps.ca&utm_medium=ai-search&utm_campaign=search"
_UTM_MORE   = "utm_source=camps.ca&utm_medium=ai-search&utm_campaign=search_more"


def _camps_url(prettyurl: str, camp_id, ourkids_session_id=None,
               utm: str = _UTM_SEARCH) -> str:
    base = f"https://www.camps.ca/{prettyurl}/{camp_id}"
    if ourkids_session_id:
        base += f"/session/{ourkids_session_id}"
    return f"{base}?{utm}"


def _normalise_website(url: str, utm: str = _UTM_SEARCH) -> str:
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}{utm}"


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


_LINK_STYLE = (
    "font-size:0.82rem; font-weight:600; font-family:Nunito,sans-serif; "
    "color:#D93600; text-decoration:none;"
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
    ourkids_seid = result.get("ourkids_session_id")

    # ── Line 1: Session name · Camp name ──────────────────────────────────────
    line1 = (
        f'<p style="margin:0 0 3px 0; font-family:Nunito,sans-serif; font-weight:800; '
        f'font-size:1.05rem; color:#333333;">{session_name} '
        f'<span style="font-weight:600; font-size:0.92rem; color:{tier_col};">'
        f'· {camp_name}</span></p>'
    )

    # ── Line 2: Dot-separated metadata ────────────────────────────────────────
    meta_parts = [p for p in [camp_type, ages, location, cost,
                              f"{gender} only" if gender else ""] if p]
    meta_str = "  ·  ".join(meta_parts)
    line2 = (
        f'<p style="margin:0 0 5px 0; font-size:0.85rem; color:#555555; '
        f'font-family:Lato,sans-serif;">{meta_str}</p>'
    ) if meta_str else ""

    # ── Line 3: AI Rationale (one sentence, no metadata repetition) ───────────
    line3 = (
        f'<p style="margin:0 0 6px 0; font-size:0.85rem; color:#555555; '
        f'font-style:italic; font-family:Lato,sans-serif; line-height:1.45;">'
        f'{rationale}</p>'
    ) if rationale else ""

    # ── Line 4: Text links ────────────────────────────────────────────────────
    links = []
    if prettyurl:
        camp_id = result.get("camp_id") or result.get("id", "")
        url = _camps_url(prettyurl, camp_id, ourkids_seid)
        links.append(
            f'<a href="{url}" target="_blank" rel="noopener" '
            f'style="{_LINK_STYLE}">View Program ↗</a>'
        )
    if website:
        links.append(
            f'<a href="{_normalise_website(website)}" target="_blank" '
            f'rel="noopener noreferrer" style="{_LINK_STYLE}">Camp Website ↗</a>'
        )
    line4 = (
        f'<p style="margin:0;">{"  ·  ".join(links)}</p>'
    ) if links else ""

    # ── Assemble card ──────────────────────────────────────────────────────────
    return (
        f'<div style="padding:0 0.4rem; margin-bottom:10px;">'
        f'<div style="border-left:4px solid {tier_col}; border-radius:12px; '
        f'background:#ffffff; padding:14px 16px 12px 16px; '
        f'box-shadow:0 2px 8px rgba(0,0,0,0.06);">'
        + line1 + line2 + line3 + line4
        + "</div></div>"
    )


# ── Compact row style (used inside the expander) ──────────────────────────────
_ROW_NAME = (
    "font-family:Nunito,sans-serif; font-weight:700; font-size:0.88rem; "
    "color:#333333; margin:0 0 2px 0;"
)
_ROW_META = (
    "font-family:Lato,sans-serif; font-size:0.78rem; color:#555555; margin:0;"
)
_ROW_LINK = (
    "font-size:0.75rem; font-weight:700; font-family:Nunito,sans-serif; "
    "color:#D93600; text-decoration:none; white-space:nowrap;"
)


def render_compact_card(result: dict):
    """
    Render a compact camp card for the "More Camps" section.
    Slim format: session · camp, dot-separated metadata, link.
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
    prettyurl    = result.get("prettyurl") or result.get("slug", "")
    ourkids_seid = result.get("ourkids_session_id")

    meta_parts = [p for p in [camp_type, ages, location, cost] if p]
    meta_str = "  ·  ".join(meta_parts)

    # Link
    link_html = ""
    if prettyurl:
        camp_id = result.get("camp_id") or result.get("id", "")
        link_html = (
            f'<a href="{_camps_url(prettyurl, camp_id, ourkids_seid)}" '
            f'target="_blank" rel="noopener" '
            f'style="{_ROW_LINK} font-size:0.82rem;">View Program ↗</a>'
        )

    card_html = (
        f'<div style="padding:0 0.4rem; margin-bottom:6px;">'
        f'<div style="border-left:3px solid {tier_col}; border-radius:10px; '
        f'background:#ffffff; padding:10px 14px 8px 14px; '
        f'box-shadow:0 1px 4px rgba(0,0,0,0.05);">'
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
        f'  <div style="flex:1; min-width:0;">'
        f'    <p style="margin:0 0 2px 0; font-family:Nunito,sans-serif; font-weight:800; '
        f'    font-size:0.95rem; color:#333333;">{session_name} '
        f'    <span style="font-weight:600; font-size:0.85rem; color:{tier_col};">'
        f'    · {camp_name}</span></p>'
        f'    <p style="margin:0; font-size:0.82rem; color:#555555; '
        f'    font-family:Lato,sans-serif;">{meta_str}</p>'
        f'  </div>'
        f'  <div style="padding-top:4px; flex-shrink:0;">{link_html}</div>'
        f'</div>'
        + '</div></div>'
    )

    return card_html


def render_extra_sessions(extra: list[dict], camp_name: str, tier: str) -> None:
    """
    Render an expander below the primary card listing additional ranked sessions
    from the same camp in a compact format.

    extra      — list of result dicts (same shape as render_card input)
    camp_name  — displayed in the expander label
    tier       — used for the accent colour on session names
    """
    if not extra:
        return ""

    n      = len(extra)
    label  = f"{'1 more session' if n == 1 else f'{n} more sessions'} at {camp_name}"
    tier_col = _TIER_COLOUR.get(tier, _TIER_COLOUR["bronze"])

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
        ourkids_seid = r.get("ourkids_session_id")
        link_html = ""
        if prettyurl:
            camp_id = r.get("camp_id") or r.get("id", "")
            link_html = (
                f'<a href="{_camps_url(prettyurl, camp_id, ourkids_seid, _UTM_MORE)}" '
                f'target="_blank" rel="noopener" '
                f'style="{_ROW_LINK}">View ↗</a>'
            )

        rows_html.append(
            f'<div style="display:flex; justify-content:space-between; '
            f'align-items:flex-start; padding:8px 0; '
            f'border-bottom:1px solid #e0e0e0;">'
            f'  <div style="flex:1; min-width:0; padding-right:12px;">'
            f'    <p style="{_ROW_NAME} color:{tier_col};">{name}</p>'
            f'    <p style="{_ROW_META}">{meta_str}</p>'
            f'  </div>'
            f'  <div style="padding-top:2px;">{link_html}</div>'
            f'</div>'
        )

    all_rows = "".join(rows_html)
    return (
        f'<details style="margin:-8px 0.4rem 10px; cursor:pointer;">'
        f'<summary style="font-family:Nunito,sans-serif; font-size:0.82rem; '
        f'font-weight:700; color:#555555; padding:6px 0;">{label}</summary>'
        f'<div style="padding:0 4px;">{all_rows}</div>'
        f'</details>'
    )
