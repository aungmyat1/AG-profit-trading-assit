"""AG_ENTRY_CONFIRMATION_V2 shapes -- additive to ENTRY_CONFIRMATION_V1.

Nothing here replaces or mutates the V1 contract (models.py, engine.py); V2 wraps V1
and adds trade-idea-generation / conditional-execution context on top of it. See
docs/specs/ENTRY_CONFIRMATION_V2_SPEC.md.

Still governed by the same non-objective as V1: never a trade decision, never a lot
size, never an order_send call. Ambiguous presenter concepts are represented as
explicit UNRESOLVED/PARTIAL states with preserved evidence rather than invented rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from .models import EntryConfirmationResult

CONTRACT_VERSION_V2 = "AG_ENTRY_CONFIRMATION_V2"


class ConfirmationRoute(str, Enum):
    DAILY_GAP_REACTION = "DAILY_GAP_REACTION"
    H1_POI_REACTION = "H1_POI_REACTION"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    NONE = "NONE"
    MULTIPLE = "MULTIPLE"
    UNRESOLVED = "UNRESOLVED"


class ConfirmationModel(str, Enum):
    CHARACTER_CHANGE_WITH_INDUCEMENT = "CHARACTER_CHANGE_WITH_INDUCEMENT"
    SUPPLY_DEMAND_SHIFT = "SUPPLY_DEMAND_SHIFT"
    SWEEP_DROP_PUMP = "SWEEP_DROP_PUMP"
    NONE = "NONE"
    UNRESOLVED = "UNRESOLVED"


class EntryMethod(str, Enum):
    LAST_PULLBACK = "LAST_PULLBACK"
    GAP = "GAP"
    CURRENT_GAP = "CURRENT_GAP"
    ORDER_BLOCK = "ORDER_BLOCK"
    GAP_AND_ORDER_BLOCK = "GAP_AND_ORDER_BLOCK"
    FIFTY_PERCENT_INVERTED_GAP = "FIFTY_PERCENT_INVERTED_GAP"
    UNRESOLVED = "UNRESOLVED"


class StructuralInvalidationType(str, Enum):
    CHOCH_EXTREME_SWING = "CHOCH_EXTREME_SWING"
    M5_ORDER_BLOCK_EXTREME = "M5_ORDER_BLOCK_EXTREME"
    LIQUIDITY_SWEEP_WICK = "LIQUIDITY_SWEEP_WICK"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class DirectionalContext:
    """A1/A2 pass-through: HTF compass + next-target context. Never independently
    computed here -- see poi.py/route.py module docstrings and rule set sections 6-7."""
    status: str = "UNRESOLVED"  # "RESOLVED" / "UNRESOLVED"
    htf_direction: Optional[str] = None
    target_reference: Optional[float] = None
    target_side: Optional[str] = None
    target_status: Optional[str] = None
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


@dataclass(frozen=True)
class GapContext:
    status: str = "UNAVAILABLE"  # UNAVAILABLE / UNTOUCHED / GAP_TOUCHED / GAP_FILLED / GAP_REACTED / GAP_INVALIDATED
    gap_low: Optional[float] = None
    gap_high: Optional[float] = None
    gap_midpoint: Optional[float] = None
    reaction_time: Optional[datetime] = None
    reaction_policy: str = "PARTIAL"
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


@dataclass(frozen=True)
class InvertedGapContext:
    status: str = "UNAVAILABLE"  # UNAVAILABLE / NORMAL_GAP / INVERTED_GAP / INVALIDATED_GAP
    policy: str = "PARTIAL"
    gap_low: Optional[float] = None
    gap_high: Optional[float] = None
    gap_midpoint: Optional[float] = None
    origin_time: Optional[datetime] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class POIContext:
    status: str = "UNRESOLVED"
    # DORMANT / UNRESOLVED / WAITING_POI / POI_REACHED / WAITING_CONFIRMATION /
    # WAITING_LIQUIDITY_EVENT / INVALIDATED -- deliberately never CONFIRMED (rule 14:
    # PRICE_AT_POI != ENTRY_CONFIRMED).
    poi_type: Optional[str] = None
    poi_high: Optional[float] = None
    poi_low: Optional[float] = None
    poi_midpoint: Optional[float] = None
    poi_direction: Optional[str] = None
    poi_timeframe: Optional[str] = None
    liquidity_association: Optional[str] = None
    structure_association: Optional[str] = None
    price_action_coverage: Optional[str] = None  # "CONFIRMED" / "NOT_CONFIRMED" / "UNRESOLVED"
    mitigation_state: Optional[str] = None
    invalidation_state: Optional[str] = None
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


@dataclass(frozen=True)
class SpreadContext:
    status: str = "UNRESOLVED"  # "RESOLVED" / "UNRESOLVED"
    spread: Optional[float] = None
    alert_reference_price: Optional[float] = None
    spread_adjusted_alert_price: Optional[float] = None
    invalidation_reference_price: Optional[float] = None
    spread_adjusted_invalidation: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class TypedEvent:
    kind: str
    status: str  # PASS / FAIL / PENDING / INDETERMINATE / UNRESOLVED
    timestamp: Optional[datetime] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class RouteResult:
    route: str = ConfirmationRoute.UNRESOLVED.value
    matching_routes: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None


@dataclass(frozen=True)
class EntryGeometry:
    entry_method: str = EntryMethod.UNRESOLVED.value
    entry_candidates: Tuple[str, ...] = field(default_factory=tuple)
    entry_reference: Optional[float] = None
    status: str = "UNRESOLVED"  # WAITING_ENTRY_PRICE / ENTRY_REFERENCE_AVAILABLE / UNRESOLVED
    structural_invalidation_type: str = StructuralInvalidationType.UNRESOLVED.value
    structural_invalidation_reference: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class EntryConfirmationV2Result:
    version: str = CONTRACT_VERSION_V2
    symbol: str = ""
    timeframe: str = ""
    evaluation_time: Optional[datetime] = None

    v1: Optional["EntryConfirmationResult"] = None  # verbatim V1 result, if the caller requested one

    directional_context: DirectionalContext = field(default_factory=DirectionalContext)
    gap_context: GapContext = field(default_factory=GapContext)
    inverted_gap_context: InvertedGapContext = field(default_factory=InvertedGapContext)
    poi_context: POIContext = field(default_factory=POIContext)

    route: RouteResult = field(default_factory=RouteResult)
    confirmation_model: str = ConfirmationModel.UNRESOLVED.value
    event_sequence: Tuple[TypedEvent, ...] = field(default_factory=tuple)
    entry_geometry: EntryGeometry = field(default_factory=EntryGeometry)
    spread_context: SpreadContext = field(default_factory=SpreadContext)

    status: str = "DORMANT"
    # DORMANT / WAITING_CONTEXT / WAITING_POI / WAITING_REACTION / WAITING_CANDLE_CLOSE /
    # WAITING_CONFIRMATION / PARTIAL / CONFIRMED / WAITING_ENTRY_PRICE / INDETERMINATE

    evidence: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_policies: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None
