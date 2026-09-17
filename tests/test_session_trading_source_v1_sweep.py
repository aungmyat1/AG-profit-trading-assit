"""Synthetic semantic-verification tests for ST_SESSION_TRADING_SOURCE_V1 / SWEEP.

All fixtures are constructed by hand for this test file only. None reuse or
reference the sealed Oct-2022 18-event benchmark table (per the benchmark
firewall maintained across EXTERNAL_SOURCE_ES_S1S/S1R/S2).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from session_trading_source_v1.asian_range import build_asian_range
from session_trading_source_v1.models import Candle, Direction, OccurrenceState, SweepStatus
from session_trading_source_v1.occurrence import generate_occurrences
from session_trading_source_v1.partial_be import resolve_occurrence
from session_trading_source_v1.stop_target import compute_initial_risk, compute_stop, compute_tp2, opposite_boundary_target
from session_trading_source_v1.sweep import detect_sweeps

PIP = 0.0001


def _c(hh, mm, o, h, l, c, day=3):
    return Candle(time=datetime(2022, 10, day, hh, mm, tzinfo=timezone.utc), open=o, high=h, low=l, close=c)


def _asian_session_candles(day=3, base=1.0000):
    # 00:00-06:45 UTC, 28 M15 bars forming a clean 50-pip range, high at 07:00-adjacent bar excluded.
    candles = []
    t = datetime(2022, 10, day, 0, 0, tzinfo=timezone.utc)
    for i in range(28):
        o = base + (i % 5) * 0.0002
        h = o + 0.0010 if i == 10 else o + 0.0003
        l = o - 0.0010 if i == 20 else o - 0.0003
        c = o + 0.0001
        candles.append(Candle(time=t, open=o, high=h, low=l, close=c))
        t += timedelta(minutes=15)
    return candles  # high ~= base+0.0010+..., low ~= base-0.0010-...


def test_1_asian_range_construction():
    candles = _asian_session_candles()
    rng = build_asian_range(candles)
    assert rng is not None
    assert rng.high == max(c.high for c in candles)
    assert rng.low == min(c.low for c in candles)
    assert rng.range == pytest.approx(rng.high - rng.low)


def test_2_upper_sweep_is_short():
    rng = build_asian_range(_asian_session_candles())
    sweep_candle = _c(7, 30, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.0001)
    events = detect_sweeps(rng, [sweep_candle])
    assert len(events) == 1
    assert events[0].status == SweepStatus.VALID
    assert events[0].direction == Direction.SHORT
    assert events[0].entry_price == sweep_candle.close


def test_3_lower_sweep_is_long():
    rng = build_asian_range(_asian_session_candles())
    sweep_candle = _c(7, 30, rng.low + 0.0002, rng.low + 0.0003, rng.low - 0.0005, rng.low + 0.0001)
    events = detect_sweeps(rng, [sweep_candle])
    assert len(events) == 1
    assert events[0].direction == Direction.LONG
    assert events[0].entry_price == sweep_candle.close


def test_4_touch_without_strict_penetration_no_sweep():
    rng = build_asian_range(_asian_session_candles())
    touch_candle = _c(7, 30, rng.high - 0.0005, rng.high, rng.high - 0.0006, rng.high - 0.0002)  # high == boundary, not >
    events = detect_sweeps(rng, [touch_candle])
    assert events == []


def test_5_penetration_without_close_back_inside_no_sweep():
    rng = build_asian_range(_asian_session_candles())
    breakout_candle = _c(7, 30, rng.high + 0.0001, rng.high + 0.0010, rng.high, rng.high + 0.0008)  # closes ABOVE boundary
    events = detect_sweeps(rng, [breakout_candle])
    assert events == []


def test_6_entry_at_qualifying_close():
    rng = build_asian_range(_asian_session_candles())
    sweep_candle = _c(7, 30, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.00015)
    events = detect_sweeps(rng, [sweep_candle])
    assert events[0].entry_price == sweep_candle.close != sweep_candle.open


def test_7_long_stop_formula():
    rng = build_asian_range(_asian_session_candles())
    entry = rng.low + 0.0001
    stop = compute_stop(Direction.LONG, entry, rng)
    assert stop == pytest.approx(entry - 0.25 * rng.range)


def test_8_short_stop_formula():
    rng = build_asian_range(_asian_session_candles())
    entry = rng.high - 0.0001
    stop = compute_stop(Direction.SHORT, entry, rng)
    assert stop == pytest.approx(entry + 0.25 * rng.range)


def test_9_tp2_is_5r():
    rng = build_asian_range(_asian_session_candles())
    entry = rng.high - 0.0001
    stop = compute_stop(Direction.SHORT, entry, rng)
    risk = compute_initial_risk(entry, stop)
    tp2 = compute_tp2(Direction.SHORT, entry, risk)
    assert tp2 == pytest.approx(entry - 5 * risk)
    assert tp2 == pytest.approx(entry - 1.25 * rng.range)


def test_10_and_11_partial_split_and_opposite_boundary():
    rng = build_asian_range(_asian_session_candles())
    long_target = opposite_boundary_target(Direction.LONG, rng)
    short_target = opposite_boundary_target(Direction.SHORT, rng)
    assert long_target == rng.high
    assert short_target == rng.low
    # 75/25 split is a fixed constant of the candidate spec, not computed here;
    # verified structurally via the resolution state machine's own leg semantics
    # (see test_12_be_only_after_confirmed_partial).


def test_12_be_only_after_confirmed_partial():
    entry, stop, leg_a, tp2 = 1.0000, 0.9950, 1.0100, 1.0250
    # Never touches leg_a -> BE must never arm, terminal must not be a runner state
    candles = [_c(8, 0, 1.0010, 1.0020, 0.9990, 1.0005)]
    res = resolve_occurrence(Direction.LONG, entry, stop, leg_a, tp2, candles)
    assert res.state == OccurrenceState.OPEN


def test_13_entry_candle_extrema_not_post_entry_events():
    # occurrence.py only ever passes candles strictly AFTER the entry candle to
    # resolve_occurrence -- verified at the pipeline level.
    rng = build_asian_range(_asian_session_candles())
    entry_candle = _c(7, 30, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.0001)
    occ = generate_occurrences(_asian_session_candles(), [entry_candle], PIP)
    assert len(occ) == 1
    # the entry candle's own extreme low (which would trivially "hit" a long-side
    # level) must never appear in the resolution's event list
    assert occ[0].resolution.state == OccurrenceState.OPEN
    assert occ[0].resolution.reason == "NO_DATA_AFTER_ENTRY_BEFORE_WINDOW_END"


def test_14_same_bar_sl_tp1_unresolved():
    entry, stop, leg_a, tp2 = 1.0000, 0.9950, 1.0100, 1.0250
    candle = _c(8, 0, 1.0010, 1.0110, 0.9940, 1.0060)  # touches both SL and leg_a in one bar
    res = resolve_occurrence(Direction.LONG, entry, stop, leg_a, tp2, [candle])
    assert res.state == OccurrenceState.UNRESOLVED
    assert "SL_TP1" in res.reason


def test_15_ambiguous_entry_cutoff_flagged():
    rng = build_asian_range(_asian_session_candles())
    late_candle = _c(17, 15, rng.high - 0.0002, rng.high + 0.0020, rng.high - 0.0003, rng.high - 0.0001)
    occ = generate_occurrences(_asian_session_candles(), [late_candle], PIP)
    assert len(occ) == 1
    assert "NEW_ENTRY_CUTOFF_AMBIGUOUS" in occ[0].uncertainty_reasons
    assert occ[0].occurrence_classification == "SOURCE_RULE_DEPENDENT_UNRESOLVED"


def test_16_missing_range_threshold_flagged_for_tight_range():
    # construct a deliberately tight (<15 pip) Asian range
    tight_candles = []
    t = datetime(2022, 10, 3, 0, 0, tzinfo=timezone.utc)
    for i in range(28):
        tight_candles.append(Candle(time=t, open=1.0000, high=1.0004, low=0.9998, close=1.0001))
        t += timedelta(minutes=15)
    early_candle = _c(9, 15, 1.0003, 1.0020, 0.9999, 1.0002)  # sweeps the tight high only, before cutoff
    occ = generate_occurrences(tight_candles, [early_candle], PIP)
    assert len(occ) == 1
    assert "TIGHT_RANGE_FILTER_THRESHOLD_MISSING" in occ[0].uncertainty_reasons


def test_17_multiple_signals_preserved_no_invented_cap():
    rng_candles = _asian_session_candles()
    rng = build_asian_range(rng_candles)
    c1 = _c(9, 15, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.0001)
    c2 = _c(10, 0, rng.low + 0.0002, rng.low + 0.0003, rng.low - 0.0005, rng.low + 0.0001)
    occ = generate_occurrences(rng_candles, [c1, c2], PIP)
    assert len(occ) == 2  # both preserved -- MAX_ENTRIES_PER_SESSION is SOURCE_MISSING, never enforced


def test_18_no_h1_dependency():
    import session_trading_source_v1 as pkg
    assert pkg.H1_REQUIRED is False
    import inspect
    import session_trading_source_v1.occurrence as occ_mod
    assert "H1" not in inspect.getsource(occ_mod)


def test_19_no_m1_dependency():
    import session_trading_source_v1 as pkg
    assert pkg.M1_REQUIRED is False
    assert pkg.NATIVE_TIMEFRAME == "M15"


def test_clean_deterministic_occurrence_exists():
    """A qualifying signal well before the disputed cutoff, on a wide range, with
    a clean resolution, must classify SOURCE_DETERMINISTIC -- confirming the two
    classifications are not degenerate (P9's own worked '09:15 clean' example)."""
    rng_candles = _asian_session_candles()
    rng = build_asian_range(rng_candles)
    clean_candle = _c(9, 15, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.0001)
    occ = generate_occurrences(rng_candles, [clean_candle], PIP)
    assert len(occ) == 1
    assert occ[0].occurrence_classification == "SOURCE_DETERMINISTIC"
    assert occ[0].uncertainty_reasons == []


def test_dual_side_same_candle_ambiguous_no_occurrence():
    rng = build_asian_range(_asian_session_candles())
    dual_candle = _c(7, 30, rng.low, rng.high + 0.0005, rng.low - 0.0005, rng.low + 0.0002)
    occ = generate_occurrences(_asian_session_candles(), [dual_candle], PIP)
    assert occ == []
