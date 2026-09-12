"""Friction-stress framework capability (mission section 22). Extends, rather than
duplicates, `performance.cost_model` -- the only signed scenario in this repository
today is CONTRACT_CEILING; BASE/SEVERE remain explicitly unsigned. This module
never invents values for them.
"""
from __future__ import annotations

from typing import Dict, Optional

from performance import cost_model

from .models import FrictionAssumptions

FRICTION_MATCH = "FRICTION_MATCH"
FRICTION_TRANSLATABLE = "FRICTION_TRANSLATABLE"
FRICTION_MISMATCH = "FRICTION_MISMATCH"
FRICTION_INCOMPLETE = "FRICTION_INCOMPLETE"

STATUS_NO_SIGNED_SCENARIOS = "NO_SIGNED_SCENARIOS"
STATUS_PARTIAL_SIGNED_SCENARIO_SET = "PARTIAL_SIGNED_SCENARIO_SET"
STATUS_FULL_SIGNED_SCENARIO_SET = "FULL_SIGNED_SCENARIO_SET"

_RELATIVE_TOLERANCE = 0.10  # 10% -- a translatable-but-not-identical scenario


def signed_friction_scenarios() -> Dict[str, Optional[Dict[str, float]]]:
    """Reuses `performance.cost_model.FRICTION_SCENARIOS` verbatim -- no second
    friction-scenario registry is introduced."""
    return dict(cost_model.FRICTION_SCENARIOS)


def friction_stress_status(scenarios: Optional[Dict[str, Optional[Dict[str, float]]]] = None) -> str:
    scenarios = scenarios if scenarios is not None else signed_friction_scenarios()
    signed = [k for k, v in scenarios.items() if v is not None]
    if not signed:
        return STATUS_NO_SIGNED_SCENARIOS
    if len(signed) < len(scenarios):
        return STATUS_PARTIAL_SIGNED_SCENARIO_SET
    return STATUS_FULL_SIGNED_SCENARIO_SET


def classify_friction_compatibility(
    candidate_friction: FrictionAssumptions,
    signed_scenario: Optional[Dict[str, float]] = None,
) -> str:
    """Classifies the candidate's OWN stated friction against the one signed
    (CONTRACT_CEILING) scenario, per mission section 9. Never silently maps an
    unrelated assumption onto CONTRACT_CEILING -- an unstated candidate assumption
    is FRICTION_INCOMPLETE, not assumed equal or assumed zero."""
    if signed_scenario is None:
        signed_scenario = signed_friction_scenarios()[cost_model.SCENARIO_CONTRACT_CEILING]

    if not candidate_friction.is_stated():
        return FRICTION_INCOMPLETE
    if signed_scenario is None:
        return FRICTION_INCOMPLETE

    # Only directly comparable when the candidate expressed spread/slippage in the
    # same unit family (pips) the signed scenario uses -- otherwise it is
    # translatable at best (a real unit conversion, not performed here) rather than
    # silently treated as a match.
    if candidate_friction.spread_unit not in (None, "pips") or candidate_friction.slippage_unit not in (None, "pips"):
        return FRICTION_TRANSLATABLE

    spread_diff = abs(candidate_friction.spread - signed_scenario["spread_pips"])
    slippage_diff = abs(candidate_friction.slippage - signed_scenario["slippage_pips"])
    spread_tol = signed_scenario["spread_pips"] * _RELATIVE_TOLERANCE
    slippage_tol = max(signed_scenario["slippage_pips"] * _RELATIVE_TOLERANCE, 1e-9)

    if spread_diff <= spread_tol and slippage_diff <= slippage_tol:
        return FRICTION_MATCH
    return FRICTION_MISMATCH
