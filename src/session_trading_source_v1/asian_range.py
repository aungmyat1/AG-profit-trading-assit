"""Asian reference range construction. NEW_SOURCE_IMPLEMENTATION.

Frozen source contract (ST_SESSION_TRADING_SOURCE_V1_CANDIDATE_SPEC.md, P3):
  ASIAN_SESSION_START = 00:00 UTC
  ASIAN_SESSION_END   = 07:00 UTC
  A = AsianHigh - AsianLow, frozen after session completion, M15 only.
"""
from __future__ import annotations

from datetime import time
from typing import Optional, Sequence

from .models import AsianRange, Candle

ASIAN_SESSION_START_UTC = time(0, 0)
ASIAN_SESSION_END_UTC = time(7, 0)


def is_in_asian_session(candle: Candle) -> bool:
    t = candle.time.time()
    return ASIAN_SESSION_START_UTC <= t < ASIAN_SESSION_END_UTC


def build_asian_range(session_candles: Sequence[Candle]) -> Optional[AsianRange]:
    """`session_candles` must already be filtered to the 00:00-07:00 UTC window for
    one trading day and fully closed (no lookahead). Returns None if no candles are
    available or the resulting range is non-positive (degenerate) -- never guesses."""
    candles = [c for c in session_candles if is_in_asian_session(c)]
    if not candles:
        return None
    high_candle = max(candles, key=lambda c: c.high)
    low_candle = min(candles, key=lambda c: c.low)
    rng = AsianRange(high=high_candle.high, low=low_candle.low,
                      high_time=high_candle.time, low_time=low_candle.time)
    if rng.range <= 0:
        return None
    return rng
