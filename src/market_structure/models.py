"""Project-owned market-structure shapes. Nothing here is smartmoneyconcepts' own
DataFrame/Series output -- that stays confined to market_structure/smc_adapter.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

STATE_BULLISH = "BULLISH"
STATE_BEARISH = "BEARISH"
STATE_UNDEFINED = "STRUCTURE_STATE_UNDEFINED"


class StructurePointKind(str, Enum):
    SWING_HIGH = "SWING_HIGH"
    SWING_LOW = "SWING_LOW"
    BULLISH_BOS = "BULLISH_BOS"
    BEARISH_BOS = "BEARISH_BOS"
    BULLISH_CHOCH = "BULLISH_CHOCH"
    BEARISH_CHOCH = "BEARISH_CHOCH"
    # Added for the tiered (external/internal) model, market_structure/tiers.py --
    # additive only; analyze_structure()/StructureResult above never produce these.
    HH = "HH"
    HL = "HL"
    LH = "LH"
    LL = "LL"


@dataclass(frozen=True)
class StructurePoint:
    time_utc: datetime
    price: float
    kind: StructurePointKind


@dataclass(frozen=True)
class MarketStructureConfig:
    swing_length: int
    close_break: bool
    default_analysis_count: int


@dataclass(frozen=True)
class StructureResult:
    symbol: str
    timeframe: str
    status: str  # "VALID" or a failure reason code (see analyzer.py)
    reason_codes: Tuple[str, ...]

    state: Optional[str] = None  # STATE_BULLISH / STATE_BEARISH / STATE_UNDEFINED
    latest_swing_high: Optional[StructurePoint] = None
    latest_swing_low: Optional[StructurePoint] = None
    latest_bos: Optional[StructurePoint] = None
    latest_choch: Optional[StructurePoint] = None
    previous_high: Optional[float] = None
    previous_low: Optional[float] = None

    # Provenance -- enough to reproduce this analysis.
    broker_resolved_symbol: Optional[str] = None
    data_start_utc: Optional[datetime] = None
    data_end_utc: Optional[datetime] = None
    closed_candle_count: Optional[int] = None
    config: Optional[MarketStructureConfig] = None
    smc_version: Optional[str] = None


@dataclass(frozen=True)
class StructureTier:
    """One structure tier (EXTERNAL or INTERNAL) -- see market_structure/tiers.py for
    the frozen swing_length values and the HH/HL/LH/LL labeling rule. Additive to
    StructureResult above, not a replacement."""

    tier: str  # "EXTERNAL" or "INTERNAL"
    swing_length: int
    direction: str  # STATE_BULLISH / STATE_BEARISH / STATE_UNDEFINED
    swings: Tuple[StructurePoint, ...]  # ALL confirmed swings this tier, chronological
    events: Tuple[StructurePoint, ...]  # ALL confirmed BOS/CHOCH this tier, chronological
    latest_swing_high: Optional[StructurePoint] = None
    latest_swing_low: Optional[StructurePoint] = None
    latest_bos: Optional[StructurePoint] = None
    latest_choch: Optional[StructurePoint] = None


@dataclass(frozen=True)
class TieredStructureResult:
    symbol: str
    timeframe: str
    status: str  # "VALID" or a failure reason code
    reason_codes: Tuple[str, ...]

    external: Optional[StructureTier] = None
    internal: Optional[StructureTier] = None

    data_start_utc: Optional[datetime] = None
    data_end_utc: Optional[datetime] = None
    closed_candle_count: Optional[int] = None
    smc_version: Optional[str] = None
