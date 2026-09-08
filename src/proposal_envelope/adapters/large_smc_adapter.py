"""Adapter, not a rewrite: proposals.models.SMCTradeProposal -> CanonicalProposal.

Reads ONLY fields already present on SMCTradeProposal (see src/proposals/models.py's own
docstring: "DETECTION and PROPOSAL are kept strictly separate ... this module never
redetects anything"). No behavior change to proposals/*: this adapter is a pure, one-way
mapping function with no side effects on the source object or the packages that produce
it.

Large-SMC's own strategy id is ST_LARGE_SMC_V1 (see
performance/adapters/large_smc_adapter.py, the only other place this repo already names
it) -- proposals.models.SMCTradeProposal itself carries no strategy_id field (single
strategy per module, so it was never modeled there), so this adapter supplies the
constant explicitly rather than inventing a synthesized one from proposal data.

SMCTradeProposal has no explicit stop_loss/target/expected_R fields (verified: none exist
anywhere in src/proposals/*.py). Its deterministic invalidation_price is the closest
strategy-owned analog to a risk boundary and is mapped to `stop` accordingly; targets and
expected_R stay empty/None -- per Workstream 0 ("direction, entry, stop, targets, expected
R, and expiry only when strategy-owned"), a field this strategy layer never computes must
never be synthesized here.
"""
from __future__ import annotations

from typing import Optional

from proposals.models import (
    LIFECYCLE_EXPIRED,
    LIFECYCLE_INVALIDATED,
    STATUS_ENTRY_CANDIDATE_INVALIDATED,
    SMCTradeProposal,
)

from ..models import (
    AUTHORITY_NONE,
    CanonicalProposal,
    CostAssumptions,
    DataProvenance,
    PROPOSAL_EXPIRED,
    PROPOSAL_INVALIDATED,
    PROPOSAL_READY,
    WATCHER_EXPIRED,
    WATCHER_INVALIDATED,
    WATCHER_SETUP_QUALIFIED,
    WatcherOccurrenceTimestamps,
    blocked_envelope,
)

SOURCE_MODULE = "proposals.models.SMCTradeProposal"
LARGE_SMC_STRATEGY_ID = "ST_LARGE_SMC_V1"


def _required_fields_present(proposal: SMCTradeProposal) -> Optional[str]:
    """Returns None if every field a PROPOSAL_READY envelope requires is present on the
    source object, else the reason_code identifying the first missing one -- Workstream
    0's own rule: a missing required field maps to BLOCKED, never a partial READY."""
    if not proposal.direction:
        return "MISSING_DIRECTION"
    if proposal.entry_reference is None:
        return "MISSING_ENTRY_REFERENCE"
    if proposal.invalidation_price is None:
        return "MISSING_INVALIDATION_PRICE"
    if not proposal.symbol:
        return "MISSING_SYMBOL"
    return None


