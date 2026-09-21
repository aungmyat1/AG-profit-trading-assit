"""V2-3B: SSC shadow/replay adapter -- state mapping, evidence/geometry
preservation, replay/data-mode preservation, CandidateStore integration, and
negative fail-closed cases.

Fixtures build `strategy_contract.decision.StrategyDecision` via
`strategy_contract.decision.from_session_sweep_continuation_replay` from a
hand-built `session_sweep_continuation.replay.ReplayResult` / `Campaign` --
the exact canonical shape `session_sweep_continuation.canonical_consumer.
run_canonical_shadow_cycle` already produces every decision cycle. No MT5, no
live feed, no replay engine invoked here; this proves the adapter/funnel/store
wiring against representative canonical output.
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone

import pytest

from session_sweep_continuation.campaign import Campaign, CampaignEntry, CampaignStatus
from session_sweep_continuation.setups import SetupModel
from session_sweep_continuation.replay import ReplayResult
from strategy_contract.decision import from_session_sweep_continuation_replay

from opportunity.candidate_store import CandidateStore
from opportunity.contracts import MarketEvent
from opportunity.engine import TERMINAL_OUTCOMES, evaluate_funnel
from opportunity.registry_binding import StrategyBinding
from opportunity.ssc_adapter import (
    SSCFunnelAdapter,
    SSCStrategyIdentityMismatchError,
    SSCUnmappedCampaignStatusError,
    STRATEGY_ID,
    STRATEGY_VERSION,
)
from opportunity.stages import (
    OUTCOME_ACTIVE,
    OUTCOME_EXPIRED,
    OUTCOME_INVALIDATED,
    OUTCOME_WAIT,
    STAGE_CONTEXT_VALID,
    STAGE_ENTRY_CONFIRMED,
    STAGE_MARKET_ELIGIBLE,
    STAGE_OPPORTUNITY_READY,
    STAGE_SETUP_DETECTED,
)
from opportunity.transitions import FunnelState

T0 = datetime(2026, 9, 20, 6, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 9, 20)


def binding():
    return StrategyBinding(
        strategy_id=STRATEGY_ID, semantic_version=STRATEGY_VERSION, engine_id="session_sweep_continuation.replay",
        engine_version=None, adapter_id="opportunity.ssc_adapter", adapter_version="1", dispatchable=False,
    )


def market_event(session_pair="ASIAN_LONDON", symbol="EURUSD", asof=T0, mode="REPLAY"):
    """Stable event_id per (symbol, session_pair, trading_date) occurrence --
    see ssc_adapter module docstring, 'INTENDED EVENT-IDENTITY PATTERN'. Direction
    is deliberately excluded from the key."""
    return MarketEvent(
        event_id=f"SSC:{symbol}:{session_pair}:{TRADING_DATE.isoformat()}",
        event_type="SESSION_CYCLE_EVALUATED", symbol=symbol, market="FX", venue=None,
        timeframe="M15", bar_open_time=T0, bar_close_time=T0, market_data_asof=asof,
        market_data_mode=mode, snapshot_fingerprint=None, source="session_sweep_continuation.canonical_consumer",
    )


def replay_result(*, regime=None, campaign=None, accepted_setups=None, rejected_setups=None, symbol="EURUSD"):
    return ReplayResult(
        symbol=symbol, session_pair="ASIAN_LONDON", trading_date=TRADING_DATE, regime=regime,
        campaign=campaign, accepted_setups=accepted_setups or [], rejected_setups=rejected_setups or [], steps=[],
    )


def campaign(status: CampaignStatus, *, entries=0, direction="LONG"):
    c = Campaign(
        campaign_id=f"EURUSD-ASIAN_LONDON-20260920-{direction}", strategy_id=STRATEGY_ID,
        strategy_version=STRATEGY_VERSION, symbol="EURUSD", session_pair="ASIAN_LONDON",
        trading_date=TRADING_DATE, direction=direction, regime="TREND_UP", status=status,
    )
    c.entries = [
        CampaignEntry(setup_model=SetupModel.S1, entry_time=T0, risk_pct=0.5, entry_price=1.1, stop_price=1.09)
        for _ in range(entries)
    ]
    return c


def decision_for(result: ReplayResult):
    return from_session_sweep_continuation_replay(result)


def test_no_regime_yet_maps_to_market_eligible_wait():
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime=None)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_MARKET_ELIGIBLE
    assert projection.outcome == OUTCOME_WAIT


def test_regime_unknown_no_trade_maps_to_context_valid_invalidated():
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="UNKNOWN")))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_CONTEXT_VALID
    assert projection.outcome == OUTCOME_INVALIDATED
    assert projection.outcome in TERMINAL_OUTCOMES


def test_regime_known_no_setup_maps_to_context_valid_wait():
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP")))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_CONTEXT_VALID
    assert projection.outcome == OUTCOME_WAIT


def test_active_campaign_no_entries_maps_to_setup_detected_active():
    c = campaign(CampaignStatus.ACTIVE, entries=0)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_SETUP_DETECTED
    assert projection.outcome == OUTCOME_ACTIVE


def test_active_campaign_with_entries_maps_to_entry_confirmed_active():
    c = campaign(CampaignStatus.ACTIVE, entries=1)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_ACTIVE


def test_invalidated_campaign_is_terminal():
    c = campaign(CampaignStatus.INVALIDATED, entries=1)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_INVALIDATED
    assert projection.outcome in TERMINAL_OUTCOMES


def test_session_expired_campaign_is_terminal():
    c = campaign(CampaignStatus.SESSION_EXPIRED, entries=0)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_SETUP_DETECTED
    assert projection.outcome == OUTCOME_EXPIRED
    assert projection.outcome in TERMINAL_OUTCOMES


def test_risk_exhausted_campaign_is_terminal_entry_confirmed():
    c = campaign(CampaignStatus.RISK_EXHAUSTED, entries=2)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_EXPIRED
    assert projection.outcome in TERMINAL_OUTCOMES


def test_complete_campaign_maps_to_opportunity_ready_active():
    c = campaign(CampaignStatus.COMPLETE, entries=1)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_OPPORTUNITY_READY
    assert projection.outcome == OUTCOME_ACTIVE
    assert projection.outcome not in TERMINAL_OUTCOMES


# --- negative / fail-closed cases -------------------------------------------------

def test_no_setup_cannot_produce_entry_confirmed():
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP")))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage != STAGE_ENTRY_CONFIRMED


def test_unrecognized_campaign_status_fails_closed():
    result = replay_result(regime="TREND_UP", campaign=campaign(CampaignStatus.ACTIVE))
    decision = decision_for(result)
    decision.setup_properties["campaign_status"] = "SOMETHING_NEW"
    adapter = SSCFunnelAdapter(decision=decision)
    with pytest.raises(SSCUnmappedCampaignStatusError):
        adapter.project(adapter.observe(market_event(), FunnelState()))


def test_no_direction_yields_no_fabricated_geometry():
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP")))
    geometry = adapter.candidate_geometry(adapter.observe(market_event(), FunnelState()))
    assert geometry is None


def test_direction_present_never_fabricates_entry_or_targets():
    c = campaign(CampaignStatus.ACTIVE, entries=1, direction="SHORT")
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_DOWN", campaign=c)))
    geometry = adapter.candidate_geometry(adapter.observe(market_event(), FunnelState()))
    assert geometry.direction == "SHORT"
    assert geometry.entry is None
    assert geometry.invalidation is None
    assert geometry.targets == ()


def test_replay_data_mode_is_preserved_not_upgraded_to_real():
    c = campaign(CampaignStatus.ACTIVE, entries=1)
    adapter = SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c)))
    event = market_event(mode="REPLAY")
    binding_ = binding()
    candidate, _ = evaluate_funnel(event=event, binding=binding_, adapter=adapter)
    assert candidate.market_data_mode == "REPLAY"


def test_strategy_identity_mismatch_fails_closed():
    c = campaign(CampaignStatus.ACTIVE, entries=1)
    decision = decision_for(replay_result(regime="TREND_UP", campaign=c))
    with pytest.raises(SSCStrategyIdentityMismatchError):
        SSCFunnelAdapter(decision=decision, strategy_id="ST_SOMETHING_ELSE_V1")


# --- CandidateStore integration: progression, restart -----------------------------

def test_progression_produces_one_candidate_with_valid_revision_history():
    event = market_event()
    b = binding()

    d1 = decision_for(replay_result(regime=None))
    candidate, t1 = evaluate_funnel(event=event, binding=b, adapter=SSCFunnelAdapter(decision=d1))
    assert candidate.stage == STAGE_MARKET_ELIGIBLE and candidate.revision == 1

    d2 = decision_for(replay_result(regime="TREND_UP"))
    candidate, t2 = evaluate_funnel(event=event, binding=b, adapter=SSCFunnelAdapter(decision=d2), previous_candidate=candidate)
    assert candidate.stage == STAGE_CONTEXT_VALID and candidate.revision == 2
    assert candidate.candidate_id == t1.candidate_id == t2.candidate_id

    c3 = campaign(CampaignStatus.ACTIVE, entries=0)
    d3 = decision_for(replay_result(regime="TREND_UP", campaign=c3))
    candidate, t3 = evaluate_funnel(event=event, binding=b, adapter=SSCFunnelAdapter(decision=d3), previous_candidate=candidate)
    assert candidate.stage == STAGE_SETUP_DETECTED and candidate.revision == 3

    c4 = campaign(CampaignStatus.ACTIVE, entries=1)
    d4 = decision_for(replay_result(regime="TREND_UP", campaign=c4))
    candidate, t4 = evaluate_funnel(event=event, binding=b, adapter=SSCFunnelAdapter(decision=d4), previous_candidate=candidate)
    assert candidate.stage == STAGE_ENTRY_CONFIRMED and candidate.revision == 4
    assert candidate.occurrence_id == candidate.candidate_id == t4.candidate_id


def test_terminal_campaign_cannot_be_reactivated():
    event = market_event()
    b = binding()
    c_invalid = campaign(CampaignStatus.INVALIDATED, entries=1)
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=SSCFunnelAdapter(decision=decision_for(
        replay_result(regime="TREND_UP", campaign=c_invalid))))
    assert candidate.outcome == OUTCOME_INVALIDATED

    c_active_again = campaign(CampaignStatus.ACTIVE, entries=1)
    candidate2, transition2 = evaluate_funnel(
        event=event, binding=b,
        adapter=SSCFunnelAdapter(decision=decision_for(replay_result(regime="TREND_UP", campaign=c_active_again))),
        previous_candidate=candidate,
    )
    assert transition2 is None
    assert candidate2.outcome == OUTCOME_INVALIDATED
    assert candidate2.revision == candidate.revision


def test_candidate_store_integration_and_restart_continuity():
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/ssc_candidates.json"
        event = market_event()
        b = binding()

        store = CandidateStore(path)
        d1 = decision_for(replay_result(regime="TREND_UP"))
        candidate1, transition1 = evaluate_funnel(event=event, binding=b, adapter=SSCFunnelAdapter(decision=d1))
        store.persist(candidate1, transition1)

        reloaded_store = CandidateStore(path)
        reloaded = reloaded_store.get(candidate1.candidate_id)
        assert reloaded is not None
        assert reloaded.stage == STAGE_CONTEXT_VALID

        c2 = campaign(CampaignStatus.ACTIVE, entries=0)
        d2 = decision_for(replay_result(regime="TREND_UP", campaign=c2))
        candidate2, transition2 = evaluate_funnel(
            event=event, binding=b, adapter=SSCFunnelAdapter(decision=d2), previous_candidate=reloaded,
        )
        reloaded_store.persist(candidate2, transition2)

        assert candidate2.candidate_id == candidate1.candidate_id
        assert candidate2.revision == 2
        assert len(reloaded_store.all_candidates()) == 1
