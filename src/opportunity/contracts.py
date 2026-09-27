"""AG V2 Opportunity Finder core contracts (P3/P4).

Additive only. Reuses existing canonical authorities rather than duplicating them:

- MarketSnapshot (strategy_contract.market_snapshot) remains market-truth authority.
  MarketEvent here is a thin deterministic event wrapper around it -- see events.py.
- CanonicalProposal (proposal_envelope.models) remains the canonical persisted
  proposal. OpportunityCandidate is upstream of it and is never a substitute.
- TradeIntent / TradeCommand (execution.models) and the legacy execution-layer
  TradeProposal (execution.adapter) remain the execution-side contracts; nothing
  here reaches or imports them (see module-level import-boundary tests).

Fail-closed rule throughout this module: a required field with no source-owned
value stays None/empty -- it is never fabricated, estimated, or defaulted to make
a candidate look more complete than the evidence supports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from .stages import validate_outcome, validate_stage

# ---------------------------------------------------------------------------
# Synthetic/replay firewall reason codes (P3 section 10)
# ---------------------------------------------------------------------------

SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE = "SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE"
REPLAY_DATA_NOT_BROKER_EXECUTABLE = "REPLAY_DATA_NOT_BROKER_EXECUTABLE"

# Mirrors strategy_contract.market_snapshot's mode constants -- kept independent
# (no import of a private symbol) since MarketEvent must describe REPLAY/SYNTHETIC
# events that never touch a MarketSnapshot-producing feed at all.
MARKET_DATA_MODE_REAL = "REAL"
MARKET_DATA_MODE_REPLAY = "REPLAY"
MARKET_DATA_MODE_SYNTHETIC = "SYNTHETIC"
VALID_MARKET_DATA_MODES = frozenset(
    {MARKET_DATA_MODE_REAL, MARKET_DATA_MODE_REPLAY, MARKET_DATA_MODE_SYNTHETIC}
)


def _require_tz_aware(name: str, value: Optional[datetime]) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware, got naive datetime")


# ---------------------------------------------------------------------------
# MarketEvent (P9)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MarketEvent:
    """Deterministic event identity wrapper. Same closed bar + same authoritative
    source must always resolve to the same `event_id`; future data at
    `bar_close_time` is architecturally impossible to represent (callers construct
    this only from already-closed evidence -- see events.py).

    Does not replace MarketSnapshot. `snapshot_fingerprint`, when the event was
    built from one, is MarketSnapshot.fingerprint verbatim.
    """

    event_id: str
    event_type: str

    symbol: str
    market: str
    venue: Optional[str]

    timeframe: str

    bar_open_time: datetime
    bar_close_time: datetime

    market_data_asof: datetime
    market_data_mode: str

    snapshot_fingerprint: Optional[str]

    source: str
    sequence_id: Optional[int] = None

    def __post_init__(self) -> None:
        if self.market_data_mode not in VALID_MARKET_DATA_MODES:
            raise ValueError(
                f"market_data_mode must be one of {sorted(VALID_MARKET_DATA_MODES)}, "
                f"got {self.market_data_mode!r}"
            )
        for name, value in (
            ("bar_open_time", self.bar_open_time),
            ("bar_close_time", self.bar_close_time),
            ("market_data_asof", self.market_data_asof),
        ):
            _require_tz_aware(name, value)
        if self.bar_close_time < self.bar_open_time:
            raise ValueError("bar_close_time cannot precede bar_open_time")
        if self.market_data_asof < self.bar_close_time:
            raise ValueError(
                "market_data_asof cannot precede bar_close_time -- future data at T "
                "is not representable"
            )


# ---------------------------------------------------------------------------
# Candidate geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateGeometry:
    """Missing source-owned geometry stays None -- never derived or invented to
    allow proposal formation. `targets` is empty, not a guessed single value,
    when the strategy has not itself produced targets yet."""

    direction: Optional[str] = None
    entry: Optional[float] = None
    invalidation: Optional[float] = None
    targets: Tuple[float, ...] = field(default_factory=tuple)
    estimated_rr: Optional[float] = None


# ---------------------------------------------------------------------------
# OpportunityCandidate (P13)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OpportunityCandidate:
    """Opportunity-domain truth only. Never authoritative for portfolio risk,
    execution decisions, strategy profitability, or Demo/Live authorization --
    those remain owned by RiskDecision/ExecutionDecision/the registry
    respectively. No `funnel_history` field on purpose (P12): history belongs in
    a transition ledger, not an ever-growing list on the candidate itself."""

    candidate_id: str
    occurrence_id: str

    strategy_id: str
    strategy_version: str
    strategy_engine_version: Optional[str]

    symbol: str
    market: str
    venue: Optional[str]
    direction: Optional[str]

    detected_at: datetime
    last_evaluated_at: datetime
    expires_at: Optional[datetime]

    stage: str
    outcome: str
    revision: int

    raw_strategy_state: Mapping[str, Any] = field(default_factory=dict)

    context_evidence: Mapping[str, Any] = field(default_factory=dict)
    setup_evidence: Mapping[str, Any] = field(default_factory=dict)
    trigger_evidence: Mapping[str, Any] = field(default_factory=dict)

    geometry: Optional[CandidateGeometry] = None

    market_data_mode: str = MARKET_DATA_MODE_REAL
    data_lineage: Optional[str] = None

    latest_transition_id: Optional[str] = None

    def __post_init__(self) -> None:
        validate_stage(self.stage)
        validate_outcome(self.outcome)
        if self.market_data_mode not in VALID_MARKET_DATA_MODES:
            raise ValueError(
                f"market_data_mode must be one of {sorted(VALID_MARKET_DATA_MODES)}, "
                f"got {self.market_data_mode!r}"
            )
        for name, value in (
            ("detected_at", self.detected_at),
            ("last_evaluated_at", self.last_evaluated_at),
            ("expires_at", self.expires_at),
        ):
            _require_tz_aware(name, value)
        if self.revision < 1:
            raise ValueError("revision must be >= 1")


# ---------------------------------------------------------------------------
# Proposal eligibility (P15)
# ---------------------------------------------------------------------------

ELIGIBILITY_ELIGIBLE = "ELIGIBLE"
ELIGIBILITY_BLOCKED = "BLOCKED"
ELIGIBILITY_INCOMPLETE = "INCOMPLETE"
VALID_ELIGIBILITY_STATES = frozenset(
    {ELIGIBILITY_ELIGIBLE, ELIGIBILITY_BLOCKED, ELIGIBILITY_INCOMPLETE}
)


@dataclass(frozen=True)
class ProposalEligibilityDecision:
    """Only ELIGIBLE may proceed to the existing proposal_envelope formation gate.
    A strategy having a meaningful research candidate (e.g. Large SMC
    raw_state=RESEARCH_QUALIFIED) never by itself implies ELIGIBLE -- research
    qualification is not translated into actionable readiness here."""

    candidate_id: str
    status: str
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.status not in VALID_ELIGIBILITY_STATES:
            raise ValueError(
                f"status must be one of {sorted(VALID_ELIGIBILITY_STATES)}, got {self.status!r}"
            )
        _require_tz_aware("evaluated_at", self.evaluated_at)


def synthetic_or_replay_block_reasons(market_data_mode: str, *, broker_bound: bool) -> Tuple[str, ...]:
    """Deterministic firewall check (P10). `broker_bound` is True only when the
    eligibility question is specifically about reaching real broker execution
    (as opposed to forming a research-only candidate)."""
    reasons = []
    if market_data_mode == MARKET_DATA_MODE_SYNTHETIC:
        reasons.append(SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE)
    if broker_bound and market_data_mode == MARKET_DATA_MODE_REPLAY:
        reasons.append(REPLAY_DATA_NOT_BROKER_EXECUTABLE)
    return tuple(reasons)


# ---------------------------------------------------------------------------
# Shared evidence-authority contracts (P16-P18)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataAuthority:
    """Typed boundary for dataset identity/lineage. A caller must not be able to
    substitute unrelated metadata and have it treated as authority -- every field
    here must trace to the dataset's own manifest/source, never inferred."""

    dataset_id: str
    symbol: str
    timeframe: str
    source: str
    content_fingerprint: Optional[str] = None
    normalization: Optional[str] = None
    coverage_start: Optional[datetime] = None
    coverage_end: Optional[datetime] = None
    lineage: Optional[str] = None
    protected_role: Optional[str] = None
    authorization_status: str = "NOT_EVALUATED"

    def __post_init__(self) -> None:
        _require_tz_aware("coverage_start", self.coverage_start)
        _require_tz_aware("coverage_end", self.coverage_end)


@dataclass(frozen=True)
class WarmupRequirement:
    """Based on actual available closed observations, not elapsed calendar time.
    Establishes the shared contract only -- does not rewrite any strategy's own
    warm-up logic (e.g. historical_replay.warmup_readiness)."""

    timeframe: str
    required_closed_bars: int
    available_closed_bars: int

    @property
    def ready(self) -> bool:
        return self.available_closed_bars >= self.required_closed_bars


@dataclass(frozen=True)
class FrictionEvidence:
    """One shared vocabulary intended for eventual reuse by SSC, Large SMC,
    session strategies, BTC/crypto strategies, risk, and execution. Never
    silently reinterprets an existing historical friction artifact -- a
    compatibility adapter must map old evidence into this shape explicitly,
    preserving the original exactly."""

    spread: Optional[float] = None
    commission: Optional[float] = None
    slippage: Optional[float] = None
    swap: Optional[float] = None
    fees: Optional[float] = None
    evidence_source: Optional[str] = None
    coverage_status: str = "NOT_EVALUATED"
    qualification_status: str = "NOT_EVALUATED"
    observed_at: Optional[datetime] = None
    evidence_refs: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_tz_aware("observed_at", self.observed_at)
