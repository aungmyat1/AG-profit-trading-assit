"""ProposalEligibility (WP-3): the boundary between OpportunityCandidate and

    OpportunityCandidate
            v
    ProposalEligibilityDecision  (THIS module)
            v
    CanonicalProposal   (WP-4, out of scope here)

Answers exactly one question -- "may this candidate proceed to proposal
formation?" -- and nothing else. In particular it never decides:

  - whether the strategy is economically profitable (no such authority exists
    anywhere in the repo -- see proposal_envelope.strategy_authority's own
    economic_edge_established note);
  - whether the owner approves the trade;
  - whether Demo or Live execution is authorized;
  - whether an MT5 order should be sent.

`ELIGIBLE` here is not `OWNER_APPROVED`, not `EXECUTION_AUTHORIZED`, and not
`ECONOMICALLY_QUALIFIED` -- see docs/v2/AG_V2_OPPORTUNITY_STRATEGY_MODEL.md,
"Validation independence".

Reuses existing canonical authority rather than duplicating it:

- `opportunity.contracts.ProposalEligibilityDecision` is the existing output
  contract (unmodified) -- this module only supplies the evaluator that was
  missing for it.
- `opportunity.engine.TERMINAL_OUTCOMES` is the existing terminal-outcome
  authority (Safety Invariant #9) -- never redefined here.
- `opportunity.contracts.synthetic_or_replay_block_reasons` is the existing
  synthetic/replay firewall -- called with `broker_bound=True` because
  proceeding to proposal formation is specifically the broker-bound question.
- `opportunity.registry_binding.StrategyBinding` is read for
  `opportunity_authority` (registry `registered`) and
  `live_observation_supported` (registry `active`) ONLY. `binding.dispatchable`
  / `binding.proposal_authority` are deliberately NOT used: those fields
  describe `strategy_manager.manager.evaluate()` dispatchability, which today
  is true only for SESSION_TRADE_V1 (see registry_binding.py's own docstring)
  and is a different call path than ST_ASIAN_SWEEP_5R_V1's actual operational
  route (scripts/run_fx_cycle_once.py -> run_post_asian_pilot.py ->
  strategy_engine.loader.load_strategy(), established by WP-2). Gating on
  `.dispatchable` would make the one strategy WP-3 needs to support always
  ineligible.

Readiness rule (P4/P7): a candidate may only become ELIGIBLE once it carries a
complete, strategy-produced trade plan -- `outcome == ACTIVE`, `stage` has
reached at least ENTRY_CONFIRMED (the funnel point at which
docs/v2/AG_V2_OPPORTUNITY_STRATEGY_MODEL.md's strategy examples place a fired
trigger), AND `geometry` is fully populated (direction/entry/invalidation all
present). The last condition matters independently of stage: per
docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md, SSC's own adapter reaches
ENTRY_CONFIRMED mid-campaign (after only one entry, well before its own
COMPLETE/OPPORTUNITY_READY checkpoint) and never populates entry/invalidation
geometry at all (known SSC-adapter debt) -- stage alone would wrongly promote
that mid-campaign state. Requiring populated geometry is what actually ties
this decision to "a complete, strategy-owned opportunity exists", not just a
stage label, and is strategy-neutral: it holds for Asian Sweep
(`asian_sweep_adapter._project_ready` only ever returns non-None geometry once
`PostAsianDecision.status == READY`) without hardcoding anything about Asian
Sweep here.

Pure function: no I/O, no MT5/execution import (see
tests/test_opportunity_import_boundaries.py, which already covers this whole
package), no CandidateStore mutation, no CanonicalProposal construction, no
ProposalLedger write. The caller supplies `binding` (already resolved, e.g. via
`registry_binding.resolve_strategy_binding`) and an explicit `evaluated_at`; the
function itself performs no registry/file/clock access.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .contracts import (
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    ELIGIBILITY_INCOMPLETE,
    OpportunityCandidate,
    ProposalEligibilityDecision,
    synthetic_or_replay_block_reasons,
)
from .engine import TERMINAL_OUTCOMES
from .registry_binding import StrategyBinding
from .stages import (
    FUNNEL_STAGES,
    OUTCOME_ACTIVE,
    OUTCOME_EXPIRED,
    OUTCOME_WAIT,
    STAGE_ENTRY_CONFIRMED,
)

# ---------------------------------------------------------------------------
# Machine-readable reason codes. Every one maps to a condition this repository
# actually enforces (see module docstring for each authority) -- no reason is
# invented for a check the repository does not itself perform.
# ---------------------------------------------------------------------------

REASON_STRATEGY_IDENTITY_MISMATCH = "STRATEGY_IDENTITY_MISMATCH"
REASON_STRATEGY_NOT_REGISTERED = "STRATEGY_NOT_REGISTERED"
REASON_STRATEGY_NOT_OPERATIONALLY_ENABLED = "STRATEGY_NOT_OPERATIONALLY_ENABLED"
REASON_TERMINAL_CANDIDATE = "TERMINAL_CANDIDATE"
REASON_EXPIRED = "EXPIRED"
REASON_NOT_YET_READY = "NOT_YET_READY"
REASON_MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
REASON_UNSUPPORTED_STATE = "UNSUPPORTED_STATE"

_ENTRY_CONFIRMED_INDEX = FUNNEL_STAGES.index(STAGE_ENTRY_CONFIRMED)


def _decision(
    candidate: OpportunityCandidate, status: str, reason_codes, evaluated_at: datetime,
) -> ProposalEligibilityDecision:
    return ProposalEligibilityDecision(
        candidate_id=candidate.candidate_id,
        status=status,
        reason_codes=tuple(reason_codes),
        evaluated_at=evaluated_at,
    )


def evaluate_proposal_eligibility(
    candidate: OpportunityCandidate,
    binding: StrategyBinding,
    *,
    evaluated_at: Optional[datetime] = None,
) -> ProposalEligibilityDecision:
    """May `candidate` proceed to proposal formation? Deterministic for the same
    `(candidate, binding, evaluated_at)` triple -- no clock/registry/file access
    performed inside this function itself."""
    now = evaluated_at if evaluated_at is not None else datetime.now(timezone.utc)

    if candidate.strategy_id != binding.strategy_id:
        return _decision(candidate, ELIGIBILITY_BLOCKED, (REASON_STRATEGY_IDENTITY_MISMATCH,), now)

    registry_reasons = []
    if not binding.opportunity_authority:
        registry_reasons.append(REASON_STRATEGY_NOT_REGISTERED)
    if not binding.live_observation_supported:
        registry_reasons.append(REASON_STRATEGY_NOT_OPERATIONALLY_ENABLED)
    if registry_reasons:
        return _decision(candidate, ELIGIBILITY_BLOCKED, registry_reasons, now)

    if candidate.outcome in TERMINAL_OUTCOMES:
        reason = REASON_EXPIRED if candidate.outcome == OUTCOME_EXPIRED else REASON_TERMINAL_CANDIDATE
        return _decision(candidate, ELIGIBILITY_BLOCKED, (reason,), now)

    if candidate.expires_at is not None and candidate.expires_at <= now:
        return _decision(candidate, ELIGIBILITY_BLOCKED, (REASON_EXPIRED,), now)

    firewall_reasons = synthetic_or_replay_block_reasons(candidate.market_data_mode, broker_bound=True)
    if firewall_reasons:
        return _decision(candidate, ELIGIBILITY_BLOCKED, firewall_reasons, now)

    if candidate.outcome != OUTCOME_ACTIVE:
        # WAIT is the only non-terminal outcome left at this point (TERMINAL_OUTCOMES
        # already excluded above) -- anything else would be a FUNNEL_OUTCOMES addition
        # this module has no documented projection for yet.
        if candidate.outcome != OUTCOME_WAIT:
            return _decision(candidate, ELIGIBILITY_BLOCKED, (REASON_UNSUPPORTED_STATE,), now)
        return _decision(candidate, ELIGIBILITY_INCOMPLETE, (REASON_NOT_YET_READY,), now)

    if FUNNEL_STAGES.index(candidate.stage) < _ENTRY_CONFIRMED_INDEX:
        return _decision(candidate, ELIGIBILITY_INCOMPLETE, (REASON_NOT_YET_READY,), now)

    geometry = candidate.geometry
    if (
        geometry is None
        or geometry.direction is None
        or geometry.entry is None
        or geometry.invalidation is None
    ):
        return _decision(candidate, ELIGIBILITY_INCOMPLETE, (REASON_MISSING_REQUIRED_INPUT,), now)

    return _decision(candidate, ELIGIBILITY_ELIGIBLE, (), now)
