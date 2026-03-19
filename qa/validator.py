"""
qa/validator.py
Validates QA tester findings against the live pipeline and database.
Reproduces searches, cross-references camps.ca category pages, classifies issues.
"""
import json
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.fuzzy_preprocessor import preprocess
from core.intent_parser import parse_intent
from core import cssl
from db.connection import get_connection


# camps.ca URL slug extraction pattern
_CAMPSCA_URL_RE = re.compile(
    r"camps\.ca/([a-z0-9_-]+?)(?:\.php)?(?:\?|$|#| )", re.IGNORECASE
)

# Load override index for cross-referencing
_SLUG_TO_CAMP_IDS: dict[str, list[int]] = {}
try:
    _overrides_path = os.path.join(
        os.path.dirname(__file__), "..", "db", "camp_tag_overrides.json"
    )
    with open(_overrides_path) as _f:
        for _cid_str, _slugs in json.load(_f).items():
            _cid = int(_cid_str)
            for _slug in _slugs:
                _SLUG_TO_CAMP_IDS.setdefault(_slug, []).append(_cid)
except (FileNotFoundError, json.JSONDecodeError, ValueError):
    pass

# Load CANONICAL_PAGES for URL → slug mapping
try:
    from db.tag_from_campsca_pages import CANONICAL_PAGES
except ImportError:
    CANONICAL_PAGES = {}


@dataclass
class ValidationResult:
    item_id: str
    issue_type: str  # SEARCH_QUALITY | DATA_QUALITY | UI_UX | LINK_ISSUE | EXPECTED_BEHAVIOR
    is_valid_issue: bool
    pipeline_results: list[dict] = field(default_factory=list)
    expected_camps: list[str] | None = None
    missing_camps: list[str] = field(default_factory=list)
    extra_camps: list[str] = field(default_factory=list)
    root_cause: str | None = None
    details: str = ""
    # Pipeline internals for debugging
    fuzzy_hints: dict = field(default_factory=dict)
    intent_tags: list[str] = field(default_factory=list)
    intent_ics: float = 0.0
    result_count: int = 0
    rcs: float = 0.0


def _extract_campsca_slug(text: str) -> str | None:
    """Extract a camps.ca category slug from tester text (URL or page reference)."""
    # Direct URL match
    m = _CAMPSCA_URL_RE.search(text)
    if m:
        raw = m.group(1)
        # Map URL path to slug via CANONICAL_PAGES
        for path, slugs in CANONICAL_PAGES.items():
            # path is like "/animal-camps.php" — compare against raw
            path_stem = path.lstrip("/").replace(".php", "").replace("_", "-")
            if raw.replace("_", "-") == path_stem or raw == path.lstrip("/").replace(".php", ""):
                return slugs[0] if slugs else None
        # Fallback: use raw path as slug guess
        return raw.replace("_", "-").replace("-camps", "").replace("-camp", "")
    return None


def _get_camps_for_slug(slug: str) -> dict[int, str]:
    """Return {camp_id: camp_name} for camps tagged with this slug (DB + overrides).

    If exact slug match finds nothing, tries prefix match (e.g. 'acro' -> 'acro-dance').
    """
    camps: dict[int, str] = {}

    # From override index
    for cid in _SLUG_TO_CAMP_IDS.get(slug, []):
        camps[cid] = ""  # name filled from DB below

    # Also check override index with prefix match
    if not camps:
        for override_slug, cids in _SLUG_TO_CAMP_IDS.items():
            if override_slug.startswith(slug + "-") or override_slug.startswith(slug):
                if override_slug == slug or override_slug.startswith(slug + "-"):
                    for cid in cids:
                        camps[cid] = ""

    # From program_tags
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Try exact match first, then prefix match
        actual_slug = slug
        cursor.execute(
            "SELECT slug FROM activity_tags WHERE slug = %s AND is_active = 1", (slug,)
        )
        if not cursor.fetchone():
            # Try prefix match
            cursor.execute(
                "SELECT slug FROM activity_tags WHERE slug LIKE %s AND is_active = 1 LIMIT 1",
                (slug + "%",),
            )
            row = cursor.fetchone()
            if row:
                actual_slug = row["slug"]

        cursor.execute(
            "SELECT DISTINCT c.id, c.camp_name "
            "FROM camps c "
            "JOIN programs p ON p.camp_id = c.id "
            "JOIN program_tags pt ON pt.program_id = p.id "
            "JOIN activity_tags at ON at.id = pt.tag_id "
            "WHERE at.slug = %s AND c.status = 1 AND p.status = 1",
            (actual_slug,),
        )
        for row in cursor.fetchall():
            camps[row["id"]] = row["camp_name"]

        # Fill names for override-only camps
        unnamed = [cid for cid, name in camps.items() if not name]
        if unnamed:
            ph = ", ".join(["%s"] * len(unnamed))
            cursor.execute(
                f"SELECT id, camp_name FROM camps WHERE id IN ({ph})", tuple(unnamed)
            )
            for row in cursor.fetchall():
                camps[row["id"]] = row["camp_name"]
    finally:
        cursor.close()
        conn.close()

    return camps


