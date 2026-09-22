"""WP-4 bridge: opportunity.contracts.OpportunityCandidate -> CanonicalProposal.

    OpportunityCandidate
            v
    ProposalEligibilityDecision   (opportunity.proposal_eligibility, WP-3, REUSED here
                                    verbatim -- this module never re-implements any of
                                    its rules)
            v
    ELIGIBLE?
       NO  -> no PROPOSAL_READY envelope (BLOCKED / INCOMPLETE, see below)
       YES
            v
    CanonicalProposal (proposal_envelope.models, PROPOSAL_READY)

Unlike the existing per-family adapters (fx_adapter, ssc_adapter, large_smc_adapter,
large_smc_research_adapter), which each translate a STRATEGY-NATIVE decision object,
this adapter's input is already the strategy-neutral `OpportunityCandidate`. It is
therefore the one bridge every opportunity-domain strategy can share -- it adds no new
detection logic and duplicates no per-family mapping.

The caller supplies the eligibility decision already resolved by
`opportunity.proposal_eligibility.evaluate_proposal_eligibility` -- this module does not
call it internally and does not re-derive ELIGIBLE/BLOCKED/INCOMPLETE from the candidate
itself. That keeps WP-3's eligibility rules as the single authority for "may this
candidate proceed"; this module only ever answers "what does that decision look like as
a CanonicalProposal".

ELIGIBLE != proposal persisted, != risk approved, != owner confirmed, != execution
authorized, != Demo authorized, != Live authorized, != broker order. This module never
writes to a ledger, never sizes a position, never imports execution/mt5. It performs NO
registry/file/clock access itself -- `strategy_authority`, like `eligibility`, is
supplied already-resolved by the caller (see proposal_envelope.strategy_authority);
omitting it leaves every governance field at CanonicalProposal's own safe default
(economic_edge_established=False, demo_eligible=False, demo_authorized=False,
live_authorized=False, execution_eligible=False) rather than inferring one.
`execution_authority` is always AUTHORITY_NONE regardless of what `strategy_authority`
reports -- exactly like every other adapter in this package, assigning anything else
would be inventing an authorization decision this module has no evidence for.

Identity: `candidate.occurrence_id` (opportunity-domain, already the authoritative
"which underlying setup occurrence is this" key -- see contracts.OpportunityCandidate)
is reused verbatim to compose `proposal_envelope_id`, namespaced "OPP:" so it can never
collide with another family's prefix ("FX:", "LSMC:", "FXOCC:", "BLOCKED:"). The SAME
occurrence therefore keeps the SAME proposal_envelope_id across BLOCKED/INCOMPLETE/READY
transitions of its own lifecycle -- deterministic for the same
(candidate.strategy_id, candidate.occurrence_id) pair, and different whenever either
differs. `source_record_id` is `candidate.candidate_id` (this specific candidate
object's own identity), distinct from the occurrence it belongs to, matching every
other adapter's source_module/source_record_id provenance discipline.

Trade-plan fields (entry/stop/targets/expected_R) are populated ONLY on the ELIGIBLE ->
PROPOSAL_READY path, matching Workstream 0's "never a partial PROPOSAL_READY" rule --
even if `candidate.geometry` happens to carry partial values on a BLOCKED/INCOMPLETE
candidate, they are surfaced only inside `setup_evidence` (informational), never as the
top-level trade-plan fields.

Pure function: no I/O, no MT5/execution import, no wall clock, no CandidateStore
mutation, no ProposalLedger write (see test_opportunity_proposal_bridge.py, which proves
this both statically and behaviorally). `contract_type` and `timestamps.state_entered_at`
stay None: OpportunityCandidate carries no contract_type field, and the funnel
deliberately keeps no `funnel_history` (contracts.py's own docstring) for this module to
read a stage-entry timestamp from without adding I/O -- both are MISSING, never
fabricated.
"""
from __future__ import annotations

from typing import Optional

from opportunity.contracts import (
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_INCOMPLETE,
    OpportunityCandidate,
    ProposalEligibilityDecision,
    REPLAY_DATA_NOT_BROKER_EXECUTABLE,
    SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE,
)
from opportunity.proposal_eligibility import (
    REASON_EXPIRED,
    REASON_TERMINAL_CANDIDATE,
)
from opportunity.stages import (
    STAGE_CONTEXT_VALID,
    STAGE_ENTRY_CONFIRMED,
    STAGE_LOCATION_VALID,
    STAGE_MARKET_ELIGIBLE,
    STAGE_OPPORTUNITY_READY,
    STAGE_SETUP_DETECTED,
    STAGE_TRIGGER_ARMED,
)
from proposal_envelope.strategy_authority import StrategyAuthority

