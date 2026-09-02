"""ST_LARGE_SMC_V1 research-decision contract (RESEARCH_ONLY_FUNNEL_V1 phase).

`LargeSMCResearchDecision` is the engine's only output shape -- one per composed E*M
combination (see engine.py's module docstring for why this is a tuple, never a single
"selected" decision). It carries strategy identity explicitly (strategy_id/version) so
it is never mistaken for the shared, strategy-agnostic `SMCEntryCombinationResult` the
live SMC_CONDITIONAL_ENTRY_V2 watcher also produces from the same underlying M-models.

Decision states deliberately exclude an actionable `READY` (per the owner's explicit
research-safety instruction: RESEARCH_QUALIFIED is the ceiling while
status=RESEARCH_DRAFT, never an actionable READY). `RESEARCH_QUALIFIED` is defined here
but -- honestly, given the current unsigned state of C10 (broker stop) -- can never
actually be reached by engine.py this phase; every candidate that would otherwise
qualify resolves to BLOCKED instead. See engine.py.

Pending-entry expiry (OUTCOME_LIFECYCLE_V1 phase, 2026-09-02) is RESOLVED_BY_REUSE, not
unsigned: `historical_replay/fill_simulator.py` already establishes, for this exact E/M
pipeline, that no time-based expiry exists -- a pending entry is terminal only via FILL
or structural INVALIDATION; `UNFILLED_AS_OF_DATA_END` is a data-boundary artifact, never
a fabricated strategy state. See `pending_entry.py`. Only C10 (broker stop) still blocks
an otherwise-qualifying candidate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional, Tuple

STRATEGY_ID = "ST_LARGE_SMC_V1"
ENGINE_VERSION = "LARGE_SMC_RESEARCH_ENGINE_V1"


class LargeSMCDecisionState(str, Enum):
    """No READY. RESEARCH_QUALIFIED is the actionable ceiling under RESEARCH_DRAFT, and
    -- honestly -- currently unreachable (see module docstring)."""

    RESEARCH_QUALIFIED = "RESEARCH_QUALIFIED"
    WATCH = "WATCH"
    NO_TRADE = "NO_TRADE"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"
    BLOCKED = "BLOCKED"
    DATA_ERROR = "DATA_ERROR"


# Reason codes this engine actually emits -- never invented ad hoc at call sites.
REASON_UNSIGNED_C10_BROKER_STOP = "UNSIGNED_CONTRACT:C10_BROKER_STOP"
# Retained for provenance only -- pending-entry expiry is RESOLVED_BY_REUSE as of
# OUTCOME_LIFECYCLE_V1 (see module docstring); no longer emitted by engine.py.
REASON_UNSIGNED_PENDING_ENTRY_EXPIRY = "UNSIGNED_CONTRACT:PENDING_ENTRY_EXPIRY"
REASON_REJECT_NO_TARGET = "REJECT_NO_TARGET"
REASON_SYMBOL_NOT_IN_FROZEN_UNIVERSE = "SYMBOL_NOT_IN_FROZEN_UNIVERSE"
REASON_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class LargeSMCResearchDecision:
    strategy_id: str = STRATEGY_ID
    strategy_version: str = ""
    engine_version: str = ENGINE_VERSION

    symbol: str = ""
    evaluation_timestamp: Optional[datetime] = None

    entry_condition: Optional[str] = None  # "E1"/"E2"/"E3"
    maneuver: Optional[str] = None  # "M1"/"M2"/"M3"
    combination: Optional[str] = None  # "E1M1".."E3M3"
    direction: Optional[str] = None

    # Identity (C14/C14B, reused verbatim -- see proposals/identity.py,
    # proposals/occurrence_identity.py). setup_family_id spans multiple eligibility
    # intervals; candidate_occurrence_id is the single-occurrence identity.
    event_id: Optional[str] = None
    setup_family_id: Optional[str] = None
    eligibility_interval_id: Optional[str] = None
    m_candidate_source_id: Optional[str] = None
    candidate_occurrence_id: Optional[str] = None

    entry_array: Optional[str] = None
    entry_price: Optional[float] = None
    # Entry-array price range when the underlying M-model exposes one (M1's FVG/OB
    # bounds, M2's zone bounds) -- reuses proposals.gate._entry_range(m_result)
    # verbatim, the same helper historical_replay.orchestrator.SetupLedgerRow already
    # uses. None/None for M3 (single entry_level, no range) -- see that helper's own
    # docstring; never fabricated.
    entry_low: Optional[float] = None
    entry_high: Optional[float] = None

    structural_invalidation_price: Optional[float] = None
    structural_invalidation_source_type: Optional[str] = None
    structural_invalidation_reason: Optional[str] = None
    structural_invalidation_trigger: Optional[str] = None

    # C11 HYBRID_WITH_STRUCTURAL_FALLBACK target fields -- see target_model.py.
    target_price: Optional[float] = None
    target_tier: Optional[str] = None  # "PRIMARY_EXTERNAL_LIQUIDITY" / "FALLBACK_M5_SWING"
    target_type: Optional[str] = None
    target_source: Optional[str] = None
    target_source_id: Optional[str] = None
    target_side: Optional[str] = None
    target_status_at_selection: Optional[str] = None
    target_selected_at: Optional[datetime] = None  # decision_timestamp -- STATIC, selected once
    target_anchor_price: Optional[float] = None
    target_anchor_source: str = "SELECTED_M_MODEL_CANDIDATE_ENTRY_PRICE"
    target_evidence_timestamp: Optional[datetime] = None

    # C10 -- always None this phase; UNSIGNED_CONTRACT:C10_BROKER_STOP is carried in
    # reason_codes whenever a candidate would otherwise need one.
    simulated_broker_stop: Optional[float] = None

    # C12 (E-context eligibility, distinct from pending-entry lifecycle below).
    e_context_eligibility_end: Optional[datetime] = None  # C12, reused (is_eligible_at)
    # RESOLVED_BY_REUSE (OUTCOME_LIFECYCLE_V1): always None by construction -- no
    # time-based pending-entry expiry exists (see module docstring). A candidate's
    # pending-entry fate is FILLED / INVALIDATED_BEFORE_FILL / UNFILLED_AS_OF_DATA_END /
    # INTRABAR_AMBIGUOUS / NO_ENTRY_CONTRACT -- see pending_entry.PendingEntryOutcome,
    # computed separately (never inline here, to keep PRE_OUTCOME_COUNTS unchanged).
    pending_entry_expiry: Optional[datetime] = None

    state: str = LargeSMCDecisionState.WATCH.value
    missing_conditions: Tuple[str, ...] = field(default_factory=tuple)
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    data_quality_state: str = "OK"  # "OK" / "DATA_ERROR"

    evidence: Dict[str, Any] = field(default_factory=dict)