def _check_fuzzy_alias(term: str) -> str | None:
    """Check if a search term has a FUZZY_ALIAS mapping. Returns diagnostic string."""
    from taxonomy_mapping import FUZZY_ALIASES

    normalized = term.lower().strip()
    # Check individual words only (not full phrase)
    stop_words = {
        "camps", "camp", "with", "near", "for", "the", "and", "in", "on",
        "at", "to", "a", "an", "my", "our", "is", "are", "summer",
        "winter", "spring", "fall", "toronto", "ottawa", "vancouver",
        "montreal", "calgary", "edmonton", "winnipeg", "halifax",
        "ontario", "quebec", "alberta", "british", "columbia", "manitoba",
        "gta", "mississauga", "brampton", "markham", "scarborough",
    }
    missing = []
    for word in normalized.split():
        if word in FUZZY_ALIASES:
            continue
        if len(word) > 3 and word not in stop_words:
            missing.append(word)
    return f"No FUZZY_ALIAS for: {', '.join(missing)}" if missing else None


def _is_ui_ux_feedback(entry: dict) -> bool:
    """Detect if an entry is UI/UX feedback rather than a search issue.

    Only classifies as UI/UX when the SEARCH TERM itself is UI feedback
    (e.g. starts with "UI:", mentions links/accordion/layout).
    Tester complaints about "should display X" are NOT UI/UX — they're search quality.
    """
    search = entry.get("search_term", "").lower().strip()

    # Explicit UI prefix
    if search.startswith("ui:") or search.startswith("ui "):
        return True

    # Search term is a UI/UX description, not a camp search query
    ui_indicators = [
        "button", "click", "font", "layout", "scroll", "navigation",
        "popup", "modal", "sidebar", "dropdown", "checkbox", "radio",
        "accordion", "birdie", "profile link", "program link",
        "session name", "camp name", "icons by type",
    ]
    return any(ind in search for ind in ui_indicators)