from ..models import (
    AUTHORITY_NONE,
    CanonicalProposal,
    DataProvenance,
    PROPOSAL_BLOCKED,
    PROPOSAL_INCOMPLETE,
    PROPOSAL_READY,
    WATCHER_CONTEXT_IDENTIFIED,
    WATCHER_DATA_BLOCKED,
    WATCHER_EXPIRED,
    WATCHER_INVALIDATED,
    WATCHER_LIQUIDITY_SWEPT,
    WATCHER_POI_APPROACH,
    WATCHER_SCANNING,
    WATCHER_SETUP_QUALIFIED,
    WATCHER_STRUCTURE_CONFIRMING,
    WatcherOccurrenceTimestamps,
)

SOURCE_MODULE = "opportunity.contracts.OpportunityCandidate"
BRIDGE_VERSION = "AG_OPPORTUNITY_PROPOSAL_BRIDGE_V1"

# Coarse, monotonic, conservative mapping from the strategy-neutral funnel stage
# (opportunity.stages) to the proposal envelope's own watcher_state vocabulary
# (proposal_envelope.models). The two enums were authored independently for different
# worksteams and are not in 1:1 semantic correspondence -- this mapping never claims
# more progress than the funnel stage's evidence supports, and WATCHER_SETUP_QUALIFIED
# is deliberately withheld here (reserved for the ELIGIBLE/PROPOSAL_READY path only), so
# an INCOMPLETE candidate that has reached ENTRY_CONFIRMED/OPPORTUNITY_READY without
# complete geometry is never presented as "qualified".
_STAGE_TO_WATCHER_STATE_INCOMPLETE = {
    STAGE_MARKET_ELIGIBLE: WATCHER_SCANNING,
    STAGE_CONTEXT_VALID: WATCHER_CONTEXT_IDENTIFIED,
    STAGE_LOCATION_VALID: WATCHER_POI_APPROACH,
    STAGE_SETUP_DETECTED: WATCHER_LIQUIDITY_SWEPT,
    STAGE_TRIGGER_ARMED: WATCHER_STRUCTURE_CONFIRMING,
    STAGE_ENTRY_CONFIRMED: WATCHER_STRUCTURE_CONFIRMING,
    STAGE_OPPORTUNITY_READY: WATCHER_STRUCTURE_CONFIRMING,
}

_FIREWALL_REASONS = frozenset(
    {SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE, REPLAY_DATA_NOT_BROKER_EXECUTABLE}
)


class BridgeIdentityMismatch(ValueError):
    """`eligibility.candidate_id` does not match `candidate.candidate_id`. Fail closed --
    this module never silently attaches an eligibility decision to an unrelated
    candidate (mirrors fx_adapter's own TRADE_PROPOSAL_IDENTITY_MISMATCH discipline)."""


class UnsupportedEligibilityStatus(ValueError):
    """Defensive fail-closed branch: `ProposalEligibilityDecision.__post_init__` already
    enum-validates `status`, so this is unreachable via normal construction. Guards the
    same way `opportunity.proposal_eligibility`'s WP-3 R1 remediation guards an unknown
    `stage` -- if this module's own assumptions about the eligibility contract ever
    change, no proposal is silently formed for an unrecognized status."""


def _iso(value) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _proposal_envelope_id(candidate: OpportunityCandidate) -> str:
    return f"OPP:{candidate.strategy_id}:{candidate.occurrence_id}"


def _blocked_watcher_state(
    candidate: OpportunityCandidate, eligibility: ProposalEligibilityDecision,
) -> str:
    reasons = eligibility.reason_codes
    if REASON_EXPIRED in reasons:
        return WATCHER_EXPIRED
    if REASON_TERMINAL_CANDIDATE in reasons:
        return WATCHER_INVALIDATED
    if any(r in _FIREWALL_REASONS for r in reasons):
        return WATCHER_DATA_BLOCKED
    return _STAGE_TO_WATCHER_STATE_INCOMPLETE.get(candidate.stage, WATCHER_SCANNING)


