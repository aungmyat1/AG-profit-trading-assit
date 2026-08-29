"""SMC_TRADE_PROPOSAL_V1 (spec sections 30-34): the deterministic proposal layer above
SMC_CONDITIONAL_ENTRY_V2's composer output. DETECTION (E1/E2/E3/M1/M2/M3) and PROPOSAL
are kept strictly separate (spec section 30) -- this module never redetects anything; it
only reads fields already present on `SMCEntryCombinationResult`/the underlying M-result
and formats them into a proposal, or declines to (spec section 31: no READY combination
means no proposal, not a relaxed one).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

SMC_TRADE_PROPOSAL_V1 = "SMC_TRADE_PROPOSAL_V1"

STATUS_ENTRY_CANDIDATE_READY = "ENTRY_CANDIDATE_READY"
STATUS_ENTRY_CANDIDATE_INVALIDATED = "ENTRY_CANDIDATE_INVALIDATED"

LIFECYCLE_CREATED = "CREATED"
LIFECYCLE_STILL_VALID = "STILL_VALID"
LIFECYCLE_UPDATED = "UPDATED"
LIFECYCLE_INVALIDATED = "INVALIDATED"
LIFECYCLE_EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class SMCTradeProposal:
    version: str = SMC_TRADE_PROPOSAL_V1
    proposal_id: str = ""
    setup_id: str = ""
    snapshot_id: str = ""
    snapshot_time: Optional[str] = None  # ISO string
    symbol: str = ""

    combination: str = ""  # "E1M1".."E3M3"
    entry_condition: str = ""
    maneuver: str = ""
    direction: Optional[str] = None

    reference_timeframe: Optional[str] = None
    check_timeframe: Optional[str] = None
    confirmation_timeframe: Optional[str] = None
    execution_timeframe: Optional[str] = None

    entry_type: Optional[str] = None  # e.g. "FVG" / "ORDER_BLOCK" -- from entry_array
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None
    entry_reference: Optional[float] = None  # single representative price (midpoint when a range exists)

    # Deterministic invalidation (spec sections 2-11): copied verbatim from the
    # composed combination's own invalidation_* fields, which themselves are copied
    # verbatim from the underlying M-result (entry_confirmation.invalidation) -- never
    # recomputed or invented here. `invalidation_state` is kept for backward
    # compatibility (the state name once actually triggered); the new fields carry the
    # deterministic price/source/reason/trigger whenever the M-model has one at all,
    # even before it is breached.
    invalidation_state: Optional[str] = None
    invalidation_price: Optional[float] = None
    invalidation_source_type: Optional[str] = None
    invalidation_reason: Optional[str] = None
    invalidation_trigger: Optional[str] = None

    evidence: Dict[str, Any] = field(default_factory=dict)
    missing_conditions: Tuple[str, ...] = field(default_factory=tuple)

    market_map_snapshot_id: Optional[str] = None
    status: str = STATUS_ENTRY_CANDIDATE_READY

    # Lifecycle (spec sections 13-15) -- populated by proposals.lifecycle, not by
    # generate_proposals() itself (which stays pure/stateless, see gate.py). Defaults
    # to CREATED so a caller that only ever calls generate_proposals() (no lifecycle
    # tracking) still gets an honest, non-misleading value rather than an empty string.
    lifecycle: str = LIFECYCLE_CREATED
    changed_fields: Tuple[str, ...] = field(default_factory=tuple)
