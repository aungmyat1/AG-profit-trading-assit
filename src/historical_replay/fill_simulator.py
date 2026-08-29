"""Entry-fill simulation (historical-validation continuation spec sections 30-38).
READY != FILLED: a setup can become READY and price may never return to the entry
array, or the setup may invalidate before ever filling. This module answers "would the
actual entry array have filled" using the same M5 OHLC series the replay already
loaded -- never a second, invented entry rule (spec section 31: consume entry_low/
entry_high/entry_reference from the composer/M-model's own output, exactly as recorded
in the SetupLedgerRow, do not recompute a market-entry substitute).

ENTRY_EXPIRY = UNDEFINED (spec section 22, 37): no signed time-based expiry rule exists
anywhere in entry_confirmation today. This module does NOT invent one -- a setup that
neither fills nor invalidates before the loaded data ends is reported
UNFILLED_AS_OF_DATA_END, never silently treated as a permanent negative result.

SAME-BAR AMBIGUITY (spec sections 33/36, 57-58): M1/M3 invalidation is a LIVE_PRICE
comparison (entry_confirmation.invalidation.TRIGGER_LIVE_PRICE) which cannot be resolved
from M5 OHLC alone when entry and invalidation levels are both touched inside the same
bar -- this is classified INTRABAR_AMBIGUOUS, never resolved by assuming an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Sequence

from strategy_engine.session import Candle

STATUS_FILLED = "FILLED"
STATUS_UNFILLED_AS_OF_DATA_END = "UNFILLED_AS_OF_DATA_END"
STATUS_INVALIDATED_BEFORE_FILL = "INVALIDATED_BEFORE_FILL"
STATUS_INTRABAR_AMBIGUOUS = "INTRABAR_AMBIGUOUS"
STATUS_NO_ENTRY_CONTRACT = "NO_ENTRY_CONTRACT"  # entry_low/high/reference all missing -- cannot simulate


@dataclass(frozen=True)
class FillResult:
    setup_id: str
    combination: str
    direction: Optional[str]
    ready_time: datetime
    status: str
    fill_time: Optional[datetime] = None
    fill_price: Optional[float] = None
    invalidation_time: Optional[datetime] = None
    note: str = ""


def _entry_bounds(entry_low: Optional[float], entry_high: Optional[float],
                   entry_reference: Optional[float]) -> Optional[tuple]:
    if entry_low is not None and entry_high is not None:
        return (min(entry_low, entry_high), max(entry_low, entry_high))
    if entry_reference is not None:
        return (entry_reference, entry_reference)
    return None


def _touches(candle: Candle, low: float, high: float) -> bool:
    return candle.low <= high and candle.high >= low


def _invalidation_touched_intrabar(candle: Candle, invalidation_price: float, direction: str) -> bool:
    """M1/M3's LIVE_PRICE trigger and M2's CLOSED_CANDLE_CLOSE trigger are both
    approximated here from the wick (the most permissive/conservative read available
    without tick data) -- overstating rather than understating invalidation risk;
    ambiguity classification (see below) is what keeps this honest rather than silently
    picking a favorable resolution."""
    if direction == "LONG":
        return candle.low < invalidation_price
    if direction == "SHORT":
        return candle.high > invalidation_price
    return False


def simulate_fill(
    setup_id: str, combination: str, direction: Optional[str], ready_time: datetime,
    entry_low: Optional[float], entry_high: Optional[float], entry_reference: Optional[float],
    invalidation_price: Optional[float],
    forward_candles: Sequence[Candle],
) -> FillResult:
    """`forward_candles` must already be filtered to this symbol's M5 series with
    `time >= ready_time`, ascending. Evaluating what happens AFTER a known READY time
    is not lookahead (spec's no-lookahead invariant governs DETECTION, not post-hoc
    outcome evaluation -- see module docstring)."""
    bounds = _entry_bounds(entry_low, entry_high, entry_reference)
    if bounds is None or direction not in ("LONG", "SHORT"):
        return FillResult(setup_id=setup_id, combination=combination, direction=direction,
                           ready_time=ready_time, status=STATUS_NO_ENTRY_CONTRACT,
                           note="entry_low/high/reference and/or direction unavailable")
    low, high = bounds

    for candle in forward_candles:
        entry_hit = _touches(candle, low, high)
        invalidation_hit = (
            invalidation_price is not None
            and _invalidation_touched_intrabar(candle, invalidation_price, direction)
        )
        if entry_hit and invalidation_hit:
            return FillResult(setup_id=setup_id, combination=combination, direction=direction,
                               ready_time=ready_time, status=STATUS_INTRABAR_AMBIGUOUS,
                               invalidation_time=candle.time,
                               note=f"entry and invalidation both touched within {candle.time.isoformat()}'s M5 bar")
        if invalidation_hit:
            return FillResult(setup_id=setup_id, combination=combination, direction=direction,
                               ready_time=ready_time, status=STATUS_INVALIDATED_BEFORE_FILL,
                               invalidation_time=candle.time)
        if entry_hit:
            fill_price = entry_reference if entry_reference is not None else (low if direction == "LONG" else high)
            return FillResult(setup_id=setup_id, combination=combination, direction=direction,
                               ready_time=ready_time, status=STATUS_FILLED,
                               fill_time=candle.time, fill_price=fill_price)

    return FillResult(setup_id=setup_id, combination=combination, direction=direction,
                       ready_time=ready_time, status=STATUS_UNFILLED_AS_OF_DATA_END,
                       note="no touch of entry array or invalidation level within the loaded data")
