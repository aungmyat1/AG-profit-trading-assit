"""Tests for svos.forward -- chronological guard, future-data guard, dedupe, restart (P11/P12/P14)."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from svos.forward import (
    DECISION_NO_SETUP,
    DECISION_PROPOSAL,
    ForwardDecision,
    ForwardOrchestrator,
    ForwardValidationCampaign,
    ProposalSpec,
)
from svos.friction_profile import (
    FrictionComponent,
    FrictionComponentState,
    FrictionProfile,
)
from svos.virtual_broker import Side, VirtualAccount, VirtualBroker, VirtualCandle

T0 = datetime(2026, 9, 1, 8, 0)


def _candle(t0_min: int, o: float, h: float, lo: float, c: float) -> VirtualCandle:
    return VirtualCandle(time=T0 + timedelta(minutes=t0_min), open=o, high=h, low=lo, close=c)


def _broker() -> VirtualBroker:
    profile = FrictionProfile(
        spread=FrictionComponent(FrictionComponentState.MODELED, 0.0),
        commission=FrictionComponent(FrictionComponentState.MODELED, 0.0),
        slippage=FrictionComponent(FrictionComponentState.MODELED, 0.0),
    )
    account = VirtualAccount(
        starting_balance_R=100.0, max_open_positions=5,
        risk_per_trade_R=2.0, daily_loss_limit_R=20.0,
    )
    return VirtualBroker(profile, account)


def _campaign(**overrides) -> ForwardValidationCampaign:
    base = dict(
        campaign_id="CAMP-1",
        candidate_fingerprint="f" * 64,
        frozen_at=(T0 - timedelta(days=1)).isoformat(),
        symbols=("EURUSD",),
        sessions=("ASIAN_LONDON",),
        friction_profile_ref="FR1",
        risk_profile={"max_open_positions": 5, "risk_per_trade_R": 2.0, "daily_loss_limit_R": 20.0},
        minimum_occurrence_target=1,
        evaluation_metrics=("net_expectancy_R", "profit_factor"),
        acceptance_criteria={"minimum_net_expectancy_R": 0.0},
    )
    base.update(overrides)
    return ForwardValidationCampaign(**base)


def _proposal_fn(proposals):
    """Returns a decision_fn that emits the given proposals then NO_SETUP."""
    queue = list(proposals)

    def fn(candle: VirtualCandle) -> ForwardDecision:
        if queue:
            return ForwardDecision(DECISION_PROPOSAL, queue.pop(0))
        return ForwardDecision(DECISION_NO_SETUP)

    return fn


def test_no_setup_is_valid_and_counted():
    orch = ForwardOrchestrator(_campaign(), lambda c: ForwardDecision(DECISION_NO_SETUP), _broker())
    orch.on_candle(_candle(0, 1.0, 1.0, 1.0, 1.0))
    orch.on_candle(_candle(15, 1.0, 1.0, 1.0, 1.0))
    metrics = orch.finalize()
    assert metrics.opportunities == 2
    assert metrics.no_setups == 2
    assert metrics.proposals == 0
    assert metrics.fills == 0


def test_chronological_guard_rejects_out_of_order():
    orch = ForwardOrchestrator(_campaign(), lambda c: ForwardDecision(DECISION_NO_SETUP), _broker())
    orch.on_candle(_candle(15, 1.0, 1.0, 1.0, 1.0))
    with pytest.raises(ValueError):
        orch.on_candle(_candle(0, 1.0, 1.0, 1.0, 1.0))


def test_future_candle_before_freeze_rejected():
    campaign = _campaign(frozen_at=(T0 + timedelta(minutes=10)).isoformat())
    orch = ForwardOrchestrator(campaign, lambda c: ForwardDecision(DECISION_NO_SETUP), _broker())
    with pytest.raises(ValueError):
        orch.on_candle(_candle(0, 1.0, 1.0, 1.0, 1.0))


def test_duplicate_cycle_rejected():
    proposal = ProposalSpec(
        proposal_id="p1", symbol="EURUSD", side=Side.LONG, stop_loss=0.9980,
        setup="S1", session="ASIAN_LONDON", direction="LONG",
    )
    orch = ForwardOrchestrator(_campaign(), _proposal_fn([proposal, proposal]), _broker())
    orch.on_candle(_candle(0, 1.0, 1.0, 1.0, 1.0))  # proposal 1 -> pending order
    orch.on_candle(_candle(15, 1.0, 1.0, 1.0, 1.0))  # duplicate -> skipped
    assert orch.finalize().proposals == 1


def test_proposal_flows_through_broker_to_metrics():
    proposal = ProposalSpec(
        proposal_id="p1", symbol="EURUSD", side=Side.LONG, stop_loss=0.9980,
        setup="S1", session="ASIAN_LONDON", direction="LONG",
    )
    orch = ForwardOrchestrator(_campaign(), _proposal_fn([proposal]), _broker())
    orch.on_candle(_candle(0, 1.0000, 1.0002, 0.9990, 1.0000))  # proposal -> pending
    orch.on_candle(_candle(15, 1.0000, 1.0004, 0.9975, 0.9990))  # fill + SL

    metrics = orch.finalize()
    assert metrics.proposals == 1
    assert metrics.fills == 1
    assert metrics.resolved_positions == 1
    assert metrics.losses == 1
    assert metrics.by_setup["S1"].net_R == pytest.approx(-1.0)


def test_checkpoint_roundtrip_restart_safe(tmp_path):
    orch = ForwardOrchestrator(_campaign(), lambda c: ForwardDecision(DECISION_NO_SETUP), _broker())
    orch.on_candle(_candle(0, 1.0, 1.0, 1.0, 1.0))
    path = str(tmp_path / "forward_checkpoint.json")
    orch.save_checkpoint(path)

    orch2 = ForwardOrchestrator(_campaign(), lambda c: ForwardDecision(DECISION_NO_SETUP), _broker())
    orch2.load_checkpoint(path)
    # restored consumption position means the next duplicate candle is rejected
    with pytest.raises(ValueError):
        orch2.on_candle(_candle(0, 1.0, 1.0, 1.0, 1.0))


def test_checkpoint_campaign_mismatch_rejected(tmp_path):
    orch = ForwardOrchestrator(_campaign(), lambda c: ForwardDecision(DECISION_NO_SETUP), _broker())
    path = str(tmp_path / "fwd.json")
    orch.save_checkpoint(path)
    other = ForwardOrchestrator(
        _campaign(campaign_id="OTHER"), lambda c: ForwardDecision(DECISION_NO_SETUP), _broker()
    )
    with pytest.raises(ValueError):
        other.load_checkpoint(path)
