"""strategy_engine.sweep_retest.occurrence_identity -- new for this task (the sweep/MSS/
retest qualification logic itself is already covered by
tests/test_liquidity_sweep_retest_strategy.py; this only tests the NEW deterministic
occurrence-id composer)."""
from __future__ import annotations

import datetime as dt

from strategy_engine.sweep_retest.occurrence_identity import btc_occurrence_id

UTC = dt.timezone.utc


def _id(**overrides):
    kwargs = dict(
        strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="2.0.0",
        exchange="BINANCE_USDT_M_PERP", canonical_symbol="BTCUSDT",
        reference_trading_day=dt.date(2026, 1, 4), direction="SHORT",
        sweep_time=dt.datetime(2026, 1, 5, 13, 45, tzinfo=UTC),
        mss_time=dt.datetime(2026, 1, 5, 14, 0, tzinfo=UTC),
    )
    kwargs.update(overrides)
    return btc_occurrence_id(**kwargs)


def test_deterministic_same_inputs_same_id():
    assert _id() == _id()


def test_prefixed():
    assert _id().startswith("BTC-OCC-")


def test_different_direction_different_id():
    assert _id(direction="SHORT") != _id(direction="LONG")


def test_different_sweep_time_different_id():
    assert _id() != _id(sweep_time=dt.datetime(2026, 1, 5, 13, 50, tzinfo=UTC))


def test_different_mss_time_different_id():
    assert _id() != _id(mss_time=dt.datetime(2026, 1, 5, 14, 5, tzinfo=UTC))


def test_different_reference_day_different_id():
    assert _id() != _id(reference_trading_day=dt.date(2026, 1, 5))


def test_different_symbol_different_id():
    assert _id() != _id(canonical_symbol="ETHUSDT")


def test_different_exchange_different_id():
    assert _id() != _id(exchange="BYBIT_USDT_M_PERP")


def test_different_strategy_version_different_id():
    assert _id() != _id(strategy_version="2.0.1")
