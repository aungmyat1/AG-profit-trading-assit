from datetime import datetime, timezone

from session_sweep_continuation.regime import Regime
from session_sweep_continuation.setups import (
    SetupModel,
    evaluate_s1_sweep_reversal,
    evaluate_s2_breakout_continuation,
    evaluate_s3_pullback_continuation,
)
from session_sweep_continuation.swing_structure import BOSDirection, BOSEvent, Swing, SwingType
from strategy_engine.session.candles import Candle

T = datetime(2026, 9, 10, 7, 0, tzinfo=timezone.utc)


def _c(o, h, l, c):
    return Candle(T, o, h, l, c)


# --- S1 ---

def test_s1_valid_long_sweep_wick_breach_close_back_inside():
    candle = _c(1.1000, 1.1005, 1.0940, 1.1000)  # wick breaches low 1.0950, closes back inside
    result = evaluate_s1_sweep_reversal(candle, 0, reference_high=1.1050, reference_low=1.0950, regime=Regime.RANGE)
    assert result is not None
    assert result.direction == "LONG"
    assert result.evidence["sweep_extreme_price"] == 1.0940


def test_s1_invalid_regime_rejected():
    candle = _c(1.1000, 1.1005, 1.0940, 1.1000)
    result = evaluate_s1_sweep_reversal(candle, 0, reference_high=1.1050, reference_low=1.0950, regime=Regime.TREND_UP)
    assert result is None


def test_s1_no_close_back_inside_is_invalid():
    candle = _c(1.1000, 1.1005, 1.0940, 1.0945)  # closes still outside range
    result = evaluate_s1_sweep_reversal(candle, 0, reference_high=1.1050, reference_low=1.0950, regime=Regime.RANGE)
    assert result is None


def test_s1_dual_side_sweep_same_candle_is_ambiguous_no_trade():
    candle = _c(1.1000, 1.1060, 1.0940, 1.1000)  # wicks both sides, closes inside
    result = evaluate_s1_sweep_reversal(candle, 0, reference_high=1.1050, reference_low=1.0950, regime=Regime.RANGE)
    assert result is None


# --- S2 ---

def _swing(price, idx=0, t=SwingType.LOW):
    return Swing(index=idx, swing_type=t, price=price, time=T, confirmed_at=T)


def test_s2_requires_bos_and_trend_regime_no_sweep_needed():
    bos = BOSEvent(BOSDirection.UP, 5, T, _swing(1.0900), 1.1000, displacement_confirmed=True)
    result = evaluate_s2_breakout_continuation(bos, _c(1.0990, 1.1005, 1.0985, 1.1000), Regime.TREND_UP)
    assert result is not None
    assert result.direction == "LONG"
    assert result.setup_model == SetupModel.S2


def test_s2_wrong_regime_rejected_bos_required():
    bos = BOSEvent(BOSDirection.UP, 5, T, _swing(1.0900), 1.1000, displacement_confirmed=True)
    result = evaluate_s2_breakout_continuation(bos, _c(1.0990, 1.1005, 1.0985, 1.1000), Regime.RANGE)
    assert result is None


def test_s2_trend_required_direction_must_match_bos_direction():
    bos = BOSEvent(BOSDirection.DOWN, 5, T, _swing(1.1100, t=SwingType.HIGH), 1.1000, displacement_confirmed=True)
    result = evaluate_s2_breakout_continuation(bos, _c(1.0990, 1.1005, 1.0985, 1.1000), Regime.TREND_UP)
    assert result is None


# --- S3 ---

def test_s3_requires_prior_bos():
    signals = {"eligible_fvg_retrace": True, "ema20_retest": True, "breakout_level_retest": False,
               "pullback_liquidity_sweep": False, "displacement_reconfirmation": False}
    result = evaluate_s3_pullback_continuation(None, _c(1.1, 1.1, 1.1, 1.1), 0, "LONG", Regime.TREND_UP, signals, minimum_score=2)
    assert result is None


def test_s3_score_below_minimum_rejected():
    bos = BOSEvent(BOSDirection.UP, 5, T, _swing(1.0900), 1.1000, displacement_confirmed=True)
    signals = {"eligible_fvg_retrace": True, "ema20_retest": False, "breakout_level_retest": False,
               "pullback_liquidity_sweep": False, "displacement_reconfirmation": False}
    result = evaluate_s3_pullback_continuation(bos, _c(1.1, 1.1, 1.1, 1.1), 0, "LONG", Regime.TREND_UP, signals, minimum_score=2)
    assert result is None


def test_s3_score_at_or_above_minimum_accepted():
    bos = BOSEvent(BOSDirection.UP, 5, T, _swing(1.0900), 1.1000, displacement_confirmed=True)
    signals = {"eligible_fvg_retrace": True, "ema20_retest": True, "breakout_level_retest": False,
               "pullback_liquidity_sweep": False, "displacement_reconfirmation": False}
    result = evaluate_s3_pullback_continuation(bos, _c(1.1, 1.1, 1.1, 1.1), 0, "LONG", Regime.TREND_UP, signals, minimum_score=2)
    assert result is not None
    assert result.evidence["continuation_score"] == 2


def test_s3_ema_only_never_qualifies_alone_even_with_lowered_threshold():
    bos = BOSEvent(BOSDirection.UP, 5, T, _swing(1.0900), 1.1000, displacement_confirmed=True)
    signals = {"eligible_fvg_retrace": False, "ema20_retest": True, "breakout_level_retest": False,
               "pullback_liquidity_sweep": False, "displacement_reconfirmation": False}
    # even a misconfigured minimum_score=1 must not let EMA-only qualify
    result = evaluate_s3_pullback_continuation(bos, _c(1.1, 1.1, 1.1, 1.1), 0, "LONG", Regime.TREND_UP, signals, minimum_score=1)
    assert result is None
