"""DUAL_DAYTRADING_RUNTIME_V1 spec sections 35-36: persistent, restart-safe
once-per-(strategy_id, symbol, reference_session, trading_date) session evaluation.
"""
from __future__ import annotations

import datetime as dt
import os

from daytrading.decision.models import MarketBias, MarketBiasDirection
from daytrading_runtime.session_runtime import PersistentSessionRuntime
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)
DAY_2 = dt.date(2026, 1, 6)


def _candle(hour, minute, o, h, l, c):
    return Candle(dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), o, h, l, c)


def _bias(direction):
    return MarketBias(direction=direction, timeframe="H1")


def _flat_session(n=24, price=1.1000):
    return [_candle(*divmod(15 * i, 60), price, price, price, price) for i in range(n)]


def _sell_side_sweep_candle():
    return _candle(6, 15, 1.0999, 1.0999, 1.0995, 1.1002)


def test_incomplete_session_is_not_persisted(tmp_path):
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "session_events.json"))
    runtime = PersistentSessionRuntime(store)
    result = runtime.process_symbol(
        "TEST", "EURUSD", "asian", DAY, _flat_session(n=5), 24, _bias(MarketBiasDirection.BULLISH.value),
    )
    assert result is None
    assert store.all() == {}


def test_completed_session_persists_and_is_not_reevaluated(tmp_path):
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "session_events.json"))
    runtime = PersistentSessionRuntime(store)
    first = runtime.process_symbol(
        "TEST", "GBPUSD", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        post_session_candles=[_sell_side_sweep_candle()],
    )
    assert first is not None
    assert first["proposal"]["proposal_status"] == "WAITING_CONFIRMATION"

    second = runtime.process_symbol(
        "TEST", "GBPUSD", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        post_session_candles=[_sell_side_sweep_candle()],
    )
    assert second == first  # returns the persisted record, not a fresh evaluation


def test_restart_simulation_new_runtime_instance_same_store_no_duplicate(tmp_path):
    path = os.path.join(str(tmp_path), "session_events.json")
    first_runtime = PersistentSessionRuntime(JsonKeyValueStore(path))
    first = first_runtime.process_symbol(
        "TEST", "USDJPY", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        post_session_candles=[_sell_side_sweep_candle()],
    )
    assert first is not None

    # Simulate a process restart: brand-new runtime + store instance pointed at the
    # same file.
    second_runtime = PersistentSessionRuntime(JsonKeyValueStore(path))
    second = second_runtime.process_symbol(
        "TEST", "USDJPY", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        post_session_candles=[_sell_side_sweep_candle()],
    )
    assert second == first


def test_different_reference_session_is_independent_event(tmp_path):
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "session_events.json"))
    runtime = PersistentSessionRuntime(store)
    asian = runtime.process_symbol(
        "TEST", "EURUSD", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        post_session_candles=[_sell_side_sweep_candle()],
    )
    london = runtime.process_symbol(
        "TEST", "EURUSD", "london", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        post_session_candles=[_sell_side_sweep_candle()],
    )
    assert asian is not None and london is not None
    assert asian["event_id"] != london["event_id"]


def test_next_trading_date_is_independent_event(tmp_path):
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "session_events.json"))
    runtime = PersistentSessionRuntime(store)
    day1 = runtime.process_symbol(
        "TEST", "EURUSD", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
    )
    day2 = runtime.process_symbol(
        "TEST", "EURUSD", "asian", DAY_2, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
    )
    assert day1 is not None and day2 is not None
    assert day1["event_id"] != day2["event_id"]


def test_five_configured_symbols_give_five_independent_event_ids(tmp_path):
    from daytrading_workflow.universe import load_session_universe

    universe = load_session_universe()
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "session_events.json"))
    runtime = PersistentSessionRuntime(store)
    event_ids = set()
    for symbol in universe.configured_symbols:
        result = runtime.process_symbol(
            "TEST", symbol, "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
        )
        event_ids.add(result["event_id"])
    assert len(event_ids) == len(universe.configured_symbols)


def test_no_setup_is_persisted_and_terminal(tmp_path):
    store = JsonKeyValueStore(os.path.join(str(tmp_path), "session_events.json"))
    runtime = PersistentSessionRuntime(store)
    first = runtime.process_symbol(
        "TEST", "EURUSD", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
    )
    assert first["proposal"]["proposal_status"] == "NO_SETUP"
    second = runtime.process_symbol(
        "TEST", "EURUSD", "asian", DAY, _flat_session(), 24, _bias(MarketBiasDirection.BULLISH.value),
    )
    assert second == first  # NO_SETUP is not re-visited
