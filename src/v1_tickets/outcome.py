"""Manual Trade Ticket V1 Phase 7 -- outcome resolver for manual tickets (read-only data).

Resolves every manual ticket with order fields -- taken and shadow (skipped / missed /
expired / blocked) -- on closed M1/M5 bars after its time invalidation: first touch of TP1
vs SL vs expiry, MFE, MAE, gross R and net R after cost. A bar touching both TP1 and SL is
AMBIGUOUS (never guessed). Every result is tagged VIRTUAL_FORWARD: a reconstruction from
bars, never demo or live performance, never an executed trade. Raw proposal, owner decision
and virtual outcome are stored side by side; nothing here optimizes on them.
"""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Callable, Dict, List, Optional, Sequence

from v1_tickets.manual_ticket import ticket_path
from v1_tickets.owner_decision import _decision_version, load_decisions
from v1_tickets.scan_record import append_jsonl, read_jsonl

TAG = "VIRTUAL_FORWARD"
TP1, SL, EXPIRY, AMBIGUOUS = "TP1", "SL", "EXPIRY", "AMBIGUOUS"
NOT_RESOLVABLE, DATA_INSUFFICIENT = "NOT_RESOLVABLE", "DATA_INSUFFICIENT"
OUTCOME_DIR = os.path.join("ticket_delivery", "manual", "outcomes")


def _ts(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value).astimezone(dt.timezone.utc)


def resolve_levels(*, direction: str, entry: float, sl: float, tp1: float, start: dt.datetime, horizon: dt.datetime,
                   bars: Sequence[Any], tf: dt.timedelta, now: dt.datetime, cost_r: Optional[float]) -> Dict[str, Any]:
    """Pure first-touch resolution on closed bars whose open is in [start, horizon)."""
    risk = abs(entry - sl)
    if not risk > 0:
        return {"result": NOT_RESOLVABLE, "reason": "ZERO_STOP_DISTANCE"}
    sign = 1.0 if direction == "LONG" else -1.0
    window = sorted((b for b in bars if start <= b.time < horizon and b.time + tf <= now), key=lambda b: b.time)
    if not window or window[0].time > start + tf:
        return {"result": DATA_INSUFFICIENT, "reason": "NO_BARS_AT_START"}
    mfe = mae = 0.0
    for b in window:
        fav = ((b.high - entry) if sign > 0 else (entry - b.low)) / risk
        adv = ((entry - b.low) if sign > 0 else (b.high - entry)) / risk
        hit_tp = b.high >= tp1 if sign > 0 else b.low <= tp1
        hit_sl = b.low <= sl if sign > 0 else b.high >= sl
        if hit_tp and hit_sl:
            return {"result": AMBIGUOUS, "reason": "TP1_AND_SL_SAME_BAR", "bar": b.time.isoformat(),
                    "mfe_R": round(max(mfe, fav), 4), "mae_R": round(max(mae, adv), 4),
                    "gross_R": None, "net_R": None}
        mfe, mae = max(mfe, fav), max(mae, adv)
        if hit_tp or hit_sl:
            gross = sign * ((tp1 if hit_tp else sl) - entry) / risk
            return _done(TP1 if hit_tp else SL, b.time, gross, mfe, mae, cost_r)
    if window[-1].time + tf < horizon:
        return {"result": DATA_INSUFFICIENT, "reason": "BARS_END_BEFORE_HORIZON"}
    gross = sign * (window[-1].close - entry) / risk
    return _done(EXPIRY, window[-1].time, gross, mfe, mae, cost_r)


def _done(result: str, at: dt.datetime, gross: float, mfe: float, mae: float, cost_r: Optional[float]) -> Dict[str, Any]:
    return {"result": result, "bar": at.isoformat(), "mfe_R": round(mfe, 4), "mae_R": round(mae, 4),
            "gross_R": round(gross, 4), "net_R": round(gross - cost_r, 4) if cost_r is not None else None,
            "cost_R": cost_r}


def resolve_ticket(ticket: Dict[str, Any], decision: Optional[Dict[str, Any]], bars: Sequence[Any], *,
                   tf: dt.timedelta, now: dt.datetime) -> Dict[str, Any]:
    start = _ts(ticket["signal_close_utc"])
    horizon = _ts(ticket["invalid_if"]["time_invalidation_utc"])
    l5 = {c["id"]: c for c in ticket["logic_gate"]["L5"]["checks"]}
    cost = ticket.get("cost_in_R")                     # measured spread (+ commission when recorded)
    cost_basis = ("NOT_AVAILABLE" if cost is None else
                  "SPREAD_AND_COMMISSION" if l5["L5.commission_R"]["value"] is not None
                  else "SPREAD_ONLY_COMMISSION_NOT_AVAILABLE")
    record: Dict[str, Any] = {
        "tag": TAG, "executed_by_system": False, "is_demo_or_live_performance": False,
        "ticket_id": ticket["ticket_id"], "strategy": ticket["strategy"], "symbol": ticket["symbol"],
        "session": ticket["session"], "session_date": ticket["session_date"], "timeframe_minutes": int(tf.total_seconds() // 60),
        "raw_proposal": {k: ticket.get(k) for k in ("state", "stop_reason", "direction", "order_type", "entry", "sl",
                                                    "tp1", "tp2", "rr_tp1", "cost_in_R", "valid_until", "content_hash")},
        "owner_decision": decision,
        "virtual_outcome": resolve_levels(direction=ticket["direction"], entry=ticket["entry"], sl=ticket["sl"],
                                          tp1=ticket["tp1"], start=start, horizon=horizon, bars=bars, tf=tf,
                                          now=now, cost_r=cost),
        "cost_basis": cost_basis, "resolved_at": now.isoformat(),
    }
    if decision and decision.get("decision") == "TAKEN":
        fill = _ts(decision["fill_time"])
        record["owner_trade_outcome"] = resolve_levels(
            direction=ticket["direction"], entry=decision["actual_fill"], sl=decision["actual_sl"],
            tp1=decision["actual_tp"] if decision.get("actual_tp") is not None else ticket["tp1"],
            start=fill - dt.timedelta(seconds=fill.timestamp() % tf.total_seconds()),
            horizon=horizon, bars=bars, tf=tf, now=now, cost_r=cost)
        record["owner_trade_outcome"]["note"] = ("reconstructed from bars from the bar containing the owner's "
                                                 "recorded fill; not a broker record")
    return record


def outcome_path(journal: str, day: dt.date) -> str:
    return os.path.join(journal, OUTCOME_DIR, f"{day.isoformat()}.jsonl")


def resolve_day(journal: str, day: dt.date, fetch_bars: Callable[[str], Sequence[Any]], *, now: dt.datetime,
                tf: dt.timedelta = dt.timedelta(minutes=5)) -> Dict[str, Any]:
    """Append one outcome per ticket of `day` once it is resolvable; idempotent (resolved ids skipped)."""
    done = {o["ticket_id"] for o in read_jsonl(outcome_path(journal, day))}
    decisions = load_decisions(journal)
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for t in read_jsonl(ticket_path(journal, day)):
        grouped.setdefault(t["ticket_id"], []).append(t)
    summary = {"resolved": [], "pending": [], "skipped_no_levels": 0}
    bars_cache: Dict[str, Sequence[Any]] = {}
    for tid, rows in grouped.items():
        ticket = _decision_version(rows)
        if tid in done:
            continue
        if ticket.get("direction") is None or not ticket.get("signal_close_utc"):
            summary["skipped_no_levels"] += 1
            continue
        if now < _ts(ticket["invalid_if"]["time_invalidation_utc"]):
            summary["pending"].append((tid, "BEFORE_HORIZON"))
            continue
        if ticket["symbol"] not in bars_cache:
            bars_cache[ticket["symbol"]] = fetch_bars(ticket["symbol"])
        rec = resolve_ticket(ticket, decisions.get(tid), bars_cache[ticket["symbol"]], tf=tf, now=now)
        if rec["virtual_outcome"]["result"] == DATA_INSUFFICIENT:
            summary["pending"].append((tid, rec["virtual_outcome"]["reason"]))
            continue
        append_jsonl(outcome_path(journal, day), rec)
        summary["resolved"].append(tid)
    return summary
