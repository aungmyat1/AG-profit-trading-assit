from session_sweep_continuation.regime import Regime, classify_regime, ema

CONFIG = {
    "regime": {
        "min_reference_candles": 4,
        "range_max_pips": 25.0,
        "ema_fast_period": 3,
        "ema_slow_period": 5,
    }
}


def test_unknown_when_insufficient_candles():
    result = classify_regime([1.1, 1.1, 1.1], range_pips=10.0, candle_count=3, config=CONFIG)
    assert result.regime == Regime.UNKNOWN


def test_range_when_within_max_pips():
    closes = [1.1000, 1.1002, 1.1001, 1.1003, 1.1002, 1.1004]
    result = classify_regime(closes, range_pips=20.0, candle_count=6, config=CONFIG)
    assert result.regime == Regime.RANGE


def test_trend_up_when_ema_aligned_up_and_wide_range():
    closes = [1.1000, 1.1010, 1.1025, 1.1040, 1.1060, 1.1080]
    result = classify_regime(closes, range_pips=80.0, candle_count=6, config=CONFIG)
    assert result.regime == Regime.TREND_UP


def test_trend_down_when_ema_aligned_down_and_wide_range():
    closes = [1.1080, 1.1060, 1.1040, 1.1025, 1.1010, 1.1000]
    result = classify_regime(closes, range_pips=80.0, candle_count=6, config=CONFIG)
    assert result.regime == Regime.TREND_DOWN


def test_transition_when_wide_range_but_mixed_alignment():
    # General uptrend (ema_fast > ema_slow) but a sharp final drop puts last_close
    # below ema_slow -- neither TREND_UP's nor TREND_DOWN's condition is fully met,
    # so this must classify as TRANSITION. Verified against the module's own `ema`
    # rather than hand-picked numbers, to avoid an accidentally-wrong fixture.
    closes = [1.1000, 1.1000, 1.1000, 1.1000, 1.1200, 1.0950]
    fast = ema(closes, CONFIG["regime"]["ema_fast_period"])
    slow = ema(closes, CONFIG["regime"]["ema_slow_period"])
    assert fast > slow  # precondition for this fixture to actually test TRANSITION
    assert closes[-1] < slow
    result = classify_regime(closes, range_pips=80.0, candle_count=6, config=CONFIG)
    assert result.regime == Regime.TRANSITION
