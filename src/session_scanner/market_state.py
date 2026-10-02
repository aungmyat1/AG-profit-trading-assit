"""Deterministic multi-timeframe market state (D1 / H1 / M15 / M5).

Every field is either (a) computed by an existing project authority (structure via
market_structure.smc_adapter, the same library path analyze_structure() uses), or
(b) a plainly-labeled DESCRIPTIVE calculation. None of it is decision-bearing: the
strategy engine alone decides SIGNAL / NO_TRADE.

Liquidity events use the strategy engine's own strict-penetration predicate
(strategy_engine.session.setups.entry_2_sweep: high > level and close < level, mirrored for
lows; one candle breaching both sides is AMBIGUOUS). Levels the strategy contract does not
define a sweep rule for (previous-day high/low) are reported STRATEGY_CONTRACT_INCOMPLETE.
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from market_structure.models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED
from market_structure.smc_adapter import candles_to_dataframe, latest_swings_and_breaks
from strategy_engine.session import Candle

DESCRIPTIVE = "DESCRIPTIVE"
CONTRACT_INCOMPLETE = "STRATEGY_CONTRACT_INCOMPLETE"


def to_engine_candles(bars) -> List[Candle]:
    return [Candle(time=b.time_utc, open=b.open, high=b.high, low=b.low, close=b.close, volume=b.tick_volume)
            for b in bars]


def ema(values: Sequence[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def structure(bars, swing_length: int, close_break: bool) -> dict:
    """Same rule as market_structure.tiers: state follows the most recent BOS/CHOCH event."""
    if len(bars) < max(swing_length * 20, 100):
        return {"status": "INSUFFICIENT_STRUCTURE_HISTORY", "state": STATE_UNDEFINED}
    try:
        latest = latest_swings_and_breaks(candles_to_dataframe(to_engine_candles(bars)), swing_length, close_break)
    except Exception as exc:  # library errors are reported, never guessed around
        return {"status": f"STRUCTURE_ERROR:{type(exc).__name__}", "state": STATE_UNDEFINED}
    events = [p for p in (latest["latest_bos"], latest["latest_choch"]) if p is not None]
    state = STATE_UNDEFINED
    if events:
        last = max(events, key=lambda p: p.time_utc)
        state = STATE_BULLISH if "BULLISH" in last.kind.value else STATE_BEARISH
    pt = lambda p: {"price": p.price, "time_utc": p.time_utc.isoformat(), "kind": p.kind.value} if p else None  # noqa: E731
    return {"status": "VALID", "authority": "market_structure.smc_adapter", "state": state,
            "swing_high": pt(latest["latest_swing_high"]), "swing_low": pt(latest["latest_swing_low"]),
            "latest_bos": pt(latest["latest_bos"]), "latest_choch": pt(latest["latest_choch"])}


def sweep_events(bars, high: Optional[float], low: Optional[float], label: str) -> List[dict]:
    if high is None or low is None:
        return []
    out = []
    for b in bars:
        up = b.high > high and b.close < high
        dn = b.low < low and b.close > low
        if up and dn:
            out.append({"event": f"{label}_DUAL_SWEEP_AMBIGUOUS", "time_utc": b.time_utc.isoformat()})
        elif up:
            out.append({"event": f"{label}_HIGH_SWEEP", "time_utc": b.time_utc.isoformat(), "level": high,
                        "wick": b.high, "close": b.close})
        elif dn:
            out.append({"event": f"{label}_LOW_SWEEP", "time_utc": b.time_utc.isoformat(), "level": low,
                        "wick": b.low, "close": b.close})
    return out


def position_vs(price: float, high: Optional[float], low: Optional[float]) -> Optional[str]:
    if high is None or low is None:
        return None
    return "ABOVE" if price > high else "BELOW" if price < low else "INSIDE"


def d1_state(d1_closed, price: float, pip_size: float, pdh_pdl: dict) -> dict:
    if len(d1_closed) < 2:
        return {"status": "INSUFFICIENT"}
    last, prev = d1_closed[-1], d1_closed[-2]
    return {"label": DESCRIPTIVE, "basis": "broker server-day D1 bars",
            "last_closed_d1_utc": last.time_utc.isoformat(),
            "last_closed_direction": "UP_CLOSE" if last.close > last.open else "DOWN_CLOSE" if last.close < last.open else "FLAT",
            "close_vs_prior_close": "HIGHER" if last.close > prev.close else "LOWER" if last.close < prev.close else "EQUAL",
            "last_closed_range_pips": round((last.high - last.low) / pip_size, 1),
            "price_vs_last_closed_d1_range": position_vs(price, last.high, last.low),
            "previous_utc_day": pdh_pdl,
            "major_liquidity_reference": {"previous_day_high": pdh_pdl.get("high"),
                                          "previous_day_low": pdh_pdl.get("low")}}


def h1_state(h1_closed, ema_period: int, swing_length: int, close_break: bool) -> dict:
    closes = [b.close for b in h1_closed]
    e = ema(closes, ema_period)
    bias = None if e is None else "ABOVE_EMA" if closes[-1] > e else "BELOW_EMA" if closes[-1] < e else "AT_EMA"
    return {"structure": structure(h1_closed, swing_length, close_break),
            "ema_bias": {"label": DESCRIPTIVE, "indicator": f"EMA_{ema_period}", "ema": e,
                         "last_close": closes[-1] if closes else None, "state": bias},
            "premium_discount": CONTRACT_INCOMPLETE}


def m15_state(m15_closed, box: Optional[dict], post_bars, swing_length: int, close_break: bool) -> dict:
    last = m15_closed[-1] if m15_closed else None
    hi, lo = (box or {}).get("high"), (box or {}).get("low")
    breakout = None
    if last is not None and hi is not None:
        breakout = "CLOSED_ABOVE_BOX" if last.close > hi else "CLOSED_BELOW_BOX" if last.close < lo else "INSIDE_BOX"
    return {"structure": structure(m15_closed, swing_length, close_break),
            "reference_box": box, "last_closed_close": last.close if last else None,
            "breakout_state": {"label": DESCRIPTIVE, "state": breakout},
            "sweeps_since_reference_close": sweep_events(post_bars, hi, lo, "REFERENCE"),
            "displacement": CONTRACT_INCOMPLETE}


def m5_state(m5_closed, box: Optional[dict], window_start) -> dict:
    hi, lo = (box or {}).get("high"), (box or {}).get("low")
    in_window = [b for b in m5_closed if window_start is not None and b.time_utc >= window_start]
    last = m5_closed[-1] if m5_closed else None
    return {"label": "OBSERVATION_ONLY",
            "note": "ST_ASIAN_SWEEP_5R_V1 is an M15 contract; M5 is not decision-bearing",
            "last_closed_m5_utc": last.time_utc.isoformat() if last else None,
            "last_close_vs_box": position_vs(last.close, hi, lo) if last else None,
            "sweeps_in_trade_window": sweep_events(in_window, hi, lo, "REFERENCE"),
            "reclaim_break_retest": CONTRACT_INCOMPLETE}