def _base_kwargs(
    candidate: OpportunityCandidate,
    strategy_authority: Optional[StrategyAuthority],
    data_provenance: DataProvenance,
) -> dict:
    kwargs = dict(
        proposal_envelope_id=_proposal_envelope_id(candidate),
        identity_version=BRIDGE_VERSION,
        strategy_id=candidate.strategy_id,
        strategy_version=candidate.strategy_version,
        market=candidate.market,
        venue=candidate.venue,
        symbol=candidate.symbol,
        execution_authority=AUTHORITY_NONE,
        market_context_evidence=dict(candidate.context_evidence),
        confirmation_evidence=dict(candidate.trigger_evidence),
        data_provenance=data_provenance,
        timestamps=WatcherOccurrenceTimestamps(
            detected_at=_iso(candidate.detected_at),
            last_evaluated_at=_iso(candidate.last_evaluated_at),
            expires_at=_iso(candidate.expires_at),
        ),
        source_module=SOURCE_MODULE,
        source_record_id=candidate.candidate_id,
    )
    if strategy_authority is not None:
        kwargs.update(
            economic_edge_established=strategy_authority.economic_edge_established,
            demo_eligible=strategy_authority.demo_eligible,
            demo_authorized=strategy_authority.demo_authorized,
            live_authorized=strategy_authority.live_authorized,
            proposal_only=strategy_authority.proposal_only,
            execution_eligible=strategy_authority.execution_eligible,
            broker_mutation_blocked=strategy_authority.broker_mutation_blocked,
            lifecycle_stage=strategy_authority.lifecycle_stage,
        )
    return kwargs


def to_canonical_proposal(
    candidate: OpportunityCandidate,
    eligibility: ProposalEligibilityDecision,
    *,
    strategy_authority: Optional[StrategyAuthority] = None,
) -> CanonicalProposal:
    """Deterministic for the same `(candidate, eligibility, strategy_authority)` triple.
    No registry/file/clock access performed here -- both `eligibility` and
    `strategy_authority` are caller-supplied, already-resolved authorities."""
    if eligibility.candidate_id != candidate.candidate_id:
        raise BridgeIdentityMismatch(
            f"eligibility.candidate_id={eligibility.candidate_id!r} does not match "
            f"candidate.candidate_id={candidate.candidate_id!r}"
        )

    data_provenance = DataProvenance(
        source=candidate.data_lineage or candidate.venue,
        market_data_mode=candidate.market_data_mode,
        complete_candle_evidence=(eligibility.status == ELIGIBILITY_ELIGIBLE),
    )
    base_kwargs = _base_kwargs(candidate, strategy_authority, data_provenance)
    geometry = candidate.geometry
    setup_evidence = dict(candidate.setup_evidence)

    if eligibility.status == ELIGIBILITY_ELIGIBLE:
        # WP-3 already guarantees geometry.direction/entry/invalidation are all
        # non-None for an ELIGIBLE decision (opportunity.proposal_eligibility's own
        # readiness rule) -- this branch only translates that guarantee, never
        # re-validates it.
        return CanonicalProposal(
            watcher_state=WATCHER_SETUP_QUALIFIED,
            proposal_state=PROPOSAL_READY,
            direction=geometry.direction,
            entry=geometry.entry,
            stop=geometry.invalidation,
            targets=tuple(geometry.targets),
            expected_R=geometry.estimated_rr,
            plan_expires_at=_iso(candidate.expires_at),
            setup_evidence=setup_evidence,
            reasons=eligibility.reason_codes,
            **base_kwargs,
        )

    if geometry is not None:
        setup_evidence = dict(
            setup_evidence,
            candidate_geometry_direction=geometry.direction,
            candidate_geometry_entry=geometry.entry,
            candidate_geometry_invalidation=geometry.invalidation,
        )

    if eligibility.status == ELIGIBILITY_INCOMPLETE:
        return CanonicalProposal(
            watcher_state=_STAGE_TO_WATCHER_STATE_INCOMPLETE.get(
                candidate.stage, WATCHER_SCANNING
            ),
            proposal_state=PROPOSAL_INCOMPLETE,
            direction=candidate.direction,
            setup_evidence=setup_evidence,
            reasons=eligibility.reason_codes,
            **base_kwargs,
        )

    if eligibility.status == ELIGIBILITY_BLOCKED:
        return CanonicalProposal(
            watcher_state=_blocked_watcher_state(candidate, eligibility),
            proposal_state=PROPOSAL_BLOCKED,
            direction=candidate.direction,
            setup_evidence=setup_evidence,
            reasons=eligibility.reason_codes,
            **base_kwargs,
        )

    raise UnsupportedEligibilityStatus(
        f"no CanonicalProposal mapping for eligibility.status={eligibility.status!r}"
    )
