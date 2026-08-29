"""M1_CHARACTER_CHANGE_WITH_INDUCEMENT_V1 tests. Fail-closed on the core rule: a CHoCH
found without a causally-prior, deterministically identified inducement sweep never
reaches READY -- "CHOCH=YES, INDUCEMENT=UNKNOWN => M1 != READY". Decoupled from E1
(spec section 10): M1 now takes a generic `EConditionResult`, built directly here (any
qualified E1/E2/E3 would do -- M1 does not know or care which)."""
from __future__ import annotations

import datetime as dt

from entry_confirmation.entry_models_v1 import EConditionResult
from entry_confirmation.m1_character_change_inducement import evaluate_m1_character_change_with_inducement
from liquidity.hierarchy import InducementCandidate
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure import MarketStructureConfig
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc
_CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)

_TAKEN_TIME = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_M5_START = _TAKEN_TIME + dt.timedelta(minutes=5)
_CHOCH_TIME = _M5_START + dt.timedelta(minutes=5 * 8)


def _pt(t, p, eps=0.0002):
    return Candle(time=t, open=p, high=p + eps, low=p - eps, close=p, volume=1.0)


def _bearish_m5_candles(drop_open=1.1032, drop_high=1.1034, drop_low=1.0928, drop_close=1.0930):
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [_pt(_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_CHOCH_TIME, drop_open, drop_high, drop_low, drop_close))
    return candles


def _displacement_history():
    base = _TAKEN_TIME - dt.timedelta(hours=2)
    return [Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


def _inducement_level(side=LiquiditySide.BUY_SIDE, price=1.1060):
    return LiquidityLevel(symbol="EURUSD", timeframe="M5", side=side, source="SWING_HIGH", price=price,
                           origin_time=_TAKEN_TIME - dt.timedelta(hours=1), status=LiquidityStatus.UNSWEPT)


def _target_level(side=LiquiditySide.BUY_SIDE, price=1.1200):
    return LiquidityLevel(symbol="EURUSD", timeframe="M5", side=side, source="EXTERNAL_SWING_HIGH", price=price,
                           origin_time=_TAKEN_TIME - dt.timedelta(hours=2), status=LiquidityStatus.UNSWEPT)


def _candidate(side=LiquiditySide.BUY_SIDE, price=1.1060):
    level = _inducement_level(side, price)
    target = _target_level(side)
    return InducementCandidate(candidate_id="c1", candidate=level, target_id="t1", target=target, side=side)


def _taken(price=1.1060, sweep_time=_TAKEN_TIME):
    return LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                           price=price, origin_time=_TAKEN_TIME - dt.timedelta(hours=1),
                           status=LiquidityStatus.RECLAIMED, sweep_time=sweep_time)


def _same_leg_fvg(origin_time):
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
                       low=1.0980, high=1.0995, origin_time=origin_time)


def _e1(direction="SHORT", eligible=True):
    return EConditionResult(entry_condition="E1", symbol="EURUSD", direction=direction,
                             eligible_for_confirmation=eligible)


