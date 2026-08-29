"""Tests for entry_confirmation.invalidation -- the shared, per-maneuver-honest
invalidation plumbing. M1/M3 both reuse `entry_array_invalidation()` (the exact
comparison `engine_v2_1.py` already applies internally for M3, factored out so M1 can
reuse it verbatim); M2 uses its own `m2_invalidation()` (new-controlling-zone
ZoneStatus.INVALIDATED, closed-candle-based, no sweep concept in M2 at all).
"""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation.invalidation import (
    SOURCE_ENTRY_ORDER_BLOCK_BOUNDARY,
    SOURCE_INDUCEMENT_LEVEL,
    SOURCE_LIQUIDITY_SWEEP_LEVEL,
    SOURCE_NEW_CONTROLLING_ZONE_BOUNDARY,
    TRIGGER_CLOSED_CANDLE_CLOSE,
    TRIGGER_LIVE_PRICE,
    entry_array_invalidation,
    m2_invalidation,
)
from entry_confirmation.models import CandidateDirection
from entry_confirmation.models_v2_1 import EntryArrayContext
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc


def _entry_array(candidates):
    return EntryArrayContext(entry_array_type="FVG", entry_reference=1.0995,
                              structural_invalidation_candidates=tuple(candidates))


# --------------------------------------------------------------------------- entry_array_invalidation (M1/M3 shared)

def test_no_candidates_is_no_invalidation():
    result = entry_array_invalidation(_entry_array([]), CandidateDirection.LONG, 1.0900, None, SOURCE_INDUCEMENT_LEVEL)
    assert result is None


def test_long_not_yet_breached():
    result = entry_array_invalidation(_entry_array([1.0950]), CandidateDirection.LONG, 1.0980,
                                       1.0950, SOURCE_INDUCEMENT_LEVEL)
    assert result is not None
    assert result.price == pytest.approx(1.0950)
    assert result.triggered is False
    assert result.trigger == TRIGGER_LIVE_PRICE


def test_long_breached_below_min_candidate():
    result = entry_array_invalidation(_entry_array([1.0950]), CandidateDirection.LONG, 1.0940,
                                       1.0950, SOURCE_INDUCEMENT_LEVEL)
    assert result.triggered is True
    assert result.source_type == SOURCE_INDUCEMENT_LEVEL


def test_short_breached_above_max_candidate():
    result = entry_array_invalidation(_entry_array([1.1050]), CandidateDirection.SHORT, 1.1060,
                                       1.1050, SOURCE_LIQUIDITY_SWEEP_LEVEL)
    assert result.triggered is True
    assert result.price == pytest.approx(1.1050)
    assert result.source_type == SOURCE_LIQUIDITY_SWEEP_LEVEL


def test_short_not_yet_breached():
    result = entry_array_invalidation(_entry_array([1.1050]), CandidateDirection.SHORT, 1.1020,
                                       1.1050, SOURCE_LIQUIDITY_SWEEP_LEVEL)
    assert result.triggered is False


def test_ob_boundary_wins_when_more_extreme_than_primary_long():
    """LONG: min(candidates) is the trigger. If the OB boundary is LOWER than the
    inducement/sweep level, the OB boundary is the actual invalidation price/source --
    not silently mislabeled as the primary source."""
    result = entry_array_invalidation(_entry_array([1.0950, 1.0930]), CandidateDirection.LONG, 1.0920,
                                       1.0950, SOURCE_INDUCEMENT_LEVEL)
    assert result.price == pytest.approx(1.0930)
    assert result.source_type == SOURCE_ENTRY_ORDER_BLOCK_BOUNDARY
    assert result.triggered is True


def test_ob_boundary_wins_when_more_extreme_than_primary_short():
    result = entry_array_invalidation(_entry_array([1.1050, 1.1070]), CandidateDirection.SHORT, 1.1080,
                                       1.1050, SOURCE_LIQUIDITY_SWEEP_LEVEL)
    assert result.price == pytest.approx(1.1070)
    assert result.source_type == SOURCE_ENTRY_ORDER_BLOCK_BOUNDARY
    assert result.triggered is True


def test_no_current_price_is_not_triggered():
    result = entry_array_invalidation(_entry_array([1.0950]), CandidateDirection.LONG, None,
                                       1.0950, SOURCE_INDUCEMENT_LEVEL)
    assert result is not None
    assert result.triggered is False


# --------------------------------------------------------------------------- m2_invalidation

def _zone(role, status, low=1.0970, high=1.0990):
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=role,
                       direction=ZoneDirection.BULLISH if role == ZoneRole.DEMAND else ZoneDirection.BEARISH,
                       status=status, source="test", low=low, high=high,
                       origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC))


def test_m2_no_new_zone_is_no_invalidation():
    assert m2_invalidation(None) is None


def test_m2_demand_zone_not_invalidated_yet():
    result = m2_invalidation(_zone(ZoneRole.DEMAND, ZoneStatus.FRESH))
    assert result is not None
    assert result.price == pytest.approx(1.0970)  # DEMAND boundary = low
    assert result.triggered is False
    assert result.trigger == TRIGGER_CLOSED_CANDLE_CLOSE


