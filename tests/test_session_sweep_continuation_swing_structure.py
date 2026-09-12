from datetime import datetime, timedelta, timezone

from session_sweep_continuation.swing_structure import (
    BOSDirection,
    FVGDirection,
    SwingType,
    compute_atr,
    detect_bos,
    detect_fractal_swings,
    detect_fvg,
    swings_confirmed_by,
)
from strategy_engine.session.candles import Candle

PIP = 0.0001


def _c(i, o, h, l, c):
    return Candle(datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i), o, h, l, c)


def test_fractal_swing_detection_basic_high_and_low_no_lookahead():
    # index 2 is a swing high (higher than 2 bars each side), index 5 a swing low.
    candles = [
        _c(0, 1.10, 1.101, 1.099, 1.100),
        _c(1, 1.100, 1.103, 1.099, 1.102),
        _c(2, 1.102, 1.110, 1.101, 1.105),  # swing high
        _c(3, 1.105, 1.104, 1.100, 1.101),
        _c(4, 1.101, 1.102, 1.099, 1.100),
        _c(5, 1.100, 1.101, 1.090, 1.095),  # swing low
        _c(6, 1.095, 1.098, 1.092, 1.096),
        _c(7, 1.096, 1.099, 1.093, 1.097),
    ]
    swings = detect_fractal_swings(candles, bars_each_side=2)
    highs = [s for s in swings if s.swing_type == SwingType.HIGH]
    lows = [s for s in swings if s.swing_type == SwingType.LOW]
    assert [s.index for s in highs] == [2]
    assert [s.index for s in lows] == [5]
    # confirmed_at is the close of the +2 bar -- index 4's close for the swing at 2.
    assert swings[0].confirmed_at == candles[4].time + timedelta(minutes=15)


def test_swing_not_confirmed_until_confirmation_bars_close_no_lookahead():
    candles = [
        _c(0, 1.10, 1.101, 1.099, 1.100),
        _c(1, 1.100, 1.103, 1.099, 1.102),
        _c(2, 1.102, 1.110, 1.101, 1.105),  # swing high candidate
        _c(3, 1.105, 1.104, 1.100, 1.101),
        _c(4, 1.101, 1.102, 1.099, 1.100),
    ]
    swings = detect_fractal_swings(candles, bars_each_side=2)
    assert len(swings) == 1
    too_early = candles[3].time + timedelta(minutes=15)  # before confirmation bar closes
    assert swings_confirmed_by(swings, too_early) == []
    on_time = candles[4].time + timedelta(minutes=15)
    assert swings_confirmed_by(swings, on_time) == swings


def test_bos_triggers_on_close_beyond_swing_not_on_wick():
    candles = [
        _c(0, 1.10, 1.101, 1.099, 1.100),
        _c(1, 1.100, 1.103, 1.099, 1.102),
        _c(2, 1.102, 1.110, 1.101, 1.105),  # swing high @ 1.110
        _c(3, 1.105, 1.104, 1.100, 1.101),
        _c(4, 1.101, 1.102, 1.099, 1.100),  # confirms swing high
        # candle 5: wick pokes above 1.110 but CLOSES back below -- must NOT be a BOS
        _c(5, 1.100, 1.115, 1.099, 1.105),
        # candle 6: closes above 1.110 -- this IS a BOS
        _c(6, 1.105, 1.120, 1.104, 1.115),
    ]
    as_of = candles[-1].time + timedelta(minutes=15)
    swings = detect_fractal_swings(candles, bars_each_side=2)
    events = detect_bos(candles, swings, as_of)
    assert len(events) == 1
    assert events[0].direction == BOSDirection.UP
    assert events[0].break_candle_index == 6


def test_fvg_bull_bear_min_max_rejection():
    # bullish gap: c1.high < c3.low
    c1 = _c(0, 1.1000, 1.1010, 1.0990, 1.1005)
    c2 = _c(1, 1.1005, 1.1020, 1.1000, 1.1015)
    c3 = _c(2, 1.1015, 1.1030, 1.1013, 1.1025)  # c3.low=1.1013 > c1.high=1.1010 -> gap 0.0003 = 3 pips
    events = detect_fvg([c1, c2, c3], PIP, min_pips=1.5, max_pips=15.0)
    assert len(events) == 1
    assert events[0].direction == FVGDirection.BULLISH
    assert events[0].eligible is True
    assert abs(events[0].size_pips - 3.0) < 1e-9

    # too small (< min_pips) -> ineligible
    c3_small = _c(2, 1.1015, 1.1020, 1.1011, 1.1012)  # gap = 1.1011-1.1010=0.0001 = 1 pip
    events_small = detect_fvg([c1, c2, c3_small], PIP, min_pips=1.5, max_pips=15.0)
    assert events_small[0].eligible is False

    # too large (> max_pips) -> ineligible
    c3_big = _c(2, 1.1015, 1.1200, 1.1100, 1.1150)  # gap = 1.1100-1.1010=0.0090=90 pips
    events_big = detect_fvg([c1, c2, c3_big], PIP, min_pips=1.5, max_pips=15.0)
    assert events_big[0].eligible is False

    # bearish gap: c1.low > c3.high
    b1 = _c(0, 1.1030, 1.1035, 1.1020, 1.1025)
    b2 = _c(1, 1.1025, 1.1028, 1.1010, 1.1012)
    b3 = _c(2, 1.1012, 1.1015, 1.1000, 1.1005)  # c3.high=1.1015 < c1.low=1.1020 -> gap 0.0005 = 5 pips
    events_bear = detect_fvg([b1, b2, b3], PIP, min_pips=1.5, max_pips=15.0)
    assert events_bear[0].direction == FVGDirection.BEARISH
    assert events_bear[0].eligible is True


def test_atr_deterministic_and_fails_closed_on_insufficient_history():
    candles = [_c(i, 1.10, 1.101, 1.099, 1.100) for i in range(10)]
    assert compute_atr(candles, period=14) is None  # fewer than period+1 bars
    candles_full = [_c(i, 1.10 + 0.0001 * i, 1.101 + 0.0001 * i, 1.099 + 0.0001 * i, 1.100 + 0.0001 * i) for i in range(20)]
    atr = compute_atr(candles_full, period=14)
    assert atr is not None
    # repeat call is identical (pure function, no hidden state)
    assert compute_atr(candles_full, period=14) == atr
