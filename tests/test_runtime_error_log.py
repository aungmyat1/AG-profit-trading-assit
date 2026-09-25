"""Focused tests for AG_FX_RUNTIME_ERROR_STRUCTURED_PROVENANCE_REMEDIATION_V1 --
structured runtime-error provenance additive to the existing aggregate
MonitoringCounters COUNTER_DATA_ERRORS counter. Uses tmp_path-backed JsonKeyValueStore
files throughout -- never touches the real journal/ directory, never calls MT5, never
touches execution/broker paths.
"""
from __future__ import annotations

import datetime as dt
from unittest import mock

import pytest

from mt5.market_data import MarketDataError
from post_asian_pilot import pipeline as pipeline_module
from post_asian_pilot.pilot_config import load_pilot_config
from post_asian_pilot.report import render_pilot_end_report
from post_asian_pilot.runtime_error_log import (
    FINAL_STATE_RECOVERED,
    FINAL_STATE_UNRESOLVED,
    OP_ASIAN_CANDLES_FETCH,
    RuntimeErrorLog,
)
from post_asian_pilot.store import PilotStores, save_decision
from post_asian_pilot.decision import data_error_decision
from runtime_state.store import JsonKeyValueStore
from strategy_engine.loader import load_strategy
from strategy_engine.session import Candle

UTC = dt.timezone.utc
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"


@pytest.fixture(scope="module")
def strategy():
    return load_strategy(STRATEGY_PATH)


def _m15_candles(start: dt.datetime, count: int, base: float = 1.1000, step: float = 0.0001):
    out = []
    price = base
    for i in range(count):
        t = start + dt.timedelta(minutes=15 * i)
        out.append(Candle(time=t, open=price, high=price + step, low=price - step, close=price))
        price += step * 0.1
    return out


# --------------------------------------------------------------------------- unit-level (1-5, 9)

def test_runtime_error_creates_structured_event(tmp_path):
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    now = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    event = log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", dt.date(2026, 9, 24), "asian",
                             OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", now)
    assert event["operation"] == OP_ASIAN_CANDLES_FETCH
    assert event["error_class"] == "MT5_TIMEOUT"
    assert event["timestamp"] == now.isoformat()
    assert event["attempt"] == 1
    assert event["retry_occurred"] is False
    assert event["recovered"] is False
    assert event["final_state"] == FINAL_STATE_UNRESOLVED


def test_structured_record_uses_correct_unit_identity(tmp_path):
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    now = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    event = log.record_error("ST_ASIAN_SWEEP_5R_V1", "GBPUSD", dt.date(2026, 9, 24), "asian",
                             OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", now)
    assert event["strategy_id"] == "ST_ASIAN_SWEEP_5R_V1"
    assert event["symbol"] == "GBPUSD"
    assert event["trading_date"] == "2026-09-24"
    assert event["reference_session"] == "asian"


def test_retry_attempt_remains_linked_to_original_operation(tmp_path):
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    d = dt.date(2026, 9, 24)
    t1 = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    t2 = dt.datetime(2026, 9, 24, 6, 15, tzinfo=UTC)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t1)
    second = log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH,
                              "MT5_TIMEOUT", t2)
    assert second["attempt"] == 2
    assert second["retry_occurred"] is True
    events = log.events_for_date("ST_ASIAN_SWEEP_5R_V1", d)
    assert len(events) == 2
    assert {e["operation"] for e in events} == {OP_ASIAN_CANDLES_FETCH}


def test_successful_retry_records_recovery(tmp_path):
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    d = dt.date(2026, 9, 24)
    t1 = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    t2 = dt.datetime(2026, 9, 24, 6, 15, tzinfo=UTC)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t1)
    recovered = log.record_recovery("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, t2)
    assert recovered["recovered"] is True
    assert recovered["final_state"] == FINAL_STATE_RECOVERED
    assert recovered["recovered_at"] == t2.isoformat()
    assert recovered["attempt"] == 1  # the original failed attempt, now marked recovered


def test_recovery_resolves_every_unresolved_attempt_in_the_retry_chain(tmp_path):
    """Review finding: if an operation fails twice before a later successful retry,
    the retry must close BOTH failed attempts -- not only the most recent one, which
    would otherwise leave an earlier attempt permanently UNRESOLVED even though the
    operation actually recovered."""
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    d = dt.date(2026, 9, 24)
    t1 = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    t2 = dt.datetime(2026, 9, 24, 6, 15, tzinfo=UTC)
    t3 = dt.datetime(2026, 9, 24, 6, 30, tzinfo=UTC)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t1)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t2)
    recovered = log.record_recovery("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, t3)
    assert recovered["attempt"] == 2

    events = log.events_for_date("ST_ASIAN_SWEEP_5R_V1", d)
    assert len(events) == 2
    assert all(e["recovered"] for e in events)
    assert all(e["final_state"] == FINAL_STATE_RECOVERED for e in events)
    assert sum(1 for e in events if not e["recovered"]) == 0


def test_unrecovered_failure_remains_distinguishable(tmp_path):
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    d = dt.date(2026, 9, 24)
    t1 = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t1)
    events = log.events_for_date("ST_ASIAN_SWEEP_5R_V1", d)
    assert len(events) == 1
    assert events[0]["recovered"] is False
    assert events[0]["final_state"] == FINAL_STATE_UNRESOLVED