def test_m2_demand_zone_invalidated_bullish_thesis_fails():
    result = m2_invalidation(_zone(ZoneRole.DEMAND, ZoneStatus.INVALIDATED))
    assert result.triggered is True
    assert result.source_type == SOURCE_NEW_CONTROLLING_ZONE_BOUNDARY


def test_m2_supply_zone_invalidated_bearish_thesis_fails():
    result = m2_invalidation(_zone(ZoneRole.SUPPLY, ZoneStatus.INVALIDATED, low=1.1010, high=1.1030))
    assert result.triggered is True
    assert result.price == pytest.approx(1.1030)  # SUPPLY boundary = high


def test_m2_reference_role_zone_is_undefined():
    result = m2_invalidation(_zone(ZoneRole.REFERENCE, ZoneStatus.INVALIDATED))
    assert result is None


def test_m2_zone_missing_bounds_is_undefined():
    zone = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.INVALIDATED, source="test")
    assert m2_invalidation(zone) is None


# --------------------------------------------------------------------------- end-to-end propagation (M1)
# Reuses the exact READY-reaching bearish fixture from test_m1_character_change_inducement.py
# (inducement=1.1060 BUY_SIDE, no OB -> structural_invalidation_candidates == [1.1060]).

from entry_confirmation.entry_models_v1 import EConditionResult as _EConditionResult
from entry_confirmation.m1_character_change_inducement import evaluate_m1_character_change_with_inducement
from liquidity.hierarchy import InducementCandidate
from liquidity.models import LiquidityLevel as _LiquidityLevel, LiquiditySide as _LiquiditySide, LiquidityStatus as _LiquidityStatus
from market_structure import MarketStructureConfig as _MarketStructureConfig

_M1_CFG = _MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)
_M1_TAKEN_TIME = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_M1_M5_START = _M1_TAKEN_TIME + dt.timedelta(minutes=5)
_M1_CHOCH_TIME = _M1_M5_START + dt.timedelta(minutes=5 * 8)


def _m1_pt(t, p, eps=0.0002):
    from strategy_engine.session import Candle
    return Candle(time=t, open=p, high=p + eps, low=p - eps, close=p, volume=1.0)


def _m1_bearish_m5_candles():
    from strategy_engine.session import Candle
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [_m1_pt(_M1_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_M1_CHOCH_TIME, 1.1032, 1.1034, 1.0928, 1.0930))
    return candles


def _m1_displacement_history():
    from strategy_engine.session import Candle
    base = _M1_TAKEN_TIME - dt.timedelta(hours=2)
    return [Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


def _m1_same_leg_fvg(origin_time):
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
                       low=1.0980, high=1.0995, origin_time=origin_time)


def _m1_ready_result(current_price):
    candidate = InducementCandidate(
        candidate_id="c1",
        candidate=_LiquidityLevel(symbol="EURUSD", timeframe="M5", side=_LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                                   price=1.1060, origin_time=_M1_TAKEN_TIME - dt.timedelta(hours=1),
                                   status=_LiquidityStatus.UNSWEPT),
        target_id="t1",
        target=_LiquidityLevel(symbol="EURUSD", timeframe="M5", side=_LiquiditySide.BUY_SIDE, source="EXTERNAL_SWING_HIGH",
                                price=1.1200, origin_time=_M1_TAKEN_TIME - dt.timedelta(hours=2),
                                status=_LiquidityStatus.UNSWEPT),
        side=_LiquiditySide.BUY_SIDE,
    )
    taken = _LiquidityLevel(symbol="EURUSD", timeframe="M5", side=_LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                             price=1.1060, origin_time=_M1_TAKEN_TIME - dt.timedelta(hours=1),
                             status=_LiquidityStatus.RECLAIMED, sweep_time=_M1_TAKEN_TIME)
    e = _EConditionResult(entry_condition="E1", symbol="EURUSD", direction="SHORT", eligible_for_confirmation=True)
    fvg = _m1_same_leg_fvg(_M1_TAKEN_TIME + dt.timedelta(minutes=1))
    return evaluate_m1_character_change_with_inducement(
        "EURUSD", e, candidate, taken, _m1_bearish_m5_candles(), _m1_displacement_history(),
        (fvg,), (), current_price, _M1_CHOCH_TIME + dt.timedelta(minutes=5), _M1_CFG,
    )


def test_m1_invalidation_exposed_but_not_triggered_below_inducement_level():
    result = _m1_ready_result(current_price=1.0990)
    assert result.state in ("WAITING_M5_ENTRY", "READY")
    assert result.invalidation_price == pytest.approx(1.1060)
    assert result.invalidation_source_type == SOURCE_INDUCEMENT_LEVEL
    assert result.invalidation_trigger == TRIGGER_LIVE_PRICE


def test_m1_invalidated_when_live_price_crosses_inducement_level_short():
    result = _m1_ready_result(current_price=1.1070)
    assert result.state == "INVALIDATED"
    assert result.invalidation_price == pytest.approx(1.1060)


