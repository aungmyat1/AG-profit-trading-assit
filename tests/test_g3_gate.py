"""Tests for validation_framework.g3_gate -- the G3 economic gate wrapper around the
existing economic_gate.py evaluator (WP-SV3 / WORK PACKAGE E). Synthetic fixtures only,
never a real strategy's dataset -- same discipline as test_economic_gate_evaluator.py."""
from __future__ import annotations

from performance.models import TradeMetrics
from validation_framework.g3_gate import g3_blocks_downstream, run_g3_economic_gate, to_outcome
from validation_framework.models import GateStatus

SIGNED_CONTRACT = {
    "identity": {"contract_id": "TEST_G3_CONTRACT", "version": "1", "status": "SIGNED",
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


def test_g3_pass_does_not_block_downstream():
    result = run_g3_economic_gate("ST_X", "1.0.0", "HYP_A", _metrics(), True, SIGNED_CONTRACT)
    assert result.gate_name == "G3"
    assert result.status == GateStatus.PASS
    assert g3_blocks_downstream(result) is False


def test_g3_reject_blocks_downstream():
    result = run_g3_economic_gate(
        "ST_X", "1.0.0", "HYP_A", _metrics(net_expectancy_R=-0.4), True, SIGNED_CONTRACT
    )
    assert result.status == GateStatus.FAIL
    assert g3_blocks_downstream(result) is True


def test_g3_missing_contract_blocks_never_fails_outright():
    result = run_g3_economic_gate("ST_X", "1.0.0", "HYP_A", _metrics(), True, None)
    assert result.status == GateStatus.BLOCKED
    assert g3_blocks_downstream(result) is True


def test_g3_insufficient_evidence_blocks_not_fails():
    result = run_g3_economic_gate("ST_X", "1.0.0", "HYP_A", None, False, SIGNED_CONTRACT)
    assert result.status == GateStatus.BLOCKED
    assert g3_blocks_downstream(result) is True


def test_to_outcome_mirrors_gate_result():
    result = run_g3_economic_gate("ST_X", "1.0.0", "HYP_A", _metrics(), True, SIGNED_CONTRACT)
    outcome = to_outcome("ST_X", "1.0.0", "HYP_A", result)
    assert outcome.verdict == "EDGE_VALIDATED"
    assert outcome.blocks_downstream is False
    assert outcome.contract_id == "TEST_G3_CONTRACT"
