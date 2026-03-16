#!/usr/bin/env python3
"""
tests/parity_suite.py — Camp Search Parity Suite

Measures alignment between camps.ca canonical pages, the bridge artifact
(camp_tag_overrides.json), and live CSSL retrieval.

Layers:
  0   Canonical registry integrity
  1a  Fuzzy interpretation parity (deterministic, no API cost)
  1b  Parser interpretation parity (Claude Haiku, requires ANTHROPIC_API_KEY)
  2   Bridge/override coverage
  3   Retrieval parity (against bridge artifact — requires DB)

Usage:
    python3 tests/parity_suite.py                     # Layers 0 + 2 (no DB/API)
    python3 tests/parity_suite.py --with-db            # + Layer 3
    python3 tests/parity_suite.py --with-fuzzy         # + Layer 1a
    python3 tests/parity_suite.py --with-parser        # + Layer 1a + 1b (API cost)
    python3 tests/parity_suite.py --slug hockey        # Single slug deep-dive (DB)
    python3 tests/parity_suite.py --csv report.csv     # Export to CSV
"""
import argparse
import csv
import json
import os
import sys

# ── Ensure project root is on sys.path ──────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from db.tag_from_campsca_pages import CANONICAL_PAGES, PAGE_SLUG_OVERRIDES, WEBITEMS_TO_SLUG


# ── Data loaders ────────────────────────────────────────────────────────────

def load_bridge() -> dict[str, list[int]]:
    """Load camp_tag_overrides.json → inverted: slug → [camp_ids]."""
    path = os.path.join(PROJECT_ROOT, "db", "camp_tag_overrides.json")
    with open(path) as f:
        raw = json.load(f)  # camp_id_str → [slugs]
    slug_to_camps: dict[str, list[int]] = {}
    for cid_str, slugs in raw.items():
        cid = int(cid_str)
        for slug in slugs:
            slug_to_camps.setdefault(slug, []).append(cid)
    return slug_to_camps


def build_slug_registry() -> dict[str, dict]:
    """
    Build unified slug registry from CANONICAL_PAGES + PAGE_SLUG_OVERRIDES.

    Returns slug → {
        "canonical_pages": [page_path, ...],
        "override_pages": [page_path, ...],
    }
    """
    registry: dict[str, dict] = {}
    for path, slugs in CANONICAL_PAGES.items():
        for slug in slugs:
            entry = registry.setdefault(slug, {"canonical_pages": [], "override_pages": []})
            entry["canonical_pages"].append(path)
    for path, slugs in PAGE_SLUG_OVERRIDES.items():
        for slug in slugs:
            entry = registry.setdefault(slug, {"canonical_pages": [], "override_pages": []})
            entry["override_pages"].append(path)
    return registry


# ── Layer 0: Canonical Registry Integrity ───────────────────────────────────

def layer_0(slug_registry: dict, bridge: dict) -> list[dict]:
    """Check structural health of the canonical page registry."""
    issues = []

    # 0a. Duplicate page paths across both registries
    all_paths_canonical = list(CANONICAL_PAGES.keys())
    all_paths_override = list(PAGE_SLUG_OVERRIDES.keys())
    overlap = set(all_paths_canonical) & set(all_paths_override)
    for path in sorted(overlap):
        c_slugs = CANONICAL_PAGES[path]
        o_slugs = PAGE_SLUG_OVERRIDES[path]
        if set(c_slugs) != set(o_slugs):
            issues.append({
                "check": "duplicate_path_slug_mismatch",
                "path": path,
                "canonical_slugs": c_slugs,
                "override_slugs": o_slugs,
            })
        else:
            issues.append({
                "check": "duplicate_path_same_slugs",
                "path": path,
                "slugs": c_slugs,
            })

    # 0b. Empty slug lists
    for path, slugs in list(CANONICAL_PAGES.items()) + list(PAGE_SLUG_OVERRIDES.items()):
        if not slugs:
            issues.append({"check": "empty_slug_list", "path": path})

    # 0c. Slugs in page registry that have zero bridge coverage
    all_page_slugs = set(slug_registry.keys())
    bridge_slugs = set(bridge.keys())
    unbridged = sorted(all_page_slugs - bridge_slugs)
    for slug in unbridged:
        issues.append({
            "check": "slug_not_in_bridge",
            "slug": slug,
            "pages": slug_registry[slug]["canonical_pages"] + slug_registry[slug]["override_pages"],
        })

    # 0d. Bridge slugs that have no page in the registry
    orphan_bridge = sorted(bridge_slugs - all_page_slugs)
    for slug in orphan_bridge:
        issues.append({
            "check": "bridge_slug_no_page",
            "slug": slug,
            "camp_count": len(bridge[slug]),
        })

    # 0e. Summary stats
    stats = {
        "check": "summary",
        "canonical_pages": len(CANONICAL_PAGES),
        "override_pages": len(PAGE_SLUG_OVERRIDES),
        "total_unique_slugs_in_pages": len(all_page_slugs),
        "total_unique_slugs_in_bridge": len(bridge_slugs),
        "slugs_in_both": len(all_page_slugs & bridge_slugs),
        "slugs_only_in_pages": len(all_page_slugs - bridge_slugs),
        "slugs_only_in_bridge": len(bridge_slugs - all_page_slugs),
        "page_path_overlaps": len(overlap),
    }
    issues.insert(0, stats)

    return issues


