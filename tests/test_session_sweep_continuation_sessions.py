from datetime import date, datetime, timedelta, timezone

from session_sweep_continuation.sessions import (
    build_reference_session,
    session_windows_from_config,
    trade_session_candles,
)
from strategy_engine.session.candles import Candle

PIP = 0.0001
DAY = date(2026, 9, 10)


def _candle(hour, minute, o, h, l, c):
    return Candle(datetime(2026, 9, 10, hour, minute, tzinfo=timezone.utc), o, h, l, c)


CONFIG = {
    "session_pairs": [
        {"pair_id": "ASIAN_LONDON",
         "reference_session": {"start_time_utc": "00:00", "end_time_utc": "06:00"},
         "trade_session": {"start_time_utc": "07:00", "end_time_utc": "11:00"}},
    ]
}


def test_reference_session_construction_no_future_contamination():
    windows = session_windows_from_config(CONFIG)["ASIAN_LONDON"]["reference"]
    candles = [
        _candle(0, 0, 1.1000, 1.1010, 1.0990, 1.1005),
        _candle(1, 0, 1.1005, 1.1050, 1.1000, 1.1040),  # highest
        _candle(2, 0, 1.1040, 1.1045, 1.0950, 1.0960),  # lowest
        # a candle AFTER the reference window closes with a more extreme high --
        # must never be counted even though it's chronologically close.
        _candle(6, 30, 1.0960, 1.2000, 1.0500, 1.1500),
    ]
    as_of = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    ref = build_reference_session(candles, windows, DAY, as_of, PIP)
    assert ref.high == 1.1050
    assert ref.low == 1.0950
    assert ref.candle_count == 3
    assert ref.frozen is True


def test_reference_session_excludes_not_yet_closed_candle():
    windows = session_windows_from_config(CONFIG)["ASIAN_LONDON"]["reference"]
    candles = [
        _candle(0, 0, 1.1000, 1.1010, 1.0990, 1.1005),
        _candle(5, 45, 1.1005, 1.3000, 1.0000, 1.1500),  # opens before 06:00, closes at 06:00
    ]
    # as_of BEFORE this last candle's own close (06:00) -- it must be excluded.
    as_of = datetime(2026, 9, 10, 5, 50, tzinfo=timezone.utc)
    ref = build_reference_session(candles, windows, DAY, as_of, PIP)
    assert ref.candle_count == 1
    assert ref.high == 1.1010

    as_of_after_close = datetime(2026, 9, 10, 6, 0, tzinfo=timezone.utc)
    ref2 = build_reference_session(candles, windows, DAY, as_of_after_close, PIP)
    assert ref2.candle_count == 2
    assert ref2.high == 1.3000


def test_trade_session_candles_bounded_to_window():
    windows = session_windows_from_config(CONFIG)["ASIAN_LONDON"]["trade"]
    candles = [
        _candle(6, 45, 1.1, 1.1, 1.1, 1.1),   # before trade window
        _candle(7, 0, 1.1, 1.1, 1.1, 1.1),    # in window
        _candle(10, 45, 1.1, 1.1, 1.1, 1.1),  # in window
        _candle(11, 0, 1.1, 1.1, 1.1, 1.1),   # at/after end, excluded
    ]
    as_of = datetime(2026, 9, 10, 11, 0, tzinfo=timezone.utc)
    got = trade_session_candles(candles, windows, DAY, as_of)
    assert [c.time.hour for c in got] == [7, 10]
