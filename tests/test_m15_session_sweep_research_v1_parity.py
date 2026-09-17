"""Narrow semantic-parity tests for ST_M15_SESSION_SWEEP_RESEARCH_V1 (ES-R0 P12).

Synthetic fixtures only -- no Oct-2022 data, no benchmark table, no economic
backtest. Proves baseline semantics only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from m15_session_sweep_research_v1.asian_range import build_asian_range
from m15_session_sweep_research_v1.models import Candle, Direction, OccurrenceState, SweepStatus
from m15_session_sweep_research_v1.occurrence import generate_occurrences
from m15_session_sweep_research_v1.partial_be import resolve_occurrence
from m15_session_sweep_research_v1.stop_target import compute_initial_risk, compute_stop, compute_tp2, opposite_boundary_target
from m15_session_sweep_research_v1.sweep import detect_sweeps


def _c(hh, mm, o, h, l, c, day=3):
    return Candle(time=datetime(2022, 10, day, hh, mm, tzinfo=timezone.utc), open=o, high=h, low=l, close=c)


def _asian_session_candles(day=3, base=1.0000):
    candles = []
    t = datetime(2022, 10, day, 0, 0, tzinfo=timezone.utc)
    for i in range(28):
        o = base + (i % 5) * 0.0002
        h = o + 0.0010 if i == 10 else o + 0.0003
        l = o - 0.0010 if i == 20 else o - 0.0003
        c = o + 0.0001
        candles.append(Candle(time=t, open=o, high=h, low=l, close=c))
        t += timedelta(minutes=15)
    return candles


def test_m15_only_no_h1_no_m1():
    import m15_session_sweep_research_v1 as pkg
    assert pkg.NATIVE_TIMEFRAME == "M15"
    assert pkg.H1_REQUIRED is False
    assert pkg.M1_REQUIRED is False
    import inspect
    import m15_session_sweep_research_v1.occurrence as occ_mod
    assert "H1" not in inspect.getsource(occ_mod)


def test_identity_and_claims():
    import m15_session_sweep_research_v1 as pkg
    assert pkg.STRATEGY_ID == "ST_M15_SESSION_SWEEP_RESEARCH_V1"
    assert pkg.VERSION == "0.1.0"
    assert pkg.LINEAGE_TYPE == "SOURCE_INSPIRED_RESEARCH"
    assert pkg.SOURCE_REPLICATION_CLAIM is False
    assert pkg.SOURCE_SEMANTIC_PARITY_CLAIM is False
    assert pkg.ECONOMIC_EDGE_CLAIM is False
    assert pkg.DEMO_AUTHORIZED is False
    assert pkg.LIVE_AUTHORIZED is False
    assert len(pkg.PROVENANCE_PARENTS) == 2


def test_asian_reference_range_00_to_07_utc():
    candles = _asian_session_candles()
    rng = build_asian_range(candles)
    assert rng is not None
    assert rng.high == max(c.high for c in candles)
    assert rng.low == min(c.low for c in candles)


def test_strict_sweep_plus_close_inside_short():
    rng = build_asian_range(_asian_session_candles())
    sweep_candle = _c(7, 30, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.0001)
    events = detect_sweeps(rng, [sweep_candle])
    assert len(events) == 1
    assert events[0].status == SweepStatus.VALID
    assert events[0].direction == Direction.SHORT


def test_strict_sweep_plus_close_inside_long():
    rng = build_asian_range(_asian_session_candles())
    sweep_candle = _c(7, 30, rng.low + 0.0002, rng.low + 0.0003, rng.low - 0.0005, rng.low + 0.0001)
    events = detect_sweeps(rng, [sweep_candle])
    assert len(events) == 1
    assert events[0].direction == Direction.LONG


def test_entry_at_m15_close():
    rng = build_asian_range(_asian_session_candles())
    sweep_candle = _c(7, 30, rng.high - 0.0002, rng.high + 0.0005, rng.high - 0.0003, rng.high - 0.00015)
    events = detect_sweeps(rng, [sweep_candle])
    assert events[0].entry_price == sweep_candle.close


def test_dual_side_same_candle_ambiguous_no_occurrence():
    rng = build_asian_range(_asian_session_candles())
    dual_candle = _c(7, 30, rng.low, rng.high + 0.0005, rng.low - 0.0005, rng.low + 0.0002)
    occ = generate_occurrences(_asian_session_candles(), [dual_candle])
    assert occ == []


def test_stop_0_25_A_long():
    rng = build_asian_range(_asian_session_candles())
    entry = rng.low + 0.0001
    stop = compute_stop(Direction.LONG, entry, rng)
    assert stop == pytest.approx(entry - 0.25 * rng.range)


def test_stop_0_25_A_short():
    rng = build_asian_range(_asian_session_candles())
    entry = rng.high - 0.0001
    stop = compute_stop(Direction.SHORT, entry, rng)
    assert stop == pytest.approx(entry + 0.25 * rng.range)


def test_tp2_is_5r():
    rng = build_asian_range(_asian_session_candles())
    entry = rng.high - 0.0001
    stop = compute_stop(Direction.SHORT, entry, rng)
    risk = compute_initial_risk(entry, stop)
    tp2 = compute_tp2(Direction.SHORT, entry, risk)
    assert tp2 == pytest.approx(entry - 5 * risk)
    assert tp2 == pytest.approx(entry - 1.25 * rng.range)


def test_opposite_boundary_partial_target():
    rng = build_asian_range(_asian_session_candles())
    assert opposite_boundary_target(Direction.LONG, rng) == rng.high
    assert opposite_boundary_target(Direction.SHORT, rng) == rng.low


def test_be_only_after_confirmed_partial():
    entry, stop, leg_a, tp2 = 1.0000, 0.9950, 1.0100, 1.0250
    candles = [Candle(time=datetime(2022, 10, 3, 8, 0, tzinfo=timezone.utc), open=1.0010, high=1.0020, low=0.9990, close=1.0005)]
    res = resolve_occurrence(Direction.LONG, entry, stop, leg_a, tp2, candles)
    assert res.state == OccurrenceState.OPEN  # never touched leg_a -> BE never armed


def test_dual_collision_intrabar_order_unresolved_not_stop_first():
    """Baseline research policy: INTRABAR_ORDER_UNRESOLVED, never STOP_FIRST
    (D:\\'s own documented choice, explicitly NOT inherited here -- ES-R0 P5)."""
    entry, stop, leg_a, tp2 = 1.0000, 0.9950, 1.0100, 1.0250
    candle = Candle(time=datetime(2022, 10, 3, 8, 0, tzinfo=timezone.utc), open=1.0010, high=1.0110, low=0.9940, close=1.0060)
    res = resolve_occurrence(Direction.LONG, entry, stop, leg_a, tp2, [candle])
    assert res.state == OccurrenceState.UNRESOLVED
    assert "STOP_FIRST" not in res.reason


def test_parent_v0_1_0_untouched():
    import subprocess
    out = subprocess.run(
        ["git", "diff", "--stat", "src/session_trading_source_v1/"],
        cwd=r"D:\ddev\AG profit trading", capture_output=True, text=True,
    )
    assert out.stdout.strip() == ""