def test_multiple_runtime_errors_remain_individually_explainable(tmp_path):
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    d = dt.date(2026, 9, 24)
    t1 = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t1)
    log.record_error("ST_ASIAN_SWEEP_5R_V1", "GBPUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, "MT5_TIMEOUT", t1)
    events = log.events_for_date("ST_ASIAN_SWEEP_5R_V1", d)
    assert len(events) == 2
    by_symbol = {e["symbol"]: e for e in events}
    assert set(by_symbol) == {"EURUSD", "GBPUSD"}
    # each is independently unresolved -- neither collapses into the other
    assert all(e["recovered"] is False for e in events)


def test_ordinary_success_creates_no_false_runtime_error(tmp_path):
    """A record_recovery call with no preceding unresolved failure must be a pure no-op:
    no event created, nothing written."""
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    d = dt.date(2026, 9, 24)
    now = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    result = log.record_recovery("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, now)
    assert result is None
    assert log.events_for_date("ST_ASIAN_SWEEP_5R_V1", d) == []


# --------------------------------------------------------------------------- restart persistence (8)

def test_restart_preserves_structured_provenance(tmp_path):
    path = str(tmp_path / "runtime_error_log.json")
    d = dt.date(2026, 9, 24)
    t1 = dt.datetime(2026, 9, 24, 6, 0, tzinfo=UTC)
    log_before_restart = RuntimeErrorLog.default(path)
    log_before_restart.record_error("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH,
                                    "MT5_TIMEOUT", t1)

    # Simulate a process restart: a fresh RuntimeErrorLog/JsonKeyValueStore instance
    # pointed at the same file, exactly like every other journal/* store in this repo.
    log_after_restart = RuntimeErrorLog.default(path)
    events = log_after_restart.events_for_date("ST_ASIAN_SWEEP_5R_V1", d)
    assert len(events) == 1
    assert events[0]["error_class"] == "MT5_TIMEOUT"
    assert events[0]["recovered"] is False

    t2 = dt.datetime(2026, 9, 24, 6, 15, tzinfo=UTC)
    log_after_restart.record_recovery("ST_ASIAN_SWEEP_5R_V1", "EURUSD", d, "asian", OP_ASIAN_CANDLES_FETCH, t2)

    log_after_second_restart = RuntimeErrorLog.default(path)
    events = log_after_second_restart.events_for_date("ST_ASIAN_SWEEP_5R_V1", d)
    assert events[0]["recovered"] is True


# --------------------------------------------------------------------------- backward compatibility (13)

def test_old_format_record_remains_readable_with_no_fabricated_recovery(tmp_path):
    """A JsonKeyValueStore file written before this remediation existed simply has no
    runtime_error_log.json at all (or an unrelated store's file). events_for_date() must
    return [] rather than raising or fabricating recovered=True/False for a day that
    genuinely has no structured provenance -- the aggregate counter remains the sole
    authority for such a day."""
    # A pre-existing decision store written in the pre-remediation shape (no structured
    # provenance concept at all) -- reusing the real data_error_decision()/save_decision()
    # shape already exercised elsewhere in this suite, not a guessed shape.
    strategy = load_strategy(STRATEGY_PATH)
    decision_store = JsonKeyValueStore(str(tmp_path / "decision.json"))
    d = dt.date(2026, 9, 14)  # one of the already-CLOSED historical reconciliation days
    decision = data_error_decision(strategy.strategy_id, strategy.version, "EURUSD", d, "asian",
                                   dt.datetime(2026, 9, 14, 6, 0, tzinfo=UTC), ("DATA_MISSING",))
    save_decision(decision_store, decision)

    # No runtime_error_log.json exists yet for this state_dir -- exactly the historical
    # situation for 2026-09-14/16/18/22.
    log = RuntimeErrorLog.default(str(tmp_path / "runtime_error_log.json"))
    events = log.events_for_date(strategy.strategy_id, d)
    assert events == []  # unavailable/legacy, never fabricated


def test_historical_day_report_unaffected_by_missing_structured_provenance(tmp_path, strategy):
    """A day reported before this remediation (structured log empty) must classify
    exactly as it did before: recovered_errors/unresolved_errors are both 0, and
    `result`/`runtime_errors` (the pre-existing aggregate) are unchanged."""
    stores = PilotStores.default(strategy.strategy_id, state_dir=str(tmp_path))
    pilot = load_pilot_config()
    trading_date = dt.date(2026, 9, 14)
    stores.counters.increment(strategy.strategy_id, trading_date, "data_errors")
    for symbol in pilot.universe:
        decision = data_error_decision(strategy.strategy_id, strategy.version, symbol, trading_date,
                                       pilot.reference_session_name, dt.datetime(2026, 9, 14, 8, 0, tzinfo=UTC),
                                       ("DATA_MISSING",))
        save_decision(stores.decision_store, decision)

    report = render_pilot_end_report(pilot, strategy, "AG_TRADE_ASSISTANT_V1_0_3", trading_date, stores)
    assert report["result"] == "PASS_WITH_OBSERVATIONS"  # unchanged classification
    assert report["operations"]["runtime_errors"] == 1  # unchanged aggregate
    assert report["operations"]["recovered_errors"] == 0
    assert report["operations"]["unresolved_errors"] == 0
    assert report["operations"]["runtime_error_events"] == []


# --------------------------------------------------------------------------- pipeline integration (1-7)

def test_pipeline_asian_candles_transient_failure_then_recovery(tmp_path, strategy):
    """End-to-end through the real _evaluate_pair (asian-window get_candles site): attempt
    1 raises MarketDataError -> structured error event + COUNTER_DATA_ERRORS increment;
    attempt 2 (same unit) succeeds -> structured recovery event, and the aggregate
    counter is untouched by the recovery (it only ever counts failures, same as before
    this remediation)."""
    pilot = load_pilot_config()
    stores = PilotStores.default(strategy.strategy_id, state_dir=str(tmp_path))
    trading_date = dt.date(2026, 9, 24)
    now = dt.datetime(2026, 9, 24, 6, 30, tzinfo=UTC)  # after ref_end(06:00), before window_start(07:00)

    with mock.patch.object(pipeline_module, "get_candles", side_effect=MarketDataError("MT5_TIMEOUT", "boom")):
        result = pipeline_module._evaluate_pair(pilot, strategy, "EURUSD", trading_date, now, stores)
    assert result.decision.status == "DATA_ERROR"
    assert stores.counters.snapshot(strategy.strategy_id, trading_date)["data_errors"] == 1
    events = stores.runtime_error_log.events_for_date(strategy.strategy_id, trading_date)
    assert len(events) == 1
    assert events[0]["operation"] == OP_ASIAN_CANDLES_FETCH
    assert events[0]["recovered"] is False

    good_candles = _m15_candles(dt.datetime(2026, 9, 24, 0, 0, tzinfo=UTC), 24)
    with mock.patch.object(pipeline_module, "get_candles", return_value=good_candles):
        pipeline_module._evaluate_pair(pilot, strategy, "EURUSD", trading_date, now, stores)

    # Aggregate counter unaffected by the successful retry -- still exactly 1, matching
    # the pre-remediation semantics the historical reconciliation already relied on.
    assert stores.counters.snapshot(strategy.strategy_id, trading_date)["data_errors"] == 1
    events = stores.runtime_error_log.events_for_date(strategy.strategy_id, trading_date)
    assert len(events) == 1
    assert events[0]["recovered"] is True
    assert events[0]["final_state"] == FINAL_STATE_RECOVERED


def test_pipeline_ordinary_success_creates_no_runtime_error_event(tmp_path, strategy):
    """The plain healthy path (no prior failure at all) must not create any structured
    event -- proves record_recovery()'s no-op guard is actually wired correctly into the
    real pipeline call site, not just unit-tested in isolation."""
    pilot = load_pilot_config()
    stores = PilotStores.default(strategy.strategy_id, state_dir=str(tmp_path))
    trading_date = dt.date(2026, 9, 24)
    now = dt.datetime(2026, 9, 24, 6, 30, tzinfo=UTC)

    good_candles = _m15_candles(dt.datetime(2026, 9, 24, 0, 0, tzinfo=UTC), 24)
    with mock.patch.object(pipeline_module, "get_candles", return_value=good_candles):
        pipeline_module._evaluate_pair(pilot, strategy, "EURUSD", trading_date, now, stores)

    assert stores.counters.snapshot(strategy.strategy_id, trading_date)["data_errors"] == 0
    assert stores.runtime_error_log.events_for_date(strategy.strategy_id, trading_date) == []
