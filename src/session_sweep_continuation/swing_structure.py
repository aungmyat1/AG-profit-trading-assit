"""Deterministic, lookahead-safe M15 swing/BOS/FVG/ATR detection for this new engine.

No canonical repository-wide swing detector was found in this worktree (this is a
fresh checkout of HEAD -- 5ca5854 -- which does not contain the uncommitted
src/market_swing_structure/ module referenced in project memory as recently added on
the main working tree; it is not present here to import or verify against). Per the
task's own instruction ("prefer it if deterministic/lookahead-safe/replay-safe"), this
module is a new, narrowly-scoped implementation built specifically to this spec's exact
definitions (2-bar-each-side fractal, close-only BOS, 3-candle FVG) -- if
market_swing_structure is later merged into this branch, it should be evaluated for
consolidation, but that is out of scope for this milestone and is recorded as a known
gap in the final report.

LOOKAHEAD SAFETY: a swing at index i (fractal_bars_each_side=N) requires candles
i-N..i+N to exist -- so a swing is only CONFIRMED once N bars close after it. Every
function here operates over a fixed, already-closed candle list and reports a swing's
`confirmed_at` as the close time of the candle N bars after it; callers must never use
a swing whose confirmed_at is after the current replay clock.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import List, Optional, Sequence

from strategy_engine.session.candles import Candle


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


@dataclass(frozen=True)
class Swing:
    index: int
    swing_type: SwingType
    price: float
    time: object          # the swing candle's own bar-open time
    confirmed_at: object  # close time of the confirming candle N bars later


def detect_fractal_swings(candles: Sequence[Candle], bars_each_side: int = 2) -> List[Swing]:
    """Deterministic fractal swing detection, 2-bar-each-side by default (strict
    inequality both sides -- an exact tie at any offset disqualifies the fractal,
    avoiding an ambiguous/arbitrary tie-break rule)."""
    swings: List[Swing] = []
    n = len(candles)
    for i in range(bars_each_side, n - bars_each_side):
        window = candles[i - bars_each_side : i + bars_each_side + 1]
        c = candles[i]
        is_high = all(c.high > o.high for o in window if o is not c)
        is_low = all(c.low < o.low for o in window if o is not c)
        confirm_candle = candles[i + bars_each_side]
        confirmed_at = confirm_candle.time + timedelta(minutes=15)
        if is_high:
            swings.append(Swing(i, SwingType.HIGH, c.high, c.time, confirmed_at))
        if is_low:
            swings.append(Swing(i, SwingType.LOW, c.low, c.time, confirmed_at))
    return swings


def swings_confirmed_by(swings: Sequence[Swing], as_of) -> List[Swing]:
    """Only swings whose confirmation candle has fully closed by `as_of` -- the
    lookahead guard callers must always apply before using a swing as a BOS reference
    or stop anchor."""
    return [s for s in swings if s.confirmed_at <= as_of]


class BOSDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass(frozen=True)
class BOSEvent:
    direction: BOSDirection
    break_candle_index: int
    break_candle_time: object
    broken_swing: Swing
    close_price: float
    displacement_confirmed: bool


def detect_bos(
    candles: Sequence[Candle],
    swings: Sequence[Swing],
    as_of,
    min_body_to_range_ratio: float = 0.60,
) -> List[BOSEvent]:
    """BOS on candle CLOSE only -- a wick beyond a confirmed swing never qualifies
    (bos.type: FRACTAL_CLOSE_BREAK). At each candle close, the most recently confirmed
    opposite-type swing (confirmed strictly before this candle's own close) is the
    reference; if this candle's CLOSE breaks it, that is a BOS event. Only the most
    recent not-yet-broken swing of each type is tracked, and once broken it is retired
    (cannot be broken twice).

    PERFORMANCE (AG_ST_SESSION_SWEEP_CONTINUATION_FIRST_CANONICAL_REPLAY): rewritten
    from an O(len(candles) x len(swings)) per-candle full-rescan (the original,
    behaviorally-equivalent implementation re-filtered the entire `swings` sequence on
    every single candle) to a single O(len(candles) + len(swings)) pass. `swings` is
    already produced by detect_fractal_swings in strictly increasing `.index` order,
    and `.confirmed_at` is monotonically non-decreasing with `.index` (a later swing is
    always confirmed by a later-or-equal candle) -- so swings become eligible in the
    exact same order whether discovered by re-filtering every candle or by a single
    forward-advancing pointer. "Most recent not-yet-broken swing of each type" is
    exactly the top of a stack that gains an entry each time a new swing becomes
    eligible and loses its top entry exactly when that top entry is the one broken
    (the only swing ever broken at any step is the current top, by construction) --
    a plain list used as a stack (.append/.pop of the last element) is therefore an
    exact, cheaper substitute for the original's `max(..., key=lambda s: s.index)`
    over a freshly-filtered list. No behavior, ordering, or event content changes --
    verified byte-for-byte against the pre-existing implementation via this module's
    own test suite (test_session_sweep_continuation_swing_structure.py,
    test_session_sweep_continuation_gap_remediation.py's S3 dispatch test) and the
    full session_sweep_continuation regression, unchanged by this rewrite."""
    events: List[BOSEvent] = []

    highs_sorted = [s for s in swings if s.swing_type == SwingType.HIGH]
    lows_sorted = [s for s in swings if s.swing_type == SwingType.LOW]
    # swings is already index-ordered (detect_fractal_swings appends in scan order),
    # and confirmed_at is monotonic in index -- both properties the pointer walk below
    # relies on. Sorting defensively (a no-op on already-ordered input) costs O(m log m)
    # once, not per-candle, and protects this function's own correctness if it is ever
    # called with an out-of-order swings sequence from elsewhere.
    highs_sorted.sort(key=lambda s: s.index)
    lows_sorted.sort(key=lambda s: s.index)

    hi_ptr = 0
    lo_ptr = 0
    high_stack: List[Swing] = []
    low_stack: List[Swing] = []

    for i, c in enumerate(candles):
        close_time = c.time + timedelta(minutes=15)
        if close_time > as_of:
            break

        while hi_ptr < len(highs_sorted):
            s = highs_sorted[hi_ptr]
            if s.confirmed_at <= close_time and s.index < i:
                high_stack.append(s)
                hi_ptr += 1
            else:
                break
        while lo_ptr < len(lows_sorted):
            s = lows_sorted[lo_ptr]
            if s.confirmed_at <= close_time and s.index < i:
                low_stack.append(s)
                lo_ptr += 1
            else:
                break

        if high_stack:
            latest_high = high_stack[-1]
            if c.close > latest_high.price:
                body = abs(c.close - c.open)
                rng = max(c.high - c.low, 1e-12)
                events.append(BOSEvent(
                    BOSDirection.UP, i, c.time, latest_high, c.close,
                    displacement_confirmed=(body / rng) >= min_body_to_range_ratio,
                ))
                high_stack.pop()

        if low_stack:
            latest_low = low_stack[-1]
            if c.close < latest_low.price:
                body = abs(c.close - c.open)
                rng = max(c.high - c.low, 1e-12)
                events.append(BOSEvent(
                    BOSDirection.DOWN, i, c.time, latest_low, c.close,
                    displacement_confirmed=(body / rng) >= min_body_to_range_ratio,
                ))
                low_stack.pop()

    return events


class FVGDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


@dataclass(frozen=True)
class FVGEvent:
    direction: FVGDirection
    index: int             # index of the middle (3rd... actually 2nd) candle -- see detect_fvg
    low: float
    high: float
    size_pips: float
    eligible: bool
    candle_time: object


def detect_fvg(candles: Sequence[Candle], pip_size: float, min_pips: float, max_pips: float) -> List[FVGEvent]:
    """Deterministic 3-candle M15 FVG: for candles (c1, c2, c3) at indices (i, i+1, i+2):
      bullish gap: c1.high < c3.low   -> zone [c1.high, c3.low]
      bearish gap: c1.low  > c3.high  -> zone [c3.high, c1.low]
    `eligible` is size_pips within [min_pips, max_pips] inclusive; ineligible FVGs are
    still returned (for evidence/diagnostics) but callers must gate on `eligible`."""
    events: List[FVGEvent] = []
    n = len(candles)
    for i in range(n - 2):
        c1, c3 = candles[i], candles[i + 2]
        if c1.high < c3.low:
            zone_low, zone_high = c1.high, c3.low
            size_pips = (zone_high - zone_low) / pip_size
            eligible = min_pips <= size_pips <= max_pips
            events.append(FVGEvent(FVGDirection.BULLISH, i, zone_low, zone_high, size_pips, eligible, candles[i + 1].time))
        elif c1.low > c3.high:
            zone_low, zone_high = c3.high, c1.low
            size_pips = (zone_high - zone_low) / pip_size
            eligible = min_pips <= size_pips <= max_pips
            events.append(FVGEvent(FVGDirection.BEARISH, i, zone_low, zone_high, size_pips, eligible, candles[i + 1].time))
    return events


def compute_atr(candles: Sequence[Candle], period: int = 14) -> Optional[float]:
    """Wilder's ATR over `candles` (assumed already the correct configured timeframe --
    callers must never silently substitute a different timeframe's candles here).
    Returns None if fewer than period+1 candles are available (fail closed)."""
    if len(candles) < period + 1:
        return None
    trs: List[float] = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i - 1]
        tr = max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr
