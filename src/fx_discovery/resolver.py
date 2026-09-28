"""Generic V2-style outcome resolver for FX discovery plans (single stop, single target, time exit).

Rules come from config/research/FX_DISCOVERY_V1_HYPOTHESIS_LEDGER.yaml `common_rules`. The
post-fill invariant holds: no base bar opening before the fill can resolve anything.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from strategy_engine.session import Candle

PIP = 0.0001
FRICTION_PIPS = 3.0

RESOLVED_SL, RESOLVED_TP, RESOLVED_TIME = "RESOLVED_SL", "RESOLVED_TP", "RESOLVED_TIME_EXIT"
AMBIGUOUS, UNRESOLVED, NOT_FILLED = "AMBIGUOUS_SAME_BAR", "UNRESOLVED_MISSING_DATA", "NOT_FILLED"
RESOLVED = frozenset({RESOLVED_SL, RESOLVED_TP, RESOLVED_TIME})


@dataclass(frozen=True)
class TradePlan:
    family: str
    trading_date: dt.date
    direction: str              # LONG | SHORT
    entry_type: str             # MARKET | LIMIT
    entry: float
    stop: float
    target: float
    decision_time: dt.datetime  # MARKET: the fill time. LIMIT: order activation.
    order_expiry: Optional[dt.datetime]
    time_exit: dt.datetime
    evidence: Dict = field(default_factory=dict)


@dataclass
class Outcome:
    family: str
    trading_date: str
    direction: str
    state: str
    entry: float
    stop: float
    target: float
    risk_distance: float
    fill_time: Optional[str] = None
    exit_time: Optional[str] = None
    gross_R: Optional[float] = None
    friction_R: Optional[float] = None
    net_R: Optional[float] = None
    mfe_R: Optional[float] = None
    mae_R: Optional[float] = None
    evidence: Dict = field(default_factory=dict)


def resolve(plan: TradePlan, base: Sequence[Candle], base_minutes: int) -> Outcome:
    long = plan.direction == "LONG"
    risk = (plan.entry - plan.stop) if long else (plan.stop - plan.entry)
    out = Outcome(plan.family, plan.trading_date.isoformat(), plan.direction, "", plan.entry, plan.stop,
                  plan.target, risk, evidence=dict(plan.evidence))
    if risk <= 0:
        raise ValueError("stop must be beyond entry")
    step = dt.timedelta(minutes=base_minutes)
    bars = sorted((b for b in base if plan.decision_time <= b.time < plan.time_exit), key=lambda b: b.time)
    if len(bars) != int((plan.time_exit - plan.decision_time) / step):
        out.state = UNRESOLVED
        return out

    def hit_sl(b):
        return b.low <= plan.stop if long else b.high >= plan.stop

    def hit_tp(b):
        return b.high >= plan.target if long else b.low <= plan.target

    i = 0
    if plan.entry_type == "LIMIT":
        filled = None
        for i, b in enumerate(bars):
            if plan.order_expiry is not None and b.time >= plan.order_expiry:
                break
            touch = b.low <= plan.entry if long else b.high >= plan.entry
            if touch:
                if hit_sl(b) or hit_tp(b):
                    out.state, out.fill_time = AMBIGUOUS, b.time.isoformat()
                    return out
                filled = i
                break
        if filled is None:
            out.state = NOT_FILLED
            return out
        out.fill_time = bars[filled].time.isoformat()
        i = filled + 1
    else:
        out.fill_time = plan.decision_time.isoformat()

    r = (lambda p: (p - plan.entry) / risk) if long else (lambda p: (plan.entry - p) / risk)
    best = worst = 0.0

    def done(state, gross, exit_at):
        out.state, out.mfe_R, out.mae_R = state, best, worst
        out.gross_R = gross
        out.friction_R = FRICTION_PIPS * PIP / risk
        out.net_R = gross - out.friction_R
        out.exit_time = exit_at.isoformat()
        return out

    for b in bars[i:]:
        best = max(best, r(b.high if long else b.low))
        worst = min(worst, r(b.low if long else b.high))
        sl, tp = hit_sl(b), hit_tp(b)
        if sl and tp:
            out.state, out.mfe_R, out.mae_R = AMBIGUOUS, best, worst
            return out
        if sl:
            return done(RESOLVED_SL, -1.0, b.time + step)
        if tp:
            return done(RESOLVED_TP, r(plan.target), b.time + step)
    if i >= len(bars):
        out.state = UNRESOLVED   # filled on the last bar before the time exit; nothing left to observe
        return out
    return done(RESOLVED_TIME, r(bars[-1].close), plan.time_exit)
