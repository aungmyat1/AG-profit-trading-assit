"""Tests for liquidity/: the sweep/reclaim state machine (status.py), equal-highs/lows
clustering (equal_levels.py), cross-source deduplication (dedup.py), and a live-guarded
end-to-end liquidity_result() smoke check. See test_liquidity_session_availability.py
for deterministic, clock-independent end-to-end coverage of liquidity_result() itself."""
from __future__ import annotations

import datetime as dt

import pytest

from liquidity.dedup import merge_duplicate_levels
from liquidity.equal_levels import detect_equal_highs, detect_equal_lows
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from liquidity.status import compute_status
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _candle(hour, minute, o, h, l, c, day=5):
    return Candle(time=dt.datetime(2026, 1, day, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=c, volume=1.0)


# --------------------------------------------------------------------------- sweep/reclaim state machine

def test_unswept_high_level():
    candles = [_candle(10, 0, 1.10, 1.1005, 1.0995, 1.10)]
    status, sweep, reclaim, _ = compute_status(LiquiditySide.BUY_SIDE, 1.20, candles)
    assert status == LiquidityStatus.UNSWEPT
    assert sweep is None and reclaim is None


def test_high_side_sweep_and_reclaim():
    level = 1.1050
    candles = [_candle(10, 0, 1.1040, 1.1070, 1.1035, 1.1045)]  # wick above level, closes back below
    status, sweep, reclaim, _ = compute_status(LiquiditySide.BUY_SIDE, level, candles)
    assert status == LiquidityStatus.RECLAIMED
    assert sweep == candles[0].time
    assert reclaim == candles[0].time


def test_high_side_sweep_without_reclaim_is_consumed():
    level = 1.1050
    candles = [_candle(10, 0, 1.1040, 1.1070, 1.1035, 1.1060)]  # wick above, closes ABOVE (no reclaim)
    status, sweep, reclaim, _ = compute_status(LiquiditySide.BUY_SIDE, level, candles)
    assert status == LiquidityStatus.CONSUMED
    assert sweep == candles[0].time
    assert reclaim is None


def test_low_side_sweep_and_reclaim():
    level = 1.0950
    candles = [_candle(10, 0, 1.0960, 1.0965, 1.0930, 1.0955)]  # wick below level, closes back above
    status, sweep, reclaim, _ = compute_status(LiquiditySide.SELL_SIDE, level, candles)
    assert status == LiquidityStatus.RECLAIMED


def test_low_side_sweep_without_reclaim_is_consumed():
    level = 1.0950
    candles = [_candle(10, 0, 1.0960, 1.0965, 1.0930, 1.0935)]  # wick below, closes BELOW (no reclaim)
    status, sweep, reclaim, _ = compute_status(LiquiditySide.SELL_SIDE, level, candles)
    assert status == LiquidityStatus.CONSUMED


def test_live_tick_pending_penetration_is_swept():
    status, sweep, reclaim, reasons = compute_status(LiquiditySide.BUY_SIDE, 1.1050, [], live_bid=1.1055, live_ask=1.1056)
    assert status == LiquidityStatus.SWEPT
    assert reasons == ["LIVE_PENETRATION_PENDING_CANDLE_CLOSE"]


def test_latest_event_wins_reclaim_then_reconsumed():
    level = 1.1050
    candles = [
        _candle(10, 0, 1.1040, 1.1070, 1.1035, 1.1045),   # sweep + reclaim
        _candle(10, 15, 1.1045, 1.1080, 1.1040, 1.1075),  # swept again, closes beyond -> consumed
    ]
    status, sweep, reclaim, _ = compute_status(LiquiditySide.BUY_SIDE, level, candles)
    assert status == LiquidityStatus.CONSUMED
    assert sweep == candles[0].time  # first penetration
    assert reclaim == candles[0].time  # last successful reclaim (candle 2 didn't reclaim)


# --------------------------------------------------------------------------- equal highs / lows

def test_equal_highs_cluster_within_tolerance():
    candles = [
        _candle(0, 0, 1.10, 1.1005, 1.0990, 1.10),   # padding so boundary trimming doesn't exclude the real points
        _candle(0, 15, 1.10, 1.1050, 1.0990, 1.10),
        _candle(0, 30, 1.10, 1.1010, 1.0990, 1.10),
        _candle(0, 45, 1.10, 1.1051, 1.0990, 1.10),  # within 0.0005 of the first high
        _candle(1, 0, 1.10, 1.1015, 1.0990, 1.10),
        _candle(1, 15, 1.10, 1.1005, 1.0990, 1.10),  # padding
    ]
    levels = detect_equal_highs("EURUSD", "M15", candles, tolerance_price=0.0005, extremum_window=1)
    assert len(levels) == 1
    assert levels[0].source == "EQUAL_HIGHS"
    assert levels[0].side == LiquiditySide.BUY_SIDE
    assert levels[0].price == pytest.approx(1.1051)  # max of the cluster


def test_equal_lows_cluster_within_tolerance():
    candles = [
        _candle(0, 0, 1.10, 1.1005, 1.0990, 1.10),   # padding so boundary trimming doesn't exclude the real points
        _candle(0, 15, 1.10, 1.1050, 1.0950, 1.10),
        _candle(0, 30, 1.10, 1.1010, 1.0990, 1.10),
        _candle(0, 45, 1.10, 1.1051, 1.0949, 1.10),  # within 0.0005 of the first low
        _candle(1, 0, 1.10, 1.1015, 1.0990, 1.10),
        _candle(1, 15, 1.10, 1.1005, 1.0990, 1.10),  # padding
    ]
    levels = detect_equal_lows("EURUSD", "M15", candles, tolerance_price=0.0005, extremum_window=1)
    assert len(levels) == 1
    assert levels[0].source == "EQUAL_LOWS"
    assert levels[0].side == LiquiditySide.SELL_SIDE
    assert levels[0].price == pytest.approx(1.0949)  # min of the cluster


def test_highs_outside_tolerance_do_not_cluster():
    candles = [
        _candle(0, 0, 1.10, 1.1005, 1.0990, 1.10),   # padding
        _candle(0, 15, 1.10, 1.1050, 1.0990, 1.10),
        _candle(0, 30, 1.10, 1.1010, 1.0990, 1.10),
        _candle(0, 45, 1.10, 1.1200, 1.0990, 1.10),  # far away, not within tolerance
        _candle(1, 0, 1.10, 1.1015, 1.0990, 1.10),
        _candle(1, 15, 1.10, 1.1005, 1.0990, 1.10),  # padding
    ]
    levels = detect_equal_highs("EURUSD", "M15", candles, tolerance_price=0.0005, extremum_window=1)
    assert levels == []


# --------------------------------------------------------------------------- deduplication (dedup.py)

def _level(side, source, price):
    return LiquidityLevel(symbol="EURUSD", timeframe="M15", side=side, source=source, price=price,
                           origin_time=None, status=LiquidityStatus.UNSWEPT)


def test_merge_combines_levels_within_tolerance_and_keeps_provenance():
    levels = [_level(LiquiditySide.BUY_SIDE, "SWING_HIGH", 1.1050), _level(LiquiditySide.BUY_SIDE, "ASIAN_HIGH", 1.1051)]
    merged = merge_duplicate_levels(levels, tolerance_price=0.0005)
    assert len(merged) == 1
    assert merged[0].price == 1.1051  # furthest/most-conservative extreme for BUY_SIDE
    assert set(merged[0].sources) == {"SWING_HIGH", "ASIAN_HIGH"}


def test_merge_picks_min_price_for_sell_side():
    levels = [_level(LiquiditySide.SELL_SIDE, "SWING_LOW", 1.0950), _level(LiquiditySide.SELL_SIDE, "ASIAN_LOW", 1.0949)]
    merged = merge_duplicate_levels(levels, tolerance_price=0.0005)
    assert len(merged) == 1
    assert merged[0].price == 1.0949  # furthest/most-conservative extreme for SELL_SIDE


def test_merge_leaves_distant_levels_separate():
    levels = [_level(LiquiditySide.BUY_SIDE, "SWING_HIGH", 1.1050), _level(LiquiditySide.BUY_SIDE, "PDH", 1.2000)]
    merged = merge_duplicate_levels(levels, tolerance_price=0.0005)
    assert len(merged) == 2
    assert all(m.sources == (m.source,) for m in merged)


def test_merge_never_mixes_sides():
    levels = [_level(LiquiditySide.BUY_SIDE, "SWING_HIGH", 1.1050), _level(LiquiditySide.SELL_SIDE, "SWING_LOW", 1.1050)]
    merged = merge_duplicate_levels(levels, tolerance_price=0.0005)
    assert len(merged) == 2


def test_merge_with_zero_tolerance_is_a_noop_but_still_populates_sources():
    levels = [_level(LiquiditySide.BUY_SIDE, "SWING_HIGH", 1.1050), _level(LiquiditySide.BUY_SIDE, "ASIAN_HIGH", 1.1051)]
    merged = merge_duplicate_levels(levels, tolerance_price=0.0)
    assert len(merged) == 2
    assert merged[0].sources == (merged[0].source,)


# --------------------------------------------------------------------------- live verification

def _mt5_available():
    try:
        import MetaTrader5 as mt5
        return bool(mt5.initialize())
    except Exception:
        return False


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
@pytest.mark.parametrize("timeframe", ["H1", "M15"])
def test_liquidity_result_live_eurusd_smoke(timeframe):
    """Live MT5 smoke test only: schema/sanity, no fixed source requirement.

    PDH/PDL and structural swings don't depend on session completion, but ASIAN/LONDON/
    NEW_YORK_HIGH/LOW legitimately do not appear until that session's calendar day has
    fully closed (supply_demand.session_zone() -> assistant.market_data.session_snapshot()
    -> session_clock.session_complete()). Asserting a specific session source here made
    this test pass or fail purely based on what time of day it happened to run --
    see test_liquidity_session_availability.py for the deterministic, timestamp-fixed
    coverage of that behavior instead.
    """
    from liquidity import liquidity_result
    from mt5.connection import connect

    connect()
    result = liquidity_result("EURUSD", timeframe)

    assert result.status in ("LIQUIDITY_OK", "NO_LIQUIDITY_LEVELS")
    valid_sources = {"SWING_HIGH", "SWING_LOW", "ASIAN_HIGH", "ASIAN_LOW", "LONDON_HIGH", "LONDON_LOW",
                      "NEW_YORK_HIGH", "NEW_YORK_LOW", "PDH", "PDL", "PWH", "PWL", "EQUAL_HIGHS", "EQUAL_LOWS"}
    for level in result.levels:
        assert level.symbol == "EURUSD"
        assert level.timeframe == timeframe
        assert level.source in valid_sources
        assert level.sources and set(level.sources).issubset(valid_sources)
        assert isinstance(level.price, float) and level.price > 0
        assert level.status in (LiquidityStatus.UNSWEPT, LiquidityStatus.SWEPT,
                                 LiquidityStatus.RECLAIMED, LiquidityStatus.CONSUMED, LiquidityStatus.UNKNOWN)
        assert level.side in (LiquiditySide.BUY_SIDE, LiquiditySide.SELL_SIDE)
    if result.nearest_buy_side:
        assert result.nearest_buy_side.side == LiquiditySide.BUY_SIDE
    if result.nearest_sell_side:
        assert result.nearest_sell_side.side == LiquiditySide.SELL_SIDE
