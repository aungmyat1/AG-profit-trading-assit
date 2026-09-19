"""TD-8C: canonical session facts use one closed M15 population in live and replay."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import yaml

import assistant.market_data as market_data
import session_clock as clock
from historical_replay import HistoricalCandleStore, historical_data_context
from historical_replay.candle_store import HistoricalDataError
from strategy_engine.session import Candle, build_reference_box
from strategy_engine.loader import load_strategy
from session_sweep_continuation.sessions import build_reference_session, session_windows_from_config
from supply_demand.native_zones import session_zone

DAY = date(2026, 9, 18)  # Friday
UTC = timezone.utc


def at(hour, minute=0, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def bars():
    result = []
    for hour in list(range(0, 11)) + list(range(12, 15)):
        for minute in (0, 15, 30, 45):
            t = at(hour, minute)
            p = 1.1 + len(result) * 0.0001
            result.append(Candle(time=t, open=p, high=p+0.001, low=p-0.001,
                                 close=p+0.0002, volume=10))
    return result


def store(data=None):
    result = HistoricalCandleStore()
    result.load_series("EURUSD", "M15", data if data is not None else bars())
    return result


@pytest.mark.parametrize("name,reference_close,trade_open,trade_close", [
    ("asian", 6, 7, 11), ("london_am", 11, 12, 15),
])
def test_reference_and_trade_boundaries(name, reference_close, trade_open, trade_close):
    before = at(0) if name == "asian" else at(5, 59)
    during = at(reference_close - 1)
    moments = [before, during, at(reference_close), at(reference_close, 30),
               at(trade_open), at(trade_open + 1), at(trade_close), at(trade_close + 1)]
    for index, moment in enumerate(moments):
        with historical_data_context(store(), moment):
            snap = market_data.session_snapshot("EURUSD", name, DAY)
        assert snap.session_date == DAY
        assert snap.status == ("SESSION_INCOMPLETE" if index < 2 else "OK")
        assert snap.complete == (index >= 2)
        if index >= 2:
            assert snap.bar_count == clock.expected_bar_count(name)


def test_forming_bar_missing_data_and_future_data_fail_closed():
    data = bars()
    with historical_data_context(store(data[:23]), at(6)):
        incomplete_data = market_data.session_snapshot("EURUSD", "asian", DAY)
    assert incomplete_data.status == "INSUFFICIENT_CANDLES"
    with historical_data_context(HistoricalCandleStore(), at(7)):
        with patch.object(market_data, "get_candles", side_effect=AssertionError("live range accessed")):
            missing = market_data.session_snapshot("EURUSD", "asian", DAY)
    assert missing.status == "DATA_MISSING"
    with historical_data_context(store(), at(5, 59)):
        forming = market_data.session_snapshot("EURUSD", "asian", DAY)
    assert forming.status == "SESSION_INCOMPLETE" and forming.high is None


def test_future_candle_change_has_no_effect_on_fact_at_t():
    original = bars()
    changed = list(original)
    changed[-1] = replace(changed[-1], high=changed[-1].high + 100)
    with historical_data_context(store(original), at(11)):
        first = market_data.session_snapshot("EURUSD", "london_am", DAY)
    with historical_data_context(store(changed), at(11)):
        second = market_data.session_snapshot("EURUSD", "london_am", DAY)
    assert first == second and first.status == "OK"


def test_live_replay_parity_for_same_closed_population():
    data = bars()
    start, end = clock.get_session_bounds(DAY, "asian")
    visible = [c for c in data if start <= c.time < end]
    with historical_data_context(store(data), at(7)):
        replay = market_data.session_snapshot("EURUSD", "asian", DAY)
        zone = session_zone("EURUSD", "asian", DAY)
    with patch.object(market_data, "get_candles", return_value=visible), \
         patch.object(market_data, "datetime") as fake_datetime:
        fake_datetime.now.return_value = at(7)
        live = market_data.session_snapshot("EURUSD", "asian", DAY)
    assert replay == live
    assert (zone.low, zone.high) == (replay.low, replay.high)
    box = build_reference_box("Asian", visible, clock.expected_bar_count("asian"))
    assert (box.session_high, box.session_low, box.session_complete) == (
        replay.high, replay.low, replay.status == "OK",
    )


def test_friday_reference_visible_on_weekend_but_no_saturday_fabrication():
    saturday = at(7, day=date(2026, 9, 19))
    with historical_data_context(store(), saturday):
        friday = market_data.session_snapshot("EURUSD", "asian", DAY)
        saturday_default = market_data.session_snapshot("EURUSD", "asian")
    assert friday.status == "OK" and friday.session_date == DAY
    assert saturday_default.status == "DATA_MISSING"


def test_naive_replay_clock_is_rejected_before_session_evaluation():
    with pytest.raises(HistoricalDataError, match="NAIVE_DATETIME_REJECTED"):
        with historical_data_context(store(), datetime(2026, 9, 18, 7)):
            market_data.session_snapshot("EURUSD", "asian", DAY)


@pytest.mark.parametrize("pair_id,canonical_name", [
    ("ASIAN_LONDON", "asian"), ("LONDON_NEWYORK", "london_am"),
])
def test_frozen_strategy_consumers_see_the_same_reference_population(pair_id, canonical_name):
    data = bars()
    _, reference_end = clock.get_session_bounds(DAY, canonical_name)
    replay_store = store(data)
    with historical_data_context(replay_store, reference_end):
        fact = market_data.session_snapshot("EURUSD", canonical_name, DAY)
        start, end = clock.get_session_bounds(DAY, canonical_name)
        visible = replay_store.closed_candles_in_range("EURUSD", "M15", start, end, reference_end)

    asian_strategy = load_strategy("strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
    asian_pair = next(p for p in asian_strategy.session_pairs if p.pair_id == pair_id)
    assert asian_pair.reference_session.start_time_gmt == start.strftime("%H:%M")
    assert asian_pair.reference_session.end_time_gmt == end.strftime("%H:%M")
    asian_box = build_reference_box(asian_pair.reference_session.name, visible, len(visible))

    with open("strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml", encoding="utf-8") as handle:
        ssc_config = yaml.safe_load(handle)
    ssc_window = session_windows_from_config(ssc_config)[pair_id]["reference"]
    ssc = build_reference_session(data, ssc_window, DAY, reference_end, pip_size=0.0001)
    assert fact.status == "OK"
    assert (asian_box.session_high, asian_box.session_low) == (fact.high, fact.low)
    assert (ssc.high, ssc.low, ssc.frozen, ssc.candle_count) == (
        fact.high, fact.low, True, fact.bar_count,
    )


@pytest.mark.parametrize("pair_id,before,opened,during,closed", [
    ("ASIAN_LONDON", (6, 59), (7, 0), (10, 59), (11, 0)),
    ("LONDON_NEWYORK", (11, 59), (12, 0), (14, 59), (15, 0)),
])
def test_frozen_trade_window_boundaries_are_not_reinterpreted(
    pair_id, before, opened, during, closed,
):
    asian_strategy = load_strategy("strategies/ST_ASIAN_SWEEP_5R_V1.yaml")
    asian_pair = next(p for p in asian_strategy.session_pairs if p.pair_id == pair_id)
    with open("strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml", encoding="utf-8") as handle:
        ssc_config = yaml.safe_load(handle)
    ssc_window = session_windows_from_config(ssc_config)[pair_id]["trade"]
    start, end = ssc_window.bounds_for_date(DAY)
    assert asian_pair.trade_session.start_time_gmt == start.strftime("%H:%M")
    assert asian_pair.trade_session.end_time_gmt == end.strftime("%H:%M")
    assert [start <= at(*moment) < end for moment in (before, opened, during, closed)] == [
        False, True, True, False,
    ]
