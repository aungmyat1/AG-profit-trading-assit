from __future__ import annotations

from performance import cost_model

from external_candidate.friction import (
    FRICTION_INCOMPLETE,
    FRICTION_MATCH,
    FRICTION_MISMATCH,
    FRICTION_TRANSLATABLE,
    STATUS_PARTIAL_SIGNED_SCENARIO_SET,
    classify_friction_compatibility,
    friction_stress_status,
    signed_friction_scenarios,
)
from external_candidate.models import FrictionAssumptions


def test_signed_scenarios_reuses_cost_model_verbatim():
    scenarios = signed_friction_scenarios()
    assert scenarios[cost_model.SCENARIO_CONTRACT_CEILING] is not None
    assert scenarios["BASE"] is None
    assert scenarios["SEVERE"] is None


def test_friction_stress_status_is_partial_given_current_repo_state():
    assert friction_stress_status() == STATUS_PARTIAL_SIGNED_SCENARIO_SET


def test_unstated_candidate_friction_is_incomplete():
    friction = FrictionAssumptions()
    assert classify_friction_compatibility(friction) == FRICTION_INCOMPLETE


def test_matching_pips_friction_is_match():
    friction = FrictionAssumptions(spread=2.0, spread_unit="pips", commission=0.0, slippage=1.0, slippage_unit="pips")
    assert classify_friction_compatibility(friction) == FRICTION_MATCH


def test_grossly_tighter_friction_is_mismatch():
    friction = FrictionAssumptions(spread=0.1, spread_unit="pips", commission=0.0, slippage=0.0, slippage_unit="pips")
    assert classify_friction_compatibility(friction) == FRICTION_MISMATCH


def test_non_pips_unit_is_translatable_not_assumed_equal():
    friction = FrictionAssumptions(spread=0.0002, spread_unit="price", commission=0.0, slippage=1.0, slippage_unit="pips")
    assert classify_friction_compatibility(friction) == FRICTION_TRANSLATABLE
