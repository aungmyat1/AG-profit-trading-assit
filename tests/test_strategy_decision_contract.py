"""Focused tests for src/strategy_contract/decision.py (AG_STRATEGY_TECH_SELECTIVE_PORT
_AND_REUSE_V1, Phase 1). These test the ADAPTER only -- pure mapping from an already-
produced native decision into StrategyDecision. They never construct a native decision
via a live engine call; they build small, explicit native fixtures directly, matching
this repo's existing fixture style (see tests/test_historical_replay_no_lookahead.py).
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from large_smc_research.decision import LargeSMCResearchDecision, LargeSMCDecisionState
from post_asian_pilot.decision import PostAsianDecision
from strategy_engine.models import TradeSignal
from strategy_engine.sweep_retest.models import SetupState, STATE_ENTRY_READY, STATE_WAITING_SWEEP
from strategy_contract.decision import (
    StrategyDecision,
    from_btc_setup_state,
    from_fx_decision,
    from_large_smc_decision,
)

UTC = dt.timezone.utc


def test_strategy_decision_is_frozen_and_immutable():
    decision = StrategyDecision(
        strategy_id="X", strategy_version="1.0.0", symbol="EURUSD", direction=None,
        decision_timestamp=None, confidence=None, evidence_ref=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.symbol = "GBPUSD"  # type: ignore[misc]


# --------------------------------------------------------------------------- FX

def test_fx_ready_decision_maps_direction_entry_stop_and_timestamp():
    ready_at = dt.datetime(2026, 9, 1, 6, 35, tzinfo=UTC)
    signal = TradeSignal(
        signal_id="SIG-1", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        symbol="EURUSD", pair_id="ASIAN_LONDON", reference_session="asian",
        session_date=dt.date(2026, 9, 1), box_high=1.11, box_low=1.10, box_mid=1.105,
        regime="SWEEP", setup="SWEEP", status="SIGNAL", reason_code="SWEEP_CONFIRMED",
        direction="LONG", entry=1.1010, stop_loss=1.0990, signal_timestamp=ready_at,
    )
    decision = PostAsianDecision(
        decision_id="DECISION-EURUSD-abc", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol="EURUSD", trading_date=dt.date(2026, 9, 1),
        reference_session="asian", status="READY", reason_codes=("SWEEP_CONFIRMED",),
        evaluation_time=dt.datetime(2026, 9, 1, 6, 36, tzinfo=UTC),
        signal=signal, ready_at=ready_at,
    )

    result = from_fx_decision(decision)

    assert result.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert result.strategy_version == "1.1.1"
    assert result.direction == "LONG"
    assert result.decision_timestamp == ready_at  # authoritative ready_at, not evaluation_time
    assert result.confidence is None
    assert result.evidence_ref == "DECISION-EURUSD-abc"
    assert result.setup_properties["entry"] == 1.1010
    assert result.setup_properties["stop_loss"] == 1.0990


def test_fx_no_trade_decision_has_no_direction_no_entry():
    decision = PostAsianDecision(
        decision_id="DECISION-EURUSD-xyz", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol="EURUSD", trading_date=dt.date(2026, 9, 1),
        reference_session="asian", status="NO_TRADE", reason_codes=("NO_SWEEP",),
        evaluation_time=dt.datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
    )

    result = from_fx_decision(decision)

    assert result.direction is None
    assert result.setup_properties["entry"] is None
    assert result.setup_properties["stop_loss"] is None
    assert result.decision_timestamp == decision.evaluation_time  # no ready_at -- falls back


# --------------------------------------------------------------------------- BTC

def test_btc_entry_ready_state_maps_geometry_and_requires_external_version():
    state = SetupState(
        setup_id="SETUP-BTCUSDT-1", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        symbol="BTCUSDT", state=STATE_ENTRY_READY, reason_code="RETEST_CONFIRMED",
        evaluated_at=dt.datetime(2026, 9, 1, 3, 0, tzinfo=UTC), direction="LONG",
        profile_id="CRYPTO_PERP", entry=60000.0, stop_loss=59500.0, tp1=61000.0,
        tp2=62000.0, tp2_r_multiple=4.0, strategy_qualified=True,
    )

    result = from_btc_setup_state(state, strategy_version="2.0.0")

    assert result.strategy_version == "2.0.0"  # supplied by caller, not invented
    assert result.direction == "LONG"
    assert result.setup_properties["entry"] == 60000.0
    assert result.setup_properties["strategy_qualified"] is True
    assert result.setup_properties["is_terminal"] is False
    assert result.evidence_ref == "SETUP-BTCUSDT-1"


def test_btc_waiting_state_has_no_direction_no_geometry():
    state = SetupState(
        setup_id="SETUP-BTCUSDT-2", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        symbol="BTCUSDT", state=STATE_WAITING_SWEEP, reason_code="AWAITING_SWEEP",
        evaluated_at=dt.datetime(2026, 9, 1, 1, 0, tzinfo=UTC),
    )

    result = from_btc_setup_state(state, strategy_version="2.0.0")

    assert result.direction is None
    assert result.setup_properties["entry"] is None
    assert result.setup_properties["strategy_qualified"] is False


# --------------------------------------------------------------------------- Large-SMC

def test_large_smc_c10_unsigned_stop_is_none_not_fabricated():
    """The core Phase-1 acceptance requirement for Large-SMC: stop=None must be
    preserved, never backfilled from structural_invalidation_price or any other value."""
    decision = LargeSMCResearchDecision(
        strategy_version="1.0.6", symbol="XAUUSD",
        evaluation_timestamp=dt.datetime(2026, 9, 1, 4, 0, tzinfo=UTC),
        entry_condition="E2", maneuver="M1", combination="E2M1", direction="LONG",
        candidate_occurrence_id="OCC-1", entry_price=2500.0,
        structural_invalidation_price=2490.0,  # exists, but must NOT become the stop
        target_price=2550.0, target_tier="PRIMARY_EXTERNAL_LIQUIDITY",
        simulated_broker_stop=None,
        state=LargeSMCDecisionState.BLOCKED.value,
        reason_codes=("UNSIGNED_CONTRACT:C10_BROKER_STOP",),
    )

    result = from_large_smc_decision(decision)

    assert result.strategy_id == "ST_LARGE_SMC_V1"
    assert result.direction == "LONG"
    assert result.setup_properties["stop_loss"] is None
    assert result.setup_properties["structural_invalidation_price"] == 2490.0
    assert "UNSIGNED_CONTRACT:C10_BROKER_STOP" in result.setup_properties["blockers"]
    assert result.evidence_ref == "OCC-1"


def test_large_smc_watch_state_has_no_direction():
    decision = LargeSMCResearchDecision(
        strategy_version="1.0.6", symbol="XAUUSD",
        evaluation_timestamp=dt.datetime(2026, 9, 1, 4, 0, tzinfo=UTC),
        state=LargeSMCDecisionState.WATCH.value,
    )

    result = from_large_smc_decision(decision)

    assert result.direction is None
    assert result.setup_properties["stop_loss"] is None
    assert result.setup_properties["blockers"] == ()
