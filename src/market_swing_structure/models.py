"""Normalized output shapes for the Market Swing Structure orchestration layer.

Every field here is either copied verbatim from an existing authoritative engine
(market_structure.StructureResult, liquidity.LiquidityResult, supply_demand.ZoneResult/
DealingRangeZones) or a pure, documented DERIVATION over one of those (confirmation
timestamps, mtf_alignment label) -- see confirmation.py/alignment.py/dealing_range.py.
Nothing in this module recomputes a swing, a BOS/CHoCH, a liquidity level, or a zone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional, Tuple

SCHEMA_VERSION = "MARKET_SWING_STRUCTURE_V1"
AUTHORITY = "ADVISORY_CONTEXT_ONLY"

STATUS_CANDIDATE = "CANDIDATE"
STATUS_CONFIRMED = "CONFIRMED"
STATUS_INVALIDATED = "INVALIDATED"


@dataclass(frozen=True)
class NormalizedSwing:
    """One swing point with an EXPLICIT confirmation timestamp (see confirmation.py).
    `source.engine` always names the canonical engine this was read from -- this layer
    never invents a swing that engine did not already return."""

    swing_type: str  # "SWING_HIGH" / "SWING_LOW"
    price: float
    pivot_time_utc: datetime
    confirmed_time_utc: datetime
    timeframe: str
    strength: int  # swing_length used to confirm this pivot
    status: str  # STATUS_CANDIDATE / STATUS_CONFIRMED / STATUS_INVALIDATED
    source_engine: str = "CANONICAL_MARKET_STRUCTURE"


@dataclass(frozen=True)
class StructureEvent:
    """A BOS/CHoCH/wick-sweep event, timestamped at its own CONFIRMATION time (already
    true of market_structure.StructurePoint's BOS/CHOCH time_utc -- see
    market_structure/smc_adapter.py's BrokenIndex handling -- relayed here unchanged)."""

    event_type: str  # "BOS_BULLISH" / "BOS_BEARISH" / "CHOCH_BULLISH" / "CHOCH_BEARISH"
    price: float
    confirmed_time_utc: datetime
    timeframe: str
    source_engine: str = "CANONICAL_MARKET_STRUCTURE"


@dataclass(frozen=True)
class TimeframeStructureSnapshot:
    timeframe: str
    status: str  # relayed verbatim from StructureResult.status ("VALID" or a reason code)
    structure_state: Optional[str] = None  # BULLISH / BEARISH / STRUCTURE_STATE_UNDEFINED
    last_confirmed_swing_high: Optional[NormalizedSwing] = None
    last_confirmed_swing_low: Optional[NormalizedSwing] = None
    last_bos: Optional[StructureEvent] = None
    last_choch: Optional[StructureEvent] = None
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class DealingRangeSnapshot:
    swing_high: float
    swing_low: float
    equilibrium: float
    current_zone: Optional[str]  # "PREMIUM" / "DISCOUNT" / "EQUILIBRIUM" / None (no current_price given)
    defining_timeframe: str
    source: str  # names WHICH swing pair defined this range, e.g. "structure:H1:latest_confirmed_swing_pair"


@dataclass(frozen=True)
class MarketSwingStructureResult:
    schema_version: str
    symbol: str
    analysis_time_utc: datetime
    authority: str

    timeframes: Tuple[Tuple[str, TimeframeStructureSnapshot], ...]  # ordered HTF -> LTF
    active_dealing_range: Optional[DealingRangeSnapshot]
    liquidity_context: Tuple[Any, ...]
    imbalance_context: Tuple[Any, ...]
    structure_events: Tuple[StructureEvent, ...]
    mtf_alignment: str

    provenance: Any = field(default_factory=dict)
    status: str = "OK"
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
