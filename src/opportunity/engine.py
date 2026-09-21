"""Pure universal opportunity funnel transition engine (V2-2A).

This module intentionally orchestrates the existing V2 contracts and strategy
adapter boundary. It owns no strategy semantics, persistence, proposal formation,
portfolio risk, execution authority, or broker access.

Identity continuity is enforced here whenever a previous OpportunityCandidate is
supplied: strategy id/version, engine version, symbol/market/venue and market-data
mode must remain compatible with the binding/event. This prevents a caller from
reusing a candidate id across unrelated strategy or data authorities.

Restored invariants (re-audit remediation): a semantically equivalent repeated
observation must not mint a new revision/transition (Safety Invariant #8 --
"equivalent normalized semantic input must not create new semantic transitions
merely because the system polled again"), and a candidate that has already
reached a terminal outcome must not be reactivated by ordinary evaluation
(Safety Invariant #9). Both properties existed in the original pure engine and
were dropped when the identity-continuity fix replaced it; this restores them
without reintroducing persistence, a second candidate-identity scheme, or any
change to the identity-continuity behavior verified separately.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional, Tuple

from .adapter import FunnelProjection, StrategyFunnelAdapter
from .contracts import MarketEvent, OpportunityCandidate
from .registry_binding import StrategyBinding
from .stages import (
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_REJECT,
    validate_outcome,
    validate_stage,
)
from .transitions import FunnelState, FunnelTransition

# Sticky by design (Safety Invariant #9): once a candidate's outcome reaches one
# of these, only a new occurrence (new candidate_id, via the persistence/identity
# layer -- out of scope here) can represent a later valid setup. This is the
# same terminal vocabulary stages.py's FUNNEL_OUTCOMES already defines as
# non-recoverable dispositions; it is not a second/competing outcome model.
TERMINAL_OUTCOMES = frozenset(
    {OUTCOME_REJECT, OUTCOME_INVALIDATED, OUTCOME_EXPIRED, OUTCOME_ERROR}
)


class FunnelEngineError(RuntimeError):
    """Base class for fail-closed V2-2A engine failures."""


class AdapterNotSupportedError(FunnelEngineError):
    pass


class AdapterIdentityMismatchError(FunnelEngineError):
    pass


class ObservationIdentityMismatchError(FunnelEngineError):
    pass


class CandidateIdentityMismatchError(FunnelEngineError):
    """Raised when an existing candidate is reused under different authority."""


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _candidate_id(binding: StrategyBinding, event: MarketEvent) -> str:
    return _stable_id(
        "cand",
        {
            "strategy_id": binding.strategy_id,
            "strategy_version": binding.semantic_version,
            "event_id": event.event_id,
            "symbol": event.symbol,
        },
    )


def _transition_id(
    candidate_id: str,
    event: MarketEvent,
    previous_state: FunnelState,
    projection: FunnelProjection,
) -> str:
    return _stable_id(
        "trn",
        {
            "candidate_id": candidate_id,
            "event_id": event.event_id,
            "from_stage": previous_state.stage,
            "from_outcome": previous_state.outcome,
            "from_revision": previous_state.revision,
            "to_stage": projection.stage,
            "to_outcome": projection.outcome,
            "reason_codes": tuple(projection.reason_codes),
        },
    )


def _validate_candidate_continuity(
    candidate: OpportunityCandidate,
    binding: StrategyBinding,
    event: MarketEvent,
) -> None:
    mismatches = []
    if candidate.strategy_id != binding.strategy_id:
        mismatches.append("strategy_id")
    if binding.semantic_version is not None and candidate.strategy_version != binding.semantic_version:
        mismatches.append("strategy_version")
    if binding.engine_version is not None and candidate.strategy_engine_version != binding.engine_version:
        mismatches.append("strategy_engine_version")
    if candidate.symbol != event.symbol:
        mismatches.append("symbol")
    if candidate.market != event.market:
        mismatches.append("market")
    if candidate.venue != event.venue:
        mismatches.append("venue")
    if candidate.market_data_mode != event.market_data_mode:
        mismatches.append("market_data_mode")
    if mismatches:
        raise CandidateIdentityMismatchError(
            "existing candidate authority mismatch: " + ", ".join(mismatches)
        )


def state_from_candidate(candidate: Optional[OpportunityCandidate]) -> FunnelState:
    """Project a candidate to the minimal strategy-adapter state."""
    if candidate is None:
        return FunnelState()
    return FunnelState(
        stage=candidate.stage,
        outcome=candidate.outcome,
        revision=candidate.revision,
        raw_strategy_state=candidate.raw_strategy_state,
    )


def _is_semantic_no_op(
    previous_state: FunnelState,
    observation,
    projection: FunnelProjection,
) -> bool:
    """True when the new observation changes nothing an occurrence's semantic
    state is defined by. Compared fields are intentionally limited to stage,
    outcome, and raw_strategy_state -- the only fields FunnelState retains
    across cycles. Per-cycle-only fields (reason_codes, evidence maps) and
    strategy-owned geometry are excluded from this comparison by design: they
    are not part of FunnelState/FunnelProjection's persisted semantic
    vocabulary, so a caller re-polling with fresh evidence text for an
    unchanged stage/outcome must not be treated as a new transition."""
    return (
        previous_state.stage == projection.stage
        and previous_state.outcome == projection.outcome
        and previous_state.raw_strategy_state == dict(observation.raw_strategy_state)
    )


def evaluate_funnel(
    *,
    event: MarketEvent,
    binding: StrategyBinding,
    adapter: StrategyFunnelAdapter,
    previous_candidate: Optional[OpportunityCandidate] = None,
) -> Tuple[OpportunityCandidate, Optional[FunnelTransition]]:
    """Evaluate one event through one canonical strategy adapter without I/O.

    Returns `(candidate, transition)`. `transition` is `None` in two cases,
    both returning `previous_candidate` unchanged (same revision, same
    `latest_transition_id`, no ledger write required by the caller):

    - `previous_candidate` is already terminal (Safety Invariant #9): ordinary
      evaluation never reactivates it, and the adapter is not even invoked.
    - the new observation is semantically equivalent to the previous state
      (Safety Invariant #8): the funnel ledger must record semantic
      transitions, not scheduler polling activity.
    """
    if adapter.strategy_id != binding.strategy_id:
        raise AdapterIdentityMismatchError(
            f"adapter strategy_id {adapter.strategy_id!r} != binding {binding.strategy_id!r}"
        )
    if binding.semantic_version is not None and adapter.strategy_version != binding.semantic_version:
        raise AdapterIdentityMismatchError(
            "adapter strategy_version does not match binding semantic_version"
        )
    if previous_candidate is not None:
        _validate_candidate_continuity(previous_candidate, binding, event)
        if previous_candidate.outcome in TERMINAL_OUTCOMES:
            return previous_candidate, None
    if not adapter.supports(event, binding):
        raise AdapterNotSupportedError(
            f"adapter {adapter.strategy_id!r} does not support event {event.event_id!r}"
        )

    previous_state = state_from_candidate(previous_candidate)
    observation = adapter.observe(event, previous_state)
    if observation.strategy_id != binding.strategy_id or observation.event_id != event.event_id:
        raise ObservationIdentityMismatchError(
            "strategy observation identity does not match binding/event"
        )
    if observation.market_data_mode != event.market_data_mode:
        raise ObservationIdentityMismatchError(
            "strategy observation changed market_data_mode"
        )

    projection = adapter.project(observation)
    validate_stage(projection.stage)
    validate_outcome(projection.outcome)

    if previous_candidate is not None and _is_semantic_no_op(previous_state, observation, projection):
        return previous_candidate, None

    geometry = adapter.candidate_geometry(observation)

    candidate_id = previous_candidate.candidate_id if previous_candidate else _candidate_id(binding, event)
    occurrence_id = previous_candidate.occurrence_id if previous_candidate else candidate_id
    revision = previous_state.revision + 1
    transition_id = _transition_id(candidate_id, event, previous_state, projection)

    transition = FunnelTransition(
        transition_id=transition_id,
        candidate_id=candidate_id,
        from_stage=previous_state.stage,
        from_outcome=previous_state.outcome,
        to_stage=projection.stage,
        to_outcome=projection.outcome,
        evaluated_at=event.market_data_asof,
        evidence_event_id=event.event_id,
        reason_codes=tuple(projection.reason_codes),
        raw_strategy_state=dict(observation.raw_strategy_state),
    )

    candidate = OpportunityCandidate(
        candidate_id=candidate_id,
        occurrence_id=occurrence_id,
        strategy_id=binding.strategy_id,
        strategy_version=adapter.strategy_version,
        strategy_engine_version=binding.engine_version,
        symbol=event.symbol,
        market=event.market,
        venue=event.venue,
        direction=geometry.direction if geometry is not None else None,
        detected_at=previous_candidate.detected_at if previous_candidate else event.bar_close_time,
        last_evaluated_at=event.market_data_asof,
        expires_at=previous_candidate.expires_at if previous_candidate else None,
        stage=projection.stage,
        outcome=projection.outcome,
        revision=revision,
        raw_strategy_state=dict(observation.raw_strategy_state),
        context_evidence=dict(projection.context_evidence),
        setup_evidence=dict(projection.setup_evidence),
        trigger_evidence=dict(projection.trigger_evidence),
        geometry=geometry,
        market_data_mode=event.market_data_mode,
        data_lineage=event.snapshot_fingerprint or (previous_candidate.data_lineage if previous_candidate else None),
        latest_transition_id=transition_id,
    )
    return candidate, transition
