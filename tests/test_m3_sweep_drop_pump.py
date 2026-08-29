"""M3_SWEEP_DROP_PUMP_V1 tests. Decoupled from E3Result (spec section 10): M3 now takes
a generic `EConditionResult` (built here via `e3_to_econdition`, but any E1/E2/E3
converter would do) plus the concrete `LiquidityLevel` evidence separately. This
pipeline (HTF sweep+reclaim -> M5 CHoCH -> displacement -> FVG/OB entry array) is the
same causal chain a prior revision of `e2_h1_poi_reaction.py` used to test under the E2
name -- moved here because it is HTF-liquidity-sweep-driven, i.e. M3. Exercises the REAL
market_structure engine and the REAL V2.1 sweep-shift-array pipeline.
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.e3_liquidity_sweep import e3_to_econdition, evaluate_e3_htf_liquidity_sweep
from entry_confirmation.m3_sweep_drop_pump import evaluate_m3_sweep_drop_pump
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure import MarketStructureConfig
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc
_CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)

_M5_START = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_SWEEP_TIME = _M5_START + dt.timedelta(minutes=5 * 7)
_RECLAIM_TIME = _SWEEP_TIME + dt.timedelta(minutes=1)
_CHOCH_TIME = _M5_START + dt.timedelta(minutes=5 * 8)


def _pt(t, p, eps=0.0002):
    return Candle(time=t, open=p, high=p + eps, low=p - eps, close=p, volume=1.0)


def _bearish_zigzag_m5_candles(drop_open=1.1032, drop_high=1.1034, drop_low=1.0928, drop_close=1.0930):
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [_pt(_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(time=_CHOCH_TIME, open=drop_open, high=drop_high, low=drop_low, close=drop_close))
    return candles


def _bullish_zigzag_m5_candles(pump_open=1.0968, pump_high=1.1072, pump_low=1.0966, pump_close=1.1070):
    prices = [1.1000, 1.0970, 1.0990, 1.0960, 1.0980, 1.0950, 1.0970, 1.0940]
    candles = [_pt(_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(time=_CHOCH_TIME, open=pump_open, high=pump_high, low=pump_low, close=pump_close))
    return candles


def _displacement_history():
    base = _M5_START - dt.timedelta(hours=2)
    return [Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


def _reclaimed_level(side=LiquiditySide.BUY_SIDE, price=1.1060, reclaim_time=_RECLAIM_TIME):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=side, source="ASIAN_HIGH", price=price,
        origin_time=_M5_START, status=LiquidityStatus.RECLAIMED, sweep_time=_SWEEP_TIME, reclaim_time=reclaim_time,
    )


def _consumed_level(side=LiquiditySide.BUY_SIDE, price=1.1060):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="M15", side=side, source="ASIAN_HIGH", price=price,
        origin_time=_M5_START, status=LiquidityStatus.CONSUMED, sweep_time=_SWEEP_TIME, reclaim_time=None,
    )


def _same_leg_fvg_zone(origin_time=None):
    origin_time = origin_time or (_SWEEP_TIME + dt.timedelta(minutes=3))
    return ZoneResult(
        symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
        direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
        low=1.0980, high=1.0995, origin_time=origin_time,
    )


def _econdition(level):
    return e3_to_econdition(evaluate_e3_htf_liquidity_sweep("EURUSD", level))


def _m3_kwargs(**overrides):
    kwargs = dict(
        m5_candles=_bearish_zigzag_m5_candles(), m5_displacement_history=_displacement_history(),
        m5_fvg_zones=(), m5_order_blocks=(), current_price=None,
        evaluation_time=_CHOCH_TIME + dt.timedelta(minutes=5), structure_config=_CFG,
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------- E3 gating


def test_e3_touch_only_is_not_a_sweep():
    level = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.BUY_SIDE, source="ASIAN_HIGH",
                            price=1.1060, origin_time=_M5_START, status=LiquidityStatus.UNSWEPT)
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.penetration is False
    assert result.sweep is False
    assert result.eligible_for_confirmation is False


def test_e3_consumed_sweep_without_reclaim_is_not_eligible():
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", _consumed_level())
    assert result.sweep is True
    assert result.reclaim is False
    assert result.invalidation == "SWEEP_CONSUMED_NO_RECLAIM"
    assert result.eligible_for_confirmation is False


def test_e3_reclaimed_sweep_is_eligible():
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", _reclaimed_level())
    assert result.reclaim is True
    assert result.direction == "SHORT"  # BUY_SIDE swept -> bearish reversal candidate
    assert result.eligible_for_confirmation is True


# --------------------------------------------------------------------------- M3 bearish/bullish


def test_full_bearish_sweep_drop_confirms_short_with_same_leg_fvg():
    level = _reclaimed_level()
    fvg = _same_leg_fvg_zone()
    result = evaluate_m3_sweep_drop_pump("EURUSD", _econdition(level), level, **_m3_kwargs(m5_fvg_zones=(fvg,)))

    assert result.direction == "SHORT"
    assert result.entry_condition == "E3"
    assert result.reclaim is True
    assert result.choch is not None
    assert result.displacement is True
    assert result.gap in ("FVG", "FVG_AND_ORDER_BLOCK")
    assert result.pullback_percent == 50.0
    assert result.entry_level is not None
    assert result.state in ("WAITING_M5_ENTRY", "READY")


def test_full_bullish_sweep_pump_confirms_long():
    level = _reclaimed_level(side=LiquiditySide.SELL_SIDE, price=1.0940)
    fvg = ZoneResult(
        symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
        direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="test",
        low=1.1075, high=1.1090, origin_time=_SWEEP_TIME + dt.timedelta(minutes=3),
    )
    result = evaluate_m3_sweep_drop_pump(
        "EURUSD", _econdition(level), level, **_m3_kwargs(m5_candles=_bullish_zigzag_m5_candles(), m5_fvg_zones=(fvg,)),
    )
    assert result.direction == "LONG"
    assert result.state in ("WAITING_M5_ENTRY", "READY")


# --------------------------------------------------------------------------- gating states


def test_e3_not_eligible_makes_m3_not_applicable():
    level = _consumed_level()
    result = evaluate_m3_sweep_drop_pump("EURUSD", _econdition(level), level, **_m3_kwargs())
    assert result.state == "NOT_APPLICABLE"


def test_no_liquidity_level_supplied_is_not_applicable():
    result = evaluate_m3_sweep_drop_pump("EURUSD", None, None, **_m3_kwargs())
    assert result.state == "NOT_APPLICABLE"


def test_no_choch_after_reclaim_waits_for_confirmation():
    level = _reclaimed_level()
    result = evaluate_m3_sweep_drop_pump(
        "EURUSD", _econdition(level), level, **_m3_kwargs(m5_candles=_bearish_zigzag_m5_candles()[:7]),
    )
    assert result.state == "WAITING_M5_CONFIRMATION"
    assert result.choch is None


def test_choch_before_reclaim_is_wrong_sequence_rejected():
    late_reclaim = _reclaimed_level(reclaim_time=_CHOCH_TIME + dt.timedelta(minutes=10))
    result = evaluate_m3_sweep_drop_pump("EURUSD", _econdition(late_reclaim), late_reclaim, **_m3_kwargs())
    assert result.state == "WAITING_M5_CONFIRMATION"


def test_choch_without_qualifying_displacement_never_reaches_ready():
    weak_candles = _bearish_zigzag_m5_candles(drop_open=1.1029, drop_high=1.1030, drop_low=1.1026, drop_close=1.1027)
    level = _reclaimed_level()
    result = evaluate_m3_sweep_drop_pump("EURUSD", _econdition(level), level, **_m3_kwargs(m5_candles=weak_candles))
    assert result.displacement is False
    assert result.state != "READY"


def test_level_side_mismatched_direction_is_no_valid_combination():
    # A SELL_SIDE-swept level (bullish direction) fed against a manually-built SHORT
    # E-condition -- direction alignment must reject this, not silently pick a side.
    level = _reclaimed_level(side=LiquiditySide.SELL_SIDE, price=1.0940)
    mismatched = _econdition(_reclaimed_level())  # SHORT (BUY_SIDE swept)
    result = evaluate_m3_sweep_drop_pump("EURUSD", mismatched, level, **_m3_kwargs())
    assert result.state == "NO_VALID_COMBINATION"


# --------------------------------------------------------------------------- inverted gap policy


def test_inverted_gap_policy_is_partial_never_fabricated():
    level = _reclaimed_level()
    fvg = _same_leg_fvg_zone()
    result = evaluate_m3_sweep_drop_pump("EURUSD", _econdition(level), level, **_m3_kwargs(m5_fvg_zones=(fvg,)))
    assert result.inverted_gap_policy in ("NORMAL_GAP", "PARTIAL", "UNAVAILABLE")


# --------------------------------------------------------------------------- causality


def test_zero_lookahead_future_mutation_does_not_change_past_result():
    level = _reclaimed_level()
    e_condition = _econdition(level)
    fvg = _same_leg_fvg_zone()
    kwargs = _m3_kwargs(m5_fvg_zones=(fvg,))
    result_before = evaluate_m3_sweep_drop_pump("EURUSD", e_condition, level, **kwargs)

    mutated_candles = list(kwargs["m5_candles"]) + [
        Candle(_CHOCH_TIME + dt.timedelta(minutes=25), 1.0500, 1.0900, 1.0400, 1.0850),
    ]
    kwargs2 = dict(kwargs)
    kwargs2["m5_candles"] = mutated_candles
    result_after = evaluate_m3_sweep_drop_pump("EURUSD", e_condition, level, **kwargs2)

    assert result_after.state == result_before.state
    assert result_after.choch_time == result_before.choch_time
