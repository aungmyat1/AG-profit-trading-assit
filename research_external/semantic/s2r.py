"""Pure, deterministic semantics for S2R_BREAKOUT_RETEST_CONTINUATION_V1 --
EXPERIMENTAL RESEARCH ONLY. See research_external/specs/
S2R_BREAKOUT_RETEST_CONTINUATION_V1.yaml for the full, documented specification this
module implements verbatim.

No I/O, no MT5, no broker, no execution, no optimization. Every function here is a
pure function of its inputs -- the same candles + config always produce the same
result. `evaluate_s2r_day()` and `run_s2r_over_history()` are the only entry points a
replay adapter (research_external/adapters/backtesting_py/) should call; the replay
engine must never redefine S2R semantics itself (mission's own "replay engine must
not become the authoritative definition" rule).

No-lookahead invariant: every signal's `data_available_through` is set to the
timestamp of the last candle actually consumed to produce it, and is always <=
`decision_timestamp`. Only candles at or before the current evaluation index are ever
read -- confirmed by tests/test_research_external_s2r_fixtures.py's own inspection of
which candle indices each function touches.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

from .wilder_atr import wilder_atr

Candle = Dict[str, object]  # {"time": ISO8601 UTC str, "open","high","low","close": float}

REASON_SESSION_INCOMPLETE = "SESSION_INCOMPLETE"
REASON_INVALID_DATA = "INVALID_DATA"
REASON_NO_BREAKOUT = "NO_BREAKOUT"
REASON_WEAK_DISPLACEMENT = "WEAK_DISPLACEMENT"
REASON_NO_RETEST = "NO_RETEST"
REASON_CONFIRMATION_FAILED = "CONFIRMATION_FAILED"
REASON_READY_LONG = "READY_LONG"
REASON_READY_SHORT = "READY_SHORT"


@dataclass(frozen=True)
class S2RSignal:
    reason_code: str
    decision_timestamp: Optional[str]
    data_available_through: Optional[str]
    direction: Optional[str] = None
    reference_high: Optional[float] = None
    reference_low: Optional[float] = None
    atr: Optional[float] = None
    breakout_price: Optional[float] = None
    breakout_level: Optional[float] = None
    displacement_body: Optional[float] = None
    retest_price: Optional[float] = None
    entry: Optional[float] = None
    stop: Optional[float] = None
    target: Optional[float] = None
    risk_distance: Optional[float] = None


def _parse_time(c: Candle) -> datetime:
    return datetime.fromisoformat(str(c["time"]))


def _is_valid_ohlc(c: Candle) -> bool:
    o, h, l, cl = float(c["open"]), float(c["high"]), float(c["low"]), float(c["close"])
    if any(v != v for v in (o, h, l, cl)):  # NaN check without importing math
        return False
    return h >= l and h >= o and h >= cl and l <= o and l <= cl


def calculate_reference_range(
    candles: Sequence[Candle], min_reference_candles: int,
) -> "tuple[Optional[float], Optional[float], bool]":
    """`candles` must already be filtered to exactly the reference-session window for
    one calendar day. Returns (reference_high, reference_low, complete)."""
    if len(candles) < min_reference_candles:
        return None, None, False
    highs = [float(c["high"]) for c in candles]
    lows = [float(c["low"]) for c in candles]
    return max(highs), min(lows), True


def detect_breakout(candle: Candle, reference_high: float, reference_low: float) -> Optional[str]:
    """Strict close-outside-range only -- a wick touch (high/low beyond range without
    a close beyond it) never qualifies (fixture F7)."""
    close = float(candle["close"])
    if close > reference_high:
        return "LONG"
    if close < reference_low:
        return "SHORT"
    return None


def detect_displacement(candle: Candle, atr: Optional[float], direction: str, atr_multiple: float) -> bool:
    if atr is None:
        return False
    body = abs(float(candle["close"]) - float(candle["open"]))
    return body >= atr_multiple * atr


def detect_retest(
    candles_after_breakout: Sequence[Candle], breakout_level: float, atr: Optional[float],
    tolerance_atr: float, max_bars: int,
) -> Optional[int]:
    """Returns the index (within `candles_after_breakout`) of the first candle whose
    range comes within `tolerance_atr * atr` of `breakout_level`, searching at most
    `max_bars` candles. None if atr is unavailable (fail closed, never a tolerance of
    zero silently)."""
    if atr is None:
        return None
    tolerance = tolerance_atr * atr
    for i, c in enumerate(candles_after_breakout[:max_bars]):
        low, high = float(c["low"]), float(c["high"])
        if (low - tolerance) <= breakout_level <= (high + tolerance):
            return i
    return None


def detect_confirmation(
    candles_from_retest: Sequence[Candle], direction: str, breakout_level: float, max_bars: int,
) -> Optional[int]:
    """Returns the index (within `candles_from_retest`, 0 = the retest candle itself)
    of the first candle whose CLOSE is beyond `breakout_level` in `direction`."""
    for i, c in enumerate(candles_from_retest[:max_bars]):
        close = float(c["close"])
        if direction == "LONG" and close > breakout_level:
            return i
        if direction == "SHORT" and close < breakout_level:
            return i
    return None


def calculate_entry(confirmation_candle: Candle) -> float:
    return float(confirmation_candle["close"])


def calculate_stop(breakout_level: float, atr: float, buffer_atr: float, direction: str) -> float:
    buffer = buffer_atr * atr
    return breakout_level - buffer if direction == "LONG" else breakout_level + buffer


def calculate_target(entry: float, stop: float, rr: float) -> float:
    risk_distance = abs(entry - stop)
    return entry + rr * risk_distance if entry > stop else entry - rr * risk_distance


def evaluate_s2r_day(
    reference_candles: Sequence[Candle],
    monitor_candles: Sequence[Candle],
    atr_at_monitor_index: Sequence[Optional[float]],
    config: dict,
) -> S2RSignal:
    """Evaluates exactly one calendar day. `atr_at_monitor_index[i]` must be the ATR
    value already computed (via wilder_atr over the FULL prior history, not reset per
    day) aligned to `monitor_candles[i]` -- this function performs no ATR computation
    itself, only consumes what the caller already computed causally."""
    all_day_candles = list(reference_candles) + list(monitor_candles)
    if not all_day_candles:
        return S2RSignal(REASON_SESSION_INCOMPLETE, None, None)

    last_time = _parse_time(all_day_candles[-1]).isoformat()

    for c in all_day_candles:
        if not _is_valid_ohlc(c):
            return S2RSignal(REASON_INVALID_DATA, _parse_time(c).isoformat(), last_time)

    min_ref = int(config["reference_session"]["min_reference_candles"])
    reference_high, reference_low, complete = calculate_reference_range(reference_candles, min_ref)
    if not complete:
        return S2RSignal(REASON_SESSION_INCOMPLETE, None, last_time)

    if not monitor_candles:
        return S2RSignal(REASON_NO_BREAKOUT, None, last_time, reference_high=reference_high, reference_low=reference_low)

    # First breakout candle only (documented simplification -- see spec's
    # `breakout.require_close_outside_reference` note).
    breakout_index = None
    direction = None
    for i, c in enumerate(monitor_candles):
        d = detect_breakout(c, reference_high, reference_low)
        if d is not None:
            breakout_index, direction = i, d
            break

    if breakout_index is None:
        return S2RSignal(
            REASON_NO_BREAKOUT, _parse_time(monitor_candles[-1]).isoformat(), last_time,
            reference_high=reference_high, reference_low=reference_low,
        )

    breakout_candle = monitor_candles[breakout_index]
    breakout_time = _parse_time(breakout_candle).isoformat()
    atr_multiple = float(config["displacement"]["atr_multiple"])
    atr = atr_at_monitor_index[breakout_index]

    if not detect_displacement(breakout_candle, atr, direction, atr_multiple):
        return S2RSignal(
            REASON_WEAK_DISPLACEMENT, breakout_time, last_time,
            direction=direction, reference_high=reference_high, reference_low=reference_low,
            atr=atr, breakout_price=float(breakout_candle["close"]),
        )

    breakout_level = reference_high if direction == "LONG" else reference_low
    body = abs(float(breakout_candle["close"]) - float(breakout_candle["open"]))

    retest_cfg = config["retest"]
    max_bars = int(retest_cfg["max_bars"])
    tolerance_atr = float(retest_cfg["tolerance_atr"])
    after_breakout = monitor_candles[breakout_index + 1:]
    atr_after_breakout = atr_at_monitor_index[breakout_index + 1:]

    retest_offset = detect_retest(after_breakout, breakout_level, atr, tolerance_atr, max_bars)
    if retest_offset is None:
        return S2RSignal(
            REASON_NO_RETEST, breakout_time, last_time,
            direction=direction, reference_high=reference_high, reference_low=reference_low,
            atr=atr, breakout_price=float(breakout_candle["close"]), breakout_level=breakout_level,
            displacement_body=body,
        )

    retest_candle = after_breakout[retest_offset]
    retest_time = _parse_time(retest_candle).isoformat()
    from_retest = after_breakout[retest_offset:]
    remaining_budget = max_bars - retest_offset
    confirmation_offset = detect_confirmation(from_retest, direction, breakout_level, remaining_budget)

    if confirmation_offset is None:
        return S2RSignal(
            REASON_CONFIRMATION_FAILED, retest_time, last_time,
            direction=direction, reference_high=reference_high, reference_low=reference_low,
            atr=atr, breakout_price=float(breakout_candle["close"]), breakout_level=breakout_level,
            displacement_body=body, retest_price=float(retest_candle["close"]),
        )

    confirmation_candle = from_retest[confirmation_offset]
    confirmation_time = _parse_time(confirmation_candle).isoformat()
    entry = calculate_entry(confirmation_candle)
    stop = calculate_stop(breakout_level, atr, float(config["stop"]["buffer_atr"]), direction)
    target = calculate_target(entry, stop, float(config["target"]["rr"]))
    risk_distance = abs(entry - stop)

    reason = REASON_READY_LONG if direction == "LONG" else REASON_READY_SHORT
    return S2RSignal(
        reason, confirmation_time, last_time,
        direction=direction, reference_high=reference_high, reference_low=reference_low,
        atr=atr, breakout_price=float(breakout_candle["close"]), breakout_level=breakout_level,
        displacement_body=body, retest_price=float(retest_candle["close"]),
        entry=entry, stop=stop, target=target, risk_distance=risk_distance,
    )


def _group_by_utc_date(candles: Sequence[Candle]) -> Dict[str, List[Candle]]:
    groups: Dict[str, List[Candle]] = {}
    for c in candles:
        date_key = str(c["time"])[:10]
        groups.setdefault(date_key, []).append(c)
    return groups


def run_s2r_over_history(candles: Sequence[Candle], config: dict) -> List[S2RSignal]:
    """Orchestrates evaluate_s2r_day() across every UTC calendar day present in
    `candles`. `candles` must be sorted chronologically and cover complete calendar
    days for reliable results (partial boundary days will report SESSION_INCOMPLETE
    or NO_BREAKOUT honestly, never fabricated). ATR is computed ONCE over the full
    supplied history (wilder_atr, reused verbatim, no lookahead: ATR at index i only
    ever uses candles[0..i])."""
    candles = list(candles)
    atr_period = int(config["atr"]["period"])
    raw_atr_series = wilder_atr(candles, period=atr_period)
    # Shift by one bar: "ATR available as of the close of the PREVIOUS bar" -- the
    # causally correct baseline against which the CURRENT bar's own range/body is
    # judged for displacement. Wilder ATR[i] as computed by wilder_atr() already
    # incorporates bar i's own true range into its value, which would make an
    # "is bar i unusually large vs ATR[i]" comparison self-referential (a huge bar
    # inflates the very ATR it is being compared against). No lookahead either way:
    # both ATR[i-1] and ATR[i] use only candles[0..i], but ATR[i-1] is the strictly
    # correct "prior volatility" baseline for expansion/displacement detection.
    atr_series: List[Optional[float]] = [None] + list(raw_atr_series[:-1])

    by_date = _group_by_utc_date(candles)
    signals: List[S2RSignal] = []

    ref_start = str(config["reference_session"]["start_time_utc"])
    ref_end = str(config["reference_session"]["end_time_utc"])
    mon_start = str(config["monitoring_window"]["start_time_utc"])

    index_of: Dict[int, int] = {id(c): i for i, c in enumerate(candles)}

    for date_key in sorted(by_date):
        day_candles = by_date[date_key]
        reference_candles = [c for c in day_candles if ref_start <= str(c["time"])[11:16] < ref_end]
        monitor_candles = [c for c in day_candles if str(c["time"])[11:16] >= mon_start]

        monitor_atrs = [atr_series[index_of[id(c)]] for c in monitor_candles]
        signals.append(evaluate_s2r_day(reference_candles, monitor_candles, monitor_atrs, config))

    return signals
