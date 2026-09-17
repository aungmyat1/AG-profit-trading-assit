"""Sweep trigger detection. NEW_SOURCE_IMPLEMENTATION.

Predicate (strict penetration + close-back-inside) is independently re-derived to
the same semantics ES-S1S proved EXACT_MATCH for
(src/strategy_engine/session/setups.py::entry_2_sweep, rows 4-8 of
SWEEP_SOURCE_SEMANTIC_MATRIX.md) but is NOT imported from that function, because
entry_2_sweep entangles this predicate with its own wick-based
stop_reference/risk_distance fields, which this candidate must not reuse
(ST_SESSION_TRADING_SOURCE_V1_CANDIDATE_SPEC.md, P5).

Entry price = the qualifying candle's own CLOSE (per this mission's own P4 text),
not max/min(open, close) -- a deliberate simplification relative to
ST_ASIAN_SWEEP_5R_V1's PARTIAL_MATCH nuance on this point.

Per P9 (research occurrence governance), this scans the ENTIRE post-session
window and returns every qualifying event -- it does NOT stop at the first match,
because MAX_ENTRIES_PER_SESSION/DAY is SOURCE_MISSING and must not be silently
enforced by an invented single-shot scan.
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