def to_canonical_proposal(proposal: SMCTradeProposal) -> CanonicalProposal:
    """Lossless mapping. Never recomputes combination/entry_condition/maneuver/
    invalidation -- those are copied verbatim into setup_evidence/confirmation_evidence
    exactly as SMCTradeProposal already carries them."""
    if proposal.status == STATUS_ENTRY_CANDIDATE_INVALIDATED or proposal.lifecycle == LIFECYCLE_INVALIDATED:
        return CanonicalProposal(
            proposal_envelope_id=f"SMC:{proposal.proposal_id}",
            strategy_id=LARGE_SMC_STRATEGY_ID, strategy_version="",  # SMCTradeProposal has no strategy-semantic version field; proposal.version is its own schema id, preserved separately below
            market="FX", symbol=proposal.symbol,
            watcher_state=WATCHER_INVALIDATED, proposal_state=PROPOSAL_INVALIDATED,
            execution_authority=AUTHORITY_NONE,
            direction=proposal.direction,
            confirmation_evidence=dict(
                invalidation_state=proposal.invalidation_state,
                invalidation_price=proposal.invalidation_price,
                invalidation_source_type=proposal.invalidation_source_type,
                invalidation_reason=proposal.invalidation_reason,
                invalidation_trigger=proposal.invalidation_trigger,
            ),
            source_module=SOURCE_MODULE, source_record_id=proposal.proposal_id,
            reasons=(proposal.invalidation_reason,) if proposal.invalidation_reason else (),
        )

    if proposal.lifecycle == LIFECYCLE_EXPIRED:
        return CanonicalProposal(
            proposal_envelope_id=f"SMC:{proposal.proposal_id}",
            strategy_id=LARGE_SMC_STRATEGY_ID, strategy_version="",  # SMCTradeProposal has no strategy-semantic version field; proposal.version is its own schema id, preserved separately below
            market="FX", symbol=proposal.symbol,
            watcher_state=WATCHER_EXPIRED, proposal_state=PROPOSAL_EXPIRED,
            execution_authority=AUTHORITY_NONE,
            direction=proposal.direction,
            source_module=SOURCE_MODULE, source_record_id=proposal.proposal_id,
        )

    missing_reason = _required_fields_present(proposal)
    if missing_reason is not None:
        return blocked_envelope(
            source_module=SOURCE_MODULE, source_record_id=proposal.proposal_id or "UNKNOWN",
            symbol=proposal.symbol, strategy_id=LARGE_SMC_STRATEGY_ID,
            # SMCTradeProposal has no strategy-semantic version field.
            strategy_version="", reasons=(missing_reason,),
        )

    return CanonicalProposal(
        proposal_envelope_id=f"SMC:{proposal.proposal_id}",
        strategy_id=LARGE_SMC_STRATEGY_ID, strategy_version="",  # SMCTradeProposal has no strategy-semantic version field; proposal.version is its own schema id, preserved separately below
        market="FX", symbol=proposal.symbol,
        watcher_state=WATCHER_SETUP_QUALIFIED, proposal_state=PROPOSAL_READY,
        execution_authority=AUTHORITY_NONE,
        direction=proposal.direction,
        entry=proposal.entry_reference,
        stop=proposal.invalidation_price,  # closest strategy-owned risk-boundary analog -- see module docstring
        targets=(),  # SMCTradeProposal defines no target field -- never synthesized
        expected_R=None,  # SMCTradeProposal defines no expected_R field -- never synthesized
        setup_evidence=dict(
            combination=proposal.combination, entry_condition=proposal.entry_condition,
            maneuver=proposal.maneuver, entry_type=proposal.entry_type,
            entry_low=proposal.entry_low, entry_high=proposal.entry_high,
            missing_conditions=proposal.missing_conditions,
        ),
        market_context_evidence=dict(
            reference_timeframe=proposal.reference_timeframe,
            check_timeframe=proposal.check_timeframe,
            confirmation_timeframe=proposal.confirmation_timeframe,
            execution_timeframe=proposal.execution_timeframe,
            market_map_snapshot_id=proposal.market_map_snapshot_id,
            snapshot_id=proposal.snapshot_id,
        ),
        confirmation_evidence=dict(evidence=proposal.evidence),
        data_provenance=DataProvenance(
            source="MT5", complete_candle_evidence=bool(proposal.snapshot_time),
        ),
        cost_assumptions=CostAssumptions(),  # Large-SMC proposal layer models no costs -- never invented
        timestamps=WatcherOccurrenceTimestamps(
            detected_at=proposal.snapshot_time,
            state_entered_at=proposal.snapshot_time,
            last_evaluated_at=proposal.snapshot_time,
            evidence_candle_close=proposal.snapshot_time,
            evidence_complete=tuple(sorted(proposal.evidence.keys())) if proposal.evidence else (),
            next_required_evidence=proposal.missing_conditions,
        ),
        source_module=SOURCE_MODULE, source_record_id=proposal.proposal_id,
    )
