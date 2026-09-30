"""RETEST_BROKEN_SWING entry trigger.

After MSS confirmation, wait up to ENTRY_TTL_M5_BARS completed M5 candles for price to
return to (retest) the broken swing level. No FVG or order-block entry alternative in V1
(spec), and the MSS displacement candle itself is never chased -- only candles strictly
after the MSS-confirming candle are considered.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from strategy_engine.session import Candle

from .mss import MSS_BEARISH, MSSEvent

ENTRY_TTL_M5_BARS = 3


@dataclass(frozen=True)
class RetestEvent:
    entry_price: float
    candle_time: datetime
    candle: Candle
    bars_after_mss: int


def find_retest(
    mss: MSSEvent, candles_after_mss: Sequence[Candle], ttl_bars: int = ENTRY_TTL_M5_BARS
) -> Optional[RetestEvent]:
    """candles_after_mss: closed M5 candles strictly after the MSS-confirming candle,
    chronological. Only the first ttl_bars of them are eligible -- a retest that would
    only be found later is SETUP_EXPIRED, not a late entry (spec: "Entry TTL: 3 completed
    M5 candles after MSS confirmation")."""
    window = list(candles_after_mss)[:ttl_bars]
    is_short = mss.kind == MSS_BEARISH
    for i, candle in enumerate(window, start=1):
        touched = candle.high >= mss.broken_swing_price if is_short else candle.low <= mss.broken_swing_price
        if touched:
            return RetestEvent(mss.broken_swing_price, candle.time, candle, i)
    return None
