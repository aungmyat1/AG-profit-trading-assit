from datetime import datetime, timezone
from dataclasses import replace

import pytest

from opportunity.adapter import FunnelProjection, StrategyObservation
from opportunity.contracts import CandidateGeometry, MarketEvent
from opportunity.engine import (
    AdapterIdentityMismatchError,
    AdapterNotSupportedError,
    CandidateIdentityMismatchError,
    ObservationIdentityMismatchError,
    evaluate_funnel,
)
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import STAGE_SETUP_DETECTED, OUTCOME_ACTIVE

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 21, 10, 15, tzinfo=timezone.utc)


def event(mode="REAL", symbol="EURUSD"):
    return MarketEvent(
        event_id="evt-1", event_type="BAR_CLOSED", symbol=symbol, market="FX",
        venue="VantageMarkets-Demo", timeframe="M15", bar_open_time=T0,
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


def test_existing_candidate_keeps_identity_and_increments_revision():
    first, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    second, transition = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter(), previous_candidate=first)
    assert second.candidate_id == first.candidate_id
    assert second.occurrence_id == first.occurrence_id
    assert second.revision == 2
    assert transition.from_stage == first.stage


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


@pytest.mark.parametrize("mutation", ["strategy", "version", "symbol", "mode"])
def test_existing_candidate_authority_drift_fails_closed(mutation):
    first, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    next_event, next_binding, next_adapter = event(), binding(), Adapter()
    if mutation == "strategy":
        first = replace(first, strategy_id="OTHER")
    elif mutation == "version":
        first = replace(first, strategy_version="0.9.0")
    elif mutation == "symbol":
        next_event = event(symbol="GBPUSD")
    else:
        next_event = event(mode="REPLAY")
    with pytest.raises(CandidateIdentityMismatchError):
        evaluate_funnel(event=next_event, binding=next_binding, adapter=next_adapter, previous_candidate=first)


def test_engine_does_not_grant_proposal_or_execution_authority():
    candidate, _ = evaluate_funnel(event=event(), binding=binding(), adapter=Adapter())
    assert candidate.stage == STAGE_SETUP_DETECTED
    assert not hasattr(candidate, "execution_authority")
    assert not hasattr(candidate, "proposal_id")
