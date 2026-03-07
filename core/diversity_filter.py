"""
core/diversity_filter.py
Diversity Filter — prevents result clustering by same camp.
"""


def apply(results: list[dict], max_per_camp: int = 2) -> list[dict]:
    """
    Ensure no more than max_per_camp results from the same camp
    appear in the top results. Preserves tier ordering.

    Overflow results are appended after the diverse set so users
    can scroll past the top 10 to see more from the same camp.
    """
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
