"""Project-owned Supply & Demand shapes. Nothing here is smartmoneyconcepts' own
DataFrame/Series -- that stays confined to supply_demand/smc_adapter.py, same isolation
rule as market_structure/smc_adapter.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple


class ZoneFamily(str, Enum):
    ORDER_BLOCK = "ORDER_BLOCK"
    FVG = "FVG"
    SESSION = "SESSION"
    PREVIOUS_DAY = "PREVIOUS_DAY"
    DEALING_RANGE = "DEALING_RANGE"


class ZoneRole(str, Enum):
    SUPPLY = "SUPPLY"
    DEMAND = "DEMAND"
    REFERENCE = "REFERENCE"


class ZoneDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NONE = "NONE"


class ZoneStatus(str, Enum):
    FRESH = "FRESH"
    TOUCHED = "TOUCHED"
    MITIGATED = "MITIGATED"
    INVALIDATED = "INVALIDATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ZoneResult:
    symbol: str
    timeframe: str
    family: ZoneFamily
    role: ZoneRole
    direction: ZoneDirection
    status: ZoneStatus
    source: str  # e.g. "smc.ob", "smc.fvg", "config/canonical_sessions.yaml", "mt5 D1 candles"
    low: Optional[float] = None
    high: Optional[float] = None
    origin_time: Optional[datetime] = None
    raw_strength_metric: Optional[float] = None  # e.g. smc OB Percentage -- NOT a probability/confidence
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ZoneQueryResult:
    """Fail-closed wrapper for a batch zone query (order_blocks_for/fair_value_gaps_for):
    status/reason_codes are always populated, `zones` only on a successful query --
    matches strategy_engine.TradeSignal / market_structure.StructureResult's pattern
    of never silently returning an empty result to mean "nothing found" AND "it failed"."""
    symbol: str
    timeframe: str
    family: ZoneFamily
    status: str  # "OK" or a reason_code
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    zones: Tuple["ZoneResult", ...] = field(default_factory=tuple)
