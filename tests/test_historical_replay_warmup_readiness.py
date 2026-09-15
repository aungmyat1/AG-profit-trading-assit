"""AG SSC HYP_002 -- regression tests for historical_replay.warmup_readiness.

Proves the actual-closed-bar-count readiness check behaves correctly where the earlier
elapsed-calendar-hours approximation (a 1000-hour span, used in
run_first_canonical_session_sweep_continuation_replay.py's `_effective_date_range`)
silently overcounted available H1 bars across weekend market closures.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from strategy_engine.session import Candle

from historical_replay.warmup_readiness import closed_h1_bar_count, sufficient_h1_warmup


def _h1_candle(t: datetime) -> Candle:
    return Candle(time=t, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)


def _weekday_h1_series(start: datetime, hours: int):
    """Contiguous hourly candles starting at `start`, skipping Saturday/Sunday entirely
    (no bar exists during weekend closure) -- mirrors real broker H1 export behavior."""
    candles = []
    t = start
    produced = 0
    while produced < hours:
        if t.weekday() < 5:  # Mon-Fri only
            candles.append(_h1_candle(t))
            produced += 1
        t = t + timedelta(hours=1)
    return candles


def test_1000_calendar_hours_with_fewer_than_1000_real_bars_is_not_sufficient():
    # A 1000-*hour* calendar span starting on a Monday spans multiple weekends, so it
    # contains far fewer than 1000 actual weekday H1 bars.
    start = datetime(2026, 5, 28, 0, 0, tzinfo=timezone.utc)  # a Thursday
    as_of = start + timedelta(hours=1000)
    all_hourly_candles = [
        _h1_candle(start + timedelta(hours=i))
        for i in range(1000)
        if (start + timedelta(hours=i)).weekday() < 5
    ]
    assert len(all_hourly_candles) < 1000
    assert not sufficient_h1_warmup(all_hourly_candles, as_of, required_bars=1000)


def test_at_least_1000_valid_closed_h1_bars_is_sufficient():
    start = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    candles = _weekday_h1_series(start, hours=1128)  # matches the actual GEN_002 warmup pull margin
    as_of = candles[-1].time + timedelta(hours=1)  # one hour after the last bar's open -> it is closed
    assert closed_h1_bar_count(candles, as_of) == 1128
    assert sufficient_h1_warmup(candles, as_of, required_bars=1000)


def test_weekend_gaps_do_not_count_as_bars():
    # Two weekday bars either side of a weekend: only the 2 real bars count, not the
    # ~48 calendar hours spanning Saturday/Sunday.
    friday_close = datetime(2026, 7, 31, 17, 0, tzinfo=timezone.utc)  # Friday
    monday_open = datetime(2026, 8, 3, 0, 0, tzinfo=timezone.utc)  # Monday
    candles = [_h1_candle(friday_close), _h1_candle(monday_open)]
    as_of = monday_open + timedelta(hours=1)
    assert closed_h1_bar_count(candles, as_of) == 2
    assert not sufficient_h1_warmup(candles, as_of, required_bars=3)


def test_warmup_bars_cannot_emit_occurrences():
    # This module only counts/validates readiness -- it exposes no function that
    # returns occurrences, trades, or any setup/decision object from warmup-only
    # candles; both public functions return bool/int only.
    import inspect

    import historical_replay.warmup_readiness as mod

    functions = [obj for name, obj in vars(mod).items()
                 if inspect.isfunction(obj) and obj.__module__ == mod.__name__]
    assert functions, "expected at least one function defined in warmup_readiness"
    for fn in functions:
        assert "occurrence" not in fn.__name__.lower()
        assert "trade" not in fn.__name__.lower()
        assert "setup" not in fn.__name__.lower()
        return_type = inspect.signature(fn).return_annotation
        assert return_type in ("bool", "int"), f"{fn.__name__} returns {return_type!r}, expected bool/int only"


def test_no_future_bar_can_initialize_state_for_a_decision():
    # A bar at or after `as_of` must never be counted as closed for that `as_of`.
    as_of = datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)
    bar_at_as_of = _h1_candle(as_of)  # open time == as_of -> NOT closed (needs open <= as_of - 1h)
    bar_after_as_of = _h1_candle(as_of + timedelta(hours=1))
    bar_well_before = _h1_candle(as_of - timedelta(hours=2))
    candles = [bar_well_before, bar_at_as_of, bar_after_as_of]
    assert closed_h1_bar_count(candles, as_of) == 1  # only bar_well_before
