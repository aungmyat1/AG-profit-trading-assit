"""Project-owned Liquidity shapes.

A liquidity LEVEL is a price a resting-order cluster is believed to sit at (a swing
point, a session extreme, PDH/PDL, an equal-highs/lows cluster). A liquidity EVENT is
something that happened to a level (a wick penetrating it, a close reclaiming it) --
see liquidity/status.py's module docstring for the exact state machine that turns a
level's candle history into its current `status`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple


class LiquiditySide(str, Enum):
    BUY_SIDE = "BUY_SIDE"    # resting liquidity ABOVE price (above swing highs, session/day highs)
    SELL_SIDE = "SELL_SIDE"  # resting liquidity BELOW price (below swing lows, session/day lows)


class LiquidityStatus(str, Enum):
    UNSWEPT = "UNSWEPT"        # no candle has traded through the level, and price is not currently through it live
    SWEPT = "SWEPT"            # the CURRENT live tick is trading through the level, not yet confirmed by a closed candle
    RECLAIMED = "RECLAIMED"    # a closed candle traded through the level, and the market has since closed back on the origin side
    CONSUMED = "CONSUMED"      # a closed candle traded through AND closed beyond the level, with no reclaim since
    UNKNOWN = "UNKNOWN"        # status could not be determined (e.g. no post-origin candle data, tick unavailable)


@dataclass(frozen=True)
class LiquidityLevel:
    symbol: str
    timeframe: str
    side: LiquiditySide
    source: str  # first-detected source, kept for backward compatibility -- see `sources`
                 # "SWING_HIGH" / "SWING_LOW" / "ASIAN_HIGH" / "ASIAN_LOW" / "LONDON_HIGH" / "LONDON_LOW" /
                 # "NEW_YORK_HIGH" / "NEW_YORK_LOW" / "PDH" / "PDL" / "PWH" / "PWL" / "EQUAL_HIGHS" / "EQUAL_LOWS"
    price: float
    origin_time: Optional[datetime]
    status: LiquidityStatus
    sweep_time: Optional[datetime] = None
    reclaim_time: Optional[datetime] = None
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    sources: Tuple[str, ...] = field(default_factory=tuple)  # every source that merged into this level
                                                              # (see liquidity/dedup.py); always contains
                                                              # at least `source` once populated by the analyzer


@dataclass(frozen=True)
class LiquidityResult:
    symbol: str
    timeframe: str
    status: str  # "LIQUIDITY_OK" / "NO_LIQUIDITY_LEVELS" / a MarketDataError-equivalent reason_code
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    levels: Tuple[LiquidityLevel, ...] = field(default_factory=tuple)
    nearest_buy_side: Optional[LiquidityLevel] = None
    nearest_sell_side: Optional[LiquidityLevel] = None
