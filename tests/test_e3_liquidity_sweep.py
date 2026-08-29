"""E3_HTF_LIQUIDITY_SWEEP_V1 tests -- TOUCH/PENETRATION/SWEEP/RECLAIM distinction (spec
section 11). Relabels `liquidity.LiquidityStatus`'s own state machine; never redetects
sweep/reclaim itself (see e3_liquidity_sweep.py's module docstring for the mapping)."""
from __future__ import annotations

import datetime as dt

from entry_confirmation.e3_liquidity_sweep import evaluate_e3_htf_liquidity_sweep
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus

UTC = dt.timezone.utc
_ORIGIN = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_SWEEP_TIME = _ORIGIN + dt.timedelta(minutes=35)
_RECLAIM_TIME = _ORIGIN + dt.timedelta(minutes=40)


def _level(side, status, sweep_time=None, reclaim_time=None, price=1.1060):
    return LiquidityLevel(symbol="EURUSD", timeframe="H1", side=side, source="EXTERNAL_SWING_HIGH", price=price,
                           origin_time=_ORIGIN, status=status, sweep_time=sweep_time, reclaim_time=reclaim_time)


def test_no_level_is_indeterminate_not_fabricated():
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", None)
    assert result.eligible_for_confirmation is False


def test_touch_only_unswept_is_never_a_sweep():
    level = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.UNSWEPT)
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.penetration is False
    assert result.sweep is False
    assert result.reclaim is False
    assert result.eligible_for_confirmation is False


def test_live_penetration_swept_state_is_penetration_not_yet_sweep():
    level = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.SWEPT, sweep_time=_SWEEP_TIME)
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.penetration is True
    assert result.sweep is False
    assert result.eligible_for_confirmation is False


def test_consumed_sweep_with_no_reclaim_is_not_eligible():
    level = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.CONSUMED, sweep_time=_SWEEP_TIME)
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.penetration is True
    assert result.sweep is True
    assert result.reclaim is False
    assert result.invalidation == "SWEEP_CONSUMED_NO_RECLAIM"
    assert result.eligible_for_confirmation is False


def test_bearish_bsl_sweep_reclaimed_is_eligible_short():
    level = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.RECLAIMED, sweep_time=_SWEEP_TIME, reclaim_time=_RECLAIM_TIME)
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.sweep is True
    assert result.reclaim is True
    assert result.direction == "SHORT"
    assert result.eligible_for_confirmation is True


def test_bullish_ssl_sweep_reclaimed_is_eligible_long():
    level = _level(LiquiditySide.SELL_SIDE, LiquidityStatus.RECLAIMED, sweep_time=_SWEEP_TIME, reclaim_time=_RECLAIM_TIME, price=1.0940)
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.sweep is True
    assert result.reclaim is True
    assert result.direction == "LONG"
    assert result.eligible_for_confirmation is True
