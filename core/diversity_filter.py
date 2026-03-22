"""
core/diversity_filter.py
Diversity Filter — prevents result clustering by same camp.
"""


def _desc_length(r: dict) -> int:
    """Return length of best available description for ranking."""
    return len(r.get("mini_description") or r.get("description") or "")


def apply(results: list[dict], max_per_camp: int = 2) -> list[dict]:
    """
    Ensure no more than max_per_camp results from the same camp
    appear in the top results. Preserves tier ordering.

    When max_per_camp is 1 (reranker mode), picks the program with
    the best description so the reranker has content to score.

    Overflow results are appended after the diverse set so users
    can scroll past the top 10 to see more from the same camp.
    """
    if max_per_camp == 1:
        return _pick_best_per_camp(results)

    seen: dict[int, int] = {}
    diverse: list[dict] = []
    overflow: list[dict] = []

    for r in results:
        camp_id = r["camp_id"]
        count = seen.get(camp_id, 0)
        if count < max_per_camp:
            diverse.append(r)
            seen[camp_id] = count + 1
        else:
            overflow.append(r)

    return diverse + overflow


def _pick_best_per_camp(results: list[dict]) -> list[dict]:
    """
    Select 1 representative program per camp, preferring programs
    that have a description (so the reranker has content to score).
    Preserves the original ordering of camps (first occurrence = rank).
    """
    # Group by camp_id, preserving encounter order
    camps: dict[int, list[dict]] = {}
    camp_order: list[int] = []
    for r in results:
        cid = r["camp_id"]
        if cid not in camps:
            camps[cid] = []
            camp_order.append(cid)
        camps[cid].append(r)

    diverse: list[dict] = []

    for cid in camp_order:
        programs = camps[cid]
        # Pick the program with the longest description
        best = max(programs, key=_desc_length)
        diverse.append(best)

    return diverse
