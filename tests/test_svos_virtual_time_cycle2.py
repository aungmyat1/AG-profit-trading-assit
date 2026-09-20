from datetime import datetime, timedelta, timezone

import pytest

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext
from market_intelligence.composer import compose_market_intelligence
from strategy_engine.session import Candle
from svos.virtual_time import VirtualClock, VirtualMarketFeed, VirtualTimeError


UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)


def _bars(minutes, count, *, future_offset=0):
    result = []
    for i in range(count):
        price = 1.0 + i + (future_offset if i == count - 1 else 0)
        result.append(Candle(START + timedelta(minutes=i * minutes), price,
                             price + 1, price - 1, price + 0.5, 1))
    return result


def _store(future_offset=0, *, omit=None, reverse_load=False):
    store = HistoricalCandleStore()
    specifications = (("M1", 1, 65), ("M15", 15, 5), ("H1", 60, 2))
    for tf, minutes, count in reversed(specifications) if reverse_load else specifications:
        if tf != omit:
            store.load_series("EURUSD", tf, _bars(minutes, count,
                              future_offset=future_offset), dataset_id=f"FIXTURE_{tf}",
                              source="CONTROLLED_FIXTURE")
    return store


def _feed(store, end_minutes=60, start_minutes=0):
    return VirtualMarketFeed(store, "EURUSD", ("M1", "M15", "H1"),
                             VirtualClock(START + timedelta(minutes=start_minutes),
                                          START + timedelta(minutes=end_minutes)))


def test_incremental_m1_m15_h1_visibility_uses_td8e():
    feed = _feed(_store())
    seen = []
    while feed.status != "END_OF_DATA":
        batch = feed.step()
        seen.extend(batch)
        if batch:
            at = feed.clock.T
            context = ReplayEvaluationContext.create(feed.store, "EURUSD", at,
                                                     ("M1", "M15", "H1"))
            for event in batch:
                assert event.candle in context.candles(event.timeframe)
                assert event.dataset_id == f"FIXTURE_{event.timeframe}"
                assert event.source_id == "CONTROLLED_FIXTURE"
    assert [(e.timeframe, e.at) for e in seen if e.at == START + timedelta(minutes=15)] == [
        ("M15", START + timedelta(minutes=15)),
        ("M1", START + timedelta(minutes=15))]
    assert {e.timeframe for e in seen if e.at == START + timedelta(hours=1)} == {"M1", "M15", "H1"}
    assert all(e.candle.time < e.at for e in seen)
    assert feed.clock.T == START + timedelta(hours=1)
    assert feed.step() == ()


def test_future_mutation_preserves_visible_semantics_but_not_full_lineage():
    a, b = _feed(_store(1), 60), _feed(_store(99), 60)
    a.run()
    b.run()
    assert [(e.at, e.timeframe, e.payload_id) for e in a.events] == [
        (e.at, e.timeframe, e.payload_id) for e in b.events]
    assert a.semantic_sequence_id == b.semantic_sequence_id
    assert a.sequence_id != b.sequence_id  # TD-8E dataset identity covers future bars.
    ca = ReplayEvaluationContext.create(a.store, "EURUSD", a.clock.T, a.timeframes)
    cb = ReplayEvaluationContext.create(b.store, "EURUSD", b.clock.T, b.timeframes)
    assert all(ca.candles(tf) == cb.candles(tf) for tf in a.timeframes)
    ma = compose_market_intelligence(ca)
    mb = compose_market_intelligence(cb)
    assert ma.quality == mb.quality
    assert ma.identity.as_of == mb.identity.as_of
    assert ma.provenance != mb.provenance  # Full dataset lineage is retained.


@pytest.mark.parametrize("mode", ["step", "accelerated", "maximum"])
def test_speed_modes_have_identical_semantic_sequence(mode):
    reference = _feed(_store())
    reference.run("maximum")
    candidate = _feed(_store())
    candidate.run(mode, sleep=lambda _: None)
    assert len(candidate.events) == len(reference.events)
    assert [(e.at, e.event_id, e.payload_id) for e in candidate.events] == [
        (e.at, e.event_id, e.payload_id) for e in reference.events]
    assert candidate.clock.T == reference.clock.T
    assert candidate.sequence_id == reference.sequence_id


def test_end_of_data_missing_series_and_clock_bounds_fail_closed():
    with pytest.raises(Exception):
        _feed(_store(omit="H1"))
    with pytest.raises(VirtualTimeError):
        VirtualClock(START + timedelta(hours=1), START)
    clock = VirtualClock(START, START + timedelta(minutes=2))
    with pytest.raises(VirtualTimeError):
        clock.advance_to(START + timedelta(minutes=3))
    assert clock.finish() == START + timedelta(minutes=2)
    with pytest.raises(VirtualTimeError):
        clock.advance_to(clock.T)
    feed = _feed(_store(), 2)
    feed.run()
    assert feed.status == "END_OF_DATA"
    assert len(feed.events) == 2
    assert feed.clock.T == START + timedelta(minutes=2)


def test_zero_raw_or_live_mt5_candle_calls(monkeypatch):
    import mt5.market_data as market_data

    calls = []
    for name in ("get_candles", "get_latest_candles", "get_tick"):
        monkeypatch.setattr(market_data, name,
                            lambda *args, _name=name, **kwargs: calls.append(_name))
    _feed(_store()).run("maximum")
    assert calls == []


def test_equal_close_times_ignore_loader_order_and_identity_replacement_fails():
    a = _feed(_store())
    a.run()
    b = _feed(_store(reverse_load=True))
    b.run()
    assert a.sequence_id == b.sequence_id
    feed = _feed(_store(), 15)
    feed.store.load_series("EURUSD", "M1", _bars(1, 65, future_offset=8),
                           dataset_id="FIXTURE_M1", source="CONTROLLED_FIXTURE")
    with pytest.raises(VirtualTimeError):
        feed.step()
