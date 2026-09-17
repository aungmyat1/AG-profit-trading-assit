"""Adapter, not a rewrite: large_smc_research.decision.LargeSMCResearchDecision (the
canonical ST_LARGE_SMC_V1 research engine's own output, src/large_smc_research/engine.py)
-> CanonicalProposal. AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_READINESS_V1_2, WP8-A.

Distinct from the pre-existing src/proposal_envelope/adapters/large_smc_adapter.py,
which -- despite its name -- adapts a DIFFERENT strategy's output (proposals.models.
SMCTradeProposal, sourced from the separate SMC_CONDITIONAL_ENTRY_V2 live watcher), not
this engine's LargeSMCResearchDecision (see AG_MULTI_STRATEGY_PROPOSAL_AND_WATCH_
READINESS_V1_2 WP0 audit). That file is left untouched -- it still correctly serves its
own pipeline; this is a new, separate adapter for the actual ST_LARGE_SMC_V1 engine.

Reads ONLY fields already computed by LargeSMCResearchEngine.evaluate() (direction,
entry_price, structural_invalidation_price, simulated_broker_stop, target_price, ...);
never re-runs the engine, never adds new SMC rules. Every field is copied verbatim.

state == RESEARCH_QUALIFIED with complete geometry (entry/stop/target/direction all
populated) is the only path that reaches PROPOSAL_READY -- the engine's own fail-closed
guarantee (decision.py: these fields are None outside RESEARCH_QUALIFIED) means this
adapter never needs to re-validate completeness, only translate it.

Friction/cost: ST_LARGE_SMC_V1's EURUSD friction_policy_contract.json is currently
`status: PROPOSED`, not `SIGNED` (artifacts/validation/ST_LARGE_SMC_V1/
EURUSD_ADMISSION_CONTRACTS/friction_policy_contract.json) -- cost_assumptions.status is
therefore always NOT_INCLUDED here, never fabricated as ITEMIZED, regardless of engine
state.

execution_authority is always AUTHORITY_NONE -- strategies/ST_LARGE_SMC_V1.yaml's own
`authority`/`execution` blocks (proposal_generation_authorized=false,
demo_authorized=false, live_authorized=false, mode=ADVISORY_ONLY) are read via
resolve_strategy_authority, never overridden.
"""
from __future__ import annotations

from typing import Optional

from proposal_envelope.strategy_authority import StrategyAuthority

from ..models import (
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PLATFORM_STATE_WATCH_DETECTED,
    PROPOSAL_BLOCKED,
    PROPOSAL_EXPIRED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_INVALIDATED,
    PROPOSAL_NO_TRADE,
    PROPOSAL_READY,
    WATCHER_CONTEXT_IDENTIFIED,
    WATCHER_EXPIRED,
    WATCHER_INVALIDATED,
    WATCHER_SETUP_QUALIFIED,
    WatcherOccurrenceTimestamps,
)

SOURCE_MODULE = "large_smc_research.decision.LargeSMCResearchDecision"

_NOT_INCLUDED_COST = CostAssumptions(
    status="NOT_INCLUDED",
    missing_fields=("spread", "commission", "slippage"),
)

_STATE_TO_PROPOSAL_STATE = {
    "NO_TRADE": PROPOSAL_NO_TRADE,
    "EXPIRED": PROPOSAL_EXPIRED,
    "INVALIDATED": PROPOSAL_INVALIDATED,
    "BLOCKED": PROPOSAL_BLOCKED,
    "DATA_ERROR": PROPOSAL_INCOMPLETE,
}

_STATE_TO_WATCHER_STATE = {
    "WATCH": WATCHER_CONTEXT_IDENTIFIED,
    "NO_TRADE": WATCHER_INVALIDATED,
    "EXPIRED": WATCHER_EXPIRED,
    "INVALIDATED": WATCHER_INVALIDATED,
    "BLOCKED": WATCHER_CONTEXT_IDENTIFIED,
    "DATA_ERROR": WATCHER_CONTEXT_IDENTIFIED,
}


def to_canonical_proposal(decision, strategy_authority: StrategyAuthority) -> CanonicalProposal:
    """`decision` is a large_smc_research.decision.LargeSMCResearchDecision."""
    source_record_id = (
        decision.candidate_occurrence_id or decision.m_candidate_source_id
        or f"{decision.symbol}|{decision.combination}|{decision.evaluation_timestamp}"
    )
    timestamps = WatcherOccurrenceTimestamps(
        detected_at=str(decision.evaluation_timestamp) if decision.evaluation_timestamp else None,
        state_entered_at=str(decision.evaluation_timestamp) if decision.evaluation_timestamp else None,
        last_evaluated_at=str(decision.evaluation_timestamp) if decision.evaluation_timestamp else None,
    )
    base_kwargs = dict(
        proposal_envelope_id=f"LSMC:{source_record_id}",
        strategy_id=decision.strategy_id,
        strategy_version=decision.strategy_version,
        market="FX",
        venue="MT5_BROKER",
        contract_type="SPOT_FX",
        symbol=decision.symbol,
        execution_authority=AUTHORITY_NONE,
        direction=decision.direction,
        data_provenance=DataProvenance(source="MT5"),
        cost_assumptions=_NOT_INCLUDED_COST,
        timestamps=timestamps,
        source_module=SOURCE_MODULE,
        source_record_id=source_record_id,
        reasons=tuple(decision.reason_codes),
        economic_edge_established=strategy_authority.economic_edge_established,
        demo_eligible=strategy_authority.demo_eligible,
        demo_authorized=strategy_authority.demo_authorized,
        live_authorized=strategy_authority.live_authorized,
        proposal_only=strategy_authority.proposal_only,
        execution_eligible=strategy_authority.execution_eligible,
        broker_mutation_blocked=strategy_authority.broker_mutation_blocked,
        lifecycle_stage=strategy_authority.lifecycle_stage,
    )

    has_complete_geometry = (
        decision.direction is not None and decision.entry_price is not None
        and decision.simulated_broker_stop is not None and decision.target_price is not None
    )

    if decision.state == "RESEARCH_QUALIFIED" and has_complete_geometry:
        return CanonicalProposal(
            watcher_state=WATCHER_SETUP_QUALIFIED,
            proposal_state=PROPOSAL_READY,
            entry=decision.entry_price,
            stop=decision.simulated_broker_stop,
            targets=(decision.target_price,),
            setup_evidence=dict(
                combination=decision.combination, entry_condition=decision.entry_condition,
                maneuver=decision.maneuver, target_tier=decision.target_tier,
                target_type=decision.target_type, structural_invalidation_price=decision.structural_invalidation_price,
            ),
            **base_kwargs,
        )

    if decision.state == "WATCH":
        return CanonicalProposal(
            watcher_state=WATCHER_CONTEXT_IDENTIFIED,
            proposal_state=PROPOSAL_INCOMPLETE,
            setup_evidence=dict(combination=decision.combination, entry_condition=decision.entry_condition,
                                 maneuver=decision.maneuver, missing_conditions=list(decision.missing_conditions),
                                 platform_state=PLATFORM_STATE_WATCH_DETECTED),
            **base_kwargs,
        )

    proposal_state = _STATE_TO_PROPOSAL_STATE.get(decision.state, PROPOSAL_INCOMPLETE)
    watcher_state = _STATE_TO_WATCHER_STATE.get(decision.state, WATCHER_CONTEXT_IDENTIFIED)
    return CanonicalProposal(
        watcher_state=watcher_state,
        proposal_state=proposal_state,
        setup_evidence=dict(combination=decision.combination, missing_conditions=list(decision.missing_conditions)),
        **base_kwargs,
    )
