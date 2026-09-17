"""Sweep trigger detection. FORK_COPY_FROZEN, byte-identical logic to
session_trading_source_v1/sweep.py (ST_SESSION_TRADING_SOURCE_V1 v0.1.0).

Strict penetration + close-back-inside; entry price = qualifying candle's own
close. Scans the entire post-session window and returns EVERY qualifying event
-- no first-match-only shortcut, no eligibility filtering, no max-entries cap.
This lineage deliberately generates the full unfiltered occurrence population;
any future eligibility hypothesis is a matter for a separately preregistered
ES-R1+ mission (ES-S6 P3/P9), never silently added here.
"""
from __future__ import annotations

from typing import List, Sequence

from .models import AsianRange, Candle, Direction, SweepEvent, SweepStatus


def detect_sweeps(asian_range: AsianRange, post_session_candles: Sequence[Candle]) -> List[SweepEvent]:
    events: List[SweepEvent] = []
    for candle in post_session_candles:
        upper_swept = candle.high > asian_range.high and candle.close < asian_range.high
        lower_swept = candle.low < asian_range.low and candle.close > asian_range.low

        if upper_swept and lower_swept:
            events.append(SweepEvent(
                status=SweepStatus.AMBIGUOUS_DUAL_SIDE, time=candle.time, direction=None, entry_price=None,
                evidence={"candle_high": candle.high, "candle_low": candle.low, "candle_close": candle.close},
            ))
            continue

        if upper_swept:
            events.append(SweepEvent(
                status=SweepStatus.VALID, time=candle.time, direction=Direction.SHORT, entry_price=candle.close,
                evidence={"asian_high": asian_range.high, "candle_high": candle.high, "candle_close": candle.close},
            ))
        elif lower_swept:
            events.append(SweepEvent(
                status=SweepStatus.VALID, time=candle.time, direction=Direction.LONG, entry_price=candle.close,
                evidence={"asian_low": asian_range.low, "candle_low": candle.low, "candle_close": candle.close},
            ))
    return events
