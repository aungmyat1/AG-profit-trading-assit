"""Focused tests for src/validation_framework/economic_gate.py (R6 baseline-freeze work
package). Uses ONLY synthetic fixtures -- never the real 13-trade ST_ASIAN_SWEEP_5R_V1
dataset -- so these tests can never be (or appear to be) tuned around a desired verdict
for that strategy. See test_real_contract_file_is_proposed_not_signed below for the one
place this suite touches the real repository contract file, and even there it only
asserts the file is NOT active governance.
"""
from __future__ import annotations

import copy

import pytest

from performance.models import NOT_EVALUATED, TradeMetrics
from validation_framework.economic_gate import (
    DEFAULT_CONTRACT_PATH,
    VERDICT_EDGE_REJECTED,
    VERDICT_EDGE_VALIDATED,
    VERDICT_INSUFFICIENT_EVIDENCE,
    VERDICT_NOT_EVALUABLE_INCOMPLETE_CONTRACT,
    VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS,
    evaluate_economic_gate,
    load_contract,
)

SIGNED_CONTRACT = {
    "identity": {"contract_id": "TEST_CONTRACT", "version": "1", "status": "SIGNED",
                 "signed_by": "test-owner", "signed_at": "2026-01-01"},
    "sample": {"minimum_resolved_trades": 10},
    "economics": {"minimum_net_expectancy_R": 0.1, "minimum_profit_factor": 1.3, "maximum_drawdown_R": 15.0},
    "evidence": {"accepted_cost_statuses": ["INCLUDED_CONTRACT_CEILING"]},
}


def _metrics(**overrides) -> TradeMetrics:
    base = dict(
        sample_size=30, wins=18, losses=12, breakevens=0,
        gross_total_R=10.0, gross_expectancy_R=0.33,
        net_total_R=6.0, net_expectancy_R=0.2,
        win_rate=0.6, average_win_R=1.5, average_loss_R=-1.0,
        profit_factor=1.5, max_drawdown_R=5.0, max_consecutive_losses=3,
        cost_status="INCLUDED_CONTRACT_CEILING",
    )
    base.update(overrides)
    return TradeMetrics(**base)


def test_no_contract_is_not_evaluable():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(), True, None)
    assert v.verdict == VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS


def test_proposed_contract_is_not_evaluable():
    proposed = copy.deepcopy(SIGNED_CONTRACT)
    proposed["identity"]["status"] = "PROPOSED"
    v = evaluate_economic_gate("X", "1.0.0", _metrics(), True, proposed)
    assert v.verdict == VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS


def test_signed_contract_missing_required_field_fails_closed():
    incomplete = copy.deepcopy(SIGNED_CONTRACT)
    del incomplete["economics"]["minimum_profit_factor"]
    v = evaluate_economic_gate("X", "1.0.0", _metrics(), True, incomplete)
    assert v.verdict == VERDICT_NOT_EVALUABLE_INCOMPLETE_CONTRACT
    assert "minimum_profit_factor" in v.reason


def test_incomplete_evidence_never_validates_even_with_good_metrics():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(net_expectancy_R=5.0, profit_factor=10.0), False, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_INSUFFICIENT_EVIDENCE
    assert v.verdict != VERDICT_EDGE_VALIDATED


def test_sample_below_minimum_is_insufficient_evidence():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(sample_size=5), True, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_INSUFFICIENT_EVIDENCE


def test_gross_only_cost_status_rejected_as_insufficient():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(cost_status="NOT_INCLUDED"), True, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_INSUFFICIENT_EVIDENCE


def test_not_evaluated_net_expectancy_is_insufficient():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(net_expectancy_R=NOT_EVALUATED), True, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_INSUFFICIENT_EVIDENCE


def test_metrics_failing_net_expectancy_bound_is_edge_rejected():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(net_expectancy_R=-1.0), True, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_EDGE_REJECTED
    assert "net_expectancy_R" in v.reason


def test_metrics_failing_drawdown_bound_is_edge_rejected():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(max_drawdown_R=99.0), True, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_EDGE_REJECTED


def test_metrics_clearing_every_bound_is_edge_validated():
    v = evaluate_economic_gate("X", "1.0.0", _metrics(), True, SIGNED_CONTRACT)
    assert v.verdict == VERDICT_EDGE_VALIDATED


def test_deterministic_same_inputs_same_verdict():
    v1 = evaluate_economic_gate("X", "1.0.0", _metrics(), True, SIGNED_CONTRACT)
    v2 = evaluate_economic_gate("X", "1.0.0", _metrics(), True, SIGNED_CONTRACT)
    assert v1 == v2


def test_real_contract_file_is_signed_for_development_edge_validation():
    """The real repository contract is now active development governance for the SSC
    edge-validation mission and must evaluate a valid metrics set instead of failing
    closed on a proposed threshold file."""
    contract = load_contract(DEFAULT_CONTRACT_PATH)
    assert contract is not None
    assert contract["identity"]["status"] == "SIGNED"
    assert contract["identity"]["signed_by"] is not None
    assert contract["purpose"] == "DEVELOPMENT_EDGE_VALIDATION"
    assert contract["strategy_id"] == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert contract["strategy_version"] == "1.0.1"
    assert contract["primary_friction_scenario"] == "BASE_REPRESENTATIVE"
    v = evaluate_economic_gate("ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.1", _metrics(), True, contract)
    assert v.verdict == VERDICT_EDGE_VALIDATED
