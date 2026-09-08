"""Adapter, not a rewrite: btc_sweep_research.pipeline.ResearchCycleResult (a
strategy_engine.sweep_retest.models.SetupState plus the optional
btc_sweep_research.proposal.BTCSweepResearchProposal built once it qualifies) ->
CanonicalProposal.

Reads ONLY fields already computed by strategy_engine.sweep_retest.engine.evaluate_setup
and btc_sweep_research.pipeline._evaluate_occurrence; never re-runs the strategy, never
imports execution.executor/execution.coordinator/execution.adapter/mt5.management_gateway
(see btc_sweep_research/pipeline.py's own module docstring for why that boundary already
matters to this exact package) and this adapter adds no new import of them either.

SetupState's state machine (strategy_engine/sweep_retest/models.py) maps onto watcher_state
as follows -- deliberately conservative, one state at a time, never skipping ahead of the
evidence the state machine itself has reached:

  WAITING_REFERENCE                        -> SCANNING
  WAITING_WINDOW                           -> CONTEXT_IDENTIFIED
  WAITING_SWEEP                            -> LIQUIDITY_APPROACH
  SWEEP_DETECTED                           -> LIQUIDITY_SWEPT
  WAITING_MSS / MSS_CONFIRMED / WAITING_RETEST -> STRUCTURE_CONFIRMING
  ENTRY_READY and every post-entry lifecycle state (ORDER_SUBMITTED, POSITION_OPEN,
    TP1_HIT, RUNNER_ACTIVE, TP2_HIT, STOPPED) -> SETUP_QUALIFIED
    (this research module has no broker order path -- ORDER_SUBMITTED/POSITION_OPEN etc.
    are this package's own SIMULATED trade-tracking states, not a real fill; the watcher
    dimension only cares that the setup qualified, which is already true by ENTRY_READY)
  BLOCKED_DAILY_LOSS / BLOCKED_OPEN_POSITION -> SETUP_QUALIFIED
    (strategy_qualified is True on these -- see SetupState's own docstring: tradability
    guard-blocked, not detection-blocked)
  SETUP_EXPIRED / SESSION_EXPIRED           -> EXPIRED
  NO_TRADE_DIRECTION / NO_TRADE_TARGET_GEOMETRY -> INVALIDATED

execution_authority is always AUTHORITY_NONE: btc_sweep_research is RESEARCH_ONLY /
PROPOSAL_ONLY by its own contract (BTCSweepResearchProposal.execution_authority is always
EXECUTION_AUTHORITY_DISABLED) and this adapter never overrides that.
"""
from __future__ import annotations

from typing import Optional

from btc_sweep_research.proposal import BTCSweepResearchProposal
from strategy_engine.sweep_retest.models import (
    STATE_BLOCKED_DAILY_LOSS,
    STATE_BLOCKED_OPEN_POSITION,
    STATE_ENTRY_READY,
    STATE_MSS_CONFIRMED,
    STATE_NO_TRADE_DIRECTION,
    STATE_NO_TRADE_TARGET_GEOMETRY,
    STATE_ORDER_SUBMITTED,
    STATE_POSITION_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_SESSION_EXPIRED,
    STATE_SETUP_EXPIRED,
    STATE_STOPPED,
    STATE_SWEEP_DETECTED,
    STATE_TP1_HIT,
    STATE_TP2_HIT,
    STATE_WAITING_MSS,
    STATE_WAITING_REFERENCE,
    STATE_WAITING_RETEST,
    STATE_WAITING_SWEEP,
    STATE_WAITING_WINDOW,
    SetupState,
)

from ..models import (
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PROPOSAL_BLOCKED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_INVALIDATED,
    PROPOSAL_EXPIRED,
    PROPOSAL_READY,
    WATCHER_CONTEXT_IDENTIFIED,
    WATCHER_INVALIDATED,
    WATCHER_LIQUIDITY_APPROACH,
    WATCHER_LIQUIDITY_SWEPT,
    WATCHER_EXPIRED,
    WATCHER_SCANNING,
    WATCHER_SETUP_QUALIFIED,
    WATCHER_STRUCTURE_CONFIRMING,
    WatcherOccurrenceTimestamps,
    blocked_envelope,
)

