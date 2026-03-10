"""
core/fuzzy_preprocessor.py
Fuzzy Pre-processor — runs BEFORE Intent Parser, zero API cost.
Catches common misspellings, aliases, and domain-specific terms.
Returns hints dict injected into Intent Parser call.
"""
import re
from taxonomy_mapping import FUZZY_ALIASES, TRAIT_ALIASES, GEO_ALIASES, GEO_COORDS

# Build AGE_ALIASES by filtering FUZZY_ALIASES for dict values (age brackets)
AGE_ALIASES: dict[str, dict] = {
    term: val
    for term, val in FUZZY_ALIASES.items()
    if isinstance(val, dict) and "age_from" in val
}

# Sort all alias keys longest-first for greedy matching
_SORTED_FUZZY = sorted(
    [(k, v) for k, v in FUZZY_ALIASES.items() if isinstance(v, list)],
    key=lambda x: len(x[0]),
    reverse=True,
)
_SORTED_TRAIT = sorted(TRAIT_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
_SORTED_GEO = sorted(GEO_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)
_SORTED_AGE = sorted(AGE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True)


def preprocess(raw_query: str) -> dict:
    """
    Scan raw user input for known aliases and return hints.

    Returns dict with (only non-empty keys):
      - tag_hints: list of candidate tag slugs
      - trait_hints: list of candidate trait slugs
      - geo_expansion: list of cities if regional term found
      - age_bracket: {age_from, age_to} if age language found
      - needs_geolocation: True if 'near me' detected
    """
    normalized = raw_query.lower().strip()
    hints: dict = {
        "tag_hints": [],
        "trait_hints": [],
        "geo_expansion": [],
        "geo_coords": None,
        "age_bracket": None,
        "needs_geolocation": False,
    }

    def word_match(term: str, text: str) -> bool:
        """Match term as whole word(s) within text."""
        pattern = r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])'
        return bool(re.search(pattern, text))

    # Check geo aliases (longest match first)
    for region, cities in _SORTED_GEO:
        if word_match(region.lower(), normalized):
            if cities is None:
                hints["needs_geolocation"] = True
            else:
                hints["geo_expansion"] = cities
                # If we have coordinates for this location, return them too
                coords = GEO_COORDS.get(region.lower())
                if coords:
                    hints["geo_coords"] = {
                        "lat": coords[0],
                        "lon": coords[1],
                        "radius_km": coords[2],
                    }
            break

    # Check age aliases (longest match first)
    for term, bracket in _SORTED_AGE:
        if word_match(term, normalized):
            hints["age_bracket"] = bracket
            break

    # Check trait aliases (longest match first, accumulate)
    for term, slugs in _SORTED_TRAIT:
        if word_match(term, normalized):
            for s in slugs:
                if s not in hints["trait_hints"]:
                    hints["trait_hints"].append(s)

    # Check activity aliases from FUZZY_ALIASES (lists only, longest match first)
    for term, mapping in _SORTED_FUZZY:
        if word_match(term, normalized):
            for s in mapping:
                if s not in hints["tag_hints"]:
                    hints["tag_hints"].append(s)

    # Return only non-empty/non-False values
    return {k: v for k, v in hints.items() if v}