def _m1_kwargs(**overrides):
    kwargs = dict(
        inducement_taken_level=_taken(), m5_candles=_bearish_m5_candles(),
        m5_displacement_history=_displacement_history(), m5_fvg_zones=(), m5_order_blocks=(),
        current_price=None, evaluation_time=_CHOCH_TIME + dt.timedelta(minutes=5), structure_config=_CFG,
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------- positive


def test_full_bearish_character_change_confirms_short():
    fvg = _same_leg_fvg(_TAKEN_TIME + dt.timedelta(minutes=1))
    result = evaluate_m1_character_change_with_inducement(
        "EURUSD", _e1("SHORT"), _candidate(), **_m1_kwargs(m5_fvg_zones=(fvg,)),
    )
    assert result.inducement_taken is True
    assert result.choch_confirmed is True
    assert result.displacement_confirmed is True
    assert result.state in ("WAITING_M5_ENTRY", "READY")


# --------------------------------------------------------------------------- fail-closed core rule


def test_no_inducement_candidate_is_never_ready_even_with_choch():
    result = evaluate_m1_character_change_with_inducement("EURUSD", _e1("SHORT"), None, **_m1_kwargs())
    assert result.inducement_level is None
    assert result.choch_confirmed is False  # CHoCH never even searched -- fail closed
    assert result.state == "WAITING_HTF_TOUCH"


def test_wrong_side_inducement_candidate_is_no_valid_combination():
    wrong_side = _candidate(side=LiquiditySide.SELL_SIDE, price=1.0940)  # SHORT needs BUY_SIDE
    result = evaluate_m1_character_change_with_inducement("EURUSD", _e1("SHORT"), wrong_side, **_m1_kwargs())
    assert result.inducement_taken is False
    assert result.state == "NO_VALID_COMBINATION"


def test_inducement_identified_but_not_taken_waits():
    untaken = LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                              price=1.1060, origin_time=_TAKEN_TIME - dt.timedelta(hours=1),
                              status=LiquidityStatus.UNSWEPT)
    result = evaluate_m1_character_change_with_inducement(
        "EURUSD", _e1("SHORT"), _candidate(), **_m1_kwargs(inducement_taken_level=untaken),
    )
    assert result.inducement_taken is False
    assert result.state == "WAITING_H1_REACTION"


def test_e1_not_eligible_makes_m1_not_applicable():
    result = evaluate_m1_character_change_with_inducement("EURUSD", _e1("SHORT", eligible=False), _candidate(), **_m1_kwargs())
    assert result.state == "NOT_APPLICABLE"


def test_no_choch_after_inducement_taken_waits_for_confirmation():
    result = evaluate_m1_character_change_with_inducement(
        "EURUSD", _e1("SHORT"), _candidate(), **_m1_kwargs(m5_candles=_bearish_m5_candles()[:8]),  # no drop candle
    )
    assert result.inducement_taken is True
    assert result.choch_confirmed is False
    assert result.state == "WAITING_M5_CONFIRMATION"


def test_choch_before_inducement_taken_is_wrong_sequence_rejected():
    late_taken = _taken(sweep_time=_CHOCH_TIME + dt.timedelta(minutes=10))
    result = evaluate_m1_character_change_with_inducement(
        "EURUSD", _e1("SHORT"), _candidate(), **_m1_kwargs(inducement_taken_level=late_taken),
    )
    assert result.choch_confirmed is False
    assert result.state == "WAITING_M5_CONFIRMATION"


def test_choch_without_qualifying_displacement_never_reaches_ready():
    weak_candles = _bearish_m5_candles(drop_open=1.1029, drop_high=1.1030, drop_low=1.1026, drop_close=1.1027)
    result = evaluate_m1_character_change_with_inducement(
        "EURUSD", _e1("SHORT"), _candidate(), **_m1_kwargs(m5_candles=weak_candles),
    )
    assert result.displacement_confirmed is False
    assert result.state != "READY"


# --------------------------------------------------------------------------- causality


def test_zero_lookahead_future_mutation_does_not_change_past_result():
    fvg = _same_leg_fvg(_TAKEN_TIME + dt.timedelta(minutes=1))
    kwargs = _m1_kwargs(m5_fvg_zones=(fvg,))
    result_before = evaluate_m1_character_change_with_inducement("EURUSD", _e1("SHORT"), _candidate(), **kwargs)

    mutated = dict(kwargs)
    mutated["m5_candles"] = list(kwargs["m5_candles"]) + [
        Candle(_CHOCH_TIME + dt.timedelta(minutes=25), 1.0500, 1.0900, 1.0400, 1.0850),
    ]
    result_after = evaluate_m1_character_change_with_inducement("EURUSD", _e1("SHORT"), _candidate(), **mutated)

    assert result_after.state == result_before.state
    assert result_after.choch_level == result_before.choch_level
