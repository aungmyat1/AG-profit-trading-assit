"""Focused tests for src/strategy_contract/market_snapshot.py (WP1, market truth contract,
AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1). Tests the contract and its constructors only --
from_mt5_latest_closed is tested with mt5.market_data.get_latest_candles monkeypatched so
no live MT5 terminal/connection is required, matching this repo's existing fixture style
(see tests/test_strategy_decision_contract.py).
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from strategy_engine.session import Candle
from mt5.market_data import MarketDataError
import strategy_contract.market_snapshot as market_snapshot
from strategy_contract.market_snapshot import (
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_REPLAY,
    MARKET_DATA_MODE_SYNTHETIC,
    MarketSnapshot,
    UnsupportedTimeframeError,
    from_mt5_latest_closed,
    from_replay_candle,
    from_synthetic_candle,
)

UTC = dt.timezone.utc


def _candle(time=dt.datetime(2026, 9, 1, 6, 15, tzinfo=UTC)) -> Candle:
    return Candle(time=time, open=1.0850, high=1.0860, low=1.0840, close=1.0855, volume=120.0)


def test_market_snapshot_is_frozen_and_immutable():
    snap = from_replay_candle("EURUSD", "M15", _candle(), source="fixture_2026_09_01.json")
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.symbol = "GBPUSD"  # type: ignore[misc]


def test_rejects_unknown_market_data_mode():
    with pytest.raises(ValueError):
        MarketSnapshot(
            symbol="EURUSD", timeframe="M15", source="x", market_data_mode="FAKE_MODE",
            bar_open_time=_candle().time, bar_close_time=_candle().time, market_data_asof=_candle().time,
            retrieved_at=_candle().time, is_closed=True, fingerprint="x",
        )


def test_unsupported_timeframe_raises():
    with pytest.raises(UnsupportedTimeframeError):
        from_replay_candle("EURUSD", "M3", _candle(), source="fixture")


def test_bar_close_time_is_bar_open_plus_timeframe():
    snap = from_replay_candle("EURUSD", "M15", _candle(), source="fixture")
    assert snap.bar_close_time == snap.bar_open_time + dt.timedelta(minutes=15)
    assert snap.market_data_asof == snap.bar_close_time


def test_fingerprint_is_deterministic_and_mode_sensitive():
    c = _candle()
    replay = from_replay_candle("EURUSD", "M15", c, source="fixture")
    replay_again = from_replay_candle("EURUSD", "M15", c, source="fixture", retrieved_at=dt.datetime(2030, 1, 1, tzinfo=UTC))
    synthetic = from_synthetic_candle("EURUSD", "M15", c)

    assert replay.fingerprint == replay_again.fingerprint  # retrieved_at must not affect identity
    assert replay.fingerprint != synthetic.fingerprint  # mode is part of the fingerprint


def test_replay_and_synthetic_modes_tagged_correctly():
    replay = from_replay_candle("EURUSD", "M15", _candle(), source="fixture")
    synthetic = from_synthetic_candle("EURUSD", "M15", _candle())
    assert replay.market_data_mode == MARKET_DATA_MODE_REPLAY
    assert synthetic.market_data_mode == MARKET_DATA_MODE_SYNTHETIC


def test_real_mode_wraps_single_latest_closed_candle(monkeypatch):
    c = _candle()
    monkeypatch.setattr(market_snapshot, "get_latest_candles", lambda symbol, timeframe, count: [c])

    snap = from_mt5_latest_closed("EURUSD", "M15")

    assert snap.market_data_mode == MARKET_DATA_MODE_REAL
    assert snap.source == "VANTAGE_DEMO_MT5"
    assert snap.symbol == "EURUSD"
    assert snap.is_closed is True
    assert snap.bar_open_time == c.time


def test_real_mode_fails_closed_never_substitutes_synthetic_data(monkeypatch):
    def _raise(symbol, timeframe, count):
        raise MarketDataError("DATA_MISSING", "no data")

    monkeypatch.setattr(market_snapshot, "get_latest_candles", _raise)

    with pytest.raises(MarketDataError) as exc_info:
        from_mt5_latest_closed("EURUSD", "M15")
    assert exc_info.value.reason_code == "DATA_MISSING"
