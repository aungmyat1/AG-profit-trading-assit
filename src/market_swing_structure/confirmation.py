"""Explicit swing-pivot confirmation timestamps (P6/P7).

market_structure.StructurePoint (see src/market_structure/models.py) stores exactly one
timestamp for a SWING_HIGH/SWING_LOW point: `time_utc`, the PIVOT bar's own time --
never the confirmation time (contrast with BOS/CHOCH points, whose `time_utc` already IS
the confirmation time via smc_adapter's BrokenIndex handling; see that module's
docstring). A swing_highs_lows(ohlc, swing_length) fractal at bar position `i` is not
knowable until `swing_length` further bars have closed (positions i+1..i+swing_length) --
the pivot's own bar alone can never confirm it.

This module makes that latent confirmation timestamp EXPLICIT: given the pivot's own
time, the timeframe, and the swing_length used to detect it, `confirmed_time_utc` is
DERIVED (not re-detected) as pivot_time + swing_length bars of that timeframe's own
duration. This is arithmetic over already-known quantities (timeframe bar duration is a
fixed repository fact, reused from historical_replay.candle_store.TIMEFRAME_MINUTES --
see that module's own canonical mapping, not duplicated here), never a second pivot
detector.

Because market_structure.analyze_structure() only ever returns a swing point that
already had its full swing_length right-side window available within the fetched
candle range (see analyzer.py's warmup_bars sizing and smc_adapter's own bookend-artifact
guard), every swing this module is ever asked to normalize is already, structurally,
confirmed as of the data it came from. `assert_confirmed_as_of` exists as an explicit,
testable safety net for that already-true invariant -- not a claim that this module
could otherwise produce an unconfirmed swing.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from historical_replay.candle_store import TIMEFRAME_MINUTES
from market_structure.models import StructurePoint, StructurePointKind

from .models import STATUS_CONFIRMED, NormalizedSwing

_SWING_KINDS = {
    StructurePointKind.SWING_HIGH: "SWING_HIGH",
    StructurePointKind.SWING_LOW: "SWING_LOW",
}


class UnsupportedTimeframeError(Exception):
    """Raised for a timeframe not in the canonical TIMEFRAME_MINUTES mapping -- fail
    closed rather than guessing a bar duration."""


def confirmed_time_for_pivot(pivot_time_utc: datetime, timeframe: str, swing_length: int) -> datetime:
    """confirmed_time_utc = pivot_time_utc + swing_length bars of `timeframe`'s own
    duration -- the time the swing_length-th right-side confirming bar closes. Pure,
    deterministic, no I/O."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise UnsupportedTimeframeError(f"{timeframe!r} not in {sorted(TIMEFRAME_MINUTES)}")
    if swing_length < 0:
        raise ValueError(f"swing_length must be >= 0, got {swing_length}")
    return pivot_time_utc + timedelta(minutes=TIMEFRAME_MINUTES[timeframe] * swing_length)


def normalize_swing_point(point: StructurePoint, timeframe: str, swing_length: int) -> Optional[NormalizedSwing]:
    """Wraps one canonical StructurePoint into a NormalizedSwing with an explicit
    confirmed_time_utc. Returns None for a non-swing StructurePoint kind (BOS/CHOCH/
    HH/HL/LH/LL) -- this function only ever normalizes SWING_HIGH/SWING_LOW, it never
    reinterprets a structural-break point as a swing."""
    swing_type = _SWING_KINDS.get(point.kind)
    if swing_type is None:
        return None
    confirmed = confirmed_time_for_pivot(point.time_utc, timeframe, swing_length)
    return NormalizedSwing(
        swing_type=swing_type,
        price=point.price,
        pivot_time_utc=point.time_utc,
        confirmed_time_utc=confirmed,
        timeframe=timeframe,
        strength=swing_length,
        status=STATUS_CONFIRMED,
    )


def assert_confirmed_as_of(swing: NormalizedSwing, as_of_utc: datetime) -> None:
    """Raises LookaheadViolationError if `swing.confirmed_time_utc` is later than
    `as_of_utc` -- i.e. a caller (strategy or skill consumer) is attempting to use this
    swing before it could actually have been known. Structurally, market_structure never
    hands back such a swing in the first place (see module docstring); this function is
    the explicit, testable guard a caller can invoke anyway (P6: 'never backdate
    structural knowledge')."""
    if swing.confirmed_time_utc > as_of_utc:
        raise LookaheadViolationError(
            f"{swing.swing_type} at {swing.pivot_time_utc.isoformat()} confirms at "
            f"{swing.confirmed_time_utc.isoformat()}, which is after as_of={as_of_utc.isoformat()} "
            "-- using it now would be lookahead."
        )


class LookaheadViolationError(Exception):
    """Raised by assert_confirmed_as_of when a swing's confirmation time is later than
    the caller's stated 'as of' time."""
