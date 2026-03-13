"""
tests/test_intent_parser.py
QA test suite for the Intent Parser.
Runs all 40 QA queries against parse_intent() and validates expected fields.

Usage:
    python -m pytest tests/test_intent_parser.py -v -s
    # or run directly:
    python tests/test_intent_parser.py
"""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from config import get_secret

from core.intent_parser import parse_intent
from core.fuzzy_preprocessor import preprocess
from tests.qa_queries import QA_QUERIES


def test_query(q: dict) -> tuple[bool, str]:
    """
    Run a single QA query and return (passed, reason).
    Returns (True, "") on full pass or (False, reason) on failure.
    Mirrors the real app pipeline: fuzzy_preprocessor → parse_intent.
    """
    fuzzy_hints = preprocess(q["query"])
    result = parse_intent(
        q["query"],
        session_context=q.get("session_context"),
        fuzzy_hints=fuzzy_hints,
    )
    failures = []

    # expect_tags — exact match (at least one must be in result.tags)
    if "expect_tags" in q:
        expected = q["expect_tags"]
        if not any(t in result.tags for t in expected):
            failures.append(f"expect_tags {expected} not in tags {result.tags}")

    # expect_tags_include — all listed must be in result.tags
    if "expect_tags_include" in q:
        for t in q["expect_tags_include"]:
            if t not in result.tags:
                failures.append(f"expect_tags_include '{t}' not in tags {result.tags}")

    # expect_tags_not — none of these should appear
    if "expect_tags_not" in q:
        for t in q["expect_tags_not"]:
            if t in result.tags:
                failures.append(f"expect_tags_not '{t}' found in tags {result.tags}")

    # expect_exclude_tags_include — all must be in result.exclude_tags
    if "expect_exclude_tags_include" in q:
        for t in q["expect_exclude_tags_include"]:
            if t not in result.exclude_tags:
                failures.append(
                    f"expect_exclude_tags_include '{t}' not in exclude_tags {result.exclude_tags}"
                )

    # expect_city
    if "expect_city" in q:
        if result.city != q["expect_city"]:
            failures.append(f"expect_city {q['expect_city']!r} got {result.city!r}")

    # expect_cities_include
    if "expect_cities_include" in q:
        for city in q["expect_cities_include"]:
            if city not in result.cities:
                failures.append(
                    f"expect_cities_include '{city}' not in cities {result.cities}"
                )

    # expect_province
    if "expect_province" in q:
        if result.province != q["expect_province"]:
            failures.append(
                f"expect_province {q['expect_province']!r} got {result.province!r}"
            )

    # expect_age_from — allow ±1 tolerance
    if "expect_age_from" in q:
        expected_af = q["expect_age_from"]
        if result.age_from is None or abs(result.age_from - expected_af) > 1:
            failures.append(
                f"expect_age_from {expected_af} got {result.age_from}"
            )

    # expect_age_to
    if "expect_age_to" in q:
        expected_at = q["expect_age_to"]
        if result.age_to is None or abs(result.age_to - expected_at) > 1:
            failures.append(f"expect_age_to {expected_at} got {result.age_to}")

    # expect_type
    if "expect_type" in q:
        if result.type != q["expect_type"]:
            failures.append(f"expect_type {q['expect_type']!r} got {result.type!r}")

    # expect_gender
    if "expect_gender" in q:
        if result.gender != q["expect_gender"]:
            failures.append(
                f"expect_gender {q['expect_gender']!r} got {result.gender!r}"
            )

    # expect_traits — exact match (at least one)
    if "expect_traits" in q:
        expected = q["expect_traits"]
        if not any(t in result.traits for t in expected):
            failures.append(
                f"expect_traits {expected} not in traits {result.traits}"
            )

    # expect_traits_include — all must be present
    if "expect_traits_include" in q:
        for t in q["expect_traits_include"]:
            if t not in result.traits:
                failures.append(
                    f"expect_traits_include '{t}' not in traits {result.traits}"
                )

    # expect_language
    if "expect_language" in q:
        if result.detected_language != q["expect_language"]:
            failures.append(
                f"expect_language {q['expect_language']!r} got {result.detected_language!r}"
            )

    # expect_voice
    if "expect_voice" in q:
        if result.voice != q["expect_voice"]:
            failures.append(f"expect_voice {q['expect_voice']!r} got {result.voice!r}")

    # expect_ics_max
    if "expect_ics_max" in q:
        if result.ics > q["expect_ics_max"]:
            failures.append(
                f"expect_ics_max {q['expect_ics_max']} but ICS was {result.ics}"
            )

    # expect_recognized
    if "expect_recognized" in q:
        if result.recognized != q["expect_recognized"]:
            failures.append(
                f"expect_recognized {q['expect_recognized']} got {result.recognized}"
            )

    # expect_is_special_needs
    if "expect_is_special_needs" in q:
        if result.is_special_needs != q["expect_is_special_needs"]:
            failures.append(
                f"expect_is_special_needs {q['expect_is_special_needs']} "
                f"got {result.is_special_needs}"
            )

    # expect_is_virtual
    if "expect_is_virtual" in q:
        if result.is_virtual != q["expect_is_virtual"]:
            failures.append(
                f"expect_is_virtual {q['expect_is_virtual']} got {result.is_virtual}"
            )

    # expect_language_immersion
    if "expect_language_immersion" in q:
        if result.language_immersion != q["expect_language_immersion"]:
            failures.append(
                f"expect_language_immersion {q['expect_language_immersion']!r} "
                f"got {result.language_immersion!r}"
            )

    # expect_accepted_suggestion
    if "expect_accepted_suggestion" in q:
        if result.accepted_suggestion != q["expect_accepted_suggestion"]:
            failures.append(
                f"expect_accepted_suggestion {q['expect_accepted_suggestion']} "
                f"got {result.accepted_suggestion}"
            )

    passed = len(failures) == 0
    reason = "; ".join(failures)
    return passed, reason


