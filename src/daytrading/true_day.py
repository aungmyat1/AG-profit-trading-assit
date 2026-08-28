"""DAYTRADING_TRUE_DAY_CONTEXT (spec sections 12-14): the NY-midnight trading day used by
Narrative Bias. Deliberately separate from CANONICAL_SESSION_WINDOWS (config/canonical_
sessions.yaml, consumed via supply_demand.session_zone) -- that source of truth is not
touched or redefined here. This module only answers "what is today's NY calendar day, in
UTC, given a timestamp", using a real DST-aware timezone (zoneinfo), never a fixed offset
and never a bar-count assumption ("23 H1 bars = 1 day" is reference material, not a rule).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

REFERENCE_TIMEZONE = "America/New_York"
_NY_TZ = ZoneInfo(REFERENCE_TIMEZONE)


@dataclass(frozen=True)
class TrueDayContext:
    reference_timezone: str
    trading_date: str  # NY calendar date of day_start, "YYYY-MM-DD"
    day_start_utc: datetime  # NY 00:00 for trading_date, expressed in UTC
    day_end_utc: datetime  # next NY 00:00, expressed in UTC (exclusive)


def true_day_window(evaluation_time_utc: datetime) -> TrueDayContext:
    """The NY 00:00 -> next NY 00:00 window containing `evaluation_time_utc`."""
    if evaluation_time_utc.tzinfo is None:
        raise ValueError("evaluation_time_utc must be timezone-aware")
    ny_now = evaluation_time_utc.astimezone(_NY_TZ)
    ny_midnight = ny_now.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = ny_midnight.astimezone(timezone.utc)
    day_end_utc = (ny_midnight + timedelta(days=1)).astimezone(timezone.utc)
    return TrueDayContext(
        reference_timezone=REFERENCE_TIMEZONE,
        trading_date=ny_midnight.date().isoformat(),
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
    )


def true_day_open(candles: Sequence, day_context: TrueDayContext) -> Optional[float]:
    """The open of the first candle at/after day_start_utc. `candles` must expose
    `.time` (UTC) and `.open` (strategy_engine.session.Candle shape) and may be in any
    order; missing/absent midnight bar -> None (fail closed, spec section 32)."""
    in_day = [c for c in candles if day_context.day_start_utc <= c.time < day_context.day_end_utc]
    if not in_day:
        return None
    first = min(in_day, key=lambda c: c.time)
    return first.open


def causal_candles(candles: Sequence, evaluation_time_utc: datetime, day_context: TrueDayContext) -> tuple:
    """Candles strictly within the true day and at/before evaluation_time_utc, sorted.
    Defensive causality filter -- applied even if the caller already trimmed its query,
    so a caller accidentally passing future candles can never leak into EXPECTED_PROFILE
    (spec section 11)."""
    kept = [c for c in candles
            if day_context.day_start_utc <= c.time < day_context.day_end_utc and c.time <= evaluation_time_utc]
    return tuple(sorted(kept, key=lambda c: c.time))
