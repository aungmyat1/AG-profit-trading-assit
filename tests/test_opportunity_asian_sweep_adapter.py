"""V2-3C: Asian Sweep (ST_ASIAN_SWEEP_5R_V1) shadow/funnel adapter -- state
mapping, both session pairs, occurrence identity, idempotence, terminal
stickiness, trading-date/session-boundary behavior, research-authority
preservation, and negative fail-closed cases.

Fixtures build `post_asian_pilot.decision.PostAsianDecision` via that module's
own real constructors (`map_trade_signal_to_decision` / `watch_decision` /
`data_error_decision`) from hand-built `strategy_engine.models.TradeSignal`
instances -- the exact canonical shape `post_asian_pilot.pipeline._evaluate_pair`
already produces every decision cycle. No MT5, no live feed invoked here; this
proves the adapter/funnel wiring against representative canonical output. A
separate canonical-parity test (`test_asian_sweep_canonical_parity_...` below)
drives the REAL `strategy_engine.evaluate()` end to end, matching
tests/test_strategy_engine.py's own fixtures, to prove the adapter never
reinterprets genuine canonical engine output.
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta, timezone

import pytest

from post_asian_pilot.decision import (
    STATUS_EXPIRED,
    STATUS_NO_TRADE,
    STATUS_READY,
    STATUS_WATCH,
    data_error_decision,
    map_trade_signal_to_decision,
    watch_decision,
)
from strategy_engine import evaluate, load_strategy
from strategy_engine.models import TradeSignal
from strategy_engine.session import Candle

from opportunity.asian_sweep_adapter import (
    AsianSweepFunnelAdapter,
    AsianSweepStrategyIdentityMismatchError,
    AsianSweepUnmappedDecisionError,
    STRATEGY_ID,
    STRATEGY_VERSION,
)
from opportunity.candidate_store import CandidateStore
from opportunity.contracts import MarketEvent
from opportunity.engine import TERMINAL_OUTCOMES, evaluate_funnel
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import (
    OUTCOME_ACTIVE,
    OUTCOME_ERROR,
    OUTCOME_EXPIRED,
    OUTCOME_REJECT,
    OUTCOME_WAIT,
    STAGE_CONTEXT_VALID,
    STAGE_ENTRY_CONFIRMED,
    STAGE_LOCATION_VALID,
    STAGE_MARKET_ELIGIBLE,
    STAGE_SETUP_DETECTED,
)
from opportunity.transitions import FunnelState

UTC = timezone.utc
TRADING_DATE = date(2026, 9, 21)
T0 = datetime(2026, 9, 21, 11, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 21, 11, 0, tzinfo=UTC)
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


def binding():
    return StrategyBinding(
        strategy_id=STRATEGY_ID, semantic_version=STRATEGY_VERSION, engine_id="strategy_engine.engine",
        engine_version=None, adapter_id="opportunity.asian_sweep_adapter", adapter_version="1",
        dispatchable=False,
    )


def market_event(pair_id="ASIAN_LONDON", symbol="EURUSD", asof=None, mode="REPLAY"):
    """Stable event_id per (symbol, pair_id, trading_date) occurrence -- see
    asian_sweep_adapter module docstring, 'INTENDED EVENT-IDENTITY PATTERN'.
    Direction deliberately excluded from the key."""
    bar_time = asof if asof is not None else T0
    return MarketEvent(
        event_id=f"ASIAN_SWEEP:{symbol}:{pair_id}:{TRADING_DATE.isoformat()}",
        event_type="SESSION_CYCLE_EVALUATED", symbol=symbol, market="FX", venue=None,
        timeframe="M15", bar_open_time=bar_time, bar_close_time=bar_time, market_data_asof=bar_time,
        market_data_mode=mode, snapshot_fingerprint=None, source="post_asian_pilot.pipeline",
    )


def trade_signal(
    *, setup, status, reason_code, pair_id="ASIAN_LONDON", reference_session="Asian",
    regime="RANGE", direction=None, entry=None, stop_loss=None, risk_distance=None,
    signal_timestamp="AUTO", symbol="EURUSD",
):
    if signal_timestamp == "AUTO":
        # entry_2_sweep always sets signal_timestamp for a VALID sweep decision --
        # decision.py's map_trade_signal_to_decision requires it for READY.
        signal_timestamp = T0 if (setup == "SWEEP" and status == "SIGNAL") else None
    return TradeSignal(
        signal_id=f"{STRATEGY_ID}:{pair_id}:{symbol}:{TRADING_DATE.isoformat()}",
        strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION, symbol=symbol, pair_id=pair_id,
        reference_session=reference_session, session_date=TRADING_DATE,
        box_high=1.1050, box_low=1.0950, box_mid=1.1000, regime=regime, setup=setup, status=status,
        reason_code=reason_code, direction=direction, entry=entry, stop_loss=stop_loss,
        risk_distance=risk_distance, signal_timestamp=signal_timestamp,
    )


def decision_watch(missing_condition, *, reference_session="Asian", valid_until=None):
    return watch_decision(
        STRATEGY_ID, STRATEGY_VERSION, "EURUSD", TRADING_DATE, reference_session, T0,
        missing_condition, valid_until=valid_until,
    )


def decision_data_error(reason_codes=("MARKET_DATA_UNAVAILABLE",), *, reference_session="Asian"):
    return data_error_decision(
        STRATEGY_ID, STRATEGY_VERSION, "EURUSD", TRADING_DATE, reference_session, T0, reason_codes,
    )


def decision_from_signal(signal: TradeSignal, *, evaluation_time=T0, window_end=WINDOW_END):
    return map_trade_signal_to_decision(signal, "snapshot-1", evaluation_time, window_end)


# --- WATCH mapping -----------------------------------------------------------


def test_waiting_reference_session_maps_to_market_eligible_wait():
    adapter = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_REFERENCE_SESSION_COMPLETION"))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_MARKET_ELIGIBLE
    assert projection.outcome == OUTCOME_WAIT


def test_waiting_execution_window_maps_to_location_valid_wait():
    adapter = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_EXECUTION_WINDOW_OPEN"))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_LOCATION_VALID
    assert projection.outcome == OUTCOME_WAIT


def test_waiting_closed_m15_maps_to_location_valid_wait():
    adapter = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_CLOSED_M15_CONFIRMATION"))
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_LOCATION_VALID
    assert projection.outcome == OUTCOME_WAIT


def test_waiting_reference_sweep_maps_to_context_valid_wait():
    signal = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    decision = decision_from_signal(signal, evaluation_time=T0, window_end=T0 + timedelta(hours=1))
    assert decision.status == STATUS_WATCH
    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_CONTEXT_VALID
    assert projection.outcome == OUTCOME_WAIT


# --- READY mapping -------------------------------------------------------------


def test_sweep_signal_maps_to_entry_confirmed_active():
    signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1005, stop_loss=1.0940, risk_distance=0.0065,
        signal_timestamp=T0,
    )
    decision = decision_from_signal(signal)
    assert decision.status == STATUS_READY
    adapter = AsianSweepFunnelAdapter(decision=decision)
    observation = adapter.observe(market_event(), FunnelState())
    projection = adapter.project(observation)
    geometry = adapter.candidate_geometry(observation)

    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_ACTIVE
    assert projection.outcome not in TERMINAL_OUTCOMES
    assert geometry.direction == "LONG"
    assert geometry.entry == 1.1005
    assert geometry.invalidation == 1.0940
    assert geometry.targets == ()
    assert geometry.estimated_rr is None


# --- NO_TRADE mapping -----------------------------------------------------------


def test_non_sweep_trend_signal_is_out_of_scope_rejected():
    signal = trade_signal(
        setup="TREND", status="SIGNAL", reason_code="BOX_DIRECTION_V1", regime="TREND",
        direction="LONG", entry=1.1000, stop_loss=1.0950,
    )
    decision = decision_from_signal(signal)
    assert decision.status == STATUS_NO_TRADE
    adapter = AsianSweepFunnelAdapter(decision=decision)
    observation = adapter.observe(market_event(), FunnelState())
    projection = adapter.project(observation)
    geometry = adapter.candidate_geometry(observation)

    assert projection.stage == STAGE_SETUP_DETECTED
    assert projection.outcome == OUTCOME_REJECT
    assert projection.outcome in TERMINAL_OUTCOMES
    # out-of-scope canonical geometry never fabricated into a candidate
    assert geometry is None


def test_non_sweep_range_signal_is_out_of_scope_rejected():
    signal = trade_signal(
        setup="RANGE", status="SIGNAL", reason_code="UPPER_BOUNDARY_REJECTION",
        direction="SHORT", entry=1.1050, stop_loss=1.1060,
    )
    decision = decision_from_signal(signal)
    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_SETUP_DETECTED
    assert projection.outcome == OUTCOME_REJECT


def test_ambiguous_dual_sweep_rejected():
    signal = trade_signal(setup="SWEEP", status="NO_TRADE", reason_code="AMBIGUOUS_DUAL_SWEEP")
    decision = decision_from_signal(signal)
    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_SETUP_DETECTED
    assert projection.outcome == OUTCOME_REJECT
    assert projection.outcome in TERMINAL_OUTCOMES


def test_flat_box_trend_rejected():
    signal = trade_signal(
        setup="NONE", status="NO_TRADE", reason_code="BOX_DIRECTION_V1_FLAT_NO_TRADE", regime="TREND",
    )
    decision = decision_from_signal(signal)
    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_CONTEXT_VALID
    assert projection.outcome == OUTCOME_REJECT
    assert projection.outcome in TERMINAL_OUTCOMES


# --- EXPIRED mapping -----------------------------------------------------------


def test_window_expired_no_setup_maps_to_context_valid_expired():
    signal = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    decision = decision_from_signal(signal, evaluation_time=WINDOW_END, window_end=WINDOW_END)
    assert decision.status == STATUS_EXPIRED
    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_CONTEXT_VALID
    assert projection.outcome == OUTCOME_EXPIRED
    assert projection.outcome in TERMINAL_OUTCOMES


# --- DATA_ERROR mapping ---------------------------------------------------------


def test_data_error_never_becomes_no_trade():
    decision = decision_data_error(("MARKET_DATA_UNAVAILABLE",))
    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(), FunnelState()))
    assert projection.stage == STAGE_MARKET_ELIGIBLE
    assert projection.outcome == OUTCOME_ERROR
    assert projection.outcome != OUTCOME_REJECT
    assert projection.outcome in TERMINAL_OUTCOMES


# --- Both session pairs --------------------------------------------------------


def test_both_session_pairs_project_independently():
    asian_signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        pair_id="ASIAN_LONDON", reference_session="Asian", direction="LONG", entry=1.1005, stop_loss=1.0940,
    )
    london_signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="UPPER_SWEEP_STRICT_PENETRATION",
        pair_id="LONDON_NEWYORK", reference_session="London", direction="SHORT", entry=1.1045, stop_loss=1.1060,
    )
    asian_adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(asian_signal))
    london_adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(london_signal))

    asian_obs = asian_adapter.observe(market_event(pair_id="ASIAN_LONDON"), FunnelState())
    london_obs = london_adapter.observe(market_event(pair_id="LONDON_NEWYORK"), FunnelState())

    asian_projection = asian_adapter.project(asian_obs)
    london_projection = london_adapter.project(london_obs)

    assert asian_projection.stage == london_projection.stage == STAGE_ENTRY_CONFIRMED
    asian_geometry = asian_adapter.candidate_geometry(asian_obs)
    london_geometry = london_adapter.candidate_geometry(london_obs)
    assert asian_geometry.direction == "LONG"
    assert london_geometry.direction == "SHORT"


# --- Occurrence identity / cross-session collision ------------------------------


def test_same_occurrence_repeated_observation_keeps_same_candidate_identity():
    event = market_event(pair_id="ASIAN_LONDON")
    b = binding()

    watch = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_EXECUTION_WINDOW_OPEN"))
    candidate1, t1 = evaluate_funnel(event=event, binding=b, adapter=watch)

    signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1005, stop_loss=1.0940,
    )
    ready = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
    candidate2, t2 = evaluate_funnel(event=event, binding=b, adapter=ready, previous_candidate=candidate1)

    assert candidate1.candidate_id == candidate2.candidate_id == t1.candidate_id == t2.candidate_id
    assert candidate1.occurrence_id == candidate2.occurrence_id
    assert candidate2.revision == candidate1.revision + 1


def test_different_session_pair_same_symbol_date_yields_different_identity():
    asian_event = market_event(pair_id="ASIAN_LONDON")
    london_event = market_event(pair_id="LONDON_NEWYORK")
    assert asian_event.event_id != london_event.event_id

    b = binding()
    watch = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_EXECUTION_WINDOW_OPEN"))
    asian_candidate, _ = evaluate_funnel(event=asian_event, binding=b, adapter=watch)
    london_candidate, _ = evaluate_funnel(event=london_event, binding=b, adapter=watch)

    assert asian_candidate.candidate_id != london_candidate.candidate_id
    assert asian_candidate.occurrence_id != london_candidate.occurrence_id


# --- Idempotence -----------------------------------------------------------------


def test_repeated_equivalent_observations_are_idempotent():
    event = market_event()
    b = binding()
    signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1005, stop_loss=1.0940,
    )
    candidate = None
    revisions = []
    for _ in range(4):
        adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
        candidate, transition = evaluate_funnel(event=event, binding=b, adapter=adapter, previous_candidate=candidate)
        revisions.append(candidate.revision)
        if len(revisions) > 1:
            assert transition is None

    assert revisions[0] == revisions[1] == revisions[2] == revisions[3] == 1


# --- Legitimate forward progression ----------------------------------------------


def test_legitimate_progression_advances_stage_and_revision():
    event = market_event()
    b = binding()

    watch = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_REFERENCE_SESSION_COMPLETION"))
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=watch)
    assert candidate.stage == STAGE_MARKET_ELIGIBLE and candidate.revision == 1

    watch2 = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_EXECUTION_WINDOW_OPEN"))
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=watch2, previous_candidate=candidate)
    assert candidate.stage == STAGE_LOCATION_VALID and candidate.revision == 2

    no_setup_yet = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    waiting_sweep = AsianSweepFunnelAdapter(
        decision=decision_from_signal(no_setup_yet, evaluation_time=T0, window_end=T0 + timedelta(hours=1))
    )
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=waiting_sweep, previous_candidate=candidate)
    assert candidate.stage == STAGE_CONTEXT_VALID and candidate.revision == 3

    signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1005, stop_loss=1.0940,
    )
    ready = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=ready, previous_candidate=candidate)
    assert candidate.stage == STAGE_ENTRY_CONFIRMED and candidate.revision == 4
    assert candidate.outcome == OUTCOME_ACTIVE


# --- Terminal stickiness -----------------------------------------------------------


def test_terminal_rejected_candidate_cannot_be_reactivated():
    event = market_event()
    b = binding()
    flat = trade_signal(setup="NONE", status="NO_TRADE", reason_code="BOX_DIRECTION_V1_FLAT_NO_TRADE", regime="TREND")
    rejected_adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(flat))
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=rejected_adapter)
    assert candidate.outcome == OUTCOME_REJECT

    signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1005, stop_loss=1.0940,
    )
    ready_adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
    candidate2, transition2 = evaluate_funnel(event=event, binding=b, adapter=ready_adapter, previous_candidate=candidate)

    assert transition2 is None
    assert candidate2.outcome == OUTCOME_REJECT
    assert candidate2.revision == candidate.revision
    assert candidate2.stage == candidate.stage


def test_terminal_transition_preserves_highest_stage_reached():
    """A candidate that reached CONTEXT_VALID (regime classified, waiting for
    sweep) and then terminates EXPIRED at a canonical stage no higher than
    CONTEXT_VALID keeps CONTEXT_VALID -- Safety Invariant #9, enforced
    generically by opportunity.engine.evaluate_funnel, not reimplemented here."""
    event = market_event()
    b = binding()

    waiting = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    waiting_adapter = AsianSweepFunnelAdapter(
        decision=decision_from_signal(waiting, evaluation_time=T0, window_end=T0 + timedelta(hours=1))
    )
    candidate, _ = evaluate_funnel(event=event, binding=b, adapter=waiting_adapter)
    assert candidate.stage == STAGE_CONTEXT_VALID

    expired = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    expired_adapter = AsianSweepFunnelAdapter(
        decision=decision_from_signal(expired, evaluation_time=T0 + timedelta(hours=1), window_end=T0 + timedelta(hours=1))
    )
    candidate2, _ = evaluate_funnel(event=event, binding=b, adapter=expired_adapter, previous_candidate=candidate)
    assert candidate2.stage == STAGE_CONTEXT_VALID
    assert candidate2.outcome == OUTCOME_EXPIRED


# --- Research authority preservation ----------------------------------------------


def test_replay_data_mode_is_preserved_not_upgraded_to_real():
    signal = trade_signal(
        setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
        direction="LONG", entry=1.1005, stop_loss=1.0940,
    )
    adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
    event = market_event(mode="REPLAY")
    candidate, _ = evaluate_funnel(event=event, binding=binding(), adapter=adapter)
    assert candidate.market_data_mode == "REPLAY"
    assert candidate.market_data_mode != "REAL"


def test_adapter_carries_no_proposal_or_execution_authority_fields():
    """StrategyFunnelAdapter's protocol has no proposal/risk/execution method --
    this only asserts the concrete adapter exposes nothing beyond the shared
    protocol surface (supports/observe/project/candidate_geometry/identity)."""
    adapter = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_REFERENCE_SESSION_COMPLETION"))
    public_attrs = {name for name in dir(adapter) if not name.startswith("_")}
    forbidden = {"propose", "authorize", "execute", "risk_decision", "order", "send_order"}
    assert public_attrs.isdisjoint(forbidden)


# --- Negative / fail-closed cases --------------------------------------------------


def test_unrecognized_missing_condition_fails_closed():
    decision = decision_watch("WAITING_REFERENCE_SESSION_COMPLETION")
    object.__setattr__(decision, "missing_condition", "SOMETHING_NEW")
    adapter = AsianSweepFunnelAdapter(decision=decision)
    with pytest.raises(AsianSweepUnmappedDecisionError):
        adapter.project(adapter.observe(market_event(), FunnelState()))


def test_unrecognized_no_trade_reason_fails_closed():
    signal = trade_signal(setup="NONE", status="NO_TRADE", reason_code="SOMETHING_NEW")
    decision = decision_from_signal(signal)
    adapter = AsianSweepFunnelAdapter(decision=decision)
    with pytest.raises(AsianSweepUnmappedDecisionError):
        adapter.project(adapter.observe(market_event(), FunnelState()))


def test_strategy_identity_mismatch_fails_closed():
    decision = decision_watch("WAITING_REFERENCE_SESSION_COMPLETION")
    with pytest.raises(AsianSweepStrategyIdentityMismatchError):
        AsianSweepFunnelAdapter(decision=decision, strategy_id="ST_SOMETHING_ELSE_V1")


def test_out_of_scope_signal_never_fabricates_geometry():
    signal = trade_signal(
        setup="TREND", status="SIGNAL", reason_code="BOX_DIRECTION_V1", regime="TREND",
        direction="LONG", entry=1.1000, stop_loss=1.0950,
    )
    adapter = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
    observation = adapter.observe(market_event(), FunnelState())
    assert adapter.candidate_geometry(observation) is None


# --- CandidateStore integration: restart continuity --------------------------------


def test_candidate_store_integration_and_restart_continuity():
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/asian_sweep_candidates.json"
        event = market_event()
        b = binding()

        store = CandidateStore(path)
        watch = AsianSweepFunnelAdapter(decision=decision_watch("WAITING_EXECUTION_WINDOW_OPEN"))
        candidate1, transition1 = evaluate_funnel(event=event, binding=b, adapter=watch)
        store.persist(candidate1, transition1)

        reloaded_store = CandidateStore(path)
        reloaded = reloaded_store.get(candidate1.candidate_id)
        assert reloaded is not None
        assert reloaded.stage == STAGE_LOCATION_VALID

        signal = trade_signal(
            setup="SWEEP", status="SIGNAL", reason_code="LOWER_SWEEP_STRICT_PENETRATION",
            direction="LONG", entry=1.1005, stop_loss=1.0940,
        )
        ready = AsianSweepFunnelAdapter(decision=decision_from_signal(signal))
        candidate2, transition2 = evaluate_funnel(event=event, binding=b, adapter=ready, previous_candidate=reloaded)
        reloaded_store.persist(candidate2, transition2)

        assert candidate2.candidate_id == candidate1.candidate_id
        assert candidate2.revision == 2
        assert len(reloaded_store.all_candidates()) == 1


# --- Trading-date / session boundary ------------------------------------------------


def test_trading_date_matches_utc_calendar_date_for_all_session_pairs():
    """Verified property (see asian_sweep_adapter module docstring,
    'TRADING-DATE SEMANTICS'): none of ST_ASIAN_SWEEP_5R_V1's session windows
    cross a UTC midnight boundary, so trading_date == the UTC calendar date of
    the reference session for both pairs."""
    import yaml

    with open(STRATEGY_PATH, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    for pair in raw["session_pairs"]:
        ref = pair["reference_session"]
        trade = pair["trade_session"]
        for window in (ref, trade):
            start_hour = int(window["start_time_gmt"].split(":")[0])
            end_hour = int(window["end_time_gmt"].split(":")[0])
            assert 0 <= start_hour <= end_hour <= 24


def test_window_end_boundary_distinguishes_watch_from_expired():
    signal_before = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    before = decision_from_signal(signal_before, evaluation_time=WINDOW_END - timedelta(minutes=1), window_end=WINDOW_END)
    assert before.status == STATUS_WATCH

    signal_at = trade_signal(setup="NONE", status="NO_TRADE", reason_code="NO_SETUP_BY_WINDOW_END")
    at_end = decision_from_signal(signal_at, evaluation_time=WINDOW_END, window_end=WINDOW_END)
    assert at_end.status == STATUS_EXPIRED

    before_adapter = AsianSweepFunnelAdapter(decision=before)
    at_end_adapter = AsianSweepFunnelAdapter(decision=at_end)
    before_projection = before_adapter.project(before_adapter.observe(market_event(), FunnelState()))
    at_end_projection = at_end_adapter.project(at_end_adapter.observe(market_event(), FunnelState()))

    assert before_projection.outcome == OUTCOME_WAIT
    assert at_end_projection.outcome == OUTCOME_EXPIRED
    assert at_end_projection.outcome in TERMINAL_OUTCOMES


# --- Canonical parity: real strategy_engine.evaluate() end to end -----------------


def test_asian_sweep_canonical_parity_sweep_signal_produces_ready_and_entry_confirmed():
    """Drives the REAL canonical evaluator (strategy_engine.evaluate(), same
    fixture shape as tests/test_strategy_engine.py::
    test_evaluate_range_with_sweep_yields_signal) through post_asian_pilot's
    real decision mapper into this adapter -- proves the adapter does not
    reinterpret genuine canonical engine output."""
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = [
        Candle(datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(datetime(2026, 1, 5, 0, 15, tzinfo=UTC), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    sweep_candle = Candle(datetime(2026, 1, 5, 7, 0, tzinfo=UTC), 1.1005, 1.1060, 1.1000, 1.1048)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", date(2026, 1, 5), session_candles, 2, [sweep_candle])
    assert signal.status == "SIGNAL"
    assert signal.setup == "SWEEP"

    eval_time = datetime(2026, 1, 5, 7, 15, tzinfo=UTC)
    window_end = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "snapshot-parity", eval_time, window_end)
    assert decision.status == STATUS_READY

    adapter = AsianSweepFunnelAdapter(decision=decision)
    observation = adapter.observe(
        MarketEvent(
            event_id=f"ASIAN_SWEEP:EURUSD:ASIAN_LONDON:{decision.trading_date.isoformat()}",
            event_type="SESSION_CYCLE_EVALUATED", symbol="EURUSD", market="FX", venue=None,
            timeframe="M15", bar_open_time=eval_time, bar_close_time=eval_time, market_data_asof=eval_time,
            market_data_mode="REPLAY", snapshot_fingerprint=None, source="post_asian_pilot.pipeline",
        ),
        FunnelState(),
    )
    projection = adapter.project(observation)
    geometry = adapter.candidate_geometry(observation)

    assert projection.stage == STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_ACTIVE
    assert geometry.direction == signal.direction == "SHORT"
    assert geometry.entry == signal.entry
    assert geometry.invalidation == signal.stop_loss


def test_asian_sweep_canonical_parity_no_setup_stays_out_of_entry_confirmed():
    strategy = load_strategy(STRATEGY_PATH)
    session_candles = [
        Candle(datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(datetime(2026, 1, 5, 0, 15, tzinfo=UTC), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    boring_candle = Candle(datetime(2026, 1, 5, 7, 0, tzinfo=UTC), 1.1005, 1.1006, 1.1004, 1.1005)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", date(2026, 1, 5), session_candles, 2, [boring_candle])
    assert signal.status == "NO_TRADE"

    eval_time = datetime(2026, 1, 5, 7, 15, tzinfo=UTC)
    window_end = datetime(2026, 1, 5, 11, 0, tzinfo=UTC)
    decision = map_trade_signal_to_decision(signal, "snapshot-parity", eval_time, window_end)
    assert decision.status == STATUS_WATCH

    adapter = AsianSweepFunnelAdapter(decision=decision)
    projection = adapter.project(adapter.observe(market_event(asof=eval_time), FunnelState()))
    assert projection.stage != STAGE_ENTRY_CONFIRMED
    assert projection.outcome == OUTCOME_WAIT
