"""AG_CANONICAL_PROPOSAL_V1 -- the strategy-neutral proposal envelope frozen by
Workstream 0 / M1A (docs/plans/BEST_MONEY_MAKING_PATHS_AND_TICKET_DELIVERY_ACTION_PLAN_V1.md,
"Workstream 0 -- Freeze the common proposal contract").

This module normalizes signed strategy/candidate outputs into one shape. It contains NO
detection logic (nothing here decides whether a setup exists) and NO execution imports
(nothing here can reach a broker order path) -- see
tests/test_proposal_envelope_execution_boundary.py for the static/behavioral proof.

Three independent dimensions (never share one enum, never inferred from one another):

  watcher_state         -- how far a research occurrence has progressed toward a
                            qualified setup. Orthogonal to whether a strategy exists.
  proposal_state        -- whether a compatible strategy turned that occurrence into a
                            complete, informational trade plan.
  execution_authority    -- whether anything is allowed to act on that plan. A
                            PROPOSAL_READY envelope may (and typically does, pre-M2)
                            carry execution_authority == NONE.

A missing REQUIRED proposal field must map proposal_state to BLOCKED -- never a partial
PROPOSAL_READY (see adapters.map_missing_field_to_blocked below and each adapter's own
"missing required field" tests). The normalizer may rename/reshape a source field; it may
never upgrade a state or synthesize a value the source strategy never produced.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

SCHEMA_VERSION = "AG_CANONICAL_PROPOSAL_V1"

# --------------------------------------------------------------------------- watcher_state
WATCHER_SCANNING = "SCANNING"
WATCHER_CONTEXT_IDENTIFIED = "CONTEXT_IDENTIFIED"
WATCHER_LIQUIDITY_APPROACH = "LIQUIDITY_APPROACH"
WATCHER_POI_APPROACH = "POI_APPROACH"
WATCHER_LIQUIDITY_SWEPT = "LIQUIDITY_SWEPT"
WATCHER_STRUCTURE_CONFIRMING = "STRUCTURE_CONFIRMING"
WATCHER_SETUP_QUALIFIED = "SETUP_QUALIFIED"
WATCHER_INVALIDATED = "INVALIDATED"
WATCHER_EXPIRED = "EXPIRED"
WATCHER_DATA_BLOCKED = "DATA_BLOCKED"

WATCHER_STATES = frozenset({
    WATCHER_SCANNING, WATCHER_CONTEXT_IDENTIFIED, WATCHER_LIQUIDITY_APPROACH,
    WATCHER_POI_APPROACH, WATCHER_LIQUIDITY_SWEPT, WATCHER_STRUCTURE_CONFIRMING,
    WATCHER_SETUP_QUALIFIED, WATCHER_INVALIDATED, WATCHER_EXPIRED, WATCHER_DATA_BLOCKED,
})

# -------------------------------------------------------------------------- proposal_state
PROPOSAL_NOT_EVALUATED = "NOT_EVALUATED"
PROPOSAL_NO_TRADE = "NO_TRADE"
PROPOSAL_INCOMPLETE = "INCOMPLETE"
PROPOSAL_STRATEGY_UNMATCHED = "STRATEGY_UNMATCHED"
PROPOSAL_READY = "PROPOSAL_READY"
PROPOSAL_INVALIDATED = "PROPOSAL_INVALIDATED"
PROPOSAL_EXPIRED = "PROPOSAL_EXPIRED"
PROPOSAL_BLOCKED = "BLOCKED"

PROPOSAL_STATES = frozenset({
    PROPOSAL_NOT_EVALUATED, PROPOSAL_NO_TRADE, PROPOSAL_INCOMPLETE, PROPOSAL_STRATEGY_UNMATCHED,
    PROPOSAL_READY, PROPOSAL_INVALIDATED, PROPOSAL_EXPIRED, PROPOSAL_BLOCKED,
})

# --------------------------------------------------------------------- execution_authority
AUTHORITY_NONE = "NONE"
AUTHORITY_DEMO_ELIGIBLE = "DEMO_ELIGIBLE"
AUTHORITY_DEMO_AUTHORIZED = "DEMO_AUTHORIZED"
AUTHORITY_LIVE_AUTHORIZED = "LIVE_AUTHORIZED"

EXECUTION_AUTHORITIES = frozenset({
    AUTHORITY_NONE, AUTHORITY_DEMO_ELIGIBLE, AUTHORITY_DEMO_AUTHORIZED, AUTHORITY_LIVE_AUTHORIZED,
})

# ------------------------------------------------------------------------------ cost status
COST_NOT_INCLUDED = "NOT_INCLUDED"
COST_ITEMIZED = "ITEMIZED"
COST_MIXED = "MIXED"
COST_NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class CostAssumptions:
    """Itemized cost inputs. Every field is `None` (never silently 0.0) when the source
    strategy/adapter has not modeled it -- `status` is the single explicit summary a
    caller must render instead of assuming a missing itemized field means zero cost."""

    spread: Optional[float] = None
    commission: Optional[float] = None
    slippage: Optional[float] = None
    swap_or_funding: Optional[float] = None
    status: str = COST_NOT_INCLUDED  # COST_NOT_INCLUDED / COST_ITEMIZED / COST_MIXED / COST_NOT_APPLICABLE
    missing_fields: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class WatcherOccurrenceTimestamps:
    """Frozen per watcher occurrence (Workstream 0 deliverable). Every field is the
    strategy/candidate's own authoritative closed-evidence timestamp -- never wall-clock
    "now" masquerading as evidence, and never invented when the source has none (in which
    case the field stays None, not a synthesized value)."""

    detected_at: Optional[str] = None  # ISO8601 -- when the occurrence was first recognized
    state_entered_at: Optional[str] = None  # ISO8601 -- when the CURRENT watcher_state began
    last_evaluated_at: Optional[str] = None  # ISO8601 -- most recent deterministic evaluation
    evidence_candle_close: Optional[str] = None  # ISO8601 -- closed-candle boundary supporting the state
    expires_at: Optional[str] = None  # ISO8601 -- strategy-/candidate-owned expiry, when defined
    evidence_complete: Tuple[str, ...] = field(default_factory=tuple)  # immutable evidence already satisfied
    next_required_evidence: Tuple[str, ...] = field(default_factory=tuple)  # signed evidence still required


@dataclass(frozen=True)
class DataProvenance:
    """Data-quality/freshness evidence backing the envelope -- never invented; a source
    adapter that has no provenance concept must leave these None/empty rather than guess."""

    source: Optional[str] = None  # e.g. "MT5", "BYBIT", broker/venue-native data source id
    data_version: Optional[str] = None
    complete_candle_evidence: bool = False
    freshness_note: Optional[str] = None


@dataclass(frozen=True)
class CanonicalProposal:
    """AG_CANONICAL_PROPOSAL_V1. See module docstring for the three independent-dimension
    rule. Constructing this object never itself decides a trade -- every field must be
    traceable to `source_module`/`source_record_id`, exactly like
    performance.models.ResolvedTradeSample's own provenance discipline."""

    schema_version: str = SCHEMA_VERSION

    # ---- identity -----------------------------------------------------------------
    proposal_envelope_id: str = ""
    strategy_id: str = ""
    strategy_version: str = ""
    application_release: Optional[str] = None

    # ---- market / venue -------------------------------------------------------------
    market: str = ""  # e.g. "FX", "CRYPTO", "METALS"
    venue: Optional[str] = None  # e.g. "MT5_BROKER", "BYBIT"
    contract_type: Optional[str] = None  # e.g. "SPOT_FX", "CRYPTO_PERP"
    symbol: str = ""

    # ---- three independent dimensions ------------------------------------------------
    watcher_state: str = WATCHER_SCANNING
    proposal_state: str = PROPOSAL_NOT_EVALUATED
    execution_authority: str = AUTHORITY_NONE

    # ---- trade plan (only ever populated when strategy-owned) -----------------------
    direction: Optional[str] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    targets: Tuple[float, ...] = field(default_factory=tuple)
    expected_R: Optional[float] = None
    plan_expires_at: Optional[str] = None  # ISO8601

    # ---- evidence ---------------------------------------------------------------------
    setup_evidence: Dict[str, Any] = field(default_factory=dict)
    market_context_evidence: Dict[str, Any] = field(default_factory=dict)
    liquidity_evidence: Dict[str, Any] = field(default_factory=dict)
    confirmation_evidence: Dict[str, Any] = field(default_factory=dict)

    # ---- data provenance ----------------------------------------------------------
    data_provenance: DataProvenance = field(default_factory=DataProvenance)

    # ---- costs --------------------------------------------------------------------
    cost_assumptions: CostAssumptions = field(default_factory=CostAssumptions)

    # ---- watcher occurrence timestamps ---------------------------------------------
    timestamps: WatcherOccurrenceTimestamps = field(default_factory=WatcherOccurrenceTimestamps)

    # ---- correction / version linkage -------------------------------------------------
    correction_of: Optional[str] = None  # proposal_envelope_id this record supersedes, if any
    version: int = 1  # monotonically increasing per proposal_envelope_id lineage

    # ---- provenance back to the source object this was normalized from ---------------
    source_module: str = ""  # e.g. "proposals.models.SMCTradeProposal"
    source_record_id: str = ""  # the source object's own identity (setup_id / decision_id / occurrence_id)
    reasons: Tuple[str, ...] = field(default_factory=tuple)  # human-auditable why proposal_state landed here


def blocked_envelope(*, source_module: str, source_record_id: str, symbol: str = "",
                      strategy_id: str = "", strategy_version: str = "",
                      reasons: Tuple[str, ...] = ()) -> CanonicalProposal:
    """The one, single way an adapter may report a missing required field: proposal_state
    is BLOCKED, never a partial PROPOSAL_READY (Workstream 0's own exit rule). Centralized
    here so no adapter can independently invent a different "partial" state."""
    return CanonicalProposal(
        proposal_envelope_id=f"BLOCKED:{source_module}:{source_record_id}",
        strategy_id=strategy_id, strategy_version=strategy_version,
        symbol=symbol, proposal_state=PROPOSAL_BLOCKED,
        source_module=source_module, source_record_id=source_record_id, reasons=reasons,
    )
