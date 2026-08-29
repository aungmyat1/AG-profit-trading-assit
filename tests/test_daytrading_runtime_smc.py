"""DUAL_DAYTRADING_RUNTIME_V1 spec sections 37-38: persistent, restart-safe SMC alert
dedup, persist-before-publish, and M5 candidate resume/advance.
"""
from __future__ import annotations

import datetime as dt
import os

from daytrading_runtime.ids import smc_alert_id
from daytrading_runtime.smc_runtime import PersistentSMCRuntime
from entry_confirmation.models import EntryConfirmationRequest
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from runtime_state.store import JsonKeyValueStore
from smc_watcher.conditions import evaluate_e3_condition
from smc_watcher.models import ALERT_STATE_CONFIRMED, ALERT_STATE_WAITING_M5_CONFIRMATION

UTC = dt.timezone.utc


def _runtime(tmp_path, alert_sink=None):
    alert_store = JsonKeyValueStore(os.path.join(str(tmp_path), "smc_alerts.json"))
    bar_store = JsonKeyValueStore(os.path.join(str(tmp_path), "bar_cursors.json"))
    return PersistentSMCRuntime(alert_store, bar_store, alert_sink=alert_sink)


def _sweep_level(sweep_time):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE, source="ASIAN_LOW",
        price=1.1000, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC),
        status=LiquidityStatus.RECLAIMED, sweep_time=sweep_time,
    )


def test_e3_trigger_is_persisted(tmp_path):
    runtime = _runtime(tmp_path)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert record is not None
    assert record["alert_state"] == ALERT_STATE_WAITING_M5_CONFIRMATION
    assert record["execution_eligible"] is False


def test_restart_simulation_no_duplicate_alert(tmp_path):
    path = os.path.join(str(tmp_path), "smc_alerts.json")
    bar_path = os.path.join(str(tmp_path), "bar_cursors.json")
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))

    first_runtime = PersistentSMCRuntime(JsonKeyValueStore(path), JsonKeyValueStore(bar_path))
    first = first_runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    second_runtime = PersistentSMCRuntime(JsonKeyValueStore(path), JsonKeyValueStore(bar_path))
    second = second_runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert second == first


def test_genuinely_new_sweep_allows_new_alert(tmp_path):
    runtime = _runtime(tmp_path)
    first_e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    first = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=first_e3)

    second_e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 6, 6, 15, tzinfo=UTC)))
    second = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=second_e3)

    assert first["alert_id"] != second["alert_id"]


def test_persist_before_publish_survives_sink_failure(tmp_path):
    class FailingSink:
        def publish(self, alert):
            raise RuntimeError("network down")

    runtime = _runtime(tmp_path, alert_sink=FailingSink())
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    assert record["notification_status"] == "FAILED"
    persisted = runtime.alert_store.get(record["alert_id"])
    assert persisted is not None  # event survives even though notification failed -- never dropped


def test_no_signed_expiry_policy_is_not_invented(tmp_path):
    runtime = _runtime(tmp_path)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert record["expires_at"] is None
    assert "UNDEFINED" in record["expiry_reason"]


# --------------------------------------------------------------------------- M5 tracking


def test_m5_confirmed_updates_alert_state_execution_still_blocked(tmp_path):
    runtime = _runtime(tmp_path)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    # No confirmations requested -> V1 engine returns INDETERMINATE, not fabricated CONFIRMED.
    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")
    advanced = runtime.advance_m5(record["alert_id"], m5_request)
    assert advanced["alert_state"] == ALERT_STATE_WAITING_M5_CONFIRMATION
    assert advanced["execution_eligible"] is False


def test_same_m5_candle_processed_twice_does_not_duplicate_transition(tmp_path):
    runtime = _runtime(tmp_path)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    bar_time = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC)
    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")

    first = runtime.advance_m5(record["alert_id"], m5_request, m5_bar_time=bar_time)
    first_eval_time = first["last_m5_evaluation_time"]

    second = runtime.advance_m5(record["alert_id"], m5_request, m5_bar_time=bar_time)
    assert second["last_m5_evaluation_time"] == first_eval_time  # not re-evaluated for the same closed bar


def test_new_closed_m5_candle_is_reevaluated(tmp_path):
    runtime = _runtime(tmp_path)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")
    first = runtime.advance_m5(record["alert_id"], m5_request, m5_bar_time=dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC))
    second = runtime.advance_m5(record["alert_id"], m5_request, m5_bar_time=dt.datetime(2026, 1, 5, 7, 5, tzinfo=UTC))
    assert second["last_m5_evaluation_time"] != first["last_m5_evaluation_time"]


def test_restart_resumes_waiting_m5_candidate(tmp_path):
    path = os.path.join(str(tmp_path), "smc_alerts.json")
    bar_path = os.path.join(str(tmp_path), "bar_cursors.json")
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))

    first_runtime = PersistentSMCRuntime(JsonKeyValueStore(path), JsonKeyValueStore(bar_path))
    record = first_runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    second_runtime = PersistentSMCRuntime(JsonKeyValueStore(path), JsonKeyValueStore(bar_path))
    resumed = second_runtime.alert_store.get(record["alert_id"])
    assert resumed["alert_state"] == ALERT_STATE_WAITING_M5_CONFIRMATION

    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")
    advanced = second_runtime.advance_m5(record["alert_id"], m5_request)
    assert advanced is not None


def test_resolved_candidate_no_longer_advances(tmp_path):
    from unittest.mock import patch

    from entry_confirmation.models import EntryConfirmationResult, OverallState

    runtime = _runtime(tmp_path)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    fake_result = EntryConfirmationResult(
        symbol="EURUSD", timeframe="M5", candidate_direction="LONG", status="EVALUATED",
        displacement=None, structure_shift=None, liquidity_reclaim=None, rejection=None,
        event_sequence=None, overall_state=OverallState.CONFIRMED,
    )
    with patch("daytrading_runtime.smc_runtime.request_m5_confirmation", return_value=fake_result):
        confirmed = runtime.advance_m5(record["alert_id"], EntryConfirmationRequest(symbol="EURUSD", timeframe="M5"))
    assert confirmed["alert_state"] == ALERT_STATE_CONFIRMED
    assert confirmed["execution_eligible"] is False

    still_confirmed = runtime.advance_m5(record["alert_id"], EntryConfirmationRequest(symbol="EURUSD", timeframe="M5"))
    assert still_confirmed == confirmed  # a resolved candidate does not keep evolving
