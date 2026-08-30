"""Sweep detection against the strategy's own frozen Asian reference box.

Same "wick pierces the level, candle closes back inside" shape as
strategy_engine.session.setups.entry_2_sweep, but evaluated on M5 candles against this
strategy's own Asian High/Low (not entry_2_sweep's session_pairs/regime plumbing) -- kept
as a separate, small function rather than forcing this strategy through
route_completed_session's TREND/RANGE routing, which this strategy does not use (H1
structure is the trend filter here, not the ER_ONLY_V2 session-box classifier). See this
package's config.py docstring for why the two strategies do not share a loader either.

wick_ratio_filter = DISABLED for V1 (spec): no wick-size threshold is enforced anywhere
in this module. `wick_ratio_hint` on SweepEvent is populated for informational/future
research purposes only -- nothing here or downstream reads it back to gate a decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from strategy_engine.session import Candle

SWEEP_HIGH = "HIGH_SWEEP"
SWEEP_LOW = "LOW_SWEEP"


@dataclass(frozen=True)
class SweepEvent:
    direction: str  # SWEEP_HIGH / SWEEP_LOW
    swept_level: float
    level_name: str  # "ASIAN_HIGH" / "ASIAN_LOW"
    extreme_price: float  # sweep candle's wick extreme (high for SWEEP_HIGH, low for SWEEP_LOW)
    candle_time: datetime
    candle: Candle
    wick_ratio_hint: Optional[float] = None  # unused future-research field; DISABLED in V1


def _wick_ratio(candle: Candle, direction: str) -> Optional[float]:
    rng = candle.high - candle.low
    if rng <= 0:
        return None
    body_edge = max(candle.open, candle.close) if direction == SWEEP_HIGH else min(candle.open, candle.close)
    wick = (candle.high - body_edge) if direction == SWEEP_HIGH else (body_edge - candle.low)
    return wick / rng


def find_qualified_sweep(
    m5_candles: Sequence[Candle],
    asian_high: float,
    asian_low: float,
    required_direction: Optional[str] = None,
) -> Optional[SweepEvent]:
    """First qualified sweep, chronologically, among CLOSED m5_candles. Only fully closed
    candles may ever be passed in -- this function has no notion of "still forming."

    A candle that qualifies both sides at once is skipped (unresolved direction, same
    posture as entry_2_sweep's AMBIGUOUS_DUAL_SWEEP) rather than reported.

    required_direction (SWEEP_HIGH / SWEEP_LOW), when given, is the H1-trend eligibility
    gate (spec: BULLISH H1 -> only LOW sweeps eligible; BEARISH H1 -> only HIGH sweeps
    eligible) -- a wrong-direction sweep candle is simply not a candidate and scanning
    continues; it does not terminate the search.
    """
    for candle in m5_candles:
        high_sweep = candle.high > asian_high and candle.close < asian_high
        low_sweep = candle.low < asian_low and candle.close > asian_low
        if high_sweep and low_sweep:
            continue

        if high_sweep and required_direction in (None, SWEEP_HIGH):
            return SweepEvent(
                SWEEP_HIGH, asian_high, "ASIAN_HIGH", candle.high, candle.time, candle,
                wick_ratio_hint=_wick_ratio(candle, SWEEP_HIGH),
            )
        if low_sweep and required_direction in (None, SWEEP_LOW):
            return SweepEvent(
                SWEEP_LOW, asian_low, "ASIAN_LOW", candle.low, candle.time, candle,
                wick_ratio_hint=_wick_ratio(candle, SWEEP_LOW),
            )
    return None