def print_layer_0(issues: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("  LAYER 0 — Canonical Registry Integrity")
    print("=" * 78)

    stats = issues[0]
    print(f"\n  Canonical pages:       {stats['canonical_pages']}")
    print(f"  Override pages:        {stats['override_pages']}")
    print(f"  Unique slugs (pages):  {stats['total_unique_slugs_in_pages']}")
    print(f"  Unique slugs (bridge): {stats['total_unique_slugs_in_bridge']}")
    print(f"  Slugs in both:         {stats['slugs_in_both']}")
    print(f"  Slugs only in pages:   {stats['slugs_only_in_pages']}")
    print(f"  Slugs only in bridge:  {stats['slugs_only_in_bridge']}")
    print(f"  Path overlaps:         {stats['page_path_overlaps']}")

    problems = [i for i in issues[1:] if i["check"] not in ("summary",)]
    if not problems:
        print("\n  No issues found.")
        return

    # Group by check type
    by_check: dict[str, list] = {}
    for item in problems:
        by_check.setdefault(item["check"], []).append(item)

    for check, items in by_check.items():
        print(f"\n  [{check}] ({len(items)} found)")
        for item in items[:15]:  # cap display
            if check == "slug_not_in_bridge":
                print(f"    {item['slug']:40s}  pages: {', '.join(item['pages'][:3])}")
            elif check == "bridge_slug_no_page":
                print(f"    {item['slug']:40s}  bridge camps: {item['camp_count']}")
            elif check == "duplicate_path_slug_mismatch":
                print(f"    {item['path']:40s}  canonical={item['canonical_slugs']} vs override={item['override_slugs']}")
            elif check == "duplicate_path_same_slugs":
                print(f"    {item['path']:40s}  (identical slugs — harmless)")
            elif check == "empty_slug_list":
                print(f"    {item['path']}")
        if len(items) > 15:
            print(f"    ... and {len(items) - 15} more")


# ── Layer 1: Interpretation Parity ──────────────────────────────────────────
#
# Tests whether the fuzzy preprocessor (1a) and intent parser (1b) resolve
# user queries to the correct slug(s) for each canonical page concept.
#
# Test cases are generated from the page registry + curated orphan slugs.
# Each concept gets multiple query variants: title-style, simple, natural-language.

def _slug_to_human(slug: str) -> str:
    """Convert a slug to a readable activity name: 'hockey' → 'Hockey'."""
    return slug.replace("-", " ").replace("multi", "").strip().title().strip()


def _build_query_variants(slug: str) -> list[dict]:
    """
    Generate query variants for a slug, grouped by difficulty.

    Returns list of {query, variant_type} dicts.
    """
    human = _slug_to_human(slug)
    variants = []

    # 1. Title-style (easiest — maps directly to page title)
    variants.append({"query": f"{human} Camps", "variant_type": "title"})

    # 2. Simple query (lowercase, no "camps")
    if human.lower() != slug:
        variants.append({"query": human.lower(), "variant_type": "simple"})
    else:
        variants.append({"query": f"{human.lower()} camp", "variant_type": "simple"})

    # 3. Natural-language (harder — requires interpretation)
    _NL_TEMPLATES = [
        "my kid wants to try {activity} this summer",
        "looking for {activity} programs for my daughter",
        "{activity} for kids near Toronto",
    ]
    # Use first template for standard, second for variety
    nl = _NL_TEMPLATES[hash(slug) % len(_NL_TEMPLATES)]
    variants.append({"query": nl.format(activity=human.lower()), "variant_type": "natural"})

    return variants


# ── Curated orphan concepts for Layer 1 testing ─────────────────────────────
# High-value orphan slugs: in WEBITEMS (real activities), popular enough to
# matter, and represent concepts a real user would search for.
# Triaged from the 85 bridge-only slugs found in Layer 0.

ORPHAN_HIGH_VALUE = [
    # Sports (popular, likely searched)
    "archery", "badminton", "diving", "flag-football", "hiking",
    "mountain-biking", "pickleball", "squash", "track-and-field",
    "survival-skills", "ropes-course", "whitewater-rafting",
    # Arts / Music (distinct sub-activities)
    "videography", "percussion", "woodworking", "3d-design",
    # Tech
    "roblox", "web-design",
    # Education
    "leadership-training", "mindfulness-training", "zoology",
    "skilled-trades-activities", "test-preparation",
]

ORPHAN_NICHE = [
    # Real activities but very few camps (1-4) or very specialized
    "3d-printing", "arduino", "board-sailing", "ceramics", "harry-potter",
    "makeup-artistry", "marine-biology", "medical-science", "meditation",
    "rowing", "safari", "sewing", "surfing", "web-development", "zip-line",
]

ORPHAN_CATEGORY_LEVEL = [
    # Parent/umbrella slugs — not direct search targets
    "adventure", "arts", "education", "health-fitness", "sports",
    "computers-tech", "health-science", "instructor-led-group",
    "instructor-led-one-on-one", "jam-camp", "musical-instrument-training",
    "sports-instructional-training", "gaga", "flag-football",
]


def build_layer1_test_cases(slug_registry: dict, bridge: dict) -> list[dict]:
    """
    Generate interpretation test cases for all page-registry slugs
    plus curated high-value orphans.

    Returns list of {slug, query, variant_type, source} dicts.
    """
    cases = []

    # All page-registry slugs
    for slug in sorted(slug_registry.keys()):
        for v in _build_query_variants(slug):
            cases.append({
                "slug": slug,
                "query": v["query"],
                "variant_type": v["variant_type"],
                "source": "page_registry",
            })

    # High-value orphans
    for slug in ORPHAN_HIGH_VALUE:
        for v in _build_query_variants(slug):
            cases.append({
                "slug": slug,
                "query": v["query"],
                "variant_type": v["variant_type"],
                "source": "orphan_high_value",
            })

    return cases


def _check_fuzzy_hit(slug: str, hints: dict) -> bool:
    """Check if fuzzy hints contain the expected slug (or a parent that expands to it)."""
    tag_hints = hints.get("tag_hints", [])
    if slug in tag_hints:
        return True
    # Also accept parent multi-slugs that expand to include this slug
    # e.g. "dance-multi" is acceptable for "ballet" queries where ballet is a child
    return False


def layer_1a(cases: list[dict]) -> list[dict]:
    """
    Layer 1a: Fuzzy interpretation parity.
    Deterministic, zero API cost.

    For each test case, runs fuzzy_preprocessor.preprocess() and checks
    whether the expected slug appears in tag_hints.
    """
    from core.fuzzy_preprocessor import preprocess

    results = []
    for case in cases:
        hints = preprocess(case["query"])
        tag_hints = hints.get("tag_hints", [])
        hit = case["slug"] in tag_hints

        results.append({
            **case,
            "fuzzy_hit": hit,
            "fuzzy_tag_hints": tag_hints,
            "fuzzy_all_hints": hints,
        })

    return results


def print_layer_1a(results: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("  LAYER 1a — Fuzzy Interpretation Parity")
    print("  (deterministic, zero API cost)")
    print("=" * 78)

    hits = [r for r in results if r["fuzzy_hit"]]
    misses = [r for r in results if not r["fuzzy_hit"]]

    # Break down by variant type
    by_variant: dict[str, dict] = {}
    for r in results:
        vt = r["variant_type"]
        by_variant.setdefault(vt, {"total": 0, "hits": 0})
        by_variant[vt]["total"] += 1
        if r["fuzzy_hit"]:
            by_variant[vt]["hits"] += 1

    # Break down by source
    by_source: dict[str, dict] = {}
    for r in results:
        src = r["source"]
        by_source.setdefault(src, {"total": 0, "hits": 0})
        by_source[src]["total"] += 1
        if r["fuzzy_hit"]:
            by_source[src]["hits"] += 1

    print(f"\n  Total test cases:  {len(results)}")
    print(f"  Fuzzy hits:        {len(hits)} ({len(hits)/len(results):.1%})")
    print(f"  Fuzzy misses:      {len(misses)} ({len(misses)/len(results):.1%})")

    print(f"\n  By variant type:")
    for vt in ["title", "simple", "natural"]:
        if vt in by_variant:
            d = by_variant[vt]
            rate = d["hits"] / d["total"] if d["total"] else 0
            print(f"    {vt:12s}  {d['hits']:4d}/{d['total']:4d}  ({rate:.1%})")

    print(f"\n  By source:")
    for src in ["page_registry", "orphan_high_value"]:
        if src in by_source:
            d = by_source[src]
            rate = d["hits"] / d["total"] if d["total"] else 0
            print(f"    {src:20s}  {d['hits']:4d}/{d['total']:4d}  ({rate:.1%})")

    # Per-slug miss analysis — group misses by slug
    miss_by_slug: dict[str, list] = {}
    for r in misses:
        miss_by_slug.setdefault(r["slug"], []).append(r)

    # Slugs that missed ALL variants (complete fuzzy blind spots)
    all_variants_by_slug: dict[str, list] = {}
    for r in results:
        all_variants_by_slug.setdefault(r["slug"], []).append(r)

    blind_spots = []
    partial_misses = []
    for slug, slug_results in sorted(all_variants_by_slug.items()):
        slug_hits = sum(1 for r in slug_results if r["fuzzy_hit"])
        if slug_hits == 0:
            blind_spots.append(slug)
        elif slug_hits < len(slug_results):
            partial_misses.append((slug, slug_hits, len(slug_results)))

    if blind_spots:
        print(f"\n  COMPLETE BLIND SPOTS ({len(blind_spots)} slugs — fuzzy missed ALL variants):")
        for slug in blind_spots:
            src = all_variants_by_slug[slug][0]["source"]
            # Show what fuzzy DID return for the title query
            title_case = next((r for r in all_variants_by_slug[slug] if r["variant_type"] == "title"), None)
            got = title_case["fuzzy_tag_hints"][:5] if title_case else []
            print(f"    {slug:40s}  [{src}]  fuzzy returned: {got}")

    if partial_misses:
        print(f"\n  PARTIAL MISSES ({len(partial_misses)} slugs — some variants hit, some missed):")
        for slug, nhits, ntotal in partial_misses[:30]:
            missed_variants = [r["variant_type"] for r in all_variants_by_slug[slug] if not r["fuzzy_hit"]]
            print(f"    {slug:40s}  {nhits}/{ntotal} hit  missed: {missed_variants}")


def layer_1b(cases: list[dict], l1a_results: list[dict]) -> list[dict]:
    """
    Layer 1b: Parser interpretation parity.
    Runs Claude Haiku on cases where fuzzy missed.

    Strategy: only test cases where fuzzy MISSED the slug, to see if the
    parser recovers. Also tests a sample of fuzzy hits to confirm parser
    doesn't override good fuzzy hints with wrong slugs.

    Requires ANTHROPIC_API_KEY.
    """
    import time
    from core.intent_parser import parse_intent
    from core.fuzzy_preprocessor import preprocess

    # Select cases: all fuzzy misses + a sample of title-variant hits
    l1a_by_key = {(r["slug"], r["query"]): r for r in l1a_results}

    to_test = []
    # All fuzzy misses
    for r in l1a_results:
        if not r["fuzzy_hit"]:
            to_test.append(r)

    # Sample of fuzzy hits (title variants only, cap at 30)
    hit_titles = [r for r in l1a_results if r["fuzzy_hit"] and r["variant_type"] == "title"]
    import random
    random.seed(42)
    sample = random.sample(hit_titles, min(30, len(hit_titles)))
    for r in sample:
        if (r["slug"], r["query"]) not in {(t["slug"], t["query"]) for t in to_test}:
            to_test.append({**r, "_is_confirmation_sample": True})

    results = []
    total = len(to_test)
    print(f"\n  Running {total} parser calls (fuzzy misses + confirmation sample)...")

    for i, case in enumerate(to_test):
        if (i + 1) % 20 == 0:
            print(f"    {i+1}/{total}...")

        query = case["query"]
        hints = preprocess(query)
        try:
            intent = parse_intent(query, fuzzy_hints=hints if hints else None)
            parser_tags = intent.tags
            parser_hit = case["slug"] in parser_tags
            error = None
        except Exception as e:
            parser_tags = []
            parser_hit = False
            error = str(e)

        results.append({
            "slug": case["slug"],
            "query": case["query"],
            "variant_type": case["variant_type"],
            "source": case["source"],
            "fuzzy_hit": case["fuzzy_hit"],
            "parser_hit": parser_hit,
            "parser_tags": parser_tags,
            "error": error,
            "is_confirmation": case.get("_is_confirmation_sample", False),
        })

        # Light rate limiting
        time.sleep(0.15)

    return results


def print_layer_1b(results: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("  LAYER 1b — Parser Interpretation Parity")
    print("  (Claude Haiku — tests fuzzy misses + confirmation sample)")
    print("=" * 78)

    misses = [r for r in results if not r["is_confirmation"]]
    confirmations = [r for r in results if r["is_confirmation"]]

    # Fuzzy misses recovered by parser
    if misses:
        recovered = [r for r in misses if r["parser_hit"]]
        still_missed = [r for r in misses if not r["parser_hit"] and not r["error"]]
        errors = [r for r in misses if r["error"]]

        print(f"\n  Fuzzy misses tested:     {len(misses)}")
        print(f"  Parser recovered:        {len(recovered)} ({len(recovered)/len(misses):.1%})")
        print(f"  Still missed (both):     {len(still_missed)}")
        print(f"  Errors:                  {len(errors)}")

        if still_missed:
            print(f"\n  BOTH FUZZY AND PARSER MISSED ({len(still_missed)}):")
            by_slug: dict[str, list] = {}
            for r in still_missed:
                by_slug.setdefault(r["slug"], []).append(r)
            for slug in sorted(by_slug.keys()):
                items = by_slug[slug]
                variants = [r["variant_type"] for r in items]
                got = items[0]["parser_tags"][:5]
                print(f"    {slug:40s}  missed variants: {variants}  parser returned: {got}")

        if recovered:
            print(f"\n  PARSER RECOVERED (fuzzy missed, parser found — {len(recovered)}):")
            for r in sorted(recovered, key=lambda x: x["slug"])[:30]:
                print(f"    {r['slug']:35s}  [{r['variant_type']}] \"{r['query'][:50]}\"")

    # Confirmation sample
    if confirmations:
        confirmed = [r for r in confirmations if r["parser_hit"]]
        broken = [r for r in confirmations if not r["parser_hit"] and not r["error"]]
        print(f"\n  Confirmation sample:     {len(confirmations)}")
        print(f"  Parser confirmed fuzzy:  {len(confirmed)} ({len(confirmed)/len(confirmations):.1%})")
        if broken:
            print(f"  Parser BROKE fuzzy hit:  {len(broken)}")
            for r in broken:
                print(f"    {r['slug']:35s}  \"{r['query'][:50]}\"  parser returned: {r['parser_tags'][:5]}")


# ── Layer 2: Bridge/Override Coverage ───────────────────────────────────────

def layer_2(slug_registry: dict, bridge: dict) -> list[dict]:
    """
    For each slug in the page registry, measure bridge coverage.

    NOTE: The bridge (camp_tag_overrides.json) is the artifact being measured,
    not ground truth. It reflects what was last scraped from camps.ca pages +
    what exists in program_tags. Camps.ca itself may list more or fewer camps
    at any given time.
    """
    rows = []
    for slug in sorted(slug_registry.keys()):
        info = slug_registry[slug]
        bridge_camps = bridge.get(slug, [])
        rows.append({
            "slug": slug,
            "bridge_camp_count": len(bridge_camps),
            "canonical_pages": info["canonical_pages"],
            "override_pages": info["override_pages"],
            "total_page_refs": len(info["canonical_pages"]) + len(info["override_pages"]),
        })
    return rows


def print_layer_2(rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("  LAYER 2 — Bridge/Override Coverage")
    print("  (measured against camp_tag_overrides.json — bridge artifact, not camps.ca truth)")
    print("=" * 78)

    zero = [r for r in rows if r["bridge_camp_count"] == 0]
    low = [r for r in rows if 0 < r["bridge_camp_count"] < 5]
    healthy = [r for r in rows if r["bridge_camp_count"] >= 5]

    print(f"\n  Total slugs in page registry: {len(rows)}")
    print(f"  Zero bridge coverage:         {len(zero)}")
    print(f"  Low coverage (1-4 camps):     {len(low)}")
    print(f"  Healthy (5+ camps):           {len(healthy)}")

    if zero:
        print(f"\n  ZERO COVERAGE ({len(zero)} slugs) — these pages have no bridge backup:")
        for r in zero:
            pages = r["canonical_pages"] + r["override_pages"]
            print(f"    {r['slug']:40s}  pages: {', '.join(pages[:3])}")

    if low:
        print(f"\n  LOW COVERAGE ({len(low)} slugs):")
        for r in low:
            print(f"    {r['slug']:40s}  {r['bridge_camp_count']} camps")

    # Top 20 by coverage
    by_count = sorted(rows, key=lambda r: r["bridge_camp_count"], reverse=True)
    print(f"\n  TOP 20 by bridge camp count:")
    for r in by_count[:20]:
        print(f"    {r['slug']:40s}  {r['bridge_camp_count']:4d} camps")


# ── Layer 3: Retrieval Parity ───────────────────────────────────────────────

def layer_3(slug_registry: dict, bridge: dict,
            filter_slug: str | None = None) -> list[dict]:
    """
    Compare CSSL retrieval against bridge artifact for each slug.

    IMPORTANT: The "expected" set comes from the bridge (camp_tag_overrides.json),
    which is a scraped artifact, not ground truth. Results are parity-against-bridge,
    not parity-against-camps.ca.

    Requires DB access.
    """
    from db.connection import get_connection

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Load tag slug → id
    cursor.execute("SELECT id, slug FROM activity_tags WHERE is_active = 1")
    slug_to_id = {r["slug"]: r["id"] for r in cursor.fetchall()}

    # Load categories for expansion
    cursor.execute("SELECT slug, filter_activity_tags FROM categories WHERE is_active = 1")
    cat_expansion: dict[str, list[str]] = {}
    for row in cursor.fetchall():
        if row["filter_activity_tags"]:
            cat_expansion[row["slug"]] = [
                s.strip() for s in row["filter_activity_tags"].split(",") if s.strip()
            ]

    slugs_to_check = [filter_slug] if filter_slug else sorted(slug_registry.keys())
    rows = []

    for slug in slugs_to_check:
        # Expand slug via categories hierarchy
        expanded = {slug}
        if slug in cat_expansion:
            expanded.update(cat_expansion[slug])

        # Resolve to tag_ids
        tag_ids = [slug_to_id[s] for s in expanded if s in slug_to_id]
        if not tag_ids:
            rows.append({
                "slug": slug,
                "error": "no_tag_ids",
                "expanded_slugs": sorted(expanded),
            })
            continue

        # Query: what camp_ids does CSSL find via program_tags?
        ph = ", ".join(["%s"] * len(tag_ids))
        cursor.execute(f"""
            SELECT DISTINCT p.camp_id
            FROM programs p
            JOIN camps c ON p.camp_id = c.id
            JOIN program_tags pt ON p.id = pt.program_id
            WHERE pt.tag_id IN ({ph})
              AND p.status = 1
              AND c.status = 1
              AND (p.end_date IS NULL OR p.end_date >= CURDATE())
        """, tuple(tag_ids))
        tagged_camps = {r["camp_id"] for r in cursor.fetchall()}

        # Bridge camps for this slug (and its expanded children)
        bridge_camps: set[int] = set()
        for s in expanded:
            bridge_camps.update(bridge.get(s, []))

        # What CSSL actually returns = tagged_camps UNION override_camps
        # The override path adds bridge camps directly (that's the parallel lookup).
        # But those override camps still need status=1 + active programs to appear.
        # Check which bridge camps are actually retrievable.
        if bridge_camps:
            ph2 = ", ".join(["%s"] * len(bridge_camps))
            cursor.execute(f"""
                SELECT DISTINCT p.camp_id
                FROM programs p
                JOIN camps c ON p.camp_id = c.id
                WHERE p.camp_id IN ({ph2})
                  AND p.status = 1
                  AND c.status = 1
                  AND (p.end_date IS NULL OR p.end_date >= CURDATE())
            """, tuple(bridge_camps))
            retrievable_bridge = {r["camp_id"] for r in cursor.fetchall()}
        else:
            retrievable_bridge = set()

        # CSSL effective result = tagged via program_tags + retrievable bridge camps
        cssl_camps = tagged_camps | retrievable_bridge

        # Bridge camps that are NOT retrievable (inactive/expired/no programs)
        unretrievable_bridge = bridge_camps - retrievable_bridge

        # Parity metrics: compare cssl_camps vs bridge_camps
        # (using retrievable_bridge as the fair expected set)
        expected = retrievable_bridge
        found = cssl_camps

        intersection = expected & found
        recall = len(intersection) / len(expected) if expected else 1.0
        precision = len(intersection) / len(found) if found else 1.0
        union = expected | found
        jaccard = len(intersection) / len(union) if union else 1.0

        rows.append({
            "slug": slug,
            "expanded_slugs": sorted(expanded),
            "bridge_total": len(bridge_camps),
            "bridge_retrievable": len(retrievable_bridge),
            "bridge_unretrievable": len(unretrievable_bridge),
            "unretrievable_ids": sorted(unretrievable_bridge) if len(unretrievable_bridge) <= 20 else f"{len(unretrievable_bridge)} camps",
            "tagged_via_program_tags": len(tagged_camps),
            "cssl_effective": len(cssl_camps),
            "recall": recall,
            "precision": precision,
            "jaccard": jaccard,
            "missing_from_cssl": sorted(expected - found)[:20],
            "extra_in_cssl": sorted(found - expected)[:20],
            "extra_count": len(found - expected),
        })

    cursor.close()
    conn.close()
    return rows


def print_layer_3(rows: list[dict]) -> None:
    print("\n" + "=" * 78)
    print("  LAYER 3 — Retrieval Parity (against bridge artifact)")
    print("  Expected = retrievable bridge camps (active camp + active program)")
    print("  Found = program_tags match UNION override parallel lookup")
    print("=" * 78)

    errors = [r for r in rows if "error" in r]
    valid = [r for r in rows if "error" not in r]

    if errors:
        print(f"\n  ERRORS ({len(errors)} slugs with no resolvable tag_ids):")
        for r in errors:
            print(f"    {r['slug']:40s}  expanded: {r['expanded_slugs']}")

    if not valid:
        print("\n  No valid results to report.")
        return

    # Summary
    perfect = [r for r in valid if r["recall"] >= 0.999 and r["precision"] >= 0.999]
    high = [r for r in valid if 0.9 <= r["recall"] < 0.999 or 0.9 <= r["precision"] < 0.999]
    low_recall = [r for r in valid if r["recall"] < 0.9]

    print(f"\n  Slugs measured:      {len(valid)}")
    print(f"  Perfect (R=P=1.0):   {len(perfect)}")
    print(f"  High (R or P ≥ 0.9): {len(high)}")
    print(f"  Low recall (< 0.9):  {len(low_recall)}")

    # Detailed table — sort by recall ascending (worst first)
    print(f"\n  {'Slug':40s} {'Brdg':>5s} {'Rtrv':>5s} {'Tags':>5s} {'CSSL':>5s} {'Recall':>7s} {'Prec':>7s} {'Jacc':>7s}")
    print("  " + "-" * 76)
    for r in sorted(valid, key=lambda x: (x["recall"], x["jaccard"])):
        flag = " !!" if r["recall"] < 0.9 else (" !" if r["recall"] < 1.0 else "")
        print(
            f"  {r['slug']:40s} {r['bridge_total']:5d} {r['bridge_retrievable']:5d} "
            f"{r['tagged_via_program_tags']:5d} {r['cssl_effective']:5d} "
            f"{r['recall']:7.1%} {r['precision']:7.1%} {r['jaccard']:7.1%}{flag}"
        )

    # Detail for low-recall slugs
    if low_recall:
        print(f"\n  LOW RECALL DETAIL (recall < 90%):")
        for r in sorted(low_recall, key=lambda x: x["recall"]):
            print(f"\n    {r['slug']} — recall {r['recall']:.1%}, precision {r['precision']:.1%}")
            print(f"      Bridge: {r['bridge_total']} total, {r['bridge_retrievable']} retrievable, {r['bridge_unretrievable']} unretrievable")
            if r["missing_from_cssl"]:
                print(f"      Missing camp_ids: {r['missing_from_cssl']}")
            if r["extra_in_cssl"]:
                extra_display = r["extra_in_cssl"]
                suffix = f" (+{r['extra_count'] - len(extra_display)} more)" if r["extra_count"] > len(extra_display) else ""
                print(f"      Extra camp_ids:   {extra_display}{suffix}")
            if r["unretrievable_ids"]:
                print(f"      Unretrievable:    {r['unretrievable_ids']}")

    # Show slugs where extras are large (even if recall is fine)
    high_extras = [r for r in valid if r["extra_count"] > 10 and r["recall"] >= 0.9]
    if high_extras:
        print(f"\n  HIGH EXTRAS (recall ≥ 90% but >10 extra camps — search may feel noisy):")
        for r in sorted(high_extras, key=lambda x: -x["extra_count"]):
            print(f"    {r['slug']:40s}  extras: {r['extra_count']:4d}  precision: {r['precision']:.1%}")


def print_slug_deep_dive(rows: list[dict]) -> None:
    """Extended output for single-slug analysis."""
    if not rows:
        print("  No data.")
        return
    r = rows[0]
    if "error" in r:
        print(f"\n  ERROR: {r['slug']} — {r['error']}")
        print(f"  Expanded slugs: {r['expanded_slugs']}")
        return

    print(f"\n  DEEP DIVE: {r['slug']}")
    print(f"  Expanded to: {r['expanded_slugs']}")
    print(f"\n  Bridge artifact:")
    print(f"    Total camps in bridge:      {r['bridge_total']}")
    print(f"    Retrievable (active+progs): {r['bridge_retrievable']}")
    print(f"    Unretrievable:              {r['bridge_unretrievable']}")
    if r["unretrievable_ids"]:
        print(f"    Unretrievable IDs:          {r['unretrievable_ids']}")
    print(f"\n  Retrieval:")
    print(f"    Via program_tags:           {r['tagged_via_program_tags']}")
    print(f"    CSSL effective (tags+over):  {r['cssl_effective']}")
    print(f"\n  Parity (against retrievable bridge):")
    print(f"    Recall:    {r['recall']:.1%}")
    print(f"    Precision: {r['precision']:.1%}")
    print(f"    Jaccard:   {r['jaccard']:.1%}")
    if r["missing_from_cssl"]:
        print(f"\n  Missing from CSSL: {r['missing_from_cssl']}")
    if r["extra_in_cssl"]:
        print(f"\n  Extra in CSSL ({r['extra_count']} total, showing first 20): {r['extra_in_cssl']}")


# ── CSV export ──────────────────────────────────────────────────────────────

def export_csv(path: str, layer2: list[dict], layer3: list[dict] | None) -> None:
    """Export combined Layer 2 + 3 data to CSV."""
    # Index layer 3 by slug
    l3_by_slug = {}
    if layer3:
        for r in layer3:
            if "error" not in r:
                l3_by_slug[r["slug"]] = r

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        header = [
            "slug", "bridge_camp_count", "canonical_pages", "override_pages",
        ]
        if layer3:
            header += [
                "bridge_retrievable", "bridge_unretrievable",
                "tagged_via_program_tags", "cssl_effective",
                "recall", "precision", "jaccard",
            ]
        writer.writerow(header)

        for r2 in layer2:
            row = [
                r2["slug"],
                r2["bridge_camp_count"],
                "; ".join(r2["canonical_pages"]),
                "; ".join(r2["override_pages"]),
            ]
            if layer3:
                r3 = l3_by_slug.get(r2["slug"])
                if r3:
                    row += [
                        r3["bridge_retrievable"], r3["bridge_unretrievable"],
                        r3["tagged_via_program_tags"], r3["cssl_effective"],
                        f"{r3['recall']:.3f}", f"{r3['precision']:.3f}", f"{r3['jaccard']:.3f}",
                    ]
                else:
                    row += ["", "", "", "", "", "", ""]
            writer.writerow(row)

    print(f"\n  CSV exported → {path}")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Camp Search Parity Suite")
    parser.add_argument("--with-db", action="store_true", help="Run Layer 3 (requires DB)")
    parser.add_argument("--with-fuzzy", action="store_true", help="Run Layer 1a (fuzzy, no API)")
    parser.add_argument("--with-parser", action="store_true", help="Run Layer 1a + 1b (API cost)")
    parser.add_argument("--slug", type=str, help="Deep-dive a single slug (requires DB)")
    parser.add_argument("--csv", type=str, help="Export results to CSV file")
    args = parser.parse_args()

    print("\n  Camp Search Parity Suite")
    print("  " + "-" * 40)

    bridge = load_bridge()
    slug_registry = build_slug_registry()

    # Layer 0
    l0_issues = layer_0(slug_registry, bridge)
    print_layer_0(l0_issues)

    # Layer 1a — Fuzzy interpretation
    l1a_results = None
    if args.with_fuzzy or args.with_parser:
        cases = build_layer1_test_cases(slug_registry, bridge)
        l1a_results = layer_1a(cases)
        print_layer_1a(l1a_results)

    # Layer 1b — Parser interpretation (only fuzzy misses + sample)
    if args.with_parser and l1a_results is not None:
        try:
            l1b_results = layer_1b(cases, l1a_results)
            print_layer_1b(l1b_results)
        except Exception as e:
            print(f"\n  Layer 1b FAILED: {e}")
            print("  (Is ANTHROPIC_API_KEY set?)")

    # Layer 2
    l2_rows = layer_2(slug_registry, bridge)
    print_layer_2(l2_rows)

    # Layer 3
    l3_rows = None
    if args.with_db or args.slug:
        try:
            l3_rows = layer_3(slug_registry, bridge, filter_slug=args.slug)
            if args.slug:
                print_slug_deep_dive(l3_rows)
            else:
                print_layer_3(l3_rows)
        except Exception as e:
            print(f"\n  Layer 3 FAILED: {e}")
            print("  (Is the DB accessible? Check DB_HOST / DB_PASSWORD env or secrets.)")

    # CSV
    if args.csv:
        export_csv(args.csv, l2_rows, l3_rows)

    print()


if __name__ == "__main__":
    main()
