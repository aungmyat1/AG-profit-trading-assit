"""Parity tests for research_external/semantic/wilder_atr.py, adapted from
aungmyat1/session-smc-trading-bot@e179fe277d3ab4ac648cfe127e47d987466b2252
(strategy/session_liquidity/displacement_detector.py::wilder_atr).

Two independent checks:
1. A hand-computable deterministic fixture (small, verifiable by inspection).
2. Cross-implementation parity against AG's OWN existing, already-tested Wilder ATR
   (src/session_sweep_continuation/swing_structure.py::compute_atr) on identical
   synthetic candles -- proving the donor function computes the same algorithm AG
   already relies on, not just that it is internally consistent with itself.
"""
from __future__ import annotations

from dataclasses import dataclass

from research_external.semantic.wilder_atr import wilder_atr
from session_sweep_continuation.swing_structure import compute_atr


def test_deterministic_hand_computable_fixture():
    # 3 candles: period=1 so the seed is TR[1] alone (no recursion needed).
    # candle0 close=10 (previous close for TR[1])
    # candle1 high=12 low=8 close=11 -> TR = max(12-8, |12-10|, |8-10|) = max(4,2,2) = 4
    candles = [
        {"high": 10, "low": 10, "close": 10},
        {"high": 12, "low": 8, "close": 11},
    ]
    result = wilder_atr(candles, period=1)
    assert result[0] is None
    assert result[1] == 4.0


def test_insufficient_history_returns_all_none():
    candles = [{"high": 10, "low": 9, "close": 9.5}] * 5
    result = wilder_atr(candles, period=14)
    assert result == [None] * 5


@dataclass(frozen=True)
class _SyntheticCandle:
    """TEST_ONLY SYNTHETIC candle matching session_sweep_continuation's Candle duck-type
    (.high/.low/.close attributes) for cross-implementation parity only."""
    high: float
    low: float
    close: float


def _synthetic_series(n: int) -> list:
    # Deterministic pseudo-price walk, no randomness -- reproducible by construction.
    base = 1.1000
    out = []
    for i in range(n):
        base += 0.0002 if i % 3 != 0 else -0.0003
        high = base + 0.0004
        low = base - 0.0003
        close = base + (0.0001 if i % 2 == 0 else -0.0001)
        out.append({"high": high, "low": low, "close": close})
    return out


def test_cross_implementation_parity_against_ag_own_compute_atr():
    period = 14
    rows = _synthetic_series(40)
    donor_series = wilder_atr(rows, period=period)
    donor_last = donor_series[-1]

    ag_candles = [_SyntheticCandle(high=r["high"], low=r["low"], close=r["close"]) for r in rows]
    ag_value = compute_atr(ag_candles, period=period)

    assert donor_last is not None
    assert ag_value is not None
    assert abs(donor_last - ag_value) < 1e-12
