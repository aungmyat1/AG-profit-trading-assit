"""Focused tests for WP4 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): MarketSnapshot ->
StrategyDecision provenance propagation. Reuses the same native-decision fixture style as
tests/test_strategy_decision_contract.py; only exercises the new market_snapshot
parameter and its fail-closed symbol-mismatch guard.
"""
from __future__ import annotations

import datetime as dt

import pytest

from post_asian_pilot.decision import PostAsianDecision
from strategy_engine.sweep_retest.models import SetupState, STATE_ENTRY_READY
from strategy_contract.decision import (
    MarketSnapshotSymbolMismatch,
    from_btc_setup_state,
    from_fx_decision,
)
from strategy_contract.market_snapshot import (
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_SYNTHETIC,
    from_mt5_latest_closed,
    from_replay_candle,
    from_synthetic_candle,
)
import strategy_contract.market_snapshot as market_snapshot_module
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _fx_ready_decision(symbol="EURUSD") -> PostAsianDecision:
    from strategy_engine.models import TradeSignal

    ready_at = dt.datetime(2026, 9, 1, 6, 35, tzinfo=UTC)
    signal = TradeSignal(
        signal_id="SIG-1", strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        symbol=symbol, pair_id="ASIAN_LONDON", reference_session="asian",
        session_date=dt.date(2026, 9, 1), box_high=1.11, box_low=1.10, box_mid=1.105,
        regime="SWEEP", setup="SWEEP", status="SIGNAL", reason_code="SWEEP_CONFIRMED",
        direction="LONG", entry=1.1010, stop_loss=1.0990, signal_timestamp=ready_at,
    )
    return PostAsianDecision(
        decision_id="DECISION-abc", strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.1.1", symbol=symbol, trading_date=dt.date(2026, 9, 1),
        reference_session="asian", status="READY", reason_codes=("SWEEP_CONFIRMED",),
        evaluation_time=dt.datetime(2026, 9, 1, 6, 36, tzinfo=UTC),
        signal=signal, ready_at=ready_at,
    )


def _candle(time=dt.datetime(2026, 9, 1, 6, 15, tzinfo=UTC)) -> Candle:
    return Candle(time=time, open=1.0850, high=1.0860, low=1.0840, close=1.0855, volume=100.0)


def test_real_market_snapshot_propagates_matching_provenance_onto_decision(monkeypatch):
    c = _candle()
    monkeypatch.setattr(market_snapshot_module, "get_latest_candles", lambda symbol, timeframe, count: [c])
    real_snap = from_mt5_latest_closed("EURUSD", "M15")
    assert real_snap.market_data_mode == MARKET_DATA_MODE_REAL  # sanity on the fixture itself

    result = from_fx_decision(_fx_ready_decision(), market_snapshot=real_snap)

    assert result.market_data_mode == MARKET_DATA_MODE_REAL
    assert result.market_data_source == real_snap.source
    assert result.market_data_asof == real_snap.market_data_asof
    assert result.market_data_fingerprint == real_snap.fingerprint


def test_synthetic_snapshot_never_reported_as_real():
    synthetic_snap = from_synthetic_candle("EURUSD", "M15", _candle())

    result = from_fx_decision(_fx_ready_decision(), market_snapshot=synthetic_snap)

    assert result.market_data_mode == MARKET_DATA_MODE_SYNTHETIC
    assert result.market_data_mode != MARKET_DATA_MODE_REAL


def test_no_snapshot_leaves_market_fields_none_backward_compatible():
    result = from_fx_decision(_fx_ready_decision())
    assert result.market_data_mode is None
    assert result.market_data_source is None
    assert result.market_data_fingerprint is None


def test_mismatched_symbol_snapshot_fails_closed_for_fx():
    wrong_symbol_snap = from_synthetic_candle("GBPUSD", "M15", _candle())
    with pytest.raises(MarketSnapshotSymbolMismatch):
        from_fx_decision(_fx_ready_decision(symbol="EURUSD"), market_snapshot=wrong_symbol_snap)


def test_mismatched_symbol_snapshot_fails_closed_for_btc():
    state = SetupState(
        setup_id="SETUP-BTCUSDT-1", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        symbol="BTCUSDT", state=STATE_ENTRY_READY, reason_code="RETEST_CONFIRMED",
        evaluated_at=dt.datetime(2026, 9, 1, 3, 0, tzinfo=UTC), direction="LONG",
        profile_id="CRYPTO_PERP", entry=60000.0, stop_loss=59500.0, tp1=61000.0,
        tp2=62000.0, tp2_r_multiple=4.0, strategy_qualified=True,
    )
    wrong_symbol_snap = from_synthetic_candle("ETHUSDT", "M15", _candle())
    with pytest.raises(MarketSnapshotSymbolMismatch):
        from_btc_setup_state(state, strategy_version="2.0.0", market_snapshot=wrong_symbol_snap)


def test_matching_symbol_snapshot_succeeds_for_btc():
    state = SetupState(
        setup_id="SETUP-BTCUSDT-1", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        symbol="BTCUSDT", state=STATE_ENTRY_READY, reason_code="RETEST_CONFIRMED",
        evaluated_at=dt.datetime(2026, 9, 1, 3, 0, tzinfo=UTC), direction="LONG",
        profile_id="CRYPTO_PERP", entry=60000.0, stop_loss=59500.0, tp1=61000.0,
        tp2=62000.0, tp2_r_multiple=4.0, strategy_qualified=True,
    )
    snap = from_synthetic_candle("BTCUSDT", "M15", _candle())
    result = from_btc_setup_state(state, strategy_version="2.0.0", market_snapshot=snap)
    assert result.market_data_mode == MARKET_DATA_MODE_SYNTHETIC
    assert result.direction == "LONG"  # strategy-specific semantics preserved unchanged
