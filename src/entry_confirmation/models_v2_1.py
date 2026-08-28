"""AG_ENTRY_CONFIRMATION_V2_1 shapes -- additive to V1 (models.py) and V2 (models_v2.py).
Freezes SMC_SWEEP_SHIFT_ARRAY_V1: liquidity sweep -> valid structural pivot -> body-close
CHoCH/MSS -> displacement -> FVG/OB entry array, with an explicit quality axis that keeps
"a structure event fired" separate from "this was a high-quality execution setup".

Nothing here mutates V1/V2 dataclasses or their entry points. See
docs/specs/ENTRY_CONFIRMATION_V2_1_SPEC.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional, Tuple

if TYPE_CHECKING:
    from entry_confirmation.models import DisplacementEvidence, StructureAlignment
    from entry_confirmation.models_v2 import GapContext, TypedEvent

CONTRACT_VERSION_V2_1 = "AG_ENTRY_CONFIRMATION_V2_1"


class PivotRole(str, Enum):
    PROTECTED_HIGH = "PROTECTED_HIGH"
    PROTECTED_LOW = "PROTECTED_LOW"
    EXTERNAL_SWING = "EXTERNAL_SWING"
    INTERNAL_SWING = "INTERNAL_SWING"
    MICRO_PIVOT = "MICRO_PIVOT"
    UNRESOLVED = "UNRESOLVED"


class StructureShiftQualityStatus(str, Enum):
    VALID_STRONG = "VALID_STRONG"
    VALID_WEAK = "VALID_WEAK"
    FAKEOUT_WICK = "FAKEOUT_WICK"
    INVALID_PIVOT = "INVALID_PIVOT"
    WRONG_SEQUENCE = "WRONG_SEQUENCE"
    MID_RANGE_LOW_CONTEXT = "MID_RANGE_LOW_CONTEXT"
    INDETERMINATE = "INDETERMINATE"


class SetupFamily(str, Enum):
    REVERSAL = "REVERSAL"
    CONTINUATION = "CONTINUATION"
    UNRESOLVED = "UNRESOLVED"


class EntryArrayType(str, Enum):
    FVG = "FVG"
    ORDER_BLOCK = "ORDER_BLOCK"
    FVG_AND_ORDER_BLOCK = "FVG_AND_ORDER_BLOCK"
    NONE = "NONE"
    UNRESOLVED = "UNRESOLVED"


class EntryMethodV21(str, Enum):
    FVG_BOUNDARY = "FVG_BOUNDARY"
    FVG_MIDPOINT = "FVG_MIDPOINT"
    ORDER_BLOCK_BOUNDARY = "ORDER_BLOCK_BOUNDARY"
    ORDER_BLOCK_ZONE = "ORDER_BLOCK_ZONE"
    FVG_OB_CONFLUENCE = "FVG_OB_CONFLUENCE"
    MARKET_TOUCH = "MARKET_TOUCH"
    UNRESOLVED = "UNRESOLVED"


class ConfluenceRelation(str, Enum):
    OVERLAP = "OVERLAP"
    PARTIAL_OVERLAP = "PARTIAL_OVERLAP"
    SAME_LEG_NO_OVERLAP = "SAME_LEG_NO_OVERLAP"
    UNRELATED = "UNRELATED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class PivotContext:
    pivot_price: Optional[float] = None
    pivot_time: Optional[datetime] = None
    pivot_timeframe: Optional[str] = None
    pivot_type: Optional[str] = None  # "SWING_HIGH" / "SWING_LOW"
    pivot_role: str = PivotRole.UNRESOLVED.value
    reason: Optional[str] = None


@dataclass(frozen=True)
class StructureShiftQuality:
    body_close_beyond_pivot: Optional[bool] = None
    wick_only_break: Optional[bool] = None
    pivot_valid: Optional[bool] = None
    post_sweep: Optional[bool] = None
    displacement_qualified: Optional[bool] = None
    fvg_created: Optional[bool] = None
    context_valid: Optional[bool] = None
    status: str = StructureShiftQualityStatus.INDETERMINATE.value
    reason: Optional[str] = None


@dataclass(frozen=True)
class DisplacementLeg:
    direction: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    qualification: Optional[str] = None  # AG_ENTRY_DISPLACEMENT_V1 status, reused verbatim
    associated_structure_event_time: Optional[datetime] = None
    associated_fvg_origin_time: Optional[datetime] = None
    associated_ob_origin_time: Optional[datetime] = None


@dataclass(frozen=True)
class EntryArrayContext:
    entry_array_type: str = EntryArrayType.UNRESOLVED.value
    entry_method: str = EntryMethodV21.UNRESOLVED.value
    entry_candidates: Tuple[str, ...] = field(default_factory=tuple)
    entry_reference: Optional[float] = None
    entry_status: str = "UNRESOLVED"  # WAITING_ENTRY_PRICE / ENTRY_REFERENCE_AVAILABLE / UNRESOLVED
    confluence: str = ConfluenceRelation.UNRESOLVED.value
    structural_invalidation_candidates: Tuple[float, ...] = field(default_factory=tuple)
    target_liquidity_reference: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class SMCSweepShiftArrayResult:
    version: str = CONTRACT_VERSION_V2_1
    symbol: str = ""
    timeframe: str = ""
    evaluation_time: Optional[datetime] = None

    setup_family: str = SetupFamily.UNRESOLVED.value

    liquidity_reference: Optional[float] = None
    liquidity_side: Optional[str] = None
    liquidity_state: Optional[str] = None
    poi_reference: Optional[str] = None

    sweep_event: Optional[str] = None  # LiquidityStatus value, copied verbatim
    reclaim_event: Optional[str] = None
    sweep_candle_time: Optional[datetime] = None

    structural_pivot: PivotContext = field(default_factory=PivotContext)
    structure_event: Optional["StructureAlignment"] = None  # V1 primitive, embedded verbatim
    structure_break_candle_time: Optional[datetime] = None
    structure_quality: StructureShiftQuality = field(default_factory=StructureShiftQuality)

    displacement: Optional["DisplacementEvidence"] = None  # V1 primitive, embedded verbatim
    displacement_leg: DisplacementLeg = field(default_factory=DisplacementLeg)

    associated_fvg: Optional["GapContext"] = None  # V2 primitive, embedded verbatim
    associated_order_block: Optional[str] = None  # description/id string, evidence only

    premium_discount_context: Optional[str] = None  # "PREMIUM" / "DISCOUNT" / "EQUILIBRIUM" / None

    entry_array: EntryArrayContext = field(default_factory=EntryArrayContext)

    event_sequence: Tuple["TypedEvent", ...] = field(default_factory=tuple)

    status: str = "WAITING_SWEEP"
    # WAITING_SWEEP / WAITING_STRUCTURE_SHIFT / FAKEOUT_WICK / WAITING_ENTRY_PRICE /
    # ENTRY_REFERENCE_AVAILABLE / INVALIDATED / NOT_CONFIRMED / INDETERMINATE
    aggregation_status: str = "INDETERMINATE"  # CONFIRMED / PARTIAL / NOT_CONFIRMED / INDETERMINATE
    quality_status: str = StructureShiftQualityStatus.INDETERMINATE.value

    evidence: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    unresolved_policies: Tuple[str, ...] = field(default_factory=tuple)
    reason: Optional[str] = None
