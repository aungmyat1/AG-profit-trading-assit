"""Small independent evaluator transcribed from the frozen YAML/owner packet only.

It deliberately does not import or call the production evaluator. Output is a plain
mapping suitable for differential tests.
"""
from __future__ import annotations

from datetime import timedelta

PIPS = {"EURUSD": .0001, "GBPUSD": .0001, "USDJPY": .01, "XAUUSD": .1}


def reference_evaluate(symbol, reference, observations, spread_distance):
    if symbol not in PIPS:
        raise ValueError("UNSUPPORTED_INSTRUMENT")
    if not reference:
        return _out("BLOCKED", "REFERENCE_NOT_READY", symbol)
    ceiling = max(x.high for x in reference)
    floor = min(x.low for x in reference)
    quarter = (ceiling - floor) / 4
    if quarter <= 0:
        return _out("BLOCKED", "INVALID_REFERENCE_RANGE", symbol,
                    reference_high=ceiling, reference_low=floor)
    for bar in observations:
        down = bar.low < floor and bar.close > floor
        up = bar.high > ceiling and bar.close < ceiling
        if not down and not up:
            continue
        decided = bar.time + timedelta(minutes=15)
        shared = dict(decision_time=decided, expiry=decided + timedelta(minutes=15),
                      reference_high=ceiling, reference_low=floor, spread_distance=spread_distance)
        if down and up:
            return _out("REJECTED", "AMBIGUOUS_DUAL_SWEEP", symbol, **shared)
        side = "LONG" if down else "SHORT"
        price = bar.close
        stop = price - quarter if down else price + quarter
        first = ceiling if down else floor
        second = price + quarter * 5 if down else price - quarter * 5
        wick = bar.low if down else bar.high
        details = dict(direction=side, entry=price, stop_loss=stop, tp1=first, tp2=second,
                       sweep_extreme=wick, **shared)
        if (down and stop > wick) or (up and stop < wick):
            return _out("REJECTED", "SL_DOES_NOT_CLEAR_SWEEP_EXTREME", symbol, **details)
        if not ((stop < price < first <= second) if down else (stop > price > first >= second)):
            return _out("REJECTED", "INVALID_TARGET_ORDER", symbol, **details)
        if spread_distance is None:
            return _out("BLOCKED", "SPREAD_UNKNOWN", symbol, **details)
        pip_cost = spread_distance / PIPS[symbol]
        r_cost = spread_distance / quarter
        details.update(spread_pips=pip_cost, spread_R=r_cost)
        if pip_cost > 2:
            return _out("REJECTED", "SPREAD_ABSOLUTE_EXCEEDED", symbol, **details)
        if r_cost > .15:
            return _out("REJECTED", "SPREAD_R_EXCEEDED", symbol, **details)
        return _out("ACTIONABLE", "PASS", symbol, **details)
    return _out("AWAITING_TRIGGER", "AWAITING_TRIGGER", symbol,
                reference_high=ceiling, reference_low=floor, spread_distance=spread_distance)


def _out(status, reason, symbol, **fields):
    names = ("direction", "decision_time", "entry", "stop_loss", "tp1", "tp2", "expiry",
             "sweep_extreme", "reference_high", "reference_low", "spread_distance",
             "spread_pips", "spread_R")
    result = {"status": status, "reason": reason, "symbol": symbol}
    result.update({name: fields.get(name) for name in names})
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in result.items()}