SOURCE_MODULE = "strategy_engine.sweep_retest.models.SetupState"

_QUALIFIED_STATES = {
    STATE_ENTRY_READY, STATE_ORDER_SUBMITTED, STATE_POSITION_OPEN, STATE_TP1_HIT,
    STATE_RUNNER_ACTIVE, STATE_TP2_HIT, STATE_STOPPED, STATE_BLOCKED_DAILY_LOSS,
    STATE_BLOCKED_OPEN_POSITION,
}

_WATCHER_STATE_BY_STATE = {
    STATE_WAITING_REFERENCE: WATCHER_SCANNING,
    STATE_WAITING_WINDOW: WATCHER_CONTEXT_IDENTIFIED,
    STATE_WAITING_SWEEP: WATCHER_LIQUIDITY_APPROACH,
    STATE_SWEEP_DETECTED: WATCHER_LIQUIDITY_SWEPT,
    STATE_WAITING_MSS: WATCHER_STRUCTURE_CONFIRMING,
    STATE_MSS_CONFIRMED: WATCHER_STRUCTURE_CONFIRMING,
    STATE_WAITING_RETEST: WATCHER_STRUCTURE_CONFIRMING,
    STATE_SETUP_EXPIRED: WATCHER_EXPIRED,
    STATE_SESSION_EXPIRED: WATCHER_EXPIRED,
    STATE_NO_TRADE_DIRECTION: WATCHER_INVALIDATED,
    STATE_NO_TRADE_TARGET_GEOMETRY: WATCHER_INVALIDATED,
}
for _s in _QUALIFIED_STATES:
    _WATCHER_STATE_BY_STATE[_s] = WATCHER_SETUP_QUALIFIED

