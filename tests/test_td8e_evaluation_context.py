from datetime import datetime, timedelta, timezone

import pytest

from historical_replay import HistoricalCandleStore, ReplayEvaluationContext, ReplayEvaluationError, BoundReplaySeries
from historical_replay.dataset_identity import build_dataset_identity
from strategy_engine.session import Candle


UTC = timezone.utc


def _bars(start, minutes, count, offset=0.0):
    return [Candle(start + timedelta(minutes=minutes * i), 1 + offset + i,
                   2 + offset + i, 0 + offset + i, 1.5 + offset + i, 1) for i in range(count)]


def test_context_is_t_bound_and_excludes_forming_and_future_bars():
    store = HistoricalCandleStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store.load_series("EURUSD", "M15", _bars(start, 15, 4))
    ctx = ReplayEvaluationContext.create(store, "EURUSD", start + timedelta(minutes=38), ("M15",))
    assert [c.time for c in ctx.candles("M15")] == [start, start + timedelta(minutes=15)]


def test_context_rejects_required_series_replacement():
    store = HistoricalCandleStore()
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store.load_series("EURUSD", "M15", _bars(start, 15, 3))
    ctx = ReplayEvaluationContext.create(store, "EURUSD", start + timedelta(hours=1), ("M15",))
    store.load_series("EURUSD", "M15", _bars(start, 15, 3, offset=10))
    with pytest.raises(ReplayEvaluationError):
        ctx.candles("M15")


def test_future_only_dataset_changes_preserve_visible_semantics_but_identity_differs():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    visible = _bars(start, 15, 3)
    s1, s2 = HistoricalCandleStore(), HistoricalCandleStore()
    s1.load_series("EURUSD", "M15", visible + _bars(start + timedelta(minutes=45), 15, 1, 1))
    s2.load_series("EURUSD", "M15", visible + _bars(start + timedelta(minutes=45), 15, 1, 9))
    t = start + timedelta(minutes=45)
    c1 = ReplayEvaluationContext.create(s1, "EURUSD", t, ("M15",))
    c2 = ReplayEvaluationContext.create(s2, "EURUSD", t, ("M15",))
    assert tuple(c1.candles("M15")) == tuple(c2.candles("M15"))
    assert c1.event_id != c2.event_id


def test_m1_lineage_is_part_of_event_identity():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M15", _bars(start, 15, 3))
    store.load_series("EURUSD", "H1", _bars(start, 60, 3))
    store.load_series("EURUSD", "M1", _bars(start, 1, 5))
    setup = ReplayEvaluationContext.create(store, "EURUSD", start + timedelta(hours=2), ("H1", "M15"))
    outcome = ReplayEvaluationContext.create(store, "EURUSD", start + timedelta(hours=2), ("H1", "M15", "M1"))
    assert setup.event_id != outcome.event_id


@pytest.mark.parametrize("timeframe,minutes", [("H1", 60), ("M15", 15), ("M1", 1)])
def test_participating_series_replacement_fails_closed(timeframe, minutes):
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store = HistoricalCandleStore()
    store.load_series("EURUSD", timeframe, _bars(start, minutes, 3))
    ctx = ReplayEvaluationContext.create(store, "EURUSD", start + timedelta(days=1), (timeframe,))
    store.load_series("EURUSD", timeframe, _bars(start, minutes, 3, offset=100))
    with pytest.raises(ReplayEvaluationError):
        ctx.candles(timeframe)


def test_nonparticipating_m1_replacement_does_not_invalidate_setup_event():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "H1", _bars(start, 60, 3))
    store.load_series("EURUSD", "M15", _bars(start, 15, 3))
    store.load_series("EURUSD", "M1", _bars(start, 1, 3))
    ctx = ReplayEvaluationContext.create(store, "EURUSD", start + timedelta(days=1), ("H1", "M15"))
    store.load_series("EURUSD", "M1", _bars(start, 1, 3, offset=100))
    assert len(ctx.candles("M15")) == 3


def test_bound_series_rejects_identity_content_symbol_and_timeframe_mismatch():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    d1 = _bars(start, 15, 2)
    d2 = _bars(start, 15, 2, offset=9)
    identity = build_dataset_identity(symbol="EURUSD", timeframe="M15", candles=d1)
    with pytest.raises(ValueError):
        BoundReplaySeries("EURUSD", "M15", identity, d2)
    with pytest.raises(ValueError):
        BoundReplaySeries("GBPUSD", "M15", identity, d1)
    with pytest.raises(ValueError):
        BoundReplaySeries("EURUSD", "H1", identity, d1)


def test_bound_series_defensively_normalizes_mutable_input():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    source = _bars(start, 15, 2)
    identity = build_dataset_identity(symbol="EURUSD", timeframe="M15", candles=source)
    bound = BoundReplaySeries("EURUSD", "M15", identity, source)
    source[0] = _bars(start, 15, 2, offset=100)[0]
    assert isinstance(bound.candles, tuple)
    assert bound.candles[0].close == 1.5
