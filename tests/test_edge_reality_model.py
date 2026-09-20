from __future__ import annotations

import pytest

from svos.edge_reality_model import (
    EDGE_REALITY_MODEL_HASH,
    EDGE_REALITY_MODEL_VERSION,
    EDGE_REALITY_MODEL,
    EdgeRealityModel,
    EdgeRealityModelError,
    compute_edge_reality_model_hash,
    validate_edge_reality_model,
    compute_net_r,
)


def test_edge_reality_model_is_frozen_and_hashes_stably():
    digest = validate_edge_reality_model()
    assert EDGE_REALITY_MODEL_VERSION == "EDGE_REALITY_MODEL_V1"
    assert EDGE_REALITY_MODEL["status"] == "FROZEN"
    assert EDGE_REALITY_MODEL_HASH == digest
    assert compute_edge_reality_model_hash() == digest


def test_edge_reality_model_is_separate_from_broker_execution_parity():
    model = EdgeRealityModel()
    assert model.not_broker_execution_parity is True
    assert model.not_live_execution_authority is True
    assert model.not_demo_execution_authority is True
    assert model.strategy_scope == "SSC v1.0.1 strategy-edge validation only"
    assert "BROKER_EXECUTION_PARITY" not in model.purpose
    assert model.spread_units["source_value"] == "pips"
    assert model.spread_units["per_side_or_round_trip"] == "round_trip_per_trade"
    assert model.spread_units["conversion_to_R"] == "(spread_price / risk_distance_price)"
    assert model.commission_units["source_classification"] == "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"


def test_known_answer_accounting_matches_net_r_formula():
    gross_r = 2.0
    spread_r = 0.20
    commission_r = 0.10
    slippage_r = 0.15
    net_r = compute_net_r(gross_r=gross_r, spread_r=spread_r, commission_r=commission_r, slippage_r=slippage_r)
    assert net_r == pytest.approx(1.55)


def test_tighter_stop_increases_friction_in_r_for_same_absolute_cost():
    absolute_cost_pips = 1.0
    wider_risk_distance = 40.0
    tighter_risk_distance = 20.0
    wide_cost_r = absolute_cost_pips / wider_risk_distance
    tight_cost_r = absolute_cost_pips / tighter_risk_distance
    assert tight_cost_r > wide_cost_r
    assert compute_net_r(gross_r=1.0, spread_r=wide_cost_r, commission_r=0.0, slippage_r=0.0) == pytest.approx(0.975)
    assert compute_net_r(gross_r=1.0, spread_r=tight_cost_r, commission_r=0.0, slippage_r=0.0) == pytest.approx(0.95)


def test_invalid_model_inputs_fail_closed():
    with pytest.raises(EdgeRealityModelError):
        EdgeRealityModel(spread_status="KNOWN", spread_value_or_model=0.0)
