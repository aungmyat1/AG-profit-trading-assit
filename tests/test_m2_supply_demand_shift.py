"""M2_SUPPLY_DEMAND_SHIFT_V1 tests. Distinct from M3 (m3_sweep_drop_pump.py): no
liquidity sweep anywhere in this pipeline -- the defining evidence is an existing
opposing-role M5 zone genuinely FAILING (ZoneStatus.INVALIDATED, closed beyond) before
the structural break, never a CHoCH alone ("Do not claim SUPPLY_DEMAND_SHIFT = TRUE
merely because a CHoCH occurred"). Decoupled from E2 (spec section 10): M2 now takes a
generic `EConditionResult`, built directly here (any qualified E1/E2/E3 would do -- M2
does not know or care which).
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.entry_models_v1 import EConditionResult
from entry_confirmation.m2_supply_demand_shift import evaluate_m2_supply_demand_shift
from market_structure import MarketStructureConfig
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc
_CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)

_ZONE_ORIGIN = dt.datetime(2026, 1, 4, 10, 0, tzinfo=UTC)
_M5_START = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_ZONE_FAIL_TIME = _M5_START - dt.timedelta(minutes=5)
_CHOCH_TIME = _M5_START + dt.timedelta(minutes=5 * 8)


def _pt(t, p, eps=0.0002):
    return Candle(time=t, open=p, high=p + eps, low=p - eps, close=p, volume=1.0)


def _displacement_history():
    base = _ZONE_FAIL_TIME - dt.timedelta(hours=2)
    return [Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


def _bearish_m5_candles(drop_open=1.1032, drop_high=1.1034, drop_low=1.0928, drop_close=1.0930):
    """Demand fails at _ZONE_FAIL_TIME (closes below zone.low), then an ascending
    zigzag, then a decisive bearish drop candle -> BEARISH_CHOCH at _CHOCH_TIME
    (same zigzag+drop shape already verified against the real structure engine in
    test_m3_sweep_drop_pump.py -- only the leading zone-failure candle is new)."""
    zone_fail_candle = Candle(_ZONE_FAIL_TIME, 1.0992, 1.0994, 1.0975, 1.0978)
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [zone_fail_candle] + [_pt(_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_CHOCH_TIME, drop_open, drop_high, drop_low, drop_close))
    return candles


def _bullish_m5_candles(pump_open=1.0968, pump_high=1.1072, pump_low=1.0966, pump_close=1.1070):
    zone_fail_candle = Candle(_ZONE_FAIL_TIME, 1.1008, 1.1025, 1.1006, 1.1022)
    prices = [1.1000, 1.0970, 1.0990, 1.0960, 1.0980, 1.0950, 1.0970, 1.0940]
    candles = [zone_fail_candle] + [_pt(_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_CHOCH_TIME, pump_open, pump_high, pump_low, pump_close))
    return candles


def _demand_zone(status=ZoneStatus.INVALIDATED, low=1.0990, high=1.1000):
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, status=status, source="test",
                       low=low, high=high, origin_time=_ZONE_ORIGIN)


def _supply_zone(status=ZoneStatus.INVALIDATED, low=1.1005, high=1.1020):
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.SUPPLY,
                       direction=ZoneDirection.BEARISH, status=status, source="test",
                       low=low, high=high, origin_time=_ZONE_ORIGIN)


def _same_leg_fvg(origin_time, direction=ZoneDirection.BEARISH):
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=direction, status=ZoneStatus.FRESH, source="test",
                       low=1.0980, high=1.0995, origin_time=origin_time)


def _e2(direction="SHORT", eligible=True):
    return EConditionResult(entry_condition="E2", symbol="EURUSD", direction=direction,
                             eligible_for_confirmation=eligible)


def _m2_kwargs(**overrides):
    kwargs = dict(
        m5_candles=_bearish_m5_candles(), m5_displacement_history=_displacement_history(),
        m5_candidate_zones=(), m5_fvg_zones=(), m5_order_blocks=(), current_price=None,
        evaluation_time=_CHOCH_TIME + dt.timedelta(minutes=5), structure_config=_CFG,
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------- bearish positive


def test_full_bearish_shift_confirms_short_with_same_leg_fvg():
    fvg = _same_leg_fvg(_ZONE_FAIL_TIME + dt.timedelta(minutes=1))
    result = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), _demand_zone(), **_m2_kwargs(m5_fvg_zones=(fvg,)))

    assert result.pre_shift_flow == "DEMAND"
    assert result.zone_failure is True
    assert result.zone_failure_time == _ZONE_FAIL_TIME
    assert result.structural_break_time is not None
    assert result.displacement_confirmed is True
    assert result.entry_fvg is not None
    assert result.state in ("WAITING_M5_ENTRY", "READY")


def test_full_bullish_shift_confirms_long():
    fvg = _same_leg_fvg(_ZONE_FAIL_TIME + dt.timedelta(minutes=1), direction=ZoneDirection.BULLISH)
    result = evaluate_m2_supply_demand_shift(
        "EURUSD", _e2("LONG"), _supply_zone(), **_m2_kwargs(m5_candles=_bullish_m5_candles(), m5_fvg_zones=(fvg,)),
    )
    assert result.pre_shift_flow == "SUPPLY"
    assert result.zone_failure is True
    assert result.state in ("WAITING_M5_ENTRY", "READY")


# --------------------------------------------------------------------------- gating: no CHoCH != shift


def test_choch_alone_without_zone_failure_never_confirms_shift():
    mitigated_demand = _demand_zone(status=ZoneStatus.MITIGATED)  # wick-touched, NOT closed beyond
    result = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), mitigated_demand, **_m2_kwargs())
    assert result.zone_failure is False
    assert result.structural_break is None  # CHoCH never even searched -- zone failure gates it
    assert result.state == "WAITING_M5_CONFIRMATION"


def test_missing_opposing_zone_waits_never_fabricates_shift():
    result = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), None, **_m2_kwargs())
    assert result.zone_failure is False
    assert result.state == "WAITING_H1_REACTION"


def test_wrong_role_opposing_zone_is_no_valid_combination():
    wrong_role = _supply_zone()  # SHORT needs a DEMAND (opposing) zone, not SUPPLY -- its
    # SUPPLY role implies a bullish shift, contradicting the SHORT E-condition.
    result = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), wrong_role, **_m2_kwargs())
    assert result.zone_failure is False
    assert result.state == "NO_VALID_COMBINATION"


def test_e2_not_eligible_makes_m2_not_applicable():
    result = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT", eligible=False), _demand_zone(), **_m2_kwargs())
    assert result.state == "NOT_APPLICABLE"


def test_no_choch_after_zone_failure_waits_for_confirmation():
    result = evaluate_m2_supply_demand_shift(
        "EURUSD", _e2("SHORT"), _demand_zone(), **_m2_kwargs(m5_candles=_bearish_m5_candles()[:8]),  # no drop candle
    )
    assert result.zone_failure is True
    assert result.structural_break is None
    assert result.state == "WAITING_M5_CONFIRMATION"


def test_choch_without_qualifying_displacement_never_reaches_ready():
    weak_candles = _bearish_m5_candles(drop_open=1.1029, drop_high=1.1030, drop_low=1.1026, drop_close=1.1027)
    result = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), _demand_zone(), **_m2_kwargs(m5_candles=weak_candles))
    assert result.displacement_confirmed is False
    assert result.state != "READY"


# --------------------------------------------------------------------------- causality


def test_zero_lookahead_future_mutation_does_not_change_past_result():
    fvg = _same_leg_fvg(_ZONE_FAIL_TIME + dt.timedelta(minutes=1))
    kwargs = _m2_kwargs(m5_fvg_zones=(fvg,))
    result_before = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), _demand_zone(), **kwargs)

    mutated = dict(kwargs)
    mutated["m5_candles"] = list(kwargs["m5_candles"]) + [
        Candle(_CHOCH_TIME + dt.timedelta(minutes=25), 1.0500, 1.0900, 1.0400, 1.0850),
    ]
    result_after = evaluate_m2_supply_demand_shift("EURUSD", _e2("SHORT"), _demand_zone(), **mutated)

    assert result_after.state == result_before.state
    assert result_after.structural_break_time == result_before.structural_break_time
