"""Actual-closed-bar-count readiness check for STRUCTURE_WARMUP_H1_BARS.

Replaces the elapsed-calendar-hours approximation used in earlier ad hoc replay
drivers (`h1_report.start_utc + timedelta(hours=N) <= ref_end`), which overcounts
available bars across weekend market closures -- no H1 bar exists during a closed
weekend, so a 1000-*hour* span can contain far fewer than 1000 actual bars. This
module counts real closed candles instead.

Mirrors HistoricalCandleStore.closed_candles's own closed-bar boundary convention (a
bar is closed as of `as_of` iff its open time <= as_of - timeframe_duration) so this
check agrees exactly with what the frozen engine will actually see when it resolves
bias for that same `as_of` -- never a looser or stricter boundary invented separately.
Does not modify strategy semantics; this is a data-readiness utility only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from strategy_engine.session import Candle

from .candle_store import timeframe_duration


def closed_h1_bar_count(h1_candles: Sequence[Candle], as_of: datetime) -> int:
    """Count of H1 candles already closed as of `as_of` (open time <= as_of - 1h).
    Bars at or after `as_of` are never counted, regardless of position in the input --
    no future bar can initialize state for a decision at `as_of`."""
    duration = timeframe_duration("H1")
    cutoff_open_time = as_of - duration
    return sum(1 for c in h1_candles if c.time <= cutoff_open_time)


def sufficient_h1_warmup(h1_candles: Sequence[Candle], as_of: datetime, required_bars: int) -> bool:
    """True iff at least `required_bars` H1 candles are already closed as of `as_of`.
    Uses actual closed bar count -- NOT elapsed calendar hours."""
    return closed_h1_bar_count(h1_candles, as_of) >= required_bars
