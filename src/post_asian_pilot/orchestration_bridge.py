"""Proposal-only bridge from canonical MarketState and closed M15 candles.

Production evaluation always uses the repository's real eligibility evaluator.
Risk and canonical proposal formation are unreachable until that evaluator returns
the typed ELIGIBLE decision for this exact candidate. No broker mutation occurs.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass
from typing import Optional, Sequence

from mt5.symbol_resolver import SymbolMeta
from opportunity.asian_sweep_adapter import AsianSweepFunnelAdapter
from opportunity.contracts import (
    ELIGIBILITY_ELIGIBLE, MARKET_DATA_MODE_REAL, MarketEvent,
    ProposalEligibilityDecision,
)
from opportunity.engine import evaluate_funnel
from opportunity.proposal_eligibility import evaluate_proposal_eligibility
from opportunity.registry_binding import resolve_strategy_binding
from post_asian_pilot.decision import PostAsianDecision, STATUS_READY, map_trade_signal_to_decision
from post_asian_pilot.pilot_config import DEFAULT_PILOT_CONFIG_PATH, load_pilot_config
from post_asian_pilot.proposal import build_entry_proposal
from post_asian_pilot.snapshot import build_asian_session_snapshot
from proposal_envelope.adapters.opportunity_adapter import to_canonical_proposal
from proposal_envelope.formation_gate import apply_formation_gate
from proposal_envelope.ledger import ProposalLedger
from proposal_envelope.models import CanonicalProposal, PROPOSAL_READY
from proposal_envelope.strategy_authority import resolve_strategy_authority
from strategy_engine.engine import evaluate as evaluate_strategy
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle
from strategy_contract.market_snapshot import MarketSnapshot
from packages.contracts.v1 import MarketState

STRATEGY_CONFIG_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"
STRATEGY_ID = "ST_ASIAN_SWEEP_5R_V1"


@dataclass(frozen=True)
class OrchestrationResult:
    decision: PostAsianDecision
    candidate: object | None
    eligibility: Optional[ProposalEligibilityDecision]
    risk_result_count: int = 0
    canonical_proposal: Optional[CanonicalProposal] = None
    persisted_proposal: Optional[CanonicalProposal] = None
    reason_code: Optional[str] = None


class MarketStateLineageError(ValueError):
    """MarketState and MarketSnapshot/candle provenance do not describe same input."""


def _validate_marketstate(state: MarketState, snapshot: MarketSnapshot, candles: Sequence[Candle]) -> None:
    if state.symbol != snapshot.symbol:
        raise MarketStateLineageError("MarketState symbol does not match MarketSnapshot")
    if snapshot.market_data_mode != MARKET_DATA_MODE_REAL:
        raise MarketStateLineageError("production orchestration requires REAL MarketSnapshot")
    if not snapshot.is_closed or snapshot.timeframe != "M15":
        raise MarketStateLineageError("production orchestration requires a closed M15 snapshot")
    facts = state.facts
    fact_source = facts.get("source")
    if fact_source is not None and fact_source != snapshot.source:
        raise MarketStateLineageError("MarketState source does not match MarketSnapshot")
    fact_asof = facts.get("source_timestamp") or facts.get("observed_at")
    if fact_asof is not None and dt.datetime.fromisoformat(fact_asof.replace("Z", "+00:00")) < snapshot.bar_close_time:
        raise MarketStateLineageError("MarketState timestamp predates triggering closed candle")
    if not candles:
        raise MarketStateLineageError("closed M15 candle sequence is empty")
    last = candles[-1]
    if last.time + dt.timedelta(minutes=15) != snapshot.bar_close_time:
        raise MarketStateLineageError("last Candle does not match MarketSnapshot closed bar")


def _evaluate_strategy_decision(
    state: MarketState, candles: Sequence[Candle], snapshot: MarketSnapshot,
    trading_date: dt.date, evaluation_time: dt.datetime,
):
    _validate_marketstate(state, snapshot, candles)
    pilot = load_pilot_config(DEFAULT_PILOT_CONFIG_PATH)
    strategy = load_strategy(pilot.strategy_source_path)
    pair = next((p for p in strategy.session_pairs if p.pair_id == pilot.pair_id), None)
    if pair is None or pair.reference_session.name.lower() != pilot.reference_session_name.lower():
        raise ValueError("pilot pair/reference session does not match strategy contract")
    ref_start = dt.datetime.combine(trading_date, dt.time.fromisoformat(pair.reference_session.start_time_gmt), tzinfo=dt.timezone.utc)
    ref_end = dt.datetime.combine(trading_date, dt.time.fromisoformat(pair.reference_session.end_time_gmt), tzinfo=dt.timezone.utc)
    session_candles = tuple(c for c in candles if ref_start <= c.time < ref_end)
    expected = int((ref_end - ref_start).total_seconds() // 900)
    snapshot_result = build_asian_session_snapshot(
        strategy.strategy_id, state.symbol, trading_date, pair.reference_session.name,
        ref_start, ref_end, session_candles, expected, as_of=evaluation_time,
        created_at_utc=evaluation_time,
    )
    if snapshot_result.status != "VALID" or snapshot_result.snapshot is None:
        raise ValueError("invalid reference-session candle input: " + ",".join(snapshot_result.reason_codes))
    post_candles = tuple(c for c in candles if c.time >= ref_end and c.time < snapshot.bar_close_time)
    signal = evaluate_strategy(
        strategy, pilot.pair_id, state.symbol, trading_date, session_candles,
        expected, post_session_candles=post_candles,
    )
    window_end = dt.datetime.combine(
        trading_date, dt.time.fromisoformat(pilot.execution_window_end_utc), tzinfo=dt.timezone.utc,
    )
    decision = map_trade_signal_to_decision(
        signal, snapshot_result.snapshot.snapshot_id, evaluation_time, window_end,
    )
    return pilot, strategy, decision


def _evaluate_opportunity_eligibility(
    state: MarketState, candles: Sequence[Candle], snapshot: MarketSnapshot,
    trading_date: dt.date, evaluation_time: dt.datetime, *, venue: str,
):
    """PRODUCTION PRE-ELIGIBILITY: strategy -> candidate -> REAL evaluator."""
    _validate_marketstate(state, snapshot, candles)
    pilot, strategy, decision = _evaluate_strategy_decision(state, candles, snapshot, trading_date, evaluation_time)
    if decision.status != STATUS_READY:
        return pilot, strategy, decision, None, None
    binding = resolve_strategy_binding(STRATEGY_ID)
    event = MarketEvent(
        event_id=f"ASIAN_SWEEP:{state.symbol}:{pilot.pair_id}:{trading_date.isoformat()}",
        event_type="BAR_CLOSE", symbol=state.symbol, market="FX", venue=venue,
        timeframe=snapshot.timeframe, bar_open_time=snapshot.bar_open_time,
        bar_close_time=snapshot.bar_close_time, market_data_asof=snapshot.market_data_asof,
        market_data_mode=snapshot.market_data_mode, snapshot_fingerprint=snapshot.fingerprint,
        source=snapshot.source,
    )
    candidate, _ = evaluate_funnel(
        event=event, binding=binding,
        adapter=AsianSweepFunnelAdapter(decision, strategy_version=strategy.version),
    )
    eligibility = evaluate_proposal_eligibility(candidate, binding, evaluated_at=evaluation_time)
    return pilot, strategy, decision, candidate, eligibility


def _validate_candidate_snapshot(candidate, snapshot: MarketSnapshot) -> None:
    """Require candidate provenance to agree before Risk and again before formation."""
    if candidate.symbol != snapshot.symbol:
        raise MarketStateLineageError("Opportunity candidate symbol does not match MarketSnapshot")
    if candidate.market_data_mode != snapshot.market_data_mode:
        raise MarketStateLineageError("Opportunity candidate mode does not match MarketSnapshot")
    if candidate.data_lineage != snapshot.fingerprint:
        raise MarketStateLineageError("Opportunity candidate fingerprint does not match MarketSnapshot")
    if candidate.last_evaluated_at != snapshot.market_data_asof:
        raise MarketStateLineageError("Opportunity candidate as-of does not match MarketSnapshot")


def _build_after_accepted_eligibility(
    candidate, eligibility: ProposalEligibilityDecision, decision: PostAsianDecision,
    strategy, *, equity: float, symbol_meta: SymbolMeta, risk_per_trade_pct: float,
    snapshot: MarketSnapshot, marketstate_event_id: str, marketstate_semantic_hash: str,
) -> tuple[Optional[CanonicalProposal], Optional[str]]:
    """Private typed post-eligibility boundary, called only after evaluator acceptance.

    Tests may call this seam with an explicit accepted eligibility fixture. The sole
    production entrypoint owns evaluator invocation and does not accept eligibility.
    """
    if not isinstance(eligibility, ProposalEligibilityDecision):
        raise TypeError("typed ProposalEligibilityDecision required")
    if eligibility.status != ELIGIBILITY_ELIGIBLE or eligibility.candidate_id != candidate.candidate_id:
        return None, "ELIGIBILITY_NOT_ACCEPTED_FOR_CANDIDATE"
    if decision.status != STATUS_READY:
        return None, "STRATEGY_DECISION_NOT_READY"
    if (
        candidate.strategy_id != decision.strategy_id
        or candidate.strategy_version != decision.strategy_version
        or candidate.symbol != decision.symbol
        or strategy.strategy_id != decision.strategy_id
        or strategy.version != decision.strategy_version
        or decision.signal is None
        or candidate.geometry is None
        or candidate.geometry.direction != decision.signal.direction
        or candidate.geometry.entry != decision.signal.entry
        or candidate.geometry.invalidation != decision.signal.stop_loss
    ):
        return None, "OPPORTUNITY_STRATEGY_LINEAGE_MISMATCH"
    _validate_candidate_snapshot(candidate, snapshot)
    risk_result = build_entry_proposal(
        decision, strategy, equity, symbol_meta, risk_per_trade_pct,
        decision.session_snapshot_id or "", now=eligibility.evaluated_at,
    )
    if risk_result.status != "READY" or risk_result.proposal is None:
        return None, risk_result.reason_code
    trade = risk_result.proposal.trade_proposal
    risk_evidence = {
        "marketstate_semantic_hash": marketstate_semantic_hash,
        "strategy_id": candidate.strategy_id, "strategy_version": candidate.strategy_version,
        "opportunity_id": candidate.candidate_id, "occurrence_id": candidate.occurrence_id,
        "eligibility_candidate_id": eligibility.candidate_id,
        "eligibility_status": eligibility.status,
        "eligibility_evaluated_at": eligibility.evaluated_at.isoformat(),
        "risk_authority": "execution.intent_builder.build_intent",
        "risk_policy_pct": risk_per_trade_pct, "risk_amount": trade.risk_amount,
        "risk_percent": trade.risk_percent, "volume": trade.volume,
        "fx_trade_proposal_id": trade.setup_id,
    }
    proposal = to_canonical_proposal(candidate, eligibility)
    if proposal.data_provenance.market_data_mode != candidate.market_data_mode:
        return None, "CANONICAL_PROVENANCE_MISMATCH"
    proposal = dataclasses.replace(
        proposal,
        targets=tuple(v for v in (trade.tp1, trade.tp2) if v is not None),
        setup_evidence={**proposal.setup_evidence, "risk_result": risk_evidence,
                        "marketstate_semantic_hash": marketstate_semantic_hash,
                        "marketstate_event_id": marketstate_event_id},
    )
    proposal = apply_formation_gate(proposal, snapshot)
    if (
        proposal.data_provenance.market_data_mode != candidate.market_data_mode
        or proposal.data_provenance.market_data_mode != snapshot.market_data_mode
        or proposal.data_provenance.market_data_fingerprint != snapshot.fingerprint
        or proposal.data_provenance.market_data_asof != snapshot.market_data_asof.isoformat()
    ):
        return proposal, "FORMATION_PROVENANCE_MISMATCH"
    if proposal.proposal_state != PROPOSAL_READY:
        return proposal, "CANONICAL_FORMATION_REJECTED"
    return proposal, None


def evaluate_marketstate_to_proposal(
    state: MarketState, candles: Sequence[Candle], snapshot: MarketSnapshot,
    trading_date: dt.date, evaluation_time: dt.datetime, *, venue: str, equity: float,
    symbol_meta: SymbolMeta, proposal_ledger: Optional[ProposalLedger] = None,
) -> OrchestrationResult:
    """Full production composition; accepted READY proposals persist to the ledger."""
    pilot, strategy, decision, candidate, eligibility = _evaluate_opportunity_eligibility(
        state, candles, snapshot, trading_date, evaluation_time, venue=venue,
    )
    if candidate is None or eligibility is None:
        return OrchestrationResult(decision, candidate, eligibility)
    if eligibility.status != ELIGIBILITY_ELIGIBLE:
        return OrchestrationResult(decision, candidate, eligibility)
    authority = resolve_strategy_authority(
        STRATEGY_ID, strategy.version, strategy_config_path=pilot.strategy_source_path,
    )
    proposal, reason = _build_after_accepted_eligibility(
        candidate, eligibility, decision, strategy, equity=equity, symbol_meta=symbol_meta,
        risk_per_trade_pct=pilot.risk_per_trade_pct, snapshot=snapshot,
        marketstate_event_id=state.event_id,
        marketstate_semantic_hash=state.semantic_hash,
    )
    if proposal is None or proposal.proposal_state != PROPOSAL_READY:
        return OrchestrationResult(decision, candidate, eligibility, 1, proposal, None, reason)
    proposal = dataclasses.replace(proposal, setup_evidence={
        **proposal.setup_evidence,
        "strategy_lifecycle_authority": authority.lifecycle_stage,
        "marketstate_symbol": state.symbol,
        "marketstate_source": snapshot.source,
        "marketstate_source_timestamp": str(state.facts.get("source_timestamp") or state.created_at),
    })
    ledger = proposal_ledger if proposal_ledger is not None else ProposalLedger()
    persisted = ledger.record_proposal(proposal)
    return OrchestrationResult(decision, candidate, eligibility, 1, proposal, persisted)
