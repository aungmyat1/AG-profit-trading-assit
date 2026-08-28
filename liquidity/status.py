"""The sweep/reclaim state machine. Pure functions, no MT5/smc imports.

Exact semantics (defined here once, per the project convention of not silently
reusing strategy-specific thresholds -- see this module's relationship to
strategy_engine/session/setups.py's entry_2_sweep below):

For a BUY_SIDE (high) level at price P, scanning CLOSED candles chronologically after
the level's origin_time:
  - a candle where high > P is a penetration (STRICT_PENETRATION: wick-only, matches
    the strict-penetration convention already used by strategy_engine.session.setups,
    but computed independently here -- general liquidity must not silently inherit a
    strategy-specific implementation).
  - if that same candle's close < P, the penetration RECLAIMED (closed back below).
  - if that same candle's close >= P, the penetration is CONSUMED as of that candle
    (closed beyond, i.e. the level held only as a wick-touch, not as a boundary).
  - the level's status after scanning history is whichever of RECLAIMED/CONSUMED the
    LAST penetrating candle resolved to; UNSWEPT if no candle ever penetrated.
  - separately, if a live tick is supplied and its price is CURRENTLY beyond P while no
    closed candle has confirmed that yet, status is upgraded to SWEPT: penetration is
    happening right now, live, pending confirmation by the next closed candle. This is
    the only situation SWEPT is reported -- once a candle closes, the outcome always
    resolves to RECLAIMED or CONSUMED, never an ambiguous "swept" leftover.

SELL_SIDE (low) levels mirror this with low < P for penetration and close > P for
reclaim.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from strategy_engine.session import Candle

from .models import LiquiditySide, LiquidityStatus


def compute_status(
    side: LiquiditySide,
    price: float,
    candles_after_origin: Sequence[Candle],
    live_bid: Optional[float] = None,
    live_ask: Optional[float] = None,
) -> Tuple[LiquidityStatus, Optional[datetime], Optional[datetime], List[str]]:
    """Returns (status, sweep_time, reclaim_time, reason_codes). sweep_time is the FIRST
    penetrating candle's time; reclaim_time is the time of the LAST reclaim (None if the
    level is currently CONSUMED / has never reclaimed)."""
    is_high = side == LiquiditySide.BUY_SIDE
    sweep_time: Optional[datetime] = None
    reclaim_time: Optional[datetime] = None
    consumed = False

    for c in candles_after_origin:
        penetrated = (c.high > price) if is_high else (c.low < price)
        if not penetrated:
            continue
        if sweep_time is None:
            sweep_time = c.time
        reclaimed_this_candle = (c.close < price) if is_high else (c.close > price)
        if reclaimed_this_candle:
            reclaim_time = c.time
            consumed = False
        else:
            consumed = True

    if sweep_time is None:
        # No closed-candle penetration on record -- check the live tick for an in-progress one.
        if live_bid is not None and live_ask is not None:
            live_price = live_ask if is_high else live_bid
            live_penetrated = (live_price > price) if is_high else (live_price < price)
            if live_penetrated:
                return LiquidityStatus.SWEPT, None, None, ["LIVE_PENETRATION_PENDING_CANDLE_CLOSE"]
        return LiquidityStatus.UNSWEPT, None, None, []

    if consumed:
        return LiquidityStatus.CONSUMED, sweep_time, reclaim_time, []
    return LiquidityStatus.RECLAIMED, sweep_time, reclaim_time, []