# ── pytest parametrize ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "q",
    QA_QUERIES,
    ids=[f"Q{i+1}: {q['query'][:50]}" for i, q in enumerate(QA_QUERIES)],
)
def test_qa_query(q):
    passed, reason = test_query(q)
    note = q.get("note", "")
    fuzzy_hints = preprocess(q["query"])
    result = parse_intent(q["query"], session_context=q.get("session_context"), fuzzy_hints=fuzzy_hints)
    print(f"\n  ICS={result.ics:.2f}  tags={result.tags}  city={result.city}")
    if note:
        print(f"  note: {note}")
    assert passed, reason


# ── standalone runner ────────────────────────────────────────────────────────

if __name__ == "__main__":
    passed_count = 0
    failed_count = 0

    for i, q in enumerate(QA_QUERIES, 1):
        try:
            ok, reason = test_query(q)
            fuzzy_hints = preprocess(q["query"])
            result = parse_intent(q["query"], session_context=q.get("session_context"), fuzzy_hints=fuzzy_hints)
            status = "PASS" if ok else "FAIL"
            note = q.get("note", "")
            print(f"[{status}] Q{i:02d}: {q['query'][:60]}")
            print(f"       ICS={result.ics:.2f}  tags={result.tags}")
            if not ok:
                print(f"       REASON: {reason}")
            if note:
                print(f"       NOTE: {note}")
            if ok:
                passed_count += 1
            else:
                failed_count += 1
        except Exception as e:
            print(f"[ERROR] Q{i:02d}: {q['query'][:60]}")
            print(f"        {e}")
            failed_count += 1

    total = passed_count + failed_count
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed_count}/{total} passed ({failed_count} failed)")
    print(f"{'='*60}")


# ── Note: Pure unit tests for _coerce_parsed and parse_intent error handling
# are in tests/test_intent_parser_unit.py (mocks anthropic, no network needed)
