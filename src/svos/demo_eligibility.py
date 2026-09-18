"""Demo eligibility (P15).

FORWARD_PASS does NOT execute Demo orders. It may only satisfy ONE prerequisite for
DEMO_ELIGIBLE. `assess_demo_eligibility` is a pure, read-only projection: it reports
whether the forward evidence and the existing governance gates are satisfied, and it
NEVER touches execution -- demo execution remains separately owner-authorized and live
remains unauthorized.

Safety invariants: DEMO_ORDER_SUBMITTED=false, LIVE_ORDER_SUBMITTED=false,
LIVE_AUTHORIZED=false are held by construction (no import of execution/mt5).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Tuple

from .forward import ForwardMetrics


@dataclass(frozen=True)
class DemoEligibilityAssessment:
    strategy_id: str
    candidate_fingerprint: str
    forward_pass: bool
    minimum_occurrences_met: bool
    governance_gates_satisfied: bool
    eligible: bool
    blockers: Tuple[str, ...]
    demo_executed: bool = False  # always False here; demo execution is owner-authorized


def assess_demo_eligibility(
    *,
    strategy_id: str,
    candidate_fingerprint: str,
    forward_metrics: ForwardMetrics,
    minimum_occurrence_target: int,
    forward_acceptance_criteria: Mapping[str, object],
    governance_gates: Mapping[str, bool],
) -> DemoEligibilityAssessment:
    blockers: list[str] = []

    forward_pass = _forward_pass(forward_metrics, forward_acceptance_criteria)
    if not forward_pass:
        blockers.append("FORWARD_ACCEPTANCE_NOT_MET")

    min_met = forward_metrics.resolved_positions >= minimum_occurrence_target
    if not min_met:
        blockers.append("MINIMUM_OCCURRENCE_TARGET_NOT_MET")

    gates_ok = all(governance_gates.values())
    if not gates_ok:
        missing = [g for g, ok in governance_gates.items() if not ok]
        blockers.append(f"GOVERNANCE_GATES_UNSATISFIED={','.join(sorted(missing))}")

    return DemoEligibilityAssessment(
        strategy_id=strategy_id,
        candidate_fingerprint=candidate_fingerprint,
        forward_pass=forward_pass,
        minimum_occurrences_met=min_met,
        governance_gates_satisfied=gates_ok,
        eligible=forward_pass and min_met and gates_ok,
        blockers=tuple(blockers),
        demo_executed=False,
    )


def _forward_pass(metrics: ForwardMetrics, criteria: Mapping[str, object]) -> bool:
    """Applies forward acceptance criteria (min net expectancy / min profit factor).
    No threshold is invented: criteria values come from the caller (frozen campaign)."""
    min_expectancy = criteria.get("minimum_net_expectancy_R")
    if min_expectancy is not None and metrics.expectancy_R < float(min_expectancy):
        return False
    min_pf = criteria.get("minimum_profit_factor")
    if min_pf is not None:
        pf = metrics.profit_factor
        if isinstance(pf, str) or float(pf) < float(min_pf):
            return False
    max_dd = criteria.get("maximum_drawdown_R")
    if max_dd is not None and metrics.max_drawdown_R > float(max_dd):
        return False
    return True
