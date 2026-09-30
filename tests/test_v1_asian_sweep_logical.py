"""AG V1 (T3): logical verification of the frozen ST_ASIAN_SWEEP_5R_V1@1.1.1 engine.

These are regressions on the current engine, not new rules: determinism, truncation
invariance (candles after the signal bar cannot change it), no look-ahead (a sweep that
only exists in future candles is invisible to a truncated call), and coverage of every V1
FX/gold instrument on both frozen session pairs. Prices are synthetic fixtures scaled per
instrument; no market data is used.
"""
from __future__ import annotations

import datetime as dt

import pytest

from strategy_engine import evaluate, load_strategy
from strategy_engine.session import Candle

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
STRATEGY = load_strategy("strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
SCALE = {"EURUSD": 1.0, "GBPUSD": 1.2, "USDJPY": 140.0, "XAUUSD": 2400.0}
# (reference start hour, first post-session hour) per frozen pair
PAIRS = {"ASIAN_LONDON": (0, 7), "LONDON_NEWYORK": (6, 12)}


def _c(hour, minute, o, h, l, c, k):
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o * k, h * k, l * k, c * k)


def _fixture(symbol, pair_id):
    k = SCALE[symbol]
    ref, post = PAIRS[pair_id]
    session = [_c(ref, 0, 1.1000, 1.1050, 1.0950, 1.1010, k), _c(ref, 15, 1.1010, 1.1040, 1.0960, 1.1005, k)]
    boring = _c(post, 0, 1.1005, 1.1006, 1.1004, 1.1005, k)
    sweep = _c(post, 15, 1.1005, 1.1060, 1.1000, 1.1048, k)  # wick above high, close back inside
    after = [_c(post, 30 + 15 * i, 1.1048, 1.1070, 1.0900, 1.0920, k) for i in range(2)]
    return session, boring, sweep, after


def test_v1_instruments_and_pairs_are_in_the_frozen_contract():
    assert STRATEGY.version == "1.1.1"
    assert set(SCALE) <= set(STRATEGY.instruments)
    assert [p.pair_id for p in STRATEGY.session_pairs] == list(PAIRS)


@pytest.mark.parametrize("symbol", sorted(SCALE))
@pytest.mark.parametrize("pair_id", sorted(PAIRS))
def test_sweep_signal_is_deterministic_and_truncation_invariant(symbol, pair_id):
    session, boring, sweep, after = _fixture(symbol, pair_id)
    first = evaluate(STRATEGY, pair_id, symbol, DAY, session, 2, [boring, sweep])
    again = evaluate(STRATEGY, pair_id, symbol, DAY, session, 2, [boring, sweep])
    extended = evaluate(STRATEGY, pair_id, symbol, DAY, session, 2, [boring, sweep, *after])
    assert first == again
    assert first.status == "SIGNAL" and first.direction == "SHORT"
    assert extended == first  # candles after the signal bar never rewrite it


@pytest.mark.parametrize("symbol", sorted(SCALE))
@pytest.mark.parametrize("pair_id", sorted(PAIRS))
def test_future_sweep_is_invisible_to_truncated_call(symbol, pair_id):
    session, boring, _sweep, _after = _fixture(symbol, pair_id)
    truncated = evaluate(STRATEGY, pair_id, symbol, DAY, session, 2, [boring])
    assert truncated.status == "NO_TRADE"
    assert truncated.direction is None and truncated.entry is None
