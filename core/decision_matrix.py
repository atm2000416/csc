"""
core/decision_matrix.py
2x2 Decision Matrix — routes based on ICS x RCS scores.
Returns routing decision and action parameters.
"""
import os
from dataclasses import dataclass
from enum import Enum


class Route(Enum):
    SHOW_RESULTS   = "show_results"
    BROADEN_SEARCH = "broaden_search"
    SHOW_CLARIFY   = "show_and_clarify"
    CLARIFY_LOOP   = "clarification_loop"


@dataclass
class Decision:
    route: Route
    show_results: bool
    invoke_casl: bool
    ask_clarification: bool
    clarification_dimensions: list[str]


def _get_thresholds() -> tuple[float, float]:
    ics_t = float(os.getenv("ICS_HIGH_THRESHOLD", 0.70))
    rcs_t = float(os.getenv("RCS_HIGH_THRESHOLD", 0.70))
    return ics_t, rcs_t


def decide(
    ics: float,
    rcs: float,
    needs_clarification: list[str] | None = None,
) -> Decision:
    """
    Route the search based on ICS and RCS scores.

    Quadrants:
      ICS >= threshold + RCS >= threshold → SHOW_RESULTS
      ICS >= threshold + RCS < threshold  → BROADEN_SEARCH (invoke CASL)
      ICS < threshold  + RCS >= threshold → SHOW_AND_CLARIFY
      ICS < threshold  + RCS < threshold  → CLARIFICATION_LOOP
    """
    ics_threshold, rcs_threshold = _get_thresholds()
    high_ics = ics >= ics_threshold
    high_rcs = rcs >= rcs_threshold
    clarify = needs_clarification or []

    if high_ics and high_rcs:
        return Decision(
            route=Route.SHOW_RESULTS,
            show_results=True,
            invoke_casl=False,
            ask_clarification=False,
            clarification_dimensions=[],
        )
    elif high_ics and not high_rcs:
        return Decision(
            route=Route.BROADEN_SEARCH,
            show_results=False,
            invoke_casl=True,
            ask_clarification=False,
            clarification_dimensions=[],
        )
    elif not high_ics and high_rcs:
        return Decision(
            route=Route.SHOW_CLARIFY,
            show_results=True,
            invoke_casl=False,
            ask_clarification=True,
            clarification_dimensions=clarify[:1],
        )
    else:
        return Decision(
            route=Route.CLARIFY_LOOP,
            show_results=False,
            invoke_casl=False,
            ask_clarification=True,
            clarification_dimensions=clarify[:2],
        )
