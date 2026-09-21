from datetime import datetime, timezone
from dataclasses import replace

import pytest

from opportunity.adapter import FunnelProjection, StrategyObservation
from opportunity.contracts import CandidateGeometry, MarketEvent
from opportunity.engine import (
    TERMINAL_OUTCOMES,
    AdapterIdentityMismatchError,
    AdapterNotSupportedError,
    CandidateIdentityMismatchError,
    ObservationIdentityMismatchError,
    evaluate_funnel,
)
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import (
    OUTCOME_ACTIVE,
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_REJECT,
    OUTCOME_WAIT,
    STAGE_ENTRY_CONFIRMED,
    STAGE_SETUP_DETECTED,
    STAGE_TRIGGER_ARMED,
)

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 21, 10, 15, tzinfo=timezone.utc)


def event(mode="REAL", symbol="EURUSD", market="FX", venue="VantageMarkets-Demo", event_id="evt-1"):
    return MarketEvent(
        event_id=event_id, event_type="BAR_CLOSED", symbol=symbol, market=market,
        venue=venue, timeframe="M15", bar_open_time=T0,
        bar_close_time=T1, market_data_asof=T1, market_data_mode=mode,
        snapshot_fingerprint="snap-1", source="test",
    )


def binding(strategy_id="TEST_STRATEGY", version="1.0.0"):
    return StrategyBinding(
        strategy_id=strategy_id, semantic_version=version, engine_id="existing_engine",
        engine_version="1", adapter_id="test_adapter", adapter_version="1",
        dispatchable=False, opportunity_authority=True, proposal_authority=False,
        execution_authority="NONE",
    )


class Adapter:
    strategy_id = "TEST_STRATEGY"
    strategy_version = "1.0.0"
    def supports(self, event, binding): return True
    def observe(self, event, previous_state):
        return StrategyObservation(strategy_id=self.strategy_id, event_id=event.event_id,
            market_data_mode=event.market_data_mode,
            raw_strategy_state={"canonical": "existing-engine-result"})
    def project(self, observation):
        return FunnelProjection(stage=STAGE_SETUP_DETECTED, outcome=OUTCOME_ACTIVE,
            reason_codes=("CANONICAL_SETUP",), setup_evidence={"setup_id": "setup-1"})
    def candidate_geometry(self, observation):
        return CandidateGeometry(direction="LONG", entry=1.1, invalidation=1.09, targets=(1.12,))


def test_first_evaluation_is_deterministic():
    a = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    b = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    assert a == b
    candidate, transition = a
    assert candidate.revision == 1
    assert candidate.latest_transition_id == transition.transition_id
    assert transition.from_stage is None


def test_existing_candidate_keeps_identity_and_increments_revision_on_real_change():
    class Advanced(Adapter):
        def project(self, observation):
            return FunnelProjection(stage=STAGE_TRIGGER_ARMED, outcome=OUTCOME_ACTIVE,
                reason_codes=("CANONICAL_TRIGGER",))

    first, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    second, transition = evaluate_funnel(
        event=event(event_id="evt-2"), binding=binding(), adapter=Advanced(), previous_candidate=first
    )
    assert second.candidate_id == first.candidate_id
    assert second.occurrence_id == first.occurrence_id
    assert second.revision == 2
    assert transition is not None
    assert transition.from_stage == first.stage
    assert transition.to_stage == STAGE_TRIGGER_ARMED


# -- Restored Safety Invariant #8: equivalent polls create no semantic transition --

def test_equivalent_projection_is_no_change():
    first, first_transition = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    second, transition = evaluate_funnel(
        event=event(event_id="evt-2"), binding=binding(), adapter=Adapter(), previous_candidate=first
    )
    assert transition is None
    assert second == first
    assert second.revision == 1
    assert second.latest_transition_id == first_transition.transition_id


def test_repeated_equivalent_projection_remains_stable_across_polls():
    candidate, first_transition = evaluate_funnel(event=event(event_id="evt-1"), binding=binding(), adapter=Adapter())
    assert candidate.revision == 1

    for poll in range(2, 5):
        candidate, transition = evaluate_funnel(
            event=event(event_id=f"evt-{poll}"), binding=binding(), adapter=Adapter(), previous_candidate=candidate
        )
        assert transition is None, f"poll {poll} should not create a transition"
        assert candidate.revision == 1, f"poll {poll} should not advance revision"
        assert candidate.latest_transition_id == first_transition.transition_id


# -- Restored Safety Invariant #9: terminal outcomes cannot be reactivated --

def _terminal_candidate(outcome):
    candidate, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    return replace(candidate, stage=STAGE_ENTRY_CONFIRMED, outcome=outcome)


@pytest.mark.parametrize("terminal_outcome", sorted(TERMINAL_OUTCOMES))
def test_terminal_candidate_cannot_be_reactivated(terminal_outcome):
    terminal = _terminal_candidate(terminal_outcome)

    class Reviving(Adapter):
        def project(self, observation):
            return FunnelProjection(stage=STAGE_TRIGGER_ARMED, outcome=OUTCOME_WAIT)

    candidate, transition = evaluate_funnel(
        event=event(event_id="evt-2"), binding=binding(), adapter=Reviving(), previous_candidate=terminal
    )
    assert transition is None
    assert candidate == terminal
    assert candidate.outcome == terminal_outcome
    assert candidate.stage == STAGE_ENTRY_CONFIRMED


