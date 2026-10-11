"""FIVE_SKILL_ASSISTANT_RUNTIME_V1 request/result contracts.

Distinct from assistant/models.py's MarketContext/StrategyResult/AssistantDecision,
which are ASSISTANT_RUNTIME_V1's strategy-execution-path shapes (require a
strategy_id, account identity, demo/live authority). This module is the OTHER,
primary path: generic market analysis that needs no registered strategy at all --
see docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md's "Strategy vs. capability boundary" and
docs/specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md.

Nothing here decides a trade. `FiveSkillAnalysisResult` composes each capability's own
structured result unchanged (StructureResult, ZoneQueryResult, LiquidityResult,
EntryConfirmationResult, TradeManagementResult) rather than flattening/copying their
fields -- each capability keeps its own authority.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Optional, Tuple

from entry_confirmation.models import ALL_CONFIRMATIONS

if TYPE_CHECKING:
    # Type-only: avoids assistant/analysis_models.py importing liquidity/supply_demand/
    # trade_management at runtime, which re-enters this module mid-init via
    # liquidity -> supply_demand -> assistant (supply_demand/native_zones.py imports
    # assistant.market_data). Safe because `from __future__ import annotations` (above)
    # makes every annotation in this file a lazy string, never evaluated at class-
    # definition time -- unlike ALL_CONFIRMATIONS above, which is a real default value.
    from entry_confirmation.models import EntryConfirmationResult
    from liquidity import LiquidityResult
    from market_structure import StructureResult
    from mt5.symbol_resolver import SymbolMeta
    from supply_demand import ValidatedOrderBlock, ZoneQueryResult
    from trade_management import ManagementPolicy, TradeManagementResult

# Skill identifiers -- match the logical taxonomy in .claude/skills/SKILL_REGISTRY.yaml
# and docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md's "Assistant skill taxonomy" verbatim.
SKILL_MARKET_STRUCTURE = "market-structure"
SKILL_SUPPLY_DEMAND = "supply-demand"
SKILL_LIQUIDITY = "liquidity"
SKILL_ENTRY_CONFIRMATION = "entry-confirmation"
SKILL_TRADE_MANAGEMENT = "trade-management"  # gated by candidate presence, not requested_skills -- see runtime

# Requestable via AssistantAnalysisRequest.requested_skills (trade-management is never
# requested this way -- it activates purely from `candidate` being supplied, per the
# mission's "Trade Management depends on whether a candidate trade exists").
REQUESTABLE_MARKET_SKILLS: Tuple[str, ...] = (
    SKILL_MARKET_STRUCTURE, SKILL_SUPPLY_DEMAND, SKILL_LIQUIDITY, SKILL_ENTRY_CONFIRMATION,
)

# Per-skill status vocabulary. Reuses each capability's own "OK"/"VALID"/status strings
# internally; these are the runtime-level summary states layered on top.
SKILL_READY = "READY"
SKILL_PARTIAL = "PARTIAL"
SKILL_NOT_REQUESTED = "NOT_REQUESTED"
SKILL_NO_CANDIDATE = "NO_CANDIDATE"
SKILL_UNAVAILABLE = "UNAVAILABLE"
SKILL_BLOCKED = "BLOCKED"

# Overall runtime status
OVERALL_READY = "READY"
OVERALL_PARTIAL = "PARTIAL"
OVERALL_BLOCKED = "BLOCKED"

# Market-context-level runtime error (blocks all downstream skills)
CONTEXT_UNAVAILABLE = "MARKET_CONTEXT_UNAVAILABLE"


@dataclass(frozen=True)
class TradeCandidate:
    """A manually- or strategy-supplied proposed trade. Optional on every
    AssistantAnalysisRequest -- its absence is the normal case for generic analysis."""

    direction: str  # "LONG" / "SHORT"
    entry_price: float
    stop_loss: float
    take_profit: Optional[float] = None
    risk_percent: Optional[float] = None
    risk_amount: Optional[float] = None
    equity: Optional[float] = None
    symbol_meta: Optional[SymbolMeta] = None
    current_price: Optional[float] = None  # overrides the AnalysisContext's live bid, if supplied
    management_policy: Optional[ManagementPolicy] = None


@dataclass(frozen=True)
class AssistantAnalysisRequest:
    symbol: str
    timeframe: str = "M15"
    requested_skills: Tuple[str, ...] = REQUESTABLE_MARKET_SKILLS
    requested_confirmations: Tuple[str, ...] = ALL_CONFIRMATIONS
    candidate: Optional[TradeCandidate] = None


@dataclass(frozen=True)
class SupplyDemandBundle:
    """Thin composition of supply_demand's own query functions -- not a new capability
    result type. validated_order_blocks uses AG_ORDER_BLOCK_V1 (validated_order_blocks_for),
    not the raw smc.ob() candidates, per the frozen contract's own recommendation.

    validated_order_blocks_for() returns a plain List[ValidatedOrderBlock] (verified
    against supply_demand/analyzer.py, not assumed to mirror order_blocks_for()'s/
    fair_value_gaps_for()'s ZoneQueryResult shape -- it does not) and fails silently to
    an empty list on a MarketDataError, with no status/reason_code of its own. This
    bundle therefore carries the tuple directly; skill_statuses' READY/PARTIAL judgment
    for supply-demand is driven by `fair_value_gaps`'s own status instead -- see
    docs/specs/FIVE_SKILL_ASSISTANT_RUNTIME_V1_SPEC.md's "Known limitations"."""

    validated_order_blocks: Tuple[ValidatedOrderBlock, ...]
    fair_value_gaps: ZoneQueryResult


# --- Execution Authority Restructure (2026-08-28) -------------------------------------
# TradeProposal wraps a TradeCandidate with the identity/lifecycle fields needed to
# execute it later on explicit user command -- see assistant/commands.py::build_proposal
# and execution/executor.py's ASSISTANT_PROPOSAL path. It never re-declares
# TradeCandidate's own direction/entry/SL/TP/sizing fields.

# Kept minimal per AG_ASSISTANT_PROPOSAL_EXECUTION_V1 -- not a full workflow engine.
# Only the transitions actually driven by code below exist as real states; AUTHORIZED/
# EXECUTING/CANCELLED/CLOSED were considered and deliberately not added -- nothing in
# this pass needs them, and inventing unused states would be scope creep.
PROPOSAL_READY = "READY_FOR_USER_DECISION"
PROPOSAL_EXPIRED = "EXPIRED"
PROPOSAL_EXECUTED = "EXECUTED"
PROPOSAL_REJECTED = "REJECTED"
PROPOSAL_STALE = "STALE"


@dataclass(frozen=True)
class TradeProposal:
    """Assistant-generated, not yet executed. Executing it requires a separate,
    explicit user command -- see execution/models.py::ExecutionSource.ASSISTANT_PROPOSAL.
    Producing this dataclass is never itself execution authorization."""

    proposal_id: str
    created_at: datetime
    expires_at: datetime
    symbol: str
    timeframe: str
    candidate: TradeCandidate
    analysis_summary: str = ""
    evidence: Tuple[str, ...] = field(default_factory=tuple)
    status: str = PROPOSAL_READY


@dataclass(frozen=True)
class FiveSkillAnalysisResult:
    symbol: str
    timeframe: str
    timestamp_utc: datetime

    market_context_status: str

    structure: Optional[StructureResult] = None
    supply_demand: Optional[SupplyDemandBundle] = None
    liquidity: Optional[LiquidityResult] = None
    entry_confirmation: Optional[EntryConfirmationResult] = None
    trade_management: Optional[TradeManagementResult] = None

    skill_statuses: Dict[str, str] = field(default_factory=dict)
    overall_status: str = OVERALL_BLOCKED
    limitations: Tuple[str, ...] = field(default_factory=tuple)
    errors: Tuple[str, ...] = field(default_factory=tuple)