# --------------------------------------------------------------------------- end-to-end propagation (M3)

from entry_confirmation.e3_liquidity_sweep import e3_to_econdition, evaluate_e3_htf_liquidity_sweep
from entry_confirmation.m3_sweep_drop_pump import evaluate_m3_sweep_drop_pump

_M3_M5_START = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_M3_SWEEP_TIME = _M3_M5_START + dt.timedelta(minutes=5 * 7)
_M3_RECLAIM_TIME = _M3_SWEEP_TIME + dt.timedelta(minutes=1)
_M3_CHOCH_TIME = _M3_M5_START + dt.timedelta(minutes=5 * 8)


def _m3_bearish_candles():
    from strategy_engine.session import Candle
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [_m1_pt(_M3_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_M3_CHOCH_TIME, 1.1032, 1.1034, 1.0928, 1.0930))
    return candles


def _m3_ready_result(current_price):
    level = _LiquidityLevel(symbol="EURUSD", timeframe="M15", side=_LiquiditySide.BUY_SIDE, source="ASIAN_HIGH",
                             price=1.1060, origin_time=_M3_M5_START, status=_LiquidityStatus.RECLAIMED,
                             sweep_time=_M3_SWEEP_TIME, reclaim_time=_M3_RECLAIM_TIME)
    e = e3_to_econdition(evaluate_e3_htf_liquidity_sweep("EURUSD", level))
    fvg = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                      direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
                      low=1.0980, high=1.0995, origin_time=_M3_SWEEP_TIME + dt.timedelta(minutes=3))
    return evaluate_m3_sweep_drop_pump(
        "EURUSD", e, level, _m3_bearish_candles(), _m1_displacement_history(), (fvg,), (),
        current_price, _M3_CHOCH_TIME + dt.timedelta(minutes=5), _M1_CFG,
    )


def test_m3_invalidation_exposed_but_not_triggered_below_sweep_level():
    result = _m3_ready_result(current_price=1.0990)
    assert result.invalidation_price == pytest.approx(1.1060)
    assert result.invalidation_source_type == SOURCE_LIQUIDITY_SWEEP_LEVEL
    assert result.state != "INVALIDATED"


def test_m3_invalidated_when_live_price_crosses_sweep_level_short():
    result = _m3_ready_result(current_price=1.1070)
    assert result.state == "INVALIDATED"
    assert result.invalidation_price == pytest.approx(1.1060)


# --------------------------------------------------------------------------- end-to-end propagation (M2)

from entry_confirmation.m2_supply_demand_shift import evaluate_m2_supply_demand_shift

_M2_ZONE_ORIGIN = dt.datetime(2026, 1, 4, 10, 0, tzinfo=UTC)
_M2_M5_START = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_M2_ZONE_FAIL_TIME = _M2_M5_START - dt.timedelta(minutes=5)
_M2_CHOCH_TIME = _M2_M5_START + dt.timedelta(minutes=5 * 8)


def _m2_bearish_candles():
    from strategy_engine.session import Candle
    zone_fail_candle = Candle(_M2_ZONE_FAIL_TIME, 1.0992, 1.0994, 1.0975, 1.0978)
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [zone_fail_candle] + [_m1_pt(_M2_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_M2_CHOCH_TIME, 1.1032, 1.1034, 1.0928, 1.0930))
    return candles


def _m2_ready_result(new_zone_status):
    opposing = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                           direction=ZoneDirection.BULLISH, status=ZoneStatus.INVALIDATED, source="test",
                           low=1.0990, high=1.1000, origin_time=_M2_ZONE_ORIGIN)
    new_supply = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.SUPPLY,
                             direction=ZoneDirection.BEARISH, status=new_zone_status, source="test",
                             low=1.1055, high=1.1075, origin_time=_M2_M5_START)
    e = _EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT", eligible_for_confirmation=True)
    fvg = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                      direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
                      low=1.0980, high=1.0995, origin_time=_M2_ZONE_FAIL_TIME + dt.timedelta(minutes=1))
    return evaluate_m2_supply_demand_shift(
        "EURUSD", e, opposing, _m2_bearish_candles(), _m1_displacement_history(),
        (new_supply,), (fvg,), (), None, _M2_CHOCH_TIME + dt.timedelta(minutes=5), _M1_CFG,
    )


def test_m2_invalidation_exposed_but_not_triggered_when_new_zone_fresh():
    result = _m2_ready_result(ZoneStatus.FRESH)
    assert result.state != "INVALIDATED"
    assert result.invalidation_price == pytest.approx(1.1075)  # SUPPLY boundary = high
    assert result.invalidation_source_type == SOURCE_NEW_CONTROLLING_ZONE_BOUNDARY
    assert result.invalidation_trigger == TRIGGER_CLOSED_CANDLE_CLOSE


def test_m2_invalidated_when_new_controlling_zone_closes_beyond():
    result = _m2_ready_result(ZoneStatus.INVALIDATED)
    assert result.state == "INVALIDATED"
    assert result.invalidation_price == pytest.approx(1.1075)
