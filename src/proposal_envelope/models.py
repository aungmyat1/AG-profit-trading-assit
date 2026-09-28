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

# V1.2 (AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2): NOT a new proposal_state --
# PROPOSAL_STATES is a frozen contract (see
# tests/test_proposal_envelope_models.py::test_proposal_states_match_source_plan_vocabulary_exactly)
# and is never widened. A watcher occurrence with genuine market evidence but incomplete
# deterministic trade geometry (e.g. ST_LARGE_SMC_V1 states short of RESEARCH_QUALIFIED)
# uses the existing PROPOSAL_INCOMPLETE state, tagged with this evidence-level marker in
# setup_evidence["platform_state"] so a reader can distinguish "no strategy decision
# exists yet" from "a strategy decision exists but a required field is missing" without
# a second competing state vocabulary.
PLATFORM_STATE_WATCH_DETECTED = "WATCH_DETECTED"

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
    # WP6 (AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1): the WP1 market_data_mode/asof/
    # fingerprint contract (strategy_contract/market_snapshot.py::MarketSnapshot),
    # propagated here so the formation gate can enforce REAL-mode-only proposal
    # formation without adapters inventing a second mode concept. All three fields are
    # additive/optional -- None means "the caller supplied no MarketSnapshot", never
    # "assume REAL".
    market_data_mode: Optional[str] = None
    market_data_asof: Optional[str] = None  # ISO8601, mirrors MarketSnapshot.market_data_asof
    market_data_fingerprint: Optional[str] = None


@dataclass(frozen=True)
class CanonicalProposal:
    """AG_CANONICAL_PROPOSAL_V1. See module docstring for the three independent-dimension
    rule. Constructing this object never itself decides a trade -- every field must be
    traceable to `source_module`/`source_record_id`, exactly like
    performance.models.ResolvedTradeSample's own provenance discipline."""

    schema_version: str = SCHEMA_VERSION

    # ---- identity -----------------------------------------------------------------
    proposal_envelope_id: str = ""
    identity_version: Optional[str] = None  # forward-only identity version stamp for new
    # proposal records; legacy records remain byte-identical and never reattributed.
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

    # ---- code/config identity (WP11A, AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1) --------
    # All three optional/None-default, exactly like every other provenance field in this
    # module: populated only from an authoritative existing source, never fabricated.
    config_hash: Optional[str] = None  # e.g. post_asian_pilot.fingerprint.fingerprint()
    # over the strategy's own YAML config -- identifies WHICH config produced this proposal
    engine_release: Optional[str] = None  # e.g. the release_id already loaded from the
    # canonical release config (config/releases/*.yaml) -- identifies WHICH release build
    git_commit: Optional[str] = None  # NOT_AVAILABLE as of WP11A: no authoritative runtime
    # producer exists anywhere in this repo (checked: every existing git_commit field in
    # src/ is itself an unpopulated passthrough). Left None; a future provenance task may
    # establish one. Never a subprocess git call, CI guess, or hardcoded value.

    # ---- governance/lifecycle (AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2) ----
    # Additive only -- every existing adapter (fx/btc/large_smc) keeps producing valid
    # records unchanged, since every field here defaults to the same fail-closed value a
    # pre-V1.2 caller already implied structurally (proposal_only/no execution authority).
    # None of these are promotion decisions: they are read from existing authorities
    # (validation_framework.lifecycle_registry, strategies/registry.yaml, the strategy's
    # own YAML) by proposal_envelope.strategy_authority.resolve_strategy_authority, never
    # invented or inferred here.
    economic_edge_established: bool = False  # no such authority/field exists anywhere in
    # this repo to read a True value from -- stays False until one is established.
    demo_eligible: bool = False
    demo_authorized: bool = False
    live_authorized: bool = False
    proposal_only: bool = True
    execution_eligible: bool = False  # mirrors src/api/app.py's own hardcoded-False
    # execution_eligible on CanonicalProposalResponse -- this field makes that same
    # invariant visible on the persisted envelope itself, not just the API DTO.
    broker_mutation_blocked: bool = True
    lifecycle_stage: Optional[str] = None  # from config/governance/strategy_lifecycle.yaml
    # via lifecycle_registry.get_lifecycle_stage() -- None only if that registry has no
    # entry for this strategy_id/version (fail-closed absence, never guessed).


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
