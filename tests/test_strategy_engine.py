"""Tests for the strategy_engine loader/engine bridge: strategies/*.yaml -> StrategyConfig
-> TradeSignal, using the real ST_ASIAN_SWEEP_5R_V1.yaml rather than a fixture, so a change
that breaks the actual registered config fails here."""
from __future__ import annotations

import datetime as dt

import pytest

from strategy_engine import evaluate, load_strategy
from strategy_engine.session import Candle

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


def _candle(hour, minute, o, h, l, c) -> Candle:
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def test_load_strategy_parses_both_session_pairs():
    strategy = load_strategy(STRATEGY_PATH)
    assert strategy.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert "EURUSD" in strategy.instruments
    pair_ids = [p.pair_id for p in strategy.session_pairs]
    assert pair_ids == ["ASIAN_LONDON", "LONDON_NEWYORK"]
    asian_pair = strategy.session_pairs[0]
    assert asian_pair.reference_session.name == "Asian"
    assert asian_pair.trade_session.name == "London_Open"


def test_evaluate_rejects_symbol_outside_instruments():
    strategy = load_strategy(STRATEGY_PATH)
    with pytest.raises(ValueError):
        evaluate(strategy, "ASIAN_LONDON", "USDCAD", DAY, [_candle(0, 0, 1.1, 1.1, 1.1, 1.1)], 1)


def test_evaluate_rejects_unknown_pair_id():
    strategy = load_strategy(STRATEGY_PATH)
    with pytest.raises(ValueError):
        evaluate(strategy, "NOT_A_PAIR", "EURUSD", DAY, [_candle(0, 0, 1.1, 1.1, 1.1, 1.1)], 1)


def test_evaluate_range_with_sweep_yields_signal():
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = [
        _candle(0, 0, 1.1000, 1.1050, 1.0950, 1.1010),
        _candle(0, 15, 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    sweep_candle = _candle(7, 0, 1.1005, 1.1050 + 0.0010, 1.1000, 1.1050 - 0.0002)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [sweep_candle])

    assert signal.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    assert signal.reference_session == "Asian"
    assert signal.regime == "RANGE"
    assert signal.setup == "SWEEP"
    assert signal.status == "SIGNAL"
    assert signal.direction == "SHORT"


def test_evaluate_no_setup_yields_no_trade():
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = [
        _candle(0, 0, 1.1000, 1.1050, 1.0950, 1.1010),
        _candle(0, 15, 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    boring_candle = _candle(7, 0, 1.1005, 1.1006, 1.1004, 1.1005)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", DAY, session_candles, 2, [boring_candle])

    assert signal.status == "NO_TRADE"
    assert signal.direction is None
