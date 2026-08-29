"""RUNTIME_OPERATIONAL_HARDENING_V1 focused tests (spec section 50): active-candidate
restart, exactly-once bar processing across restart, crash-recovery/corruption
semantics, notification retry without duplicate events, stale-data fail-closed +
recovery, and a bounded simulated soak. No trading policy is changed by this file.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from unittest.mock import patch

from daytrading_runtime.smc_runtime import PersistentSMCRuntime
from entry_confirmation.models import EntryConfirmationRequest, EntryConfirmationResult, OverallState
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from runtime_state.store import JsonKeyValueStore, StateStoreCorrupted
from smc_watcher.conditions import evaluate_e3_condition
from smc_watcher.models import ALERT_STATE_CONFIRMED, ALERT_STATE_WAITING_M5_CONFIRMATION

UTC = dt.timezone.utc


def _sweep_level(sweep_time, price=1.1000):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=LiquiditySide.SELL_SIDE, source="ASIAN_LOW",
        price=price, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC),
        status=LiquidityStatus.RECLAIMED, sweep_time=sweep_time,
    )


def _runtime(tmp_path, alert_sink=None):
    return PersistentSMCRuntime(
        JsonKeyValueStore(os.path.join(str(tmp_path), "smc_alerts.json")),
        JsonKeyValueStore(os.path.join(str(tmp_path), "bar_cursors.json")),
        alert_sink=alert_sink,
    )


# ---------------------------------------------------------- 1-3: active-candidate restart


def test_active_candidate_restart_same_bar_skipped_next_bar_processed_once(tmp_path):
    alert_path = os.path.join(str(tmp_path), "smc_alerts.json")
    bar_path = os.path.join(str(tmp_path), "bar_cursors.json")

    runtime_a = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime_a.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert record["alert_state"] == ALERT_STATE_WAITING_M5_CONFIRMATION

    bar_t = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC)
    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")
    first_pass = runtime_a.advance_m5(record["alert_id"], m5_request, m5_bar_time=bar_t)
    assert first_pass["last_m5_evaluation_time"] is not None

    # --- process "restarts": brand-new runtime instances over the same store files ---
    runtime_b = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))
    restored = runtime_b.alert_store.get(record["alert_id"])
    assert restored["alert_state"] == ALERT_STATE_WAITING_M5_CONFIRMATION  # candidate restored, not lost

    # SAME closed bar T fed again after "restart" -> must be skipped (no duplicate progression)
    same_bar_again = runtime_b.advance_m5(record["alert_id"], m5_request, m5_bar_time=bar_t)
    assert same_bar_again["last_m5_evaluation_time"] == first_pass["last_m5_evaluation_time"]

    # A genuinely NEW closed bar T+1 -> processed exactly once
    bar_t_plus_1 = dt.datetime(2026, 1, 5, 7, 5, tzinfo=UTC)
    next_bar = runtime_b.advance_m5(record["alert_id"], m5_request, m5_bar_time=bar_t_plus_1)
    assert next_bar["last_m5_evaluation_time"] != first_pass["last_m5_evaluation_time"]

    # Repeating T+1 again does not re-progress either.
    next_bar_again = runtime_b.advance_m5(record["alert_id"], m5_request, m5_bar_time=bar_t_plus_1)
    assert next_bar_again["last_m5_evaluation_time"] == next_bar["last_m5_evaluation_time"]


def test_confirmed_candidate_restart_stays_confirmed_and_never_reprocesses(tmp_path):
    alert_path = os.path.join(str(tmp_path), "smc_alerts.json")
    bar_path = os.path.join(str(tmp_path), "bar_cursors.json")
    runtime_a = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime_a.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    fake_confirmed = EntryConfirmationResult(
        symbol="EURUSD", timeframe="M5", candidate_direction="LONG", status="EVALUATED",
        displacement=None, structure_shift=None, liquidity_reclaim=None, rejection=None,
        event_sequence=None, overall_state=OverallState.CONFIRMED,
    )
    with patch("daytrading_runtime.smc_runtime.request_m5_confirmation", return_value=fake_confirmed):
        confirmed = runtime_a.advance_m5(record["alert_id"], EntryConfirmationRequest(symbol="EURUSD", timeframe="M5"))
    assert confirmed["alert_state"] == ALERT_STATE_CONFIRMED

    # "restart"
    runtime_b = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))
    resumed = runtime_b.alert_store.get(record["alert_id"])
    assert resumed["alert_state"] == ALERT_STATE_CONFIRMED

    still = runtime_b.advance_m5(record["alert_id"], EntryConfirmationRequest(symbol="EURUSD", timeframe="M5"))
    assert still == resumed  # a resolved candidate never advances again, restart or not
    assert still["execution_eligible"] is False


# ---------------------------------------------------------------- 4-5: event dedup depth


def test_same_source_event_not_duplicated_after_restart_new_distinct_event_allowed(tmp_path):
    alert_path = os.path.join(str(tmp_path), "smc_alerts.json")
    bar_path = os.path.join(str(tmp_path), "bar_cursors.json")
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))

    runtime_a = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))
    first = runtime_a.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)

    runtime_b = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))
    duplicate_attempt = runtime_b.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert duplicate_attempt == first  # same source event -- no new record after restart

    new_e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 6, 6, 15, tzinfo=UTC)))
    new_event = runtime_b.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=new_e3)
    assert new_event["alert_id"] != first["alert_id"]  # genuinely new event is still allowed


# ---------------------------------------------------------------- 8: state store hardening


def test_temp_file_leftover_from_a_crash_does_not_corrupt_reads(tmp_path):
    """A crash between temp-write and os.replace must never surface a partial file --
    only the target path is ever read, so a stray/garbage .tmp file must be inert."""
    path = os.path.join(str(tmp_path), "state.json")
    store = JsonKeyValueStore(path)
    store.put("key1", {"a": 1})

    # Simulate a crash mid-write: a leftover temp file with garbage content, target
    # file untouched.
    with open(f"{path}.tmp", "w", encoding="utf-8") as f:
        f.write("{not valid json, crash mid-write")

    reopened = JsonKeyValueStore(path)
    assert reopened.get("key1") == {"a": 1}  # original valid state, unaffected by the stray temp file


def test_corrupt_state_fails_closed_never_silently_resets(tmp_path):
    path = os.path.join(str(tmp_path), "state.json")
    store = JsonKeyValueStore(path)
    store.put("key1", {"a": 1})

    with open(path, "w", encoding="utf-8") as f:
        f.write("{ truncated")  # simulate a torn write landing directly on the target

    broken = JsonKeyValueStore(path)
    try:
        broken.get("key1")
        assert False, "expected StateStoreCorrupted"
    except StateStoreCorrupted:
        pass  # fail closed, not an empty store


# ---------------------------------------------------------------- 9-10: notification retry


def test_notification_retry_reuses_same_event_id(tmp_path):
    class FlakySink:
        def __init__(self):
            self.calls = 0

        def publish(self, alert):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("transient network error")

    sink = FlakySink()
    runtime = _runtime(tmp_path, alert_sink=sink)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))

    first = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert first["notification_status"] == "FAILED"

    retried = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert retried["alert_id"] == first["alert_id"]  # same event, not a new one
    assert retried["notification_status"] == "SENT"
    assert sink.calls == 2


def test_notification_already_sent_is_not_republished(tmp_path):
    class CountingSink:
        def __init__(self):
            self.calls = 0

        def publish(self, alert):
            self.calls += 1

    sink = CountingSink()
    runtime = _runtime(tmp_path, alert_sink=sink)
    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))

    runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    assert sink.calls == 1  # SENT status is terminal -- no repeated publish for the same event


# ---------------------------------------------------------------- 15: forming-bar safety


def test_bar_cursor_only_advances_on_a_strictly_later_closed_bar(tmp_path):
    """has_new_closed_bar must treat an equal or earlier bar_time as already-seen --
    a forming/incomplete bar with the same or older timestamp must never look new."""
    runtime = _runtime(tmp_path)
    t1 = dt.datetime(2026, 1, 5, 7, 5, tzinfo=UTC)
    t0_earlier = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC)

    assert runtime.has_new_closed_bar("EURUSD", "M5", "w1", t1) is True
    runtime.mark_bar_evaluated("EURUSD", "M5", "w1", t1)

    assert runtime.has_new_closed_bar("EURUSD", "M5", "w1", t1) is False  # same bar again -- not new
    assert runtime.has_new_closed_bar("EURUSD", "M5", "w1", t0_earlier) is False  # earlier/stale -- not new


# ---------------------------------------------------------------- 16: no execution call


def test_advance_m5_never_imports_or_calls_execution():
    import ast
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "src" / "daytrading_runtime" / "smc_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for n in names:
            assert not n.startswith("execution"), f"smc_runtime.py imports {n}"


# --------------------------------------------------------------------- simulated soak


def test_simulated_soak_many_cycles_bounded_state_no_duplicates(tmp_path):
    """Section 42: hundreds of synthetic cycles -- same bar repeated, new bars, a new
    distinct sweep event, notification failure/recovery -- state must stay bounded
    (one record per distinct event) and no duplicate alerts/progressions occur."""
    alert_path = os.path.join(str(tmp_path), "smc_alerts.json")
    bar_path = os.path.join(str(tmp_path), "bar_cursors.json")
    runtime = PersistentSMCRuntime(JsonKeyValueStore(alert_path), JsonKeyValueStore(bar_path))

    e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 5, 6, 15, tzinfo=UTC)))
    record = runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
    alert_id = record["alert_id"]

    m5_request = EntryConfirmationRequest(symbol="EURUSD", timeframe="M5")
    bar_time = dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC)

    # 300 cycles hammering the SAME closed bar and the SAME trigger -- must never grow
    # the store or re-progress the candidate.
    for _ in range(300):
        runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=e3)
        runtime.advance_m5(alert_id, m5_request, m5_bar_time=bar_time)

    assert len(runtime.alert_store.all()) == 1
    assert runtime.alert_store.get(alert_id)["alert_state"] == ALERT_STATE_WAITING_M5_CONFIRMATION

    # A genuinely new bar and a genuinely new sweep are still allowed exactly once each.
    bar_time_2 = dt.datetime(2026, 1, 5, 7, 5, tzinfo=UTC)
    runtime.advance_m5(alert_id, m5_request, m5_bar_time=bar_time_2)

    new_e3 = evaluate_e3_condition(_sweep_level(dt.datetime(2026, 1, 6, 6, 15, tzinfo=UTC)))
    for _ in range(100):
        runtime.evaluate_and_persist("SMC_CONDITIONAL", "EURUSD", e3_result=new_e3)

    assert len(runtime.alert_store.all()) == 2  # exactly one new distinct event, no matter how many polls


# ------------------------------------------------------------- 11-12: transient MT5 failure


def test_transient_market_data_failure_fails_closed_then_recovers():
    """Section 27: a MarketDataError on one cycle yields INDETERMINATE (never a
    fabricated trigger); a subsequent healthy cycle evaluates normally."""
    from daytrading_runtime import snapshot as snap
    from mt5.market_data import MarketDataError
    from smc_watcher.models import STATE_INDETERMINATE, STATE_WATCHING

    def _raise(*a, **k):
        raise MarketDataError("MT5_TIMEOUT", "transient failure")

    with patch.object(snap, "fair_value_gaps_for", side_effect=_raise):
        failed_cycle = snap.build_e1_result("EURUSD")
    assert failed_cycle.state == STATE_INDETERMINATE
    assert failed_cycle.triggered is False

    class _EmptyZoneQuery:
        status = "OK"
        zones = ()

    with patch.object(snap, "fair_value_gaps_for", return_value=_EmptyZoneQuery()), \
            patch.object(snap, "get_latest_candles", return_value=[]):
        recovered_cycle = snap.build_e1_result("EURUSD")
    assert recovered_cycle.state == STATE_WATCHING  # back to normal evaluation, not stuck INDETERMINATE


# --------------------------------------------------------- 6-7: session transition in-process


def test_session_transition_while_process_stays_alive_no_restart():
    """Section 15: the SAME PersistentSessionRuntime instance sees a session go from
    incomplete to complete across two calls (simulating two poll cycles of one running
    process) -- evaluated exactly once, on the cycle where it actually completed."""
    import os as _os

    from daytrading.decision.models import MarketBias, MarketBiasDirection
    from daytrading_runtime.session_runtime import PersistentSessionRuntime
    from runtime_state.store import JsonKeyValueStore as _Store
    from strategy_engine.session import Candle

    def candle(hour, minute, o, h, l, c):
        return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_path:
        store = _Store(_os.path.join(tmp_path, "session_events.json"))
        runtime = PersistentSessionRuntime(store)
        bias = MarketBias(direction=MarketBiasDirection.BULLISH.value, timeframe="H1")

        partial_session = [candle(*divmod(15 * i, 60), 1.1, 1.1, 1.1, 1.1) for i in range(10)]  # 10 of 24 bars
        still_incomplete = runtime.process_symbol("TEST", "EURUSD", "asian", dt.date(2026, 1, 5), partial_session, 24, bias)
        assert still_incomplete is None
        assert store.all() == {}  # not yet a SESSION_COMPLETED event -- nothing persisted

        full_session = [candle(*divmod(15 * i, 60), 1.1, 1.1, 1.1, 1.1) for i in range(24)]  # now complete
        completed = runtime.process_symbol("TEST", "EURUSD", "asian", dt.date(2026, 1, 5), full_session, 24, bias)
        assert completed is not None
        assert len(store.all()) == 1  # evaluated exactly once, on the cycle it actually completed

        # A further poll cycle in the SAME running process must not re-evaluate it.
        again = runtime.process_symbol("TEST", "EURUSD", "asian", dt.date(2026, 1, 5), full_session, 24, bias)
        assert again == completed
        assert len(store.all()) == 1
