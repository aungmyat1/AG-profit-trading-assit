"""Adapter, not a rewrite: post_asian_pilot.decision.PostAsianDecision (+ the optional,
already-persisted execution.adapter.TradeProposal that authorization.proposal_source.py
reads for an actionable READY setup) -> CanonicalProposal.

Reads ONLY fields already computed by post_asian_pilot/*; never calls
post_asian_pilot.pipeline.run_pilot_cycle / build_entry_proposal / evaluate_strategy, and
never recomputes a signal, decision, or risk-sized proposal -- the same read-only posture
authorization.proposal_source.py already documents for itself. No behavior change to
post_asian_pilot/* or execution.adapter.TradeProposal: this is a pure, one-way mapping
function.

post_asian_pilot's six public decision states (post_asian_pilot/decision.py's own
docstring) map onto the canonical watcher_state/proposal_state dimensions as follows.
This mapping is deliberately conservative -- it never claims more watcher progression
than the decision's own evidence supports:

  DATA_ERROR -> watcher DATA_BLOCKED,        proposal INCOMPLETE
  EXPIRED    -> watcher EXPIRED,             proposal PROPOSAL_EXPIRED
  NO_TRADE   -> watcher SCANNING,            proposal NO_TRADE
  WATCH      -> watcher LIQUIDITY_APPROACH,  proposal INCOMPLETE
               (ST_ASIAN_SWEEP_5R_V1's only WATCH trigger_type is LIQUIDITY_SWEEP --
                see decision.py's watch_decision/map_trade_signal_to_decision)
  READY      -> watcher SETUP_QUALIFIED,     proposal PROPOSAL_READY  (only when the
               matching, actionable TradeProposal is ALSO supplied -- see below)
  BLOCKED    -> watcher SETUP_QUALIFIED,     proposal BLOCKED
               (governor.py layers BLOCKED on top of an already-qualified READY setup
                that failed a portfolio/risk gate -- the setup itself did qualify)

A READY PostAsianDecision with no accompanying actionable TradeProposal (never won its
daily slot, or the caller simply didn't supply one) is a missing-required-field case per
Workstream 0's own rule and maps to BLOCKED, never a partial PROPOSAL_READY.

execution_authority is always AUTHORITY_NONE here: this adapter's only job is lossless
proposal-state mapping, never authorization -- assigning any other value would be
inventing an authorization decision this module has no evidence for.
"""
from __future__ import annotations

from typing import Optional

from execution.adapter import TradeProposal
from post_asian_pilot.decision import (
    PostAsianDecision,
    STATUS_BLOCKED,
    STATUS_DATA_ERROR,
    STATUS_EXPIRED,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
)

from ..models import (
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PROPOSAL_BLOCKED,
    PROPOSAL_EXPIRED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_NO_TRADE,
    PROPOSAL_READY,
    WATCHER_DATA_BLOCKED,
    WATCHER_EXPIRED,
    WATCHER_LIQUIDITY_APPROACH,
    WATCHER_SCANNING,
    WATCHER_SETUP_QUALIFIED,
    WatcherOccurrenceTimestamps,
    blocked_envelope,
)

SOURCE_MODULE = "post_asian_pilot.decision.PostAsianDecision"

_WATCHER_STATE_BY_STATUS = {
    STATUS_DATA_ERROR: WATCHER_DATA_BLOCKED,
    STATUS_EXPIRED: WATCHER_EXPIRED,
    STATUS_NO_TRADE: WATCHER_SCANNING,
    STATUS_WATCH: WATCHER_LIQUIDITY_APPROACH,
    STATUS_READY: WATCHER_SETUP_QUALIFIED,
    STATUS_BLOCKED: WATCHER_SETUP_QUALIFIED,
}

