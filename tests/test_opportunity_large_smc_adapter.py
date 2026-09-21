"""V2-3A: Large-SMC shadow/funnel adapter -- state mapping, evidence/geometry
preservation, repeated-poll idempotence, terminal stickiness, CandidateStore
integration and restart continuity, and negative fail-closed cases.

Fixtures build `historical_replay.orchestrator.SetupLedgerRow` directly (the
exact shape the existing scheduled Large-SMC watch already produces via
`run_replay`'s `SetupLedger.rows`) -- no MT5, no live watch, no replay engine
invoked here; this proves the adapter/funnel/store wiring against
representative canonical output, per the mission's semantic-parity framework.
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timezone

import pytest

from entry_confirmation.entry_models_v1 import EntryModelState
from historical_replay.fill_simulator import (
    STATUS_FILLED,
    STATUS_INTRABAR_AMBIGUOUS,
    STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_UNFILLED_AS_OF_DATA_END,
)
from historical_replay.orchestrator import SetupLedgerRow

from opportunity.candidate_store import CandidateStore
from opportunity.contracts import MarketEvent
from opportunity.engine import TERMINAL_OUTCOMES, evaluate_funnel
from opportunity.large_smc_adapter import (
    LargeSMCFunnelAdapter,
    LargeSMCUnmappedStageError,
    STRATEGY_ID,
    STRATEGY_VERSION,
)
from opportunity.registry_binding import StrategyBinding
from opportunity.transitions import FunnelState
from opportunity.stages import (
    OUTCOME_ACTIVE,
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_WAIT,
    STAGE_LOCATION_VALID,
    STAGE_MARKET_ELIGIBLE,
    STAGE_OPPORTUNITY_READY,
    STAGE_TRIGGER_ARMED,
)

T0 = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
T1 = datetime(2026, 9, 20, 9, 0, tzinfo=timezone.utc)


def binding():
    return StrategyBinding(
        strategy_id=STRATEGY_ID, semantic_version=STRATEGY_VERSION, engine_id="large_smc_research.engine",
        engine_version=None, adapter_id="opportunity.large_smc_adapter", adapter_version="1",
        dispatchable=False,
    )


def market_event(occurrence_key: str, asof: datetime = T1, mode: str = "REAL"):
    """Stable event_id per occurrence -- see large_smc_adapter module docstring,
    'INTENDED EVENT-IDENTITY PATTERN'."""
    return MarketEvent(
        event_id=f"LARGE_SMC:{occurrence_key}", event_type="RESEARCH_WATCH_POLL",
        symbol="EURUSD", market="FX", venue=None, timeframe="M5",
        bar_open_time=T0, bar_close_time=T1, market_data_asof=asof,
        market_data_mode=mode, snapshot_fingerprint=None, source="large_smc_research.live_watch",
    )


def setup_row(final_state: str, *, ready_time=None, final_time=None, terminal=False, direction="LONG",
              entry_reference=1.1000, invalidation_price=1.0950):
    return SetupLedgerRow(
        setup_id="EURUSD-E1M1-LONG-20260920", symbol="EURUSD", combination="E1M1",
        entry_condition="E1", maneuver="M1", direction=direction, reference_key="ref-1",
        first_seen_time=T0, last_seen_time=T1, ready_time=ready_time,
        entry_type="FVG" if ready_time else None, entry_low=1.0990, entry_high=1.1010,
        entry_reference=entry_reference, invalidation_price=invalidation_price,
        invalidation_source_type="STRUCTURAL", invalidation_trigger=None,
        final_state=final_state, final_time=final_time, terminal=terminal,
    )


def test_watching_maps_to_market_eligible_active():
    row = setup_row(EntryModelState.SCANNING_CONTEXT.value)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    obs = adapter.observe(market_event("s1"), previous_state=FunnelState())
    projection = adapter.project(obs)
    assert projection.stage == STAGE_MARKET_ELIGIBLE
    assert projection.outcome == OUTCOME_ACTIVE


def test_qualified_maps_to_location_valid_active():
    row = setup_row(EntryModelState.HTF_QUALIFIED.value)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage == STAGE_LOCATION_VALID
    assert projection.outcome == OUTCOME_ACTIVE


def test_ready_maps_to_trigger_armed_active():
    row = setup_row(EntryModelState.READY.value, ready_time=T1)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage == STAGE_TRIGGER_ARMED
    assert projection.outcome == OUTCOME_ACTIVE


def test_filled_maps_to_opportunity_ready_active():
    row = setup_row(EntryModelState.READY.value, ready_time=T1)
    adapter = LargeSMCFunnelAdapter(setup_row=row, occurrence_status=STATUS_FILLED)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage == STAGE_OPPORTUNITY_READY
    assert projection.outcome == OUTCOME_ACTIVE


def test_unfilled_as_of_data_end_maps_to_wait_not_terminal():
    row = setup_row(EntryModelState.READY.value, ready_time=T1)
    adapter = LargeSMCFunnelAdapter(setup_row=row, occurrence_status=STATUS_UNFILLED_AS_OF_DATA_END)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage == STAGE_TRIGGER_ARMED
    assert projection.outcome == OUTCOME_WAIT
    assert projection.outcome not in TERMINAL_OUTCOMES


def test_invalidated_is_terminal_and_retains_trigger_armed_when_ready_reached():
    row = setup_row(EntryModelState.INVALIDATED.value, ready_time=T1, final_time=T1, terminal=True)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage == STAGE_TRIGGER_ARMED
    assert projection.outcome == OUTCOME_INVALIDATED
    assert projection.outcome in TERMINAL_OUTCOMES


def test_invalidated_before_ready_retains_market_eligible_floor():
    row = setup_row(EntryModelState.INVALIDATED.value, ready_time=None, final_time=T1, terminal=True)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage == STAGE_MARKET_ELIGIBLE
    assert projection.outcome == OUTCOME_INVALIDATED


def test_expired_is_terminal():
    row = setup_row(EntryModelState.EXPIRED.value, final_time=T1, terminal=True)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.outcome == OUTCOME_EXPIRED
    assert projection.outcome in TERMINAL_OUTCOMES


def test_blocked_occurrence_status_maps_to_error_terminal():
    row = setup_row(EntryModelState.READY.value, ready_time=T1)
    adapter = LargeSMCFunnelAdapter(setup_row=row, occurrence_status=STATUS_INTRABAR_AMBIGUOUS)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.outcome == OUTCOME_ERROR
    assert projection.outcome in TERMINAL_OUTCOMES


# --- negative / fail-closed cases -------------------------------------------------

def test_resolved_stage_is_unreachable_and_fails_closed():
    from large_smc_research.watch_lifecycle import STAGE_RESOLVED

    row = setup_row(EntryModelState.READY.value, ready_time=T1)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    obs = adapter.observe(market_event("s1"), FunnelState())
    obs.raw_strategy_state["watch_lifecycle_record"]["stage"] = STAGE_RESOLVED
    with pytest.raises(LargeSMCUnmappedStageError):
        adapter.project(obs)


def test_no_setup_cannot_produce_entry_confirmed():
    row = setup_row(EntryModelState.SCANNING_CONTEXT.value)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(market_event("s1"), FunnelState()))
    assert projection.stage != "ENTRY_CONFIRMED"


def test_geometry_never_fabricates_targets():
    row = setup_row(EntryModelState.READY.value, ready_time=T1)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    geometry = adapter.candidate_geometry(adapter.observe(market_event("s1"), FunnelState()))
    assert geometry.targets == ()
    assert geometry.direction == "LONG"
    assert geometry.entry == 1.1000
    assert geometry.invalidation == 1.0950


def test_supports_rejects_wrong_symbol():
    row = setup_row(EntryModelState.SCANNING_CONTEXT.value)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    wrong_symbol_event = market_event("s1")
    wrong_symbol_event = MarketEvent(
        event_id=wrong_symbol_event.event_id, event_type=wrong_symbol_event.event_type,
        symbol="GBPUSD", market="FX", venue=None, timeframe="M5",
        bar_open_time=T0, bar_close_time=T1, market_data_asof=T1,
        market_data_mode="REAL", snapshot_fingerprint=None, source="test",
    )
    assert adapter.supports(wrong_symbol_event, binding()) is False


# --- CandidateStore integration: repeated polls, progression, restart -------------

def test_repeated_identical_poll_creates_exactly_one_revision():
    row = setup_row(EntryModelState.HTF_QUALIFIED.value)
    event = market_event("progressive-1")
    candidate = None
    transitions_seen = 0
    for _ in range(4):
        adapter = LargeSMCFunnelAdapter(setup_row=row)
        candidate, transition = evaluate_funnel(event=event, binding=binding(), adapter=adapter, previous_candidate=candidate)
        if transition is not None:
            transitions_seen += 1
    assert candidate.revision == 1
    assert transitions_seen == 1


def test_progressive_observations_produce_one_candidate_with_valid_revision_history():
    event = market_event("progressive-2")
    b = binding()

    row1 = setup_row(EntryModelState.SCANNING_CONTEXT.value)
    candidate, t1 = evaluate_funnel(event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row1))
    assert candidate.stage == STAGE_MARKET_ELIGIBLE and candidate.revision == 1

    row2 = setup_row(EntryModelState.HTF_QUALIFIED.value)
    candidate, t2 = evaluate_funnel(event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row2), previous_candidate=candidate)
    assert candidate.stage == STAGE_LOCATION_VALID and candidate.revision == 2
    assert candidate.candidate_id == t1.candidate_id == t2.candidate_id

    row3 = setup_row(EntryModelState.READY.value, ready_time=T1)
    candidate, t3 = evaluate_funnel(event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row3), previous_candidate=candidate)
    assert candidate.stage == STAGE_TRIGGER_ARMED and candidate.revision == 3
    assert candidate.candidate_id == t3.candidate_id
    assert candidate.occurrence_id == candidate.candidate_id


def test_terminal_occurrence_cannot_be_reactivated():
    event = market_event("progressive-3")
    b = binding()
    row_invalidated = setup_row(EntryModelState.INVALIDATED.value, ready_time=T1, final_time=T1, terminal=True)
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row_invalidated))
    assert candidate.outcome == OUTCOME_INVALIDATED

    row_ready_again = setup_row(EntryModelState.READY.value, ready_time=T1)
    candidate2, transition2 = evaluate_funnel(
        event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row_ready_again), previous_candidate=candidate,
    )
    assert transition2 is None
    assert candidate2.outcome == OUTCOME_INVALIDATED
    assert candidate2.revision == candidate.revision


def test_candidate_store_integration_and_restart_continuity():
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/large_smc_candidates.json"
        event = market_event("restart-1")
        b = binding()

        store = CandidateStore(path)
        row1 = setup_row(EntryModelState.SCANNING_CONTEXT.value)
        candidate1, transition1 = evaluate_funnel(event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row1))
        store.persist(candidate1, transition1)

        # Restart: recreate the store from disk, reload the candidate.
        reloaded_store = CandidateStore(path)
        reloaded = reloaded_store.get(candidate1.candidate_id)
        assert reloaded is not None
        assert reloaded.candidate_id == candidate1.candidate_id
        assert reloaded.stage == STAGE_MARKET_ELIGIBLE

        row2 = setup_row(EntryModelState.HTF_QUALIFIED.value)
        candidate2, transition2 = evaluate_funnel(
            event=event, binding=b, adapter=LargeSMCFunnelAdapter(setup_row=row2), previous_candidate=reloaded,
        )
        reloaded_store.persist(candidate2, transition2)

        assert candidate2.candidate_id == candidate1.candidate_id
        assert candidate2.revision == 2
        all_candidates = reloaded_store.all_candidates()
        assert len(all_candidates) == 1
        assert all_candidates[0].candidate_id == candidate1.candidate_id
