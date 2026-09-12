"""TEST_ONLY SYNTHETIC fixtures for research_external/semantic/s2r.py
(S2R_BREAKOUT_RETEST_CONTINUATION_V1, EXPERIMENTAL RESEARCH ONLY). Every candle
sequence below is hand-constructed and deterministic -- never real market data,
never cited as strategy evidence.

Config matches research_external/specs/S2R_BREAKOUT_RETEST_CONTINUATION_V1.yaml's
values, inlined here so these tests never silently drift from a YAML edit.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from research_external.semantic.s2r import (
    REASON_CONFIRMATION_FAILED,
    REASON_INVALID_DATA,
    REASON_NO_BREAKOUT,
    REASON_NO_RETEST,
    REASON_READY_LONG,
    REASON_READY_SHORT,
    REASON_SESSION_INCOMPLETE,
    REASON_WEAK_DISPLACEMENT,
    run_s2r_over_history,
)

_CONFIG = {
    "reference_session": {"start_time_utc": "00:00", "end_time_utc": "06:00", "min_reference_candles": 4},
    "monitoring_window": {"start_time_utc": "06:00", "end_time_utc": "24:00"},
    "atr": {"period": 3},
    "displacement": {"atr_multiple": 1.0},
    "retest": {"required": True, "max_bars": 5, "tolerance_atr": 0.25},
    "confirmation": {"close_beyond_breakout_level": True},
    "stop": {"buffer_atr": 0.20},
    "target": {"rr": 2.0},
}


def _c(day: str, hh: int, mm: int, o: float, h: float, l: float, cl: float) -> dict:
    t = f"{day}T{hh:02d}:{mm:02d}:00+00:00"
    return {"time": t, "open": o, "high": h, "low": l, "close": cl}


def _warmup(day: str, n: int, base: float = 1.1000) -> list:
    """ATR warmup candles with modest, stable ranges -- placed the day before the
    scenario day so the scenario's own ATR is already valid (non-None) by 06:00."""
    out = []
    px = base
    for i in range(n):
        px += 0.0001 if i % 2 == 0 else -0.0001
        out.append(_c(day, i // 12, (i % 12) * 5, px, px + 0.0005, px - 0.0005, px + 0.0001))
    return out


def _reference_session(day: str, ref_high: float, ref_low: float, n: int = 6) -> list:
    """n TIGHT-RANGE candles (true range ~0.0003-0.0005, matching warmup magnitude,
    so ATR stays small) whose aggregate max(high)/min(low) equal ref_high/ref_low
    exactly (first candle touches ref_low, last touches ref_high) -- keeps ATR
    realistic while still producing the intended reference range boundaries."""
    out = []
    step = (ref_high - ref_low) / max(n - 1, 1)
    for i in range(n):
        px = ref_low + step * i
        if i == 0:
            high, low = ref_low + 0.0003, ref_low
        elif i == n - 1:
            high, low = ref_high, ref_high - 0.0003
        else:
            high, low = px + 0.0002, px - 0.0002
        out.append(_c(day, 0, i * 5, px, high, low, px))
    return out


def test_f1_bullish_valid_breakout_continuation():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    # Breakout+displacement candle at 06:00: closes well above 1.1050 with a large body.
    candles.append(_c(day, 6, 0, 1.1050, 1.1090, 1.1048, 1.1085))
    # Retest candle at 06:05: dips back to touch the breakout level (1.1050) but
    # closes BELOW it -- confirmation must wait for the next candle.
    candles.append(_c(day, 6, 5, 1.1085, 1.1086, 1.1049, 1.1049))
    # Confirmation candle at 06:10: closes back above breakout level.
    candles.append(_c(day, 6, 10, 1.1049, 1.1095, 1.1047, 1.1092))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.decision_timestamp and s.decision_timestamp.startswith(day))
    assert day_signal.reason_code == REASON_READY_LONG
    assert day_signal.direction == "LONG"
    assert day_signal.entry == 1.1092
    assert day_signal.stop < day_signal.breakout_level
    assert day_signal.target > day_signal.entry


def test_f2_bearish_valid_breakout_continuation():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    candles.append(_c(day, 6, 0, 1.1000, 1.1002, 1.0960, 1.0965))
    candles.append(_c(day, 6, 5, 1.0965, 1.1001, 1.0964, 1.0990))
    candles.append(_c(day, 6, 10, 1.0990, 1.0992, 1.0955, 1.0958))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.decision_timestamp and s.decision_timestamp.startswith(day))
    assert day_signal.reason_code == REASON_READY_SHORT
    assert day_signal.direction == "SHORT"
    assert day_signal.stop > day_signal.breakout_level
    assert day_signal.target < day_signal.entry


