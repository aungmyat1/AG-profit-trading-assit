"""Deterministic regime classifier: RANGE / TREND_UP / TREND_DOWN / TRANSITION / UNKNOWN.

UNKNOWN always routes to NO_TRADE downstream (state_machine.py / setups.py never
generate a setup against an UNKNOWN regime). This is a starting hypothesis, not a
tuned model -- range_max_pips / EMA periods are plain config values, not optimized.

Rule (documented so any future change is a visible diff, not silent drift):
  - insufficient reference candles (< regime.min_reference_candles)        -> UNKNOWN
  - reference_session.range_pips <= regime.range_max_pips                  -> RANGE
  - EMA_fast > EMA_slow and last_close > EMA_slow                          -> TREND_UP
  - EMA_fast < EMA_slow and last_close < EMA_slow                          -> TREND_DOWN
  - anything else (mixed EMA alignment, wide range with no clean trend)    -> TRANSITION
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence

from strategy_engine.session.candles import Candle


class Regime(str, Enum):
    RANGE = "RANGE"
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    TRANSITION = "TRANSITION"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    ema_fast: Optional[float]
    ema_slow: Optional[float]
    last_close: Optional[float]
    range_pips: Optional[float]
    reason: str


def required_regime_warmup(config: dict) -> int:
    """The deterministic minimum trailing-closes context classify_regime() needs before
    it can even attempt a non-UNKNOWN classification: max(ema_fast_period,
    ema_slow_period) -- ema() itself returns None (fail closed) below this, which
    classify_regime already surfaces as Regime.UNKNOWN/INSUFFICIENT_EMA_HISTORY. This is
    read directly from the signed config (never hardcoded), so a config change is
    automatically reflected here."""
    fast = int(config["regime"]["ema_fast_period"])
    slow = int(config["regime"]["ema_slow_period"])
    return max(fast, slow)


def ema(values: Sequence[float], period: int) -> Optional[float]:
    """Standard EMA over the trailing `period`+ values. Returns None if there are
    fewer than `period` values (fail closed to 'insufficient data', never a partial
    or biased estimate)."""
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    e = seed
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def classify_regime(
    reference_closes: Sequence[float],
    range_pips: Optional[float],
    candle_count: int,
    config: dict,
) -> RegimeResult:
    min_candles = int(config["regime"]["min_reference_candles"])
    range_max_pips = float(config["regime"]["range_max_pips"])
    fast_period = int(config["regime"]["ema_fast_period"])
    slow_period = int(config["regime"]["ema_slow_period"])

    if candle_count < min_candles or range_pips is None:
        return RegimeResult(Regime.UNKNOWN, None, None, None, range_pips, "INSUFFICIENT_REFERENCE_CANDLES")

    ema_fast = ema(list(reference_closes), fast_period)
    ema_slow = ema(list(reference_closes), slow_period)
    last_close = reference_closes[-1] if reference_closes else None

    if ema_fast is None or ema_slow is None or last_close is None:
        return RegimeResult(Regime.UNKNOWN, ema_fast, ema_slow, last_close, range_pips, "INSUFFICIENT_EMA_HISTORY")

    if range_pips <= range_max_pips:
        return RegimeResult(Regime.RANGE, ema_fast, ema_slow, last_close, range_pips, "RANGE_WITHIN_MAX_PIPS")

    if ema_fast > ema_slow and last_close > ema_slow:
        return RegimeResult(Regime.TREND_UP, ema_fast, ema_slow, last_close, range_pips, "EMA_ALIGNED_UP")

    if ema_fast < ema_slow and last_close < ema_slow:
        return RegimeResult(Regime.TREND_DOWN, ema_fast, ema_slow, last_close, range_pips, "EMA_ALIGNED_DOWN")

    return RegimeResult(Regime.TRANSITION, ema_fast, ema_slow, last_close, range_pips, "MIXED_EMA_ALIGNMENT")
