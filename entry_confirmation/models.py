"""Project-owned Entry & Confirmation shapes (ENTRY_CONFIRMATION_V1).

See entry_confirmation/contract.py for what each primitive does and does not decide.
Nothing here produces a trade decision -- see the package docstring.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from liquidity import LiquidityResult
from market_structure import StructureResult
from strategy_engine.session import Candle

RequestedConfirmation = str  # one of the DISPLACEMENT / STRUCTURE_SHIFT / LIQUIDITY_RECLAIM / REJECTION constants below

DISPLACEMENT = "displacement"
STRUCTURE_SHIFT = "structure_shift"
LIQUIDITY_RECLAIM = "liquidity_reclaim"
REJECTION = "rejection"

ALL_CONFIRMATIONS: Tuple[str, ...] = (DISPLACEMENT, STRUCTURE_SHIFT, LIQUIDITY_RECLAIM, REJECTION)


class CandidateDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


class ConfirmationState(str, Enum):
    """Per-primitive state. Deliberately not a boolean -- see ENTRY_CONFIRMATION_V1_SPEC.md
    'Status vocabulary': the assistant and any consuming strategy need to distinguish
    "evidence says no" from "evidence unavailable" from "no signed rule exists yet"."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_REQUESTED = "NOT_REQUESTED"
    UNAVAILABLE = "UNAVAILABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNSIGNED_RULE = "UNSIGNED_RULE"
    ERROR = "ERROR"


class OverallState(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIAL = "PARTIAL"
    NOT_CONFIRMED = "NOT_CONFIRMED"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class DisplacementEvidence:
    status: ConfirmationState
    direction: Optional[str] = None  # "BULLISH" / "BEARISH" / "NEUTRAL"
    candle_timestamp: Optional[datetime] = None
    body_size: Optional[float] = None
    range_size: Optional[float] = None
    body_ratio: Optional[float] = None
    close_location: Optional[float] = None
    qualification: str = "UNSIGNED_RULE"
    rule_version: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class RejectionEvidence:
    status: ConfirmationState
    direction: Optional[str] = None
    candle_timestamp: Optional[datetime] = None
    body_size: Optional[float] = None
    range_size: Optional[float] = None
    upper_wick: Optional[float] = None
    lower_wick: Optional[float] = None
    body_ratio: Optional[float] = None
    upper_wick_ratio: Optional[float] = None
    lower_wick_ratio: Optional[float] = None
    close_location: Optional[float] = None
    qualification: str = "UNSIGNED_RULE"
    rule_version: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class StructureAlignment:
    status: ConfirmationState
    candidate_direction: Optional[str] = None
    event_kind: Optional[str] = None  # e.g. "BULLISH_CHOCH" -- copied verbatim from StructurePointKind
    event_time: Optional[datetime] = None
    event_price: Optional[float] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class LiquidityAlignment:
    status: ConfirmationState
    candidate_direction: Optional[str] = None
    level_side: Optional[str] = None  # "BUY_SIDE" / "SELL_SIDE" -- copied verbatim from LiquiditySide
    level_status: Optional[str] = None  # copied verbatim from LiquidityStatus
    level_price: Optional[float] = None
    reclaim_time: Optional[datetime] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class EntryConfirmationRequest:
    symbol: str
    timeframe: str
    candidate_direction: CandidateDirection = CandidateDirection.NONE
    requested_confirmations: Tuple[str, ...] = ()

    reference_time: Optional[datetime] = None

    # Caller-supplied candle for candle-level primitives (displacement/rejection).
    # Never fetched by this package -- see contract.py "Market data reuse".
    candidate_candle: Optional[Candle] = None

    # Caller-supplied upstream results -- never recomputed by this package.
    structure_result: Optional[StructureResult] = None
    liquidity_result: Optional[LiquidityResult] = None


@dataclass(frozen=True)
class EntryConfirmationResult:
    symbol: str
    timeframe: str
    candidate_direction: str
    status: str  # "EVALUATED" or a failure reason code

    displacement: DisplacementEvidence
    structure_shift: StructureAlignment
    liquidity_reclaim: LiquidityAlignment
    rejection: RejectionEvidence

    overall_state: OverallState
    requested_confirmations: Tuple[str, ...] = field(default_factory=tuple)
    missing_requirements: Tuple[str, ...] = field(default_factory=tuple)
    rule_versions: Tuple[str, ...] = field(default_factory=tuple)
    contract_version: str = "ENTRY_CONFIRMATION_V1"
