"""Adapter, not a rewrite: session_sweep_continuation.replay.ReplayResult (one entry of
its `accepted_setups`, produced by the canonical, unmodified `run_replay`) ->
CanonicalProposal. AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2, WP1/WP4/WP8-A.

Reads ONLY fields already computed by run_replay (setup_model/direction/entry_time/
entry_price/stop_price/risk_pct/outcome, all in the accepted_setups dict; see
session_sweep_continuation/replay.py:362-368); never re-runs the strategy, never touches
S1/S2/S3 semantics, and adds no new stop/target/risk logic. execution_authority is
always AUTHORITY_NONE -- ST_SESSION_SWEEP_CONTINUATION_V1 is OFFLINE_RESEARCH
(config/governance/strategy_lifecycle.yaml) and this adapter never overrides that.

Each accepted setup IS a real S1/S2/S3 trigger (run_replay only appends to
accepted_setups after passing regime/BOS/stop-geometry/risk-allocation gates) -- one
CanonicalProposal per accepted setup, proposal_state=PROPOSAL_READY. An empty
accepted_setups sequence (no trigger this cycle) produces no proposals at all -- the
caller (session_sweep_continuation_pilot.pipeline) never fabricates one.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional

from proposal_envelope.strategy_authority import StrategyAuthority

from ..models import (
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PROPOSAL_READY,
    WATCHER_SETUP_QUALIFIED,
    WatcherOccurrenceTimestamps,
)

SOURCE_MODULE = "session_sweep_continuation.replay.ReplayResult.accepted_setups"

_COST_STATUS_MAP = {
    "KNOWN": "ITEMIZED",
    "MODELED": "MIXED",
    "UNAVAILABLE": "NOT_INCLUDED",
}


def _cost_assumptions(outcome: Dict[str, Any]) -> CostAssumptions:
    cost_status = outcome.get("cost_status", "UNAVAILABLE")
    missing = tuple(
        name for name in ("spread_cost_R", "commission_cost_R", "slippage_cost_R")
        if outcome.get(name) is None
    )
    return CostAssumptions(
        spread=outcome.get("spread_cost_R"),
        commission=outcome.get("commission_cost_R"),
        slippage=outcome.get("slippage_cost_R"),
        status=_COST_STATUS_MAP.get(cost_status, "NOT_INCLUDED"),
        missing_fields=missing,
    )


def to_canonical_proposal(
    accepted_setup: Dict[str, Any],
    *,
    symbol: str,
    session_pair_id: str,
    trading_date: date,
    campaign_id: Optional[str],
    strategy_authority: StrategyAuthority,
) -> CanonicalProposal:
    """`accepted_setup` is one element of ReplayResult.accepted_setups (a plain dict --
    see run_replay's own construction at replay.py:362-368). `campaign_id` identifies
    the SSC campaign this entry belongs to (None only if the caller has no campaign
    object, which should not happen for an accepted setup)."""
    setup_model = accepted_setup["setup_model"]
    entry_time = accepted_setup["entry_time"]
    source_record_id = f"{symbol}|{session_pair_id}|{trading_date}|{campaign_id}|{setup_model}|{entry_time}"
    outcome = accepted_setup.get("outcome") or {}

    return CanonicalProposal(
        proposal_envelope_id=f"SSC:{source_record_id}",
        strategy_id=strategy_authority.strategy_id,
        strategy_version=strategy_authority.semantic_version,
        market="FX",
        venue="MT5_BROKER",
        contract_type="SPOT_FX",
        symbol=symbol,
        watcher_state=WATCHER_SETUP_QUALIFIED,
        proposal_state=PROPOSAL_READY,
        execution_authority=AUTHORITY_NONE,
        direction=accepted_setup.get("direction"),
        entry=accepted_setup.get("entry_price"),
        stop=accepted_setup.get("stop_price"),
        targets=(),  # SSC's target is R-multiple/state-machine-driven (partial + runner),
        # not a single static price -- see trade_management config; never fabricated here.
        expected_R=None,
        setup_evidence=dict(
            setup_model=setup_model,
            session_pair=session_pair_id,
            trading_date=str(trading_date),
            campaign_id=campaign_id,
            risk_pct=accepted_setup.get("risk_pct"),
            fill_precision=accepted_setup.get("fill_precision"),
            terminal_state=outcome.get("terminal_state"),
            gross_R=outcome.get("gross_R"),
            net_R=outcome.get("net_R"),
        ),
        data_provenance=DataProvenance(source="MT5"),
        cost_assumptions=_cost_assumptions(outcome),
        timestamps=WatcherOccurrenceTimestamps(
            detected_at=str(entry_time), state_entered_at=str(entry_time),
            last_evaluated_at=str(entry_time),
        ),
        source_module=SOURCE_MODULE, source_record_id=source_record_id,
        economic_edge_established=strategy_authority.economic_edge_established,
        demo_eligible=strategy_authority.demo_eligible,
        demo_authorized=strategy_authority.demo_authorized,
        live_authorized=strategy_authority.live_authorized,
        proposal_only=strategy_authority.proposal_only,
        execution_eligible=strategy_authority.execution_eligible,
        broker_mutation_blocked=strategy_authority.broker_mutation_blocked,
        lifecycle_stage=strategy_authority.lifecycle_stage,
    )