_PROPOSAL_STATE_BY_STATUS_NON_READY = {
    STATUS_DATA_ERROR: PROPOSAL_INCOMPLETE,
    STATUS_EXPIRED: PROPOSAL_EXPIRED,
    STATUS_NO_TRADE: PROPOSAL_NO_TRADE,
    STATUS_WATCH: PROPOSAL_INCOMPLETE,
    STATUS_BLOCKED: PROPOSAL_BLOCKED,
}


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def to_canonical_proposal(
    decision: PostAsianDecision, trade_proposal: Optional[TradeProposal] = None,
) -> CanonicalProposal:
    source_record_id = decision.decision_id

    if decision.status != STATUS_READY:
        proposal_state = _PROPOSAL_STATE_BY_STATUS_NON_READY[decision.status]
        return CanonicalProposal(
            proposal_envelope_id=f"FX:{source_record_id}",
            strategy_id=decision.strategy_id, strategy_version=decision.strategy_version,
            market="FX", venue="MT5_BROKER", contract_type="SPOT_FX", symbol=decision.symbol,
            watcher_state=_WATCHER_STATE_BY_STATUS[decision.status], proposal_state=proposal_state,
            execution_authority=AUTHORITY_NONE,
            market_context_evidence=dict(
                reference_session=decision.reference_session, trading_date=str(decision.trading_date),
            ),
            liquidity_evidence=dict(
                trigger_type=decision.trigger_type, trigger_level=decision.trigger_level,
                trigger_timeframe=decision.trigger_timeframe,
            ),
            data_provenance=DataProvenance(
                source="MT5", data_version=decision.session_snapshot_id,
                complete_candle_evidence=decision.status not in (STATUS_DATA_ERROR,),
            ),
            timestamps=WatcherOccurrenceTimestamps(
                detected_at=_iso(decision.evaluation_time),
                state_entered_at=_iso(decision.evaluation_time),
                last_evaluated_at=_iso(decision.evaluation_time),
                evidence_candle_close=_iso(decision.ready_at),
                expires_at=_iso(decision.valid_until),
                next_required_evidence=(decision.missing_condition,) if decision.missing_condition else (),
            ),
            source_module=SOURCE_MODULE, source_record_id=source_record_id,
            reasons=decision.reason_codes,
        )

    # STATUS_READY: only a genuinely PROPOSAL_READY envelope when the matching, actionable
    # TradeProposal was also supplied -- a READY decision with no such proposal is a
    # missing-required-field case (Workstream 0's own BLOCKED rule), not a partial READY.
    if trade_proposal is None:
        return blocked_envelope(
            source_module=SOURCE_MODULE, source_record_id=source_record_id, symbol=decision.symbol,
            strategy_id=decision.strategy_id, strategy_version=decision.strategy_version,
            reasons=("MISSING_ACTIONABLE_TRADE_PROPOSAL",),
        )
    if trade_proposal.setup_id != decision.decision_id and trade_proposal.symbol != decision.symbol:
        # Defensive: never silently attach an unrelated TradeProposal to this decision.
        return blocked_envelope(
            source_module=SOURCE_MODULE, source_record_id=source_record_id, symbol=decision.symbol,
            strategy_id=decision.strategy_id, strategy_version=decision.strategy_version,
            reasons=("TRADE_PROPOSAL_IDENTITY_MISMATCH",),
        )

    targets = tuple(t for t in (trade_proposal.tp1, trade_proposal.tp2) if t is not None)
    return CanonicalProposal(
        proposal_envelope_id=f"FX:{source_record_id}",
        strategy_id=decision.strategy_id, strategy_version=decision.strategy_version,
        market="FX", venue="MT5_BROKER", contract_type="SPOT_FX", symbol=decision.symbol,
        watcher_state=WATCHER_SETUP_QUALIFIED, proposal_state=PROPOSAL_READY,
        execution_authority=AUTHORITY_NONE,
        direction=trade_proposal.direction,
        entry=trade_proposal.entry,
        stop=trade_proposal.stop_loss,
        targets=targets,
        expected_R=None,  # execution.adapter.TradeProposal defines no expected_R field -- never synthesized
        plan_expires_at=_iso(decision.valid_until),
        setup_evidence=dict(
            profile_id=trade_proposal.profile_id, volume=trade_proposal.volume,
            risk_amount=trade_proposal.risk_amount, risk_percent=trade_proposal.risk_percent,
        ),
        market_context_evidence=dict(
            reference_session=decision.reference_session, trading_date=str(decision.trading_date),
        ),
        liquidity_evidence=dict(
            trigger_type=decision.trigger_type, trigger_level=decision.trigger_level,
            trigger_timeframe=decision.trigger_timeframe,
        ),
        confirmation_evidence=dict(setup_id=trade_proposal.setup_id),
        data_provenance=DataProvenance(
            source="MT5", data_version=decision.session_snapshot_id, complete_candle_evidence=True,
        ),
        cost_assumptions=CostAssumptions(),  # neither source object models spread/commission/slippage/swap
        timestamps=WatcherOccurrenceTimestamps(
            detected_at=_iso(decision.evaluation_time),
            state_entered_at=_iso(decision.ready_at),
            last_evaluated_at=_iso(decision.evaluation_time),
            evidence_candle_close=_iso(decision.ready_at),
            expires_at=_iso(decision.valid_until),
            evidence_complete=("LIQUIDITY_SWEEP", "M15_CLOSE_CONFIRMATION"),
        ),
        source_module=SOURCE_MODULE, source_record_id=source_record_id,
        reasons=decision.reason_codes,
    )