_EXPIRED_STATES = {STATE_SETUP_EXPIRED, STATE_SESSION_EXPIRED}
_INVALIDATED_STATES = {STATE_NO_TRADE_DIRECTION, STATE_NO_TRADE_TARGET_GEOMETRY}


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def to_canonical_proposal(
    setup_state: SetupState, proposal: Optional[BTCSweepResearchProposal] = None,
) -> CanonicalProposal:
    source_record_id = setup_state.setup_id
    watcher_state = _WATCHER_STATE_BY_STATE.get(setup_state.state, WATCHER_SCANNING)

    if not setup_state.strategy_qualified:
        if setup_state.state in _EXPIRED_STATES:
            proposal_state = PROPOSAL_EXPIRED
        elif setup_state.state in _INVALIDATED_STATES:
            proposal_state = PROPOSAL_INVALIDATED
        else:
            proposal_state = PROPOSAL_INCOMPLETE
        return CanonicalProposal(
            proposal_envelope_id=f"BTC:{source_record_id}",
            strategy_id=setup_state.strategy_id, strategy_version="",
            market="CRYPTO", venue="BYBIT", contract_type="CRYPTO_PERP", symbol=setup_state.symbol,
            watcher_state=watcher_state, proposal_state=proposal_state,
            execution_authority=AUTHORITY_NONE,
            direction=setup_state.direction,
            market_context_evidence=dict(
                ref_high=setup_state.ref_high, ref_low=setup_state.ref_low, ref_mid=setup_state.ref_mid,
                profile_id=setup_state.profile_id,
            ),
            liquidity_evidence=dict(
                sweep_level=setup_state.sweep_level, sweep_extreme=setup_state.sweep_extreme,
                sweep_time=_iso(setup_state.sweep_time),
            ),
            confirmation_evidence=dict(
                broken_swing_price=setup_state.broken_swing_price, mss_time=_iso(setup_state.mss_time),
            ),
            data_provenance=DataProvenance(source="BYBIT", complete_candle_evidence=False),
            timestamps=WatcherOccurrenceTimestamps(
                detected_at=_iso(setup_state.evaluated_at), state_entered_at=_iso(setup_state.evaluated_at),
                last_evaluated_at=_iso(setup_state.evaluated_at),
            ),
            source_module=SOURCE_MODULE, source_record_id=source_record_id,
            reasons=(setup_state.reason_code,) if setup_state.reason_code else (),
        )

    # strategy_qualified is True: a compatible strategy (ST_LIQUIDITY_SWEEP_RETEST_V1)
    # DID own this occurrence -- STRATEGY_UNMATCHED never applies to this adapter's input,
    # since a SetupState is only ever produced by that one signed strategy's own runtime.
    if proposal is None:
        return blocked_envelope(
            source_module=SOURCE_MODULE, source_record_id=source_record_id, symbol=setup_state.symbol,
            strategy_id=setup_state.strategy_id, reasons=("MISSING_BTC_RESEARCH_PROPOSAL",),
        )

    if setup_state.tradability_blocked:
        proposal_state = PROPOSAL_BLOCKED
        reasons = (setup_state.tradability_reason,) if setup_state.tradability_reason else ()
    else:
        proposal_state = PROPOSAL_READY
        reasons = ()

    targets = tuple(v for v in (proposal.target.get("tp1"), proposal.target.get("tp2")) if v is not None)
    funding_cost = None
    if isinstance(proposal.funding_assumption, dict):
        funding_cost = proposal.funding_assumption.get("funding_cost_estimate")
    missing_cost_fields = tuple(
        name for name, value in (("commission", proposal.estimated_fees), ("swap_or_funding", funding_cost))
        if value is None
    )
    if not missing_cost_fields:
        cost_status = "ITEMIZED"
    elif len(missing_cost_fields) == 2:
        cost_status = "NOT_INCLUDED"
    else:
        cost_status = "MIXED"
    return CanonicalProposal(
        proposal_envelope_id=f"BTC:{source_record_id}",
        strategy_id=proposal.strategy, strategy_version=proposal.strategy_version,
        market="CRYPTO", venue=proposal.exchange, contract_type="CRYPTO_PERP", symbol=proposal.instrument,
        watcher_state=WATCHER_SETUP_QUALIFIED, proposal_state=proposal_state,
        execution_authority=AUTHORITY_NONE,
        direction=proposal.direction,
        entry=proposal.entry,
        stop=proposal.stop,
        targets=targets,
        expected_R=proposal.RR,
        plan_expires_at=_iso(proposal.expiry),
        setup_evidence=dict(
            reference_day=str(proposal.reference_day), reference_high=proposal.reference_high,
            reference_low=proposal.reference_low, sweep=proposal.sweep, confirmation=proposal.confirmation,
            volume=proposal.volume, risk_amount=proposal.risk_amount,
        ),
        confirmation_evidence=dict(evidence=proposal.evidence),
        data_provenance=DataProvenance(
            source=proposal.exchange, data_version=_iso(proposal.data_timestamp),
            complete_candle_evidence=True,
        ),
        cost_assumptions=CostAssumptions(
            commission=proposal.estimated_fees, swap_or_funding=funding_cost,
            status=cost_status, missing_fields=missing_cost_fields,
        ),
        timestamps=WatcherOccurrenceTimestamps(
            detected_at=_iso(setup_state.evaluated_at),
            state_entered_at=_iso(setup_state.mss_time or setup_state.sweep_time),
            last_evaluated_at=_iso(setup_state.evaluated_at),
            evidence_candle_close=_iso(proposal.data_timestamp),
            expires_at=_iso(proposal.expiry),
            evidence_complete=("SWEEP", "MSS", "RETEST"),
        ),
        source_module=SOURCE_MODULE, source_record_id=source_record_id,
        reasons=reasons,
    )