def test_f3_weak_displacement():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    # Closes above range but tiny body -- fails the ATR-multiple displacement gate.
    candles.append(_c(day, 6, 0, 1.1050, 1.1052, 1.1049, 1.1051))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.data_available_through and day in s.data_available_through)
    assert day_signal.reason_code == REASON_WEAK_DISPLACEMENT


def test_f4_breakout_with_no_retest():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    candles.append(_c(day, 6, 0, 1.1050, 1.1090, 1.1048, 1.1085))
    # 5 subsequent candles that never come back near the breakout level (1.1050).
    for i in range(1, 6):
        candles.append(_c(day, 6, 5 * i, 1.1085 + i * 0.0005, 1.1090 + i * 0.0005, 1.1080 + i * 0.0005, 1.1088 + i * 0.0005))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.data_available_through and day in s.data_available_through)
    assert day_signal.reason_code == REASON_NO_RETEST


def test_f5_retest_with_failed_confirmation():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    candles.append(_c(day, 6, 0, 1.1050, 1.1090, 1.1048, 1.1085))
    # Retest touches breakout level but every subsequent close stays below it.
    for i in range(1, 6):
        candles.append(_c(day, 6, 5 * i, 1.1055, 1.1056, 1.1049, 1.1049))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.data_available_through and day in s.data_available_through)
    assert day_signal.reason_code == REASON_CONFIRMATION_FAILED


def test_f6_incomplete_reference_session():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000, n=2)  # below min_reference_candles=4
    candles.append(_c(day, 6, 0, 1.1050, 1.1090, 1.1048, 1.1085))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.data_available_through and day in s.data_available_through)
    assert day_signal.reason_code == REASON_SESSION_INCOMPLETE


def test_f7_boundary_touch_without_breakout_close():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    # Wick pierces 1.1050 but closes back inside the range -- not a breakout.
    candles.append(_c(day, 6, 0, 1.1040, 1.1060, 1.1038, 1.1045))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.data_available_through and day in s.data_available_through)
    assert day_signal.reason_code == REASON_NO_BREAKOUT


def test_f8_malformed_ohlc_geometry_rejects_data():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    # low > high: physically impossible bar.
    candles.append(_c(day, 6, 0, 1.1050, 1.1040, 1.1090, 1.1045))

    signals = run_s2r_over_history(candles, _CONFIG)
    day_signal = next(s for s in signals if s.data_available_through and day in s.data_available_through)
    assert day_signal.reason_code == REASON_INVALID_DATA


def test_no_lookahead_data_available_through_never_exceeds_decision_timestamp():
    day = "2026-03-02"
    candles = _warmup("2026-03-01", 30) + _reference_session(day, 1.1050, 1.1000)
    candles.append(_c(day, 6, 0, 1.1050, 1.1090, 1.1048, 1.1085))
    candles.append(_c(day, 6, 5, 1.1085, 1.1086, 1.1049, 1.1060))
    candles.append(_c(day, 6, 10, 1.1060, 1.1095, 1.1058, 1.1092))

    signals = run_s2r_over_history(candles, _CONFIG)
    for s in signals:
        if s.decision_timestamp is not None:
            assert s.decision_timestamp <= s.data_available_through