@pytest.mark.parametrize("terminal_outcome", sorted(TERMINAL_OUTCOMES))
def test_repeated_terminal_observation_remains_stable(terminal_outcome):
    terminal = _terminal_candidate(terminal_outcome)
    for poll in range(2, 5):
        candidate, transition = evaluate_funnel(
            event=event(event_id=f"evt-{poll}"), binding=binding(), adapter=Adapter(), previous_candidate=terminal
        )
        assert transition is None
        assert candidate == terminal


def test_terminal_set_matches_authoritative_outcome_vocabulary():
    assert TERMINAL_OUTCOMES == {OUTCOME_REJECT, OUTCOME_INVALIDATED, OUTCOME_EXPIRED, OUTCOME_ERROR}


def test_market_data_mode_is_preserved():
    candidate, _ = evaluate_funnel(event=event("REPLAY"), binding=binding(), adapter=Adapter())
    assert candidate.market_data_mode == "REPLAY"


def test_adapter_identity_mismatch_fails_closed():
    with pytest.raises(AdapterIdentityMismatchError):
        evaluate_funnel(event=event(), binding=binding("OTHER"), adapter=Adapter())


def test_unsupported_adapter_fails_closed():
    class Unsupported(Adapter):
        def supports(self, event, binding): return False
    with pytest.raises(AdapterNotSupportedError):
        evaluate_funnel(event=event(), binding=binding(), adapter=Unsupported())


def test_observation_cannot_change_event_identity():
    class Bad(Adapter):
        def observe(self, event, previous_state):
            return StrategyObservation(strategy_id=self.strategy_id, event_id="other-event", market_data_mode=event.market_data_mode)
    with pytest.raises(ObservationIdentityMismatchError):
        evaluate_funnel(event=event(), binding=binding(), adapter=Bad())


def test_observation_cannot_change_data_mode():
    class Bad(Adapter):
        def observe(self, event, previous_state):
            return StrategyObservation(strategy_id=self.strategy_id, event_id=event.event_id, market_data_mode="SYNTHETIC")
    with pytest.raises(ObservationIdentityMismatchError):
        evaluate_funnel(event=event(), binding=binding(), adapter=Bad())


@pytest.mark.parametrize(
    "mutation", ["strategy", "version", "symbol", "mode", "engine_version", "market", "venue"]
)
def test_existing_candidate_authority_drift_fails_closed(mutation):
    first, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    next_event, next_binding, next_adapter = event(), binding(), Adapter()
    if mutation == "strategy":
        first = replace(first, strategy_id="OTHER")
    elif mutation == "version":
        first = replace(first, strategy_version="0.9.0")
    elif mutation == "symbol":
        next_event = event(symbol="GBPUSD")
    elif mutation == "mode":
        next_event = event(mode="REPLAY")
    elif mutation == "engine_version":
        first = replace(first, strategy_engine_version="OTHER_ENGINE_VERSION")
    elif mutation == "market":
        next_event = event(market="CRYPTO")
    else:
        next_event = event(venue="OtherVenue-Demo")
    with pytest.raises(CandidateIdentityMismatchError):
        evaluate_funnel(event=next_event, binding=next_binding, adapter=next_adapter, previous_candidate=first)


def test_engine_does_not_grant_proposal_or_execution_authority():
    candidate, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    assert candidate.stage == STAGE_SETUP_DETECTED
    assert not hasattr(candidate, "execution_authority")
    assert not hasattr(candidate, "proposal_id")


def test_engine_and_store_deduplicate_repeated_unchanged_polls(tmp_path):
    """Mandatory E2E proof (re-audit remediation): four scheduler polls of one
    unchanged logical setup, run through evaluate_funnel() and persisted via
    CandidateStore exactly as a caller would (only persist when a transition
    was actually produced), must yield ONE candidate, ONE occurrence, and ONE
    persisted transition -- not four."""
    from opportunity.candidate_store import CandidateStore

    store = CandidateStore(str(tmp_path / "candidates.json"))

    candidate, transition = evaluate_funnel(event=event(event_id="evt-1"), binding=binding(), adapter=Adapter())
    assert transition is not None
    store.persist(candidate, transition)

    for poll_num in range(2, 5):
        candidate, transition = evaluate_funnel(
            event=event(event_id=f"evt-{poll_num}"), binding=binding(), adapter=Adapter(), previous_candidate=candidate
        )
        assert transition is None, f"poll {poll_num} of an unchanged setup must not produce a transition"
        # Per the architecture (section 9): no transition means no persistence
        # write is necessary -- the ledger must not record polling activity.

    all_candidates = store.all_candidates()
    assert len(all_candidates) == 1
    assert all_candidates[0].revision == 1
    assert all_candidates[0].occurrence_id == candidate.occurrence_id

    transitions = store.transitions(candidate.candidate_id)
    assert len(transitions) == 1
