from __future__ import annotations

import datetime as dt

from historical_replay.candle_store import HistoricalCandleStore
from strategy_engine.session import Candle
from svos.temporal_lookahead_contract import (
    TEMPORAL_LOOKAHEAD_CONTRACT,
    TEMPORAL_LOOKAHEAD_VERSION,
    validate_temporal_lookahead_contract,
)

UTC = dt.timezone.utc


def _h1_series(start, count, step_minutes=60):
    return [
        Candle(
            time=start + dt.timedelta(minutes=i * step_minutes),
            open=1.0 + i * 0.0001,
            high=1.0 + (i + 1) * 0.0001,
            low=0.9999 - i * 0.00005,
            close=1.0 + (i + 0.5) * 0.0001,
        )
        for i in range(count)
    ]


def _m15_series(start, count):
    return [
        Candle(
            time=start + dt.timedelta(minutes=i * 15),
            open=1.0 + i * 0.0002,
            high=1.0 + (i + 1) * 0.0002,
            low=0.9998 - i * 0.0001,
            close=1.0 + (i + 0.4) * 0.0002,
        )
        for i in range(count)
    ]


def _m1_series(start, count):
    return [
        Candle(
            time=start + dt.timedelta(minutes=i),
            open=1.0 + i * 0.00005,
            high=1.0 + (i + 1) * 0.00005,
            low=0.99995 - i * 0.00002,
            close=1.0 + (i + 0.2) * 0.00005,
        )
        for i in range(count)
    ]


def test_temporal_contract_hash_is_frozen():
    digest = validate_temporal_lookahead_contract(contract=TEMPORAL_LOOKAHEAD_CONTRACT)
    assert digest.startswith("sha256:")
    assert TEMPORAL_LOOKAHEAD_VERSION == "VD_TEMPORAL_LOOKAHEAD_V1"


def test_future_continuation_does_not_change_closed_bar_view_at_decision_time_t():
    t = dt.datetime(2026, 1, 2, 11, 0, tzinfo=UTC)

    prefix_h1 = _h1_series(dt.datetime(2026, 1, 2, 0, 0, tzinfo=UTC), 12)
    prefix_m15 = _m15_series(dt.datetime(2026, 1, 2, 0, 0, tzinfo=UTC), 48)
    prefix_m1 = _m1_series(dt.datetime(2026, 1, 2, 0, 0, tzinfo=UTC), 660)

    future_h1 = [
        Candle(
            time=t + dt.timedelta(hours=1),
            open=1.010, high=1.011, low=1.009, close=1.0105,
        ),
        Candle(
            time=t + dt.timedelta(hours=2),
            open=1.011, high=1.012, low=1.010, close=1.0115,
        ),
    ]
    future_m15 = [
        Candle(
            time=dt.datetime(2026, 1, 2, 12, 15, tzinfo=UTC),
            open=1.012, high=1.013, low=1.011, close=1.0125,
        ),
        Candle(
            time=dt.datetime(2026, 1, 2, 12, 30, tzinfo=UTC),
            open=1.0125, high=1.0135, low=1.012, close=1.013,
        ),
    ]
    future_m1 = [
        Candle(
            time=t + dt.timedelta(minutes=i),
            open=1.015 + i * 0.0002,
            high=1.016 + i * 0.0002,
            low=1.014 + i * 0.0002,
            close=1.0155 + i * 0.0002,
        )
        for i in range(1, 6)
    ]

    truncated = HistoricalCandleStore()
    truncated.load_series("EURUSD", "H1", prefix_h1)
    truncated.load_series("EURUSD", "M15", prefix_m15)
    truncated.load_series("EURUSD", "M1", prefix_m1)

    future_extended = HistoricalCandleStore()
    future_extended.load_series("EURUSD", "H1", prefix_h1 + future_h1)
    future_extended.load_series("EURUSD", "M15", prefix_m15 + future_m15)
    future_extended.load_series("EURUSD", "M1", prefix_m1 + future_m1)

    h1_visible = truncated.closed_candles("EURUSD", "H1", t, 4)
    m15_visible = truncated.closed_candles("EURUSD", "M15", t, 6)
    m1_visible = truncated.closed_candles("EURUSD", "M1", t, 30)

    assert h1_visible == future_extended.closed_candles("EURUSD", "H1", t, 4)
    assert m15_visible == future_extended.closed_candles("EURUSD", "M15", t, 6)
    assert m1_visible == future_extended.closed_candles("EURUSD", "M1", t, 30)
    assert all(c.time <= t for c in h1_visible)
    assert all(c.time <= t for c in m15_visible)
    assert all(c.time <= t for c in m1_visible)
