"""TradeTicket PREPARED_ONLY -- the owner-review read model over the existing
CanonicalProposal (Arena M5: "expose the existing CanonicalProposal as the
owner-facing TradeTicket read model").

    Opportunity -> qualify() -> evaluate_proposal_eligibility() (existing, unchanged)
      -> to_canonical_proposal() (existing, unchanged) -> prepare_sizing()
      -> TradeTicket(status=PREPARED_ONLY | PREPARED_TEST_ONLY, execution_authority=NONE)

A ticket is not a broker order. Nothing here imports execution, authorization,
ticket_delivery, owner_decision or an MT5 order/position API, and no lifecycle state
beyond PREPARED is implemented (the owner-confirm contract is declared only).

The trade plan (direction/entry/stop/targets) is read from the embedded
CanonicalProposal; the ticket adds only facts the proposal schema does not carry:
broker/server/environment, cycle, sizing, fingerprints, expiry and status.

Semantic identity: `semantic_fingerprint` hashes every ticket field except
`ticket_id` and itself. All timestamps (created_at = evaluation instant, expires_at)
are deterministic inputs, so no timestamp exclusion is needed.

CUSTOM_BUILD_REASON = NO_ACCEPTABLE_EXISTING_OR_OSS_COMPONENT (CanonicalProposal has no
broker/server/environment/cycle/sizing/instrument-fingerprint/semantic-hash fields).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from fx_opportunity.instruments import get_broker, get_instrument
from fx_opportunity.market_state import MarketState
from mt5.symbol_resolver import SymbolMeta
from opportunity.contracts import ELIGIBILITY_ELIGIBLE, OpportunityCandidate, ProposalEligibilityDecision
from opportunity.proposal_eligibility import (
    REASON_ENTRY_EQUALS_STOP,
    REASON_INVALID_STOP_GEOMETRY,
    REASON_NON_FINITE_GEOMETRY,
    evaluate_proposal_eligibility,
)
from opportunity.registry_binding import StrategyBinding
from post_asian_pilot.fingerprint import fingerprint
from proposal_envelope.adapters.opportunity_adapter import BRIDGE_VERSION, to_canonical_proposal
from proposal_envelope.models import AUTHORITY_NONE, PROPOSAL_READY, CanonicalProposal
from proposal_envelope.strategy_authority import StrategyAuthority

from .qualification import (
    MODE_PIPELINE_TEST,
    MODE_REAL,
    NO_PROPOSAL_AUTHORITY,
    QUALIFICATION_POLICY,
    ProposalAuthority,
    QualificationResult,
    qualify,
)
from .sizing import AccountSnapshot, RiskPolicy, SizingResult, prepare_sizing

SCHEMA = "AG_TRADE_TICKET_V1"
EXECUTION_AUTHORITY_NONE = "NONE"

# ---- lifecycle contract (Phase 10): declared, only PREPARED states implemented -------
PREPARED_ONLY = "PREPARED_ONLY"
PREPARED_TEST_ONLY = "PREPARED_TEST_ONLY"
OWNER_CONFIRMED = "OWNER_CONFIRMED"
DEMO_EXECUTION_REQUESTED = "DEMO_EXECUTION_REQUESTED"
DECLARED_TRANSITIONS: Mapping[str, Tuple[str, ...]] = {
    PREPARED_ONLY: (OWNER_CONFIRMED,),
    OWNER_CONFIRMED: (DEMO_EXECUTION_REQUESTED,),
    DEMO_EXECUTION_REQUESTED: (),
    PREPARED_TEST_ONLY: (),  # a test ticket never reaches the owner-confirm path
}
IMPLEMENTED_STATES = frozenset({PREPARED_ONLY, PREPARED_TEST_ONLY})

# ---- pipeline outcomes ----------------------------------------------------------------
ELIGIBILITY_NOT_ELIGIBLE = "ELIGIBILITY_NOT_ELIGIBLE"
RISK_GEOMETRY_INVALID = "RISK_GEOMETRY_INVALID"
ACCOUNT_CONTEXT_INVALID = "ACCOUNT_CONTEXT_INVALID"
SIZING_BLOCKED = "SIZING_BLOCKED"
PROVENANCE_MISSING = "PROVENANCE_MISSING"
DUPLICATE = "DUPLICATE"
DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"

_GEOMETRY_REASONS = frozenset({REASON_NON_FINITE_GEOMETRY, REASON_ENTRY_EQUALS_STOP, REASON_INVALID_STOP_GEOMETRY})
_REQUIRED_PROVENANCE = ("strategy_config_fingerprint", "pilot_config_fingerprint", "pilot_id", "lineage_fingerprint")
_LONG_SIDES = frozenset({"LONG", "BUY"})
POLICY_FINGERPRINT = fingerprint({"schema": SCHEMA, "qualification": QUALIFICATION_POLICY,
                                  "proposal_bridge": BRIDGE_VERSION})
_NON_SEMANTIC = frozenset({"ticket_id", "semantic_fingerprint"})


@dataclass(frozen=True)
class TradeTicket:
    schema: str
    ticket_id: str
    status: str
    pipeline_mode: str
    market_authoritative: bool
    execution_authority: str
    opportunity_id: str
    candidate_id: str
    proposal_envelope_id: str
    symbol: str
    broker: str
    broker_symbol: str
    server: str
    environment: str
    cycle: str
    reference_session: str
    direction: str
    entry: float
    stop_loss: float
    targets: Tuple[float, ...]
    risk_pct: float
    risk_amount: float
    position_size_lots: float
    account_currency: str
    account_equity: float
    aggregate_risk_policy: str
    strategy_id: str
    strategy_version: str
    strategy_config_hash: str
    pilot_config_hash: str
    risk_policy_fingerprint: str
    risk_policy_source: str
    policy_fingerprint: str
    market_state_fingerprint: str
    market_data_fingerprint: str
    market_data_mode: str
    instrument_fingerprint: str
    symbol_meta_fingerprint: str
    evidence: Dict[str, Any]
    created_at: str
    expires_at: str
    expiry_source: str
    proposal: CanonicalProposal
    semantic_fingerprint: str = ""

    def __post_init__(self) -> None:
        if self.status not in IMPLEMENTED_STATES:
            raise ValueError(f"ticket status {self.status!r} is not implemented in this slice")
        if self.execution_authority != EXECUTION_AUTHORITY_NONE or self.proposal.execution_authority != AUTHORITY_NONE:
            raise ValueError("a prepared ticket never carries execution authority")
        if (self.status == PREPARED_TEST_ONLY) == self.market_authoritative:
            raise ValueError("PREPARED_TEST_ONLY tickets are never market-authoritative (and vice versa)")

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def semantic_fingerprint(ticket_dict: Mapping[str, Any]) -> str:
    return fingerprint({k: v for k, v in ticket_dict.items() if k not in _NON_SEMANTIC})


def verify_ticket_dict(ticket_dict: Mapping[str, Any]) -> bool:
    """Restart parity: a persisted/reloaded ticket still hashes to its own identity."""
    fp = semantic_fingerprint(ticket_dict)
    return fp == ticket_dict.get("semantic_fingerprint") and ticket_dict.get("ticket_id") == f"TKT-{fp[:24]}"


@dataclass(frozen=True)
class TicketPipelineResult:
    status: str
    reason_codes: Tuple[str, ...]
    qualification: QualificationResult
    eligibility: Optional[ProposalEligibilityDecision] = None
    proposal: Optional[CanonicalProposal] = None
    sizing: Optional[SizingResult] = None
    ticket: Optional[TradeTicket] = None
    market_state: Optional[MarketState] = field(default=None, repr=False)

    def owner_view(self) -> Dict[str, Any]:
        return owner_view(self)


def prepare_trade_ticket(
    *,
    candidate: OpportunityCandidate,
    market_state: Optional[MarketState],
    binding: StrategyBinding,
    cycle: str,
    mode: str,
    authority: ProposalAuthority,
    provenance: Mapping[str, Any],
    broker_key: str,
    account: AccountSnapshot,
    symbol_meta: Optional[SymbolMeta],
    risk_policy: Optional[RiskPolicy],
    evaluated_at: dt.datetime,
    strategy_authority: Optional[StrategyAuthority] = None,
    existing: Optional[Mapping[str, TradeTicket]] = None,
) -> TicketPipelineResult:
    """Pure composition; deterministic for identical inputs. `existing` maps
    proposal_envelope_id -> previously prepared ticket (duplicate guard)."""
    q = qualify(candidate=candidate, market_state=market_state, cycle=cycle, mode=mode,
                authority=authority, evaluated_at=evaluated_at)
    out = dict(qualification=q, market_state=market_state)
    if not q.qualified:
        return TicketPipelineResult(q.status, q.reason_codes, **out)

    eligibility = evaluate_proposal_eligibility(candidate, binding, evaluated_at=evaluated_at)
    out["eligibility"] = eligibility
    if eligibility.status != ELIGIBILITY_ELIGIBLE:
        status = (RISK_GEOMETRY_INVALID if set(eligibility.reason_codes) & _GEOMETRY_REASONS
                  else ELIGIBILITY_NOT_ELIGIBLE)
        return TicketPipelineResult(status, (eligibility.status,) + eligibility.reason_codes, **out)

    proposal = to_canonical_proposal(candidate, eligibility, strategy_authority=strategy_authority)
    out["proposal"] = proposal
    if proposal.proposal_state != PROPOSAL_READY or proposal.execution_authority != AUTHORITY_NONE:
        return TicketPipelineResult(ELIGIBILITY_NOT_ELIGIBLE, ("PROPOSAL_NOT_READY",), **out)

    # Target geometry is not covered by eligibility (it checks finiteness only):
    # every strategy-owned target must lie beyond entry on the profit side.
    is_long = proposal.direction in _LONG_SIDES
    if not all((t > proposal.entry) if is_long else (t < proposal.entry) for t in proposal.targets):
        return TicketPipelineResult(RISK_GEOMETRY_INVALID, ("INVALID_TARGET_GEOMETRY",), **out)

    missing = tuple(k for k in _REQUIRED_PROVENANCE if not provenance.get(k))
    if missing:
        return TicketPipelineResult(PROVENANCE_MISSING, tuple(f"MISSING_{k.upper()}" for k in missing), **out)
    if risk_policy is not None and risk_policy.pilot_id != provenance["pilot_id"]:
        return TicketPipelineResult(SIZING_BLOCKED, ("RISK_POLICY_PROVENANCE_MISMATCH",), **out)

    broker = get_broker(broker_key)
    instrument = get_instrument(candidate.symbol)
    if account.server not in broker.servers:
        return TicketPipelineResult(ACCOUNT_CONTEXT_INVALID, ("BROKER_SERVER_MISMATCH",), **out)
    if account.environment != "DEMO" or broker.environment != "DEMO":
        return TicketPipelineResult(ACCOUNT_CONTEXT_INVALID, ("ACCOUNT_ENVIRONMENT_NOT_VERIFIED_DEMO",), **out)
    broker_symbol = instrument.broker_symbol(broker_key)

    sizing = prepare_sizing(
        entry=proposal.entry, stop_loss=proposal.stop, account=account, risk_policy=risk_policy,
        symbol_meta=symbol_meta, expected_symbol=broker_symbol.symbol, expected_digits=instrument.digits,
        require_verified_metadata=(mode == MODE_REAL),
    )
    out["sizing"] = sizing
    if not sizing.ok:
        return TicketPipelineResult(SIZING_BLOCKED, (sizing.reason_code,), **out)

    fields: Dict[str, Any] = dict(
        schema=SCHEMA,
        status=PREPARED_ONLY if mode == MODE_REAL else PREPARED_TEST_ONLY,
        pipeline_mode=mode,
        market_authoritative=(mode == MODE_REAL),
        execution_authority=EXECUTION_AUTHORITY_NONE,
        opportunity_id=candidate.occurrence_id,
        candidate_id=candidate.candidate_id,
        proposal_envelope_id=proposal.proposal_envelope_id,
        symbol=candidate.symbol,
        broker=broker.canonical_name,
        broker_symbol=broker_symbol.symbol,
        server=account.server,
        environment=account.environment,
        cycle=cycle,
        reference_session=market_state.reference_session,
        direction=proposal.direction,
        entry=proposal.entry,
        stop_loss=proposal.stop,
        targets=tuple(proposal.targets),
        risk_pct=risk_policy.risk_per_trade_pct,
        risk_amount=round(sizing.risk_amount, 2),
        position_size_lots=sizing.volume,
        account_currency=account.currency,
        account_equity=account.equity,
        aggregate_risk_policy="NOT_AVAILABLE",
        strategy_id=candidate.strategy_id,
        strategy_version=candidate.strategy_version,
        strategy_config_hash=provenance["strategy_config_fingerprint"],
        pilot_config_hash=provenance["pilot_config_fingerprint"],
        risk_policy_fingerprint=risk_policy.fingerprint(),
        risk_policy_source=risk_policy.source,
        policy_fingerprint=POLICY_FINGERPRINT,
        market_state_fingerprint=market_state.fingerprint,
        market_data_fingerprint=provenance["lineage_fingerprint"],
        market_data_mode=market_state.market_data_mode,
        instrument_fingerprint=market_state.instrument_fingerprint,
        symbol_meta_fingerprint=sizing.symbol_meta_fingerprint,
        evidence=dict(q.evidence, qualification_status=q.status, eligibility_status=eligibility.status),
        created_at=evaluated_at.isoformat(),
        expires_at=q.expires_at,
        expiry_source=q.expiry_source,
        proposal=proposal,
    )
    probe = TradeTicket(ticket_id="", **fields)
    fp = semantic_fingerprint(probe.to_dict())
    ticket = dataclasses.replace(probe, ticket_id=f"TKT-{fp[:24]}", semantic_fingerprint=fp)

    prior = (existing or {}).get(proposal.proposal_envelope_id)
    if prior is not None:
        if prior.semantic_fingerprint == ticket.semantic_fingerprint:
            return TicketPipelineResult(DUPLICATE, ("TICKET_ALREADY_PREPARED",), ticket=prior, **out)
        return TicketPipelineResult(DUPLICATE_CONFLICT, ("SAME_OPPORTUNITY_DIFFERENT_TICKET",), **out)
    return TicketPipelineResult(ticket.status, (), ticket=ticket, **out)


def prepare_from_fx_opportunity(result: Any, **kwargs: Any) -> TicketPipelineResult:
    """Compose downstream of fx_opportunity.runner.FxOpportunityResult (unchanged)."""
    return prepare_trade_ticket(candidate=result.candidate, market_state=result.market_state,
                                cycle=result.cycle, provenance=result.provenance,
                                evaluated_at=result.evaluated_at, **kwargs)


def owner_view(res: TicketPipelineResult) -> Dict[str, Any]:
    """Minimum owner-review shape. `ai_explanation` is advisory-only and cannot change
    qualification, risk, eligibility or authorization."""
    q, t, ms = res.qualification, res.ticket, res.market_state
    view: Dict[str, Any] = {
        "outcome": res.status,
        "reason_codes": list(res.reason_codes),
        "symbol": q.symbol,
        "cycle": q.cycle,
        "strategy": {"id": q.strategy_id, "version": q.strategy_version},
        "pipeline_mode": q.mode,
        "qualification": {"status": q.status, "reason_codes": list(q.reason_codes)},
        "eligibility": None if res.eligibility is None else {
            "status": res.eligibility.status, "reason_codes": list(res.eligibility.reason_codes)},
        "market_state": None if ms is None else {
            "as_of": ms.as_of, "reference_session": ms.reference_session,
            "reference_high": ms.reference_high, "reference_low": ms.reference_low,
            "reference_high_taken": ms.reference_high_taken, "reference_low_taken": ms.reference_low_taken,
            "last_closed_bar": ms.last_closed_bar, "spread_pips": ms.spread_pips,
            "market_data_mode": ms.market_data_mode, "fingerprint": ms.fingerprint},
        "execution_authority": EXECUTION_AUTHORITY_NONE,
        "proposal_authority": ("NONE" if q.status == NO_PROPOSAL_AUTHORITY
                               else "PIPELINE_TEST_ONLY" if q.mode == MODE_PIPELINE_TEST else "REGISTRY_AUTHORIZED"),
        "ticket": None,
        "ai_explanation": {"authority": "ADVISORY_ONLY", "text": None},
    }
    if t is not None:
        view["ticket"] = {
            "ticket_id": t.ticket_id, "status": t.status, "market_authoritative": t.market_authoritative,
            "direction": t.direction, "entry": t.entry, "stop_loss": t.stop_loss, "targets": list(t.targets),
            "why": t.evidence,
            "risk": {"risk_pct": t.risk_pct, "risk_amount": t.risk_amount, "currency": t.account_currency,
                     "position_size_lots": t.position_size_lots, "aggregate_policy": t.aggregate_risk_policy},
            "expires_at": t.expires_at, "expiry_source": t.expiry_source,
            "broker": t.broker, "server": t.server, "environment": t.environment,
            "provenance": {"strategy_config_hash": t.strategy_config_hash, "pilot_config_hash": t.pilot_config_hash,
                           "market_state_fingerprint": t.market_state_fingerprint,
                           "market_data_fingerprint": t.market_data_fingerprint,
                           "risk_policy_source": t.risk_policy_source,
                           "policy_fingerprint": t.policy_fingerprint,
                           "instrument_fingerprint": t.instrument_fingerprint,
                           "symbol_meta_fingerprint": t.symbol_meta_fingerprint,
                           "risk_policy_fingerprint": t.risk_policy_fingerprint,
                           "semantic_fingerprint": t.semantic_fingerprint},
            "next_states_declared": list(DECLARED_TRANSITIONS[t.status]),
        }
    return view
