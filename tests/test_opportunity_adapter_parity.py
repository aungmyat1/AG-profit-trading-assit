"""V2-3A/V2-3B/V2-3C semantic parity checkpoint.

Compares canonical strategy-side semantics (Large-SMC's
`large_smc_research.watch_lifecycle.WatchLifecycleRecord`; SSC's
`strategy_contract.decision.StrategyDecision`; Asian Sweep's
`post_asian_pilot.decision.PostAsianDecision`, itself wrapping a real
`strategy_engine.models.TradeSignal`) against each V2 adapter's
`FunnelProjection`/`CandidateGeometry` output for the SAME authoritative input,
field by field (not object equality -- the shapes are intentionally different
domain objects). Every asserted field either matches directly or is an
explicitly documented, non-fabricating adapter decision (see the adapter
modules' own docstrings and docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md
for the handful of accepted mapping choices, e.g. BLOCKED -> OUTCOME_ERROR,
RISK_EXHAUSTED -> OUTCOME_EXPIRED).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from entry_confirmation.entry_models_v1 import EntryModelState
from historical_replay.orchestrator import SetupLedgerRow
from large_smc_research.watch_lifecycle import project_setup_row

from post_asian_pilot.decision import STATUS_READY, map_trade_signal_to_decision
from session_sweep_continuation.campaign import Campaign, CampaignEntry, CampaignStatus
from session_sweep_continuation.replay import ReplayResult
from session_sweep_continuation.setups import SetupModel
from strategy_contract.decision import from_session_sweep_continuation_replay
from strategy_engine import evaluate, load_strategy
from strategy_engine.session import Candle

from opportunity.asian_sweep_adapter import AsianSweepFunnelAdapter
from opportunity.contracts import MarketEvent
from opportunity.large_smc_adapter import LargeSMCFunnelAdapter
from opportunity.ssc_adapter import SSCFunnelAdapter
from opportunity.stages import (
    OUTCOME_ACTIVE,
    OUTCOME_INVALIDATED,
    OUTCOME_WAIT,
    STAGE_CONTEXT_VALID,
    STAGE_ENTRY_CONFIRMED,
    STAGE_LOCATION_VALID,
    STAGE_MARKET_ELIGIBLE,
    STAGE_SETUP_DETECTED,
    STAGE_TRIGGER_ARMED,
)
from opportunity.transitions import FunnelState

T0 = datetime(2026, 9, 20, 8, 0, tzinfo=timezone.utc)
TRADING_DATE = date(2026, 9, 20)
ASIAN_SWEEP_STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


def asian_sweep_event(asof=T0, mode="REPLAY"):
    return MarketEvent(
        event_id="ASIAN_SWEEP:parity-1", event_type="SESSION_CYCLE_EVALUATED", symbol="EURUSD",
        market="FX", venue=None, timeframe="M15", bar_open_time=asof, bar_close_time=asof,
        market_data_asof=asof, market_data_mode=mode, snapshot_fingerprint=None,
        source="post_asian_pilot.pipeline",
    )


def large_smc_event():
    return MarketEvent(
        event_id="LARGE_SMC:parity-1", event_type="RESEARCH_WATCH_POLL", symbol="EURUSD",
        market="FX", venue=None, timeframe="M5", bar_open_time=T0, bar_close_time=T0,
        market_data_asof=T0, market_data_mode="REAL", snapshot_fingerprint=None,
        source="large_smc_research.live_watch",
    )


def ssc_event(mode="REPLAY"):
    return MarketEvent(
        event_id="SSC:parity-1", event_type="SESSION_CYCLE_EVALUATED", symbol="EURUSD",
        market="FX", venue=None, timeframe="M15", bar_open_time=T0, bar_close_time=T0,
        market_data_asof=T0, market_data_mode=mode, snapshot_fingerprint=None,
        source="session_sweep_continuation.canonical_consumer",
    )


# --- Large-SMC parity ---------------------------------------------------------

def test_large_smc_parity_setup_detected_stage_direction_entry_invalidation():
    row = SetupLedgerRow(
        setup_id="EURUSD-E1M1-LONG-20260920", symbol="EURUSD", combination="E1M1",
        entry_condition="E1", maneuver="M1", direction="LONG", reference_key="ref-1",
        first_seen_time=T0, last_seen_time=T0, ready_time=None, entry_type=None,
        entry_low=1.0990, entry_high=1.1010, entry_reference=1.1000,
        invalidation_price=1.0950, invalidation_source_type="STRUCTURAL",
        invalidation_trigger=None, final_state=EntryModelState.HTF_QUALIFIED.value,
        final_time=None, terminal=False,
    )
    canonical_record = project_setup_row(row)

    adapter = LargeSMCFunnelAdapter(setup_row=row)
    observation = adapter.observe(large_smc_event(), FunnelState())
    projection = adapter.project(observation)
    geometry = adapter.candidate_geometry(observation)

    # strategy identity
    assert adapter.strategy_id == "ST_LARGE_SMC_V1"
    # symbol / direction
    assert canonical_record.symbol == row.symbol == "EURUSD"
    assert canonical_record.direction == geometry.direction == "LONG"
    # canonical state -> mapped stage (documented, non-object-equal)
    assert canonical_record.stage == "QUALIFIED"
    assert projection.stage == STAGE_LOCATION_VALID
    # setup presence / trigger state
    assert canonical_record.canonical_state == EntryModelState.HTF_QUALIFIED.value
    assert projection.setup_evidence["combination"] == canonical_record.combination == "E1M1"
    # entry/invalidation preserved verbatim, never recomputed
    assert geometry.entry == row.entry_reference == 1.1000
    assert geometry.invalidation == row.invalidation_price == 1.0950
    # no targets authority on SetupLedgerRow -- never fabricated
    assert geometry.targets == ()
    # terminal state
    assert canonical_record.is_terminal is False
    assert projection.outcome == OUTCOME_ACTIVE


def test_large_smc_parity_negative_no_setup_cannot_yield_entry_confirmed():
    row = SetupLedgerRow(
        setup_id="EURUSD-E1M1-LONG-20260920", symbol="EURUSD", combination="E1M1",
        entry_condition="E1", maneuver="M1", direction=None, reference_key=None,
        first_seen_time=T0, last_seen_time=T0, ready_time=None, entry_type=None,
        entry_low=None, entry_high=None, entry_reference=None, invalidation_price=None,
        invalidation_source_type=None, invalidation_trigger=None,
        final_state=EntryModelState.SCANNING_CONTEXT.value, final_time=None, terminal=False,
    )
    canonical_record = project_setup_row(row)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(large_smc_event(), FunnelState()))

    assert canonical_record.stage == "WATCHING"
    assert projection.stage == STAGE_MARKET_ELIGIBLE
    assert projection.stage != "ENTRY_CONFIRMED"

    geometry = adapter.candidate_geometry(adapter.observe(large_smc_event(), FunnelState()))
    assert geometry.entry is None
    assert geometry.invalidation is None
    assert geometry.direction is None


def test_large_smc_parity_negative_invalidated_cannot_yield_active():
    row = SetupLedgerRow(
        setup_id="EURUSD-E1M1-LONG-20260920", symbol="EURUSD", combination="E1M1",
        entry_condition="E1", maneuver="M1", direction="LONG", reference_key="ref-1",
        first_seen_time=T0, last_seen_time=T0, ready_time=T0, entry_type="FVG",
        entry_low=1.0990, entry_high=1.1010, entry_reference=1.1000,
        invalidation_price=1.0950, invalidation_source_type="STRUCTURAL",
        invalidation_trigger="WICK_BREACH", final_state=EntryModelState.INVALIDATED.value,
        final_time=T0, terminal=True,
    )
    canonical_record = project_setup_row(row)
    adapter = LargeSMCFunnelAdapter(setup_row=row)
    projection = adapter.project(adapter.observe(large_smc_event(), FunnelState()))

    assert canonical_record.is_terminal is True
    assert canonical_record.stage == "INVALIDATED"
    assert projection.outcome == OUTCOME_INVALIDATED
    assert projection.outcome != OUTCOME_ACTIVE


# --- SSC parity -----------------------------------------------------------------

def test_ssc_parity_active_campaign_direction_setups_lineage():
    c = Campaign(
        campaign_id="EURUSD-ASIAN_LONDON-20260920-LONG", strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
        strategy_version="1.0.1", symbol="EURUSD", session_pair="ASIAN_LONDON",
        trading_date=TRADING_DATE, direction="LONG", regime="TREND_UP", status=CampaignStatus.ACTIVE,
    )
    c.entries = [CampaignEntry(setup_model=SetupModel.S2, entry_time=T0, risk_pct=0.5, entry_price=1.1, stop_price=1.09)]
    result = ReplayResult(
        symbol="EURUSD", session_pair="ASIAN_LONDON", trading_date=TRADING_DATE, regime="TREND_UP",
        campaign=c, accepted_setups=[{"setup_model": "S2_BREAKOUT_CONTINUATION"}], rejected_setups=[], steps=[],
    )
    decision = from_session_sweep_continuation_replay(result)

    adapter = SSCFunnelAdapter(decision=decision)
    observation = adapter.observe(ssc_event(mode="REPLAY"), FunnelState())
    projection = adapter.project(observation)
    geometry = adapter.candidate_geometry(observation)

    # strategy identity / symbol / direction
    assert decision.strategy_id == adapter.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1"
    assert decision.symbol == "EURUSD"
    assert decision.direction == geometry.direction == "LONG"
    # S1/S2/S3 classification preserved verbatim (never recomputed)
    assert decision.setup_properties["accepted_setups"] == result.accepted_setups
    assert projection.setup_evidence["accepted_setups"] == result.accepted_setups
    # campaign state -> mapped stage (documented)
    assert decision.setup_properties["campaign_status"] == "ACTIVE"
    assert decision.setup_properties["entry_count"] == 1
    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_ACTIVE
    # data lineage / market_data_mode preserved end to end (via the funnel engine,
    # asserted through the observation carrying the event's mode unchanged)
    assert observation.market_data_mode == "REPLAY"
    # entry/targets never fabricated -- StrategyDecision.setup_properties carries
    # no realized-entry geometry for this strategy (see ssc_adapter docstring)
    assert geometry.entry is None
    assert geometry.targets == ()


def test_ssc_parity_negative_no_setup_cannot_yield_active_setup_detected():
    result = ReplayResult(
        symbol="EURUSD", session_pair="ASIAN_LONDON", trading_date=TRADING_DATE, regime="TREND_UP",
        campaign=None, accepted_setups=[], rejected_setups=[{"reason": "NO_SIGNAL"}], steps=[],
    )
    decision = from_session_sweep_continuation_replay(result)
    adapter = SSCFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(ssc_event(), FunnelState()))

    assert decision.setup_properties["campaign_status"] is None
    assert projection.stage != STAGE_SETUP_DETECTED
    assert projection.stage == STAGE_CONTEXT_VALID
    assert projection.outcome == OUTCOME_WAIT


def test_ssc_parity_negative_replay_mode_cannot_become_real():
    result = ReplayResult(
        symbol="EURUSD", session_pair="ASIAN_LONDON", trading_date=TRADING_DATE, regime="TREND_UP",
        campaign=None, accepted_setups=[], rejected_setups=[], steps=[],
    )
    decision = from_session_sweep_continuation_replay(result)
    adapter = SSCFunnelAdapter(decision=decision)
    observation = adapter.observe(ssc_event(mode="REPLAY"), FunnelState())
    assert observation.market_data_mode == "REPLAY"
    assert observation.market_data_mode != "REAL"


# --- Asian Sweep parity (V2-3C) --------------------------------------------------


def test_asian_sweep_parity_sweep_signal_direction_entry_stop_lineage():
    """Drives the REAL strategy_engine.evaluate() (same canonical engine, same
    fixture shape as tests/test_strategy_engine.py::
    test_evaluate_range_with_sweep_yields_signal) through post_asian_pilot's
    real decision mapper, field-by-field against the adapter's projection."""
    strategy = load_strategy(ASIAN_SWEEP_STRATEGY_PATH)
    session_candles = [
        Candle(datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(datetime(2026, 1, 5, 0, 15, tzinfo=timezone.utc), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    sweep_candle = Candle(datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc), 1.1005, 1.1050 + 0.0010, 1.1000, 1.1050 - 0.0002)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", date(2026, 1, 5), session_candles, 2, [sweep_candle])
    assert signal.status == "SIGNAL"
    assert signal.setup == "SWEEP"
    assert signal.direction == "SHORT"

    eval_time = datetime(2026, 1, 5, 7, 15, tzinfo=timezone.utc)
    window_end = datetime(2026, 1, 5, 11, 0, tzinfo=timezone.utc)
    decision = map_trade_signal_to_decision(signal, "snapshot-parity", eval_time, window_end)
    assert decision.status == STATUS_READY

    adapter = AsianSweepFunnelAdapter(decision=decision)
    observation = adapter.observe(asian_sweep_event(asof=eval_time), FunnelState())
    projection = adapter.project(observation)
    geometry = adapter.candidate_geometry(observation)

    # strategy identity
    assert adapter.strategy_id == decision.strategy_id == "ST_ASIAN_SWEEP_5R_V1"
    # symbol / direction / entry / stop preserved verbatim, never recomputed
    assert decision.symbol == signal.symbol == "EURUSD"
    assert geometry.direction == signal.direction == "SHORT"
    assert geometry.entry == signal.entry
    assert geometry.invalidation == signal.stop_loss
    # canonical state -> mapped stage (documented, non-object-equal)
    assert decision.status == "READY"
    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_ACTIVE
    # setup type preserved as evidence
    assert projection.setup_evidence["setup"] == signal.setup == "SWEEP"
    # no target/rr authority on TradeSignal for a sweep entry -- never fabricated
    assert geometry.targets == ()
    assert geometry.estimated_rr is None


def test_asian_sweep_parity_negative_no_setup_cannot_yield_entry_confirmed():
    strategy = load_strategy(ASIAN_SWEEP_STRATEGY_PATH)
    session_candles = [
        Candle(datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(datetime(2026, 1, 5, 0, 15, tzinfo=timezone.utc), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    boring_candle = Candle(datetime(2026, 1, 5, 7, 0, tzinfo=timezone.utc), 1.1005, 1.1006, 1.1004, 1.1005)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", date(2026, 1, 5), session_candles, 2, [boring_candle])
    assert signal.status == "NO_TRADE"
    assert signal.direction is None

    eval_time = datetime(2026, 1, 5, 7, 15, tzinfo=timezone.utc)
    window_end = datetime(2026, 1, 5, 11, 0, tzinfo=timezone.utc)
    decision = map_trade_signal_to_decision(signal, "snapshot-parity", eval_time, window_end)

    adapter = AsianSweepFunnelAdapter(decision=decision)
    observation = adapter.observe(asian_sweep_event(asof=eval_time), FunnelState())
    projection = adapter.project(observation)

    assert projection.stage != STAGE_ENTRY_CONFIRMED
    geometry = adapter.candidate_geometry(observation)
    assert geometry is None


def test_asian_sweep_parity_negative_replay_mode_cannot_become_real():
    strategy = load_strategy(ASIAN_SWEEP_STRATEGY_PATH)
    session_candles = [
        Candle(datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(datetime(2026, 1, 5, 0, 15, tzinfo=timezone.utc), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", date(2026, 1, 5), session_candles, 2, [])
    eval_time = datetime(2026, 1, 5, 7, 15, tzinfo=timezone.utc)
    window_end = datetime(2026, 1, 5, 11, 0, tzinfo=timezone.utc)
    decision = map_trade_signal_to_decision(signal, "snapshot-parity", eval_time, window_end)

    adapter = AsianSweepFunnelAdapter(decision=decision)
    observation = adapter.observe(asian_sweep_event(asof=eval_time, mode="REPLAY"), FunnelState())
    assert observation.market_data_mode == "REPLAY"
    assert observation.market_data_mode != "REAL"
