"""Pure universal opportunity funnel transition engine (V2-2A).

This module intentionally orchestrates the existing V2 contracts and strategy
adapter boundary.  It owns no strategy semantics, persistence, proposal
formation, portfolio risk, execution authority, or broker access.

The same MarketEvent + StrategyBinding + previous FunnelState + adapter result
must produce the same transition/candidate identities and values.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import hashlib
import json
from typing import Any, Mapping, Optional, Tuple

from .adapter import FunnelProjection, StrategyFunnelAdapter, StrategyObservation
from .contracts import MarketEvent, OpportunityCandidate
from .registry_binding import StrategyBinding
from .stages import (
    OUTCOME_ERROR,
    validate_outcome,
    validate_stage,
)
from .transitions import FunnelState, FunnelTransition


class FunnelEngineError(RuntimeError):
    """Base class for fail-closed V2-2A engine failures."""


class AdapterNotSupportedError(FunnelEngineError):
    pass


class AdapterIdentityMismatchError(FunnelEngineError):
    pass


class ObservationIdentityMismatchError(FunnelEngineError):
    pass


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _stable_id(prefix: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _candidate_id(binding: StrategyBinding, event: MarketEvent) -> str:
    # Candidate identity is intentionally independent of polling/evaluation time.
    # Until V2-2B introduces a durable occurrence authority, event identity is the
    # safest deterministic occurrence boundary available to the universal engine.
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


def state_from_candidate(candidate: Optional[OpportunityCandidate]) -> FunnelState:
    """Project an existing candidate back to the minimal adapter state.

    V2-2A remains storage-independent: callers may obtain the candidate from any
    source.  Durable storage/reconstruction belongs to V2-2B.
    """
    if candidate is None:
        return FunnelState()
    return FunnelState(
        stage=candidate.stage,
        outcome=candidate.outcome,
        revision=candidate.revision,
        raw_strategy_state=candidate.raw_strategy_state,
    )


def evaluate_funnel(
    *,
    event: MarketEvent,
    binding: StrategyBinding,
    adapter: StrategyFunnelAdapter,
    previous_candidate: Optional[OpportunityCandidate] = None,
) -> Tuple[OpportunityCandidate, FunnelTransition]:
    """Evaluate one event through one canonical strategy adapter.

    This function is deliberately pure with respect to repository/runtime state:
    it performs no I/O and writes nothing.  The adapter is responsible only for
    calling/projecting the already-canonical strategy implementation.
    """
    if adapter.strategy_id != binding.strategy_id:
        raise AdapterIdentityMismatchError(
            f"adapter strategy_id {adapter.strategy_id!r} != binding {binding.strategy_id!r}"
        )
    if binding.semantic_version is not None and adapter.strategy_version != binding.semantic_version:
        raise AdapterIdentityMismatchError(
            "adapter strategy_version does not match binding semantic_version"
        )
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
    geometry = adapter.candidate_geometry(observation)

    candidate_id = (
        previous_candidate.candidate_id
        if previous_candidate is not None
        else _candidate_id(binding, event)
    )
    occurrence_id = (
        previous_candidate.occurrence_id
        if previous_candidate is not None
        else candidate_id
    )
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

    detected_at = (
        previous_candidate.detected_at
        if previous_candidate is not None
        else event.bar_close_time
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
        detected_at=detected_at,
        last_evaluated_at=event.market_data_asof,
        expires_at=previous_candidate.expires_at if previous_candidate is not None else None,
        stage=projection.stage,
        outcome=projection.outcome,
        revision=revision,
        raw_strategy_state=dict(observation.raw_strategy_state),
        context_evidence=dict(projection.context_evidence),
        setup_evidence=dict(projection.setup_evidence),
        trigger_evidence=dict(projection.trigger_evidence),
        geometry=geometry,
        market_data_mode=event.market_data_mode,
        data_lineage=(
            event.snapshot_fingerprint
            or (previous_candidate.data_lineage if previous_candidate is not None else None)
        ),
        latest_transition_id=transition_id,
    )
    return candidate, transition