def validate_finding(entry: dict) -> ValidationResult:
    """
    Validate a single QA tester finding against the live pipeline.

    Args:
        entry: dict with keys: item_id, search_term, chat_response, why_incorrect

    Returns:
        ValidationResult with classification and analysis
    """
    item_id = entry["item_id"]
    search_term = entry["search_term"]
    why_incorrect = entry.get("why_incorrect", "")

    # Strip common prefixes testers add (e.g. "SEARCH: ...")
    import re as _re
    search_term = _re.sub(r"^(?:SEARCH|search)\s*:\s*", "", search_term).strip()

    # UI/UX feedback — can't validate via pipeline
    if _is_ui_ux_feedback(entry):
        return ValidationResult(
            item_id=item_id,
            issue_type="UI_UX",
            is_valid_issue=True,
            details=f"UI/UX feedback noted: {why_incorrect}",
        )

    # Step 1: Run fuzzy preprocessor
    try:
        hints = preprocess(search_term)
    except Exception as e:
        return ValidationResult(
            item_id=item_id,
            issue_type="SEARCH_QUALITY",
            is_valid_issue=True,
            root_cause=f"Fuzzy preprocessor error: {e}",
            details=f"Preprocessing failed for '{search_term}': {e}",
        )

    # Step 2: Run intent parser
    try:
        intent = parse_intent(search_term, fuzzy_hints=hints)
    except Exception as e:
        return ValidationResult(
            item_id=item_id,
            issue_type="SEARCH_QUALITY",
            is_valid_issue=True,
            fuzzy_hints=hints,
            root_cause=f"Intent parser error: {e}",
            details=f"Intent parsing failed for '{search_term}': {e}",
        )

    # Step 3: Build params and run CSSL
    params = {}
    if intent.tags:
        params["tags"] = intent.tags
    if intent.exclude_tags:
        params["exclude_tags"] = intent.exclude_tags
    if intent.city:
        params["city"] = intent.city
    if intent.cities:
        params["cities"] = intent.cities
    if intent.province:
        params["province"] = intent.province
    if intent.age_from is not None:
        params["age_from"] = intent.age_from
    if intent.age_to is not None:
        params["age_to"] = intent.age_to
    if intent.type:
        params["type"] = intent.type
    if intent.gender:
        params["gender"] = intent.gender
    if intent.traits:
        params["traits"] = intent.traits
    if intent.is_special_needs:
        params["is_special_needs"] = True
    if intent.is_virtual:
        params["is_virtual"] = True
    if intent.lat is not None:
        params["lat"] = intent.lat
    if intent.lon is not None:
        params["lon"] = intent.lon
    if intent.radius_km is not None:
        params["radius_km"] = intent.radius_km
    if intent.date_from:
        params["date_from"] = intent.date_from
    if intent.date_to:
        params["date_to"] = intent.date_to
    if intent.cost_max is not None:
        params["cost_max"] = intent.cost_max

    try:
        results, rcs = cssl.query(params)
    except Exception as e:
        return ValidationResult(
            item_id=item_id,
            issue_type="SEARCH_QUALITY",
            is_valid_issue=True,
            fuzzy_hints=hints,
            intent_tags=intent.tags,
            intent_ics=intent.ics,
            root_cause=f"CSSL query error: {e}",
            details=f"Database query failed for '{search_term}': {e}",
        )

    result_camp_ids = {r["camp_id"] for r in results}
    result_camp_names = {r["camp_id"]: r.get("camp_name", "") for r in results}

    # Step 4: Cross-reference with camps.ca category page (if URL in tester feedback)
    expected_slug = _extract_campsca_slug(why_incorrect)
    if not expected_slug:
        expected_slug = _extract_campsca_slug(entry.get("chat_response", ""))

    expected_camps: dict[int, str] | None = None
    missing_camps: list[str] = []
    extra_camps: list[str] = []

    if expected_slug:
        expected_camps = _get_camps_for_slug(expected_slug)
        if expected_camps:
            expected_ids = set(expected_camps.keys())
            missing_ids = expected_ids - result_camp_ids
            extra_ids = result_camp_ids - expected_ids
            missing_camps = [
                expected_camps.get(cid, f"camp_id={cid}") for cid in missing_ids
            ]
            extra_camps = [
                result_camp_names.get(cid, f"camp_id={cid}") for cid in extra_ids
            ]

    # Step 5: Check for missing fuzzy aliases
    alias_diagnostic = _check_fuzzy_alias(search_term)

    # Step 6: Classify
    result = ValidationResult(
        item_id=item_id,
        issue_type="EXPECTED_BEHAVIOR",
        is_valid_issue=False,
        pipeline_results=results[:10],  # keep top 10 for response
        expected_camps=[expected_camps[k] for k in expected_camps] if expected_camps else None,
        missing_camps=missing_camps,
        extra_camps=extra_camps,
        fuzzy_hints=hints,
        intent_tags=intent.tags,
        intent_ics=intent.ics,
        result_count=len(results),
        rcs=rcs,
    )

    # Classify based on findings
    if len(results) == 0:
        result.issue_type = "SEARCH_QUALITY"
        result.is_valid_issue = True
        if not intent.tags and not intent.traits:
            result.root_cause = (
                f"No tags extracted from '{search_term}'. "
                f"{alias_diagnostic or 'Intent parser returned no tags.'}"
            )
        elif alias_diagnostic:
            result.root_cause = alias_diagnostic
        else:
            result.root_cause = (
                f"Tags {intent.tags} resolved but zero results from CSSL. "
                f"Possible filter combination too narrow."
            )
        result.details = (
            f"Zero results for '{search_term}'. "
            f"Tags: {intent.tags}, ICS: {intent.ics:.2f}. "
            f"{result.root_cause}"
        )

    elif missing_camps and len(missing_camps) > len(results) // 2:
        result.issue_type = "SEARCH_QUALITY"
        result.is_valid_issue = True
        result.root_cause = (
            f"{len(missing_camps)} camps from camps.ca/{expected_slug} page "
            f"missing from results. Likely tag coverage gaps."
        )
        result.details = (
            f"Search returned {len(results)} results but {len(missing_camps)} "
            f"expected camps missing. Tags: {intent.tags}. "
            f"Missing: {', '.join(missing_camps[:5])}"
            f"{'...' if len(missing_camps) > 5 else ''}"
        )

    elif missing_camps:
        result.issue_type = "DATA_QUALITY"
        result.is_valid_issue = True
        result.root_cause = (
            f"{len(missing_camps)} camps from camps.ca page not in results — "
            f"possible tag gaps in program_tags or overrides."
        )
        result.details = (
            f"Search returned {len(results)} results. "
            f"{len(missing_camps)} camps from camps.ca/{expected_slug} missing: "
            f"{', '.join(missing_camps[:5])}"
            f"{'...' if len(missing_camps) > 5 else ''}"
        )

    elif len(results) > 0 and intent.ics >= 0.7:
        # Results exist and confidence is high — likely working correctly
        result.issue_type = "EXPECTED_BEHAVIOR"
        result.is_valid_issue = False
        result.details = (
            f"Search returned {len(results)} results with ICS={intent.ics:.2f}, "
            f"RCS={rcs:.2f}. Tags: {intent.tags}. "
            f"Pipeline appears to be working correctly for this query."
        )
        # But check the tester's complaint — maybe they expected more/different results
        if why_incorrect and any(
            w in why_incorrect.lower()
            for w in ["missing", "not shown", "didn't show", "should show", "should display",
                      "expected", "results are off", "results are wrong", "incorrect",
                      "not displaying", "aren't showing"]
        ):
            result.issue_type = "SEARCH_QUALITY"
            result.is_valid_issue = True
            result.root_cause = alias_diagnostic or "Tester reports expected results missing."
            result.details += f" Tester says: {why_incorrect}"

    else:
        # Low confidence or few results
        result.issue_type = "SEARCH_QUALITY"
        result.is_valid_issue = True
        result.root_cause = (
            f"Low confidence (ICS={intent.ics:.2f}, RCS={rcs:.2f}). "
            f"{alias_diagnostic or ''}"
        )
        result.details = (
            f"Search returned {len(results)} results with low confidence. "
            f"Tags: {intent.tags}. {result.root_cause}"
        )

    return result
