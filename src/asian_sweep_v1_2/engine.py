"""Frozen ST_ASIAN_SWEEP_5R_V1@1.2.0 pure production evaluator.

No broker imports, sizing, outcomes, or discretionary inputs. Candle timestamps are bar
open UTC; a M15 decision exists only at bar open + 15 minutes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import Optional, Sequence

VERSION = "1.2.0"
BAR = timedelta(minutes=15)
INSTRUMENTS = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "XAUUSD": 0.1}


@dataclass(frozen=True)
class Bar:
    time: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Decision:
    status: str
    reason: str
    symbol: str
    direction: Optional[str] = None
    decision_time: Optional[datetime] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    expiry: Optional[datetime] = None
    sweep_extreme: Optional[float] = None
    reference_high: Optional[float] = None
    reference_low: Optional[float] = None
    spread_distance: Optional[float] = None
    spread_pips: Optional[float] = None
    spread_R: Optional[float] = None

    def semantic(self) -> dict:
        return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(self).items()}

    def semantic_hash(self) -> str:
        raw = json.dumps(self.semantic(), sort_keys=True, separators=(",", ":"))
        return sha256(raw.encode()).hexdigest()


def evaluate(symbol: str, reference: Sequence[Bar], trade_bars: Sequence[Bar],
             *, spread_distance: Optional[float]) -> Decision:
    if symbol not in INSTRUMENTS:
        raise ValueError("UNSUPPORTED_INSTRUMENT")
    if not reference:
        return Decision("BLOCKED", "REFERENCE_NOT_READY", symbol)
    high, low = max(b.high for b in reference), min(b.low for b in reference)
    distance = (high - low) * 0.25
    if distance <= 0:
        return Decision("BLOCKED", "INVALID_REFERENCE_RANGE", symbol,
                        reference_high=high, reference_low=low)

    for candle in trade_bars:
        upper = candle.high > high and candle.close < high
        lower = candle.low < low and candle.close > low
        if not (upper or lower):
            continue
        at = candle.time + BAR
        common = dict(symbol=symbol, decision_time=at, expiry=at + BAR,
                      reference_high=high, reference_low=low, spread_distance=spread_distance)
        if upper and lower:
            return Decision("REJECTED", "AMBIGUOUS_DUAL_SWEEP", **common)
        direction = "LONG" if lower else "SHORT"
        entry = candle.close
        stop = entry - distance if lower else entry + distance
        tp1 = high if lower else low
        tp2 = entry + 5 * distance if lower else entry - 5 * distance
        extreme = candle.low if lower else candle.high
        values = dict(direction=direction, entry=entry, stop_loss=stop, tp1=tp1, tp2=tp2,
                      sweep_extreme=extreme, **common)
        if (lower and stop > extreme) or (upper and stop < extreme):
            return Decision("REJECTED", "SL_DOES_NOT_CLEAR_SWEEP_EXTREME", **values)
        ordered = stop < entry < tp1 <= tp2 if lower else stop > entry > tp1 >= tp2
        if not ordered:
            return Decision("REJECTED", "INVALID_TARGET_ORDER", **values)
        if spread_distance is None:
            return Decision("BLOCKED", "SPREAD_UNKNOWN", **values)
        spread_pips = spread_distance / INSTRUMENTS[symbol]
        spread_r = spread_distance / distance
        values.update(spread_pips=spread_pips, spread_R=spread_r)
        if spread_pips > 2.0:
            return Decision("REJECTED", "SPREAD_ABSOLUTE_EXCEEDED", **values)
        if spread_r > 0.15:
            return Decision("REJECTED", "SPREAD_R_EXCEEDED", **values)
        return Decision("ACTIONABLE", "PASS", **values)
    return Decision("AWAITING_TRIGGER", "AWAITING_TRIGGER", symbol,
                    reference_high=high, reference_low=low, spread_distance=spread_distance)


def actionable_at(decision: Decision, now: datetime) -> bool:
    return decision.status == "ACTIONABLE" and decision.decision_time <= now < decision.expiry


def stream(symbol: str, reference: Sequence[Bar], trade_bars: Sequence[Bar],
           *, spread_distance: Optional[float]) -> Decision:
    """One production path, fed one closed bar at a time; stop at first terminal decision."""
    current = evaluate(symbol, reference, (), spread_distance=spread_distance)
    for end in range(1, len(trade_bars) + 1):
        current = evaluate(symbol, reference, trade_bars[:end], spread_distance=spread_distance)
        if current.status not in ("AWAITING_TRIGGER",):
            break
    return current
