"""AG_OUTCOME_RESOLUTION_CONTRACT_V2 resolver (config/governance/AG_OUTCOME_RESOLUTION_CONTRACT_V2.yaml).

Pure: no I/O, no MT5, no clock. The caller supplies one Opportunity and the M1 bars.

The central invariant is position_exists(t) = False for t < fill. Only M1 bars whose open
time is >= the fill timestamp (the close of the M15 sweep candle) are ever examined, so
the sweep candle's own wick cannot resolve a position that does not exist yet. This is
the defect the V1 resolver has: it starts at the sweep candle's open.

Every rule here is fixed by the frozen contract. Nothing here is tunable.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from strategy_engine.session import Candle

CONTRACT_ID = "AG_OUTCOME_RESOLUTION_CONTRACT_V2"
CANDIDATE_VERSION = "1.2.0-CANDIDATE"

TP1_VOLUME = 0.75
TP2_VOLUME = 0.25
TP2_R = 5.0
SPREAD_PIPS = 2.0
SLIPPAGE_PIPS = 1.0
COMMISSION_STATUS = "UNVERIFIED_NO_SIGNED_COMMISSION_RATE"
PIP_SIZE = 0.0001

M1 = dt.timedelta(minutes=1)
M15 = dt.timedelta(minutes=15)

RESOLVED_SL = "RESOLVED_SL"
RESOLVED_TP1_BE = "RESOLVED_TP1_BE"
RESOLVED_TP1_TP2 = "RESOLVED_TP1_TP2"
RESOLVED_SESSION_EXIT = "RESOLVED_SESSION_EXIT"
AMBIGUOUS_SAME_BAR = "AMBIGUOUS_SAME_BAR"
UNRESOLVED_MISSING_M1 = "UNRESOLVED_MISSING_M1"
EXCLUDED_NO_POST_FILL_WINDOW = "EXCLUDED_NO_POST_FILL_WINDOW"
EXCLUDED_INVALID_RISK = "EXCLUDED_INVALID_RISK"
EXCLUDED_TP1_NOT_BEYOND_ENTRY = "EXCLUDED_TP1_NOT_BEYOND_ENTRY"

RESOLVED_STATES = frozenset({RESOLVED_SL, RESOLVED_TP1_BE, RESOLVED_TP1_TP2, RESOLVED_SESSION_EXIT})


@dataclass(frozen=True)
class OpportunityInput:
    opportunity_id: str
    cycle: str
    trading_date: dt.date
    direction: str              # LONG | SHORT
    sweep_open_time: dt.datetime  # TradeSignal.signal_timestamp (M15 bar open, UTC)
    sweep_close: float          # the entry price (close of the sweep candle)
    stop: float                 # sweep wick extreme == TradeSignal.stop_loss
    box_high: float
    box_low: float
    session_cutoff: dt.datetime
    engine_entry: Optional[float] = None  # recorded V1.1.1 divergence only; never used


@dataclass
class OutcomeV2:
    opportunity_id: str
    cycle: str
    trading_date: str
    direction: str
    state: str
    entry_fill_time: str
    entry: float
    stop: float
    tp1: float
    tp2: Optional[float]
    risk_distance: float
    tp1_R: Optional[float] = None
    gross_R: Optional[float] = None
    friction_R: Optional[float] = None
    net_R: Optional[float] = None
    mfe_R: Optional[float] = None
    mae_R: Optional[float] = None
    exit_time: Optional[str] = None
    holding_minutes: Optional[float] = None
    engine_entry: Optional[float] = None
    events: List[dict] = field(default_factory=list)
    note: Optional[str] = None


def resolve_v2(opp: OpportunityInput, m1_bars: Sequence[Candle]) -> OutcomeV2:
    long = opp.direction == "LONG"
    if opp.direction not in ("LONG", "SHORT"):
        raise ValueError(f"invalid direction {opp.direction!r}")
    fill = opp.sweep_open_time + M15
    entry, stop = opp.sweep_close, opp.stop
    risk = (entry - stop) if long else (stop - entry)
    tp1 = opp.box_high if long else opp.box_low
    tp2 = (entry + TP2_R * risk) if long else (entry - TP2_R * risk)
    out = OutcomeV2(
        opportunity_id=opp.opportunity_id, cycle=opp.cycle, trading_date=opp.trading_date.isoformat(),
        direction=opp.direction, state="", entry_fill_time=fill.isoformat(), entry=entry, stop=stop,
        tp1=tp1, tp2=tp2 if risk > 0 else None, risk_distance=risk, engine_entry=opp.engine_entry,
    )

    if fill >= opp.session_cutoff:
        out.state = EXCLUDED_NO_POST_FILL_WINDOW
        return out
    if not risk > 0:
        out.state = EXCLUDED_INVALID_RISK
        return out
    if (long and tp1 <= entry) or (not long and tp1 >= entry):
        out.state = EXCLUDED_TP1_NOT_BEYOND_ENTRY
        return out
    out.tp1_R = abs(tp1 - entry) / risk

    # Post-fill eligibility: nothing opening before the fill can participate.
    bars = sorted((b for b in m1_bars if fill <= b.time < opp.session_cutoff), key=lambda b: b.time)
    expected = int((opp.session_cutoff - fill) / M1)
    if len(bars) != expected or len({b.time for b in bars}) != expected:
        out.state = UNRESOLVED_MISSING_M1
        out.note = f"expected {expected} M1 bars after fill, got {len(bars)}"
        return out

    def r_of(price: float) -> float:
        return ((price - entry) if long else (entry - price)) / risk

    best = worst = 0.0

    def track(b: Candle) -> None:
        nonlocal best, worst
        best = max(best, r_of(b.high if long else b.low))
        worst = min(worst, r_of(b.low if long else b.high))

    def finish(state: str, gross: Optional[float], exit_bar: Optional[Candle], exit_at: Optional[dt.datetime]):
        out.state = state
        out.mfe_R, out.mae_R = best, worst
        if gross is not None:
            out.gross_R = gross
            out.friction_R = (SPREAD_PIPS + SLIPPAGE_PIPS) * PIP_SIZE / risk
            out.net_R = gross - out.friction_R
        if exit_at is not None:
            out.exit_time = exit_at.isoformat()
            out.holding_minutes = (exit_at - fill).total_seconds() / 60.0
        return out

    # Phase 1: full position, SL vs TP1.
    tp1_idx = None
    for i, b in enumerate(bars):
        track(b)
        sl_hit = b.low <= stop if long else b.high >= stop
        tp1_hit = b.high >= tp1 if long else b.low <= tp1
        if sl_hit and tp1_hit:
            out.events.append({"time": b.time.isoformat(), "event": "SL_AND_TP1_SAME_BAR"})
            return finish(AMBIGUOUS_SAME_BAR, None, b, None)
        if sl_hit:
            out.events.append({"time": b.time.isoformat(), "event": "SL"})
            return finish(RESOLVED_SL, -1.0, b, b.time + M1)
        if tp1_hit:
            out.events.append({"time": b.time.isoformat(), "event": "TP1"})
            tp1_idx = i
            break

    if tp1_idx is None:
        last = bars[-1]
        out.events.append({"time": last.time.isoformat(), "event": "SESSION_EXIT_FULL", "price": last.close})
        return finish(RESOLVED_SESSION_EXIT, r_of(last.close), last, opp.session_cutoff)

    # Phase 2: 25% runner, stop at entry armed from the bar AFTER the TP1 bar.
    banked = TP1_VOLUME * out.tp1_R
    for b in bars[tp1_idx + 1:]:
        track(b)
        be_hit = b.low <= entry if long else b.high >= entry
        tp2_hit = b.high >= tp2 if long else b.low <= tp2
        if be_hit and tp2_hit:
            out.events.append({"time": b.time.isoformat(), "event": "BE_AND_TP2_SAME_BAR"})
            return finish(AMBIGUOUS_SAME_BAR, None, b, None)
        if be_hit:
            out.events.append({"time": b.time.isoformat(), "event": "RUNNER_BE"})
            return finish(RESOLVED_TP1_BE, banked, b, b.time + M1)
        if tp2_hit:
            out.events.append({"time": b.time.isoformat(), "event": "RUNNER_TP2"})
            return finish(RESOLVED_TP1_TP2, banked + TP2_VOLUME * TP2_R, b, b.time + M1)

    last = bars[-1]
    out.events.append({"time": last.time.isoformat(), "event": "SESSION_EXIT_RUNNER", "price": last.close})
    return finish(RESOLVED_SESSION_EXIT, banked + TP2_VOLUME * r_of(last.close), last, opp.session_cutoff)
