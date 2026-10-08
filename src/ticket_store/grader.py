"""Read-only-fixture-friendly M1 first-touch grading for TICKET_STORE_V1 records."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ticket_store.store import LIVE, REPLAY, TicketStore, build_outcome

UTC = dt.timezone.utc
OUTCOME_KIND = "FIRST_TOUCH_M1_V1"
COUNTERFACTUAL_KIND = "COUNTERFACTUAL_M1_V1"


@dataclass(frozen=True)
class Bar:
    time: dt.datetime
    open: float
    high: float
    low: float
    close: float


def _time(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        v = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if v.tzinfo is None:
        return None
    return v.astimezone(UTC)


def load_m1_csv(path: str | Path) -> List[Bar]:
    bars = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            time = _time(row.get("time"))
            try:
                o, h, lo, c = (float(row[k]) for k in ("open", "high", "low", "close"))
            except (TypeError, ValueError, KeyError) as exc:
                raise ValueError(f"{path}: invalid OHLC row") from exc
            if time is None or not all(math.isfinite(x) for x in (o, h, lo, c)) or h < max(o, lo, c) or lo > min(o, h, c):
                raise ValueError(f"{path}: invalid time/OHLC row")
            bars.append(Bar(time, o, h, lo, c))
    bars.sort(key=lambda b: b.time)
    if len({b.time for b in bars}) != len(bars):
        raise ValueError(f"{path}: duplicate M1 timestamps")
    return bars


def _expiry(record: Dict[str, Any], minutes: int) -> Optional[dt.datetime]:
    raw_prov = record.get("provenance")
    prov = raw_prov if isinstance(raw_prov, dict) else {}
    for key in ("expires_at_utc", "valid_until_utc", "expires_at", "valid_until"):
        if prov.get(key):
            return _time(prov[key])
    signal_raw = record.get("signal_close_utc")
    signal = _time(signal_raw) if signal_raw else _time(record.get("evaluated_at_utc"))
    return signal + dt.timedelta(minutes=minutes) if signal else None


def _level_values(record: Dict[str, Any]) -> Dict[str, Any]:
    try:
        entry, sl = float(record["entry"]), float(record["sl"])
        tp1 = float(record["tp1"]) if record.get("tp1") is not None else None
        tp2 = float(record["tp2"]) if record.get("tp2") is not None else None
    except (KeyError, TypeError, ValueError):
        return {}
    direction = record.get("direction")
    if direction not in ("LONG", "SHORT") or not all(math.isfinite(x) for x in (entry, sl)):
        return {}
    risk = abs(entry - sl)
    sign = 1 if direction == "LONG" else -1
    if risk <= 0 or sign * (entry - sl) <= 0:
        return {}
    if tp1 is not None and (not math.isfinite(tp1) or sign * (tp1 - entry) <= 0):
        return {}
    if tp2 is not None and (not math.isfinite(tp2) or sign * (tp2 - entry) <= 0):
        return {}
    return {"entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2, "risk": risk, "sign": sign}


def _touches_entry(bar: Bar, entry: float, sign: int) -> bool:
    return bar.low <= entry <= bar.high or (sign == 1 and bar.open <= entry) or (sign == -1 and bar.open >= entry)


def _spread_flags(record: Dict[str, Any]) -> tuple[list[str], Optional[float]]:
    signal = _time(record.get("signal_close_utc"))
    measured = _time(record.get("spread_measured_at_utc"))
    strategy_id = str(record.get("strategy") or "").split("@", 1)[0]
    trigger_minutes = {"ST_ASIAN_SWEEP_5R_V1": 15, "ST_LIQUIDITY_SWEEP_RETEST_V1": 5}.get(strategy_id)
    if signal is None or measured is None or trigger_minutes is None:
        return [], None
    seconds = abs((measured - signal).total_seconds())
    return (["SPREAD_TIMING_GAP"] if seconds > trigger_minutes * 60 else []), seconds


def grade_record(record: Dict[str, Any], bars: Sequence[Bar], *, expiry_minutes: int = 15) -> Dict[str, Any]:
    """Grade fills and first touches using closed M1 bars; no fill by expiry is EXPIRED.

    Tickets are considered active from signal close (inclusive) until expiry (exclusive).
    The whole fill bar participates in excursion/exit checks because M1 cannot order events
    inside that bar. If SL and either target touch in one bar, result is AMBIGUOUS and the
    reported grade is the conservative SL outcome.
    """
    levels = _level_values(record)
    start = _time(record.get("signal_close_utc")) or _time(record.get("evaluated_at_utc"))
    expiry = _expiry(record, expiry_minutes)
    flags, spread_delta = _spread_flags(record)
    common = {"ticket_id": record.get("ticket_id"), "evaluation_id": record.get("evaluation_id"),
              "strategy": record.get("strategy"), "symbol": record.get("symbol"), "session": record.get("session"),
              "state": record.get("state"), "block_reasons": list(record.get("block_reasons") or []),
              "flags": flags, "spread_timing_delta_seconds": spread_delta}
    if not levels:
        return {**common, "result": "NOT_RESOLVABLE", "reason": "MISSING_OR_INVALID_LEVELS", "net_R": None}
    if start is None or expiry is None or expiry <= start:
        return {**common, "result": "NOT_RESOLVABLE", "reason": "MISSING_OR_INVALID_EXPIRY", "net_R": None}
    ordered = sorted(bars, key=lambda b: b.time)
    window = [b for b in ordered if start <= b.time < expiry]
    if not window or window[0].time > start + dt.timedelta(minutes=1):
        return {**common, "result": "DATA_INSUFFICIENT", "reason": "NO_M1_BARS_AT_SIGNAL", "net_R": None}
    if any(b.time - a.time > dt.timedelta(minutes=1) for a, b in zip(window, window[1:])):
        return {**common, "result": "DATA_INSUFFICIENT", "reason": "M1_GAP_IN_ENTRY_WINDOW", "net_R": None}
    fill = next((b for b in window if _touches_entry(b, levels["entry"], levels["sign"])), None)
    if fill is None:
        if window[-1].time + dt.timedelta(minutes=1) < expiry:
            return {**common, "result": "DATA_INSUFFICIENT", "reason": "M1_HISTORY_ENDS_BEFORE_EXPIRY", "net_R": None}
        return {**common, "result": "EXPIRED", "grade": "EXPIRED", "fill_time_utc": None,
                "outcome_time_utc": expiry.isoformat(), "minutes_to_outcome": max(0, int((expiry - start).total_seconds() // 60)),
                "gross_R": None, "net_R": None, "spread_cost_R": None, "mfe_R": None, "mae_R": None}

    sign, entry, sl, risk = levels["sign"], levels["entry"], levels["sl"], levels["risk"]
    spread = record.get("spread_at_signal")
    try:
        spread_value = float(spread) if spread is not None else None
        spread_cost = max(0.0, spread_value) / risk if spread_value is not None and math.isfinite(spread_value) else None
    except (TypeError, ValueError):
        spread_cost = None
    mfe = mae = 0.0
    # Expiry only governs whether the pending entry filled. A filled position remains
    # eligible for later SL/TP touches in the supplied history.
    bars_after_fill = [b for b in ordered if b.time >= fill.time]
    for previous, bar in zip(bars_after_fill, bars_after_fill[1:]):
        if bar.time - previous.time > dt.timedelta(minutes=1):
            return {**common, "result": "DATA_INSUFFICIENT", "reason": "M1_GAP_AFTER_FILL",
                    "fill_time_utc": fill.time.isoformat(), "mfe_R": round(mfe, 6),
                    "mae_R": round(mae, 6), "net_R": None}
    for bar in bars_after_fill:
        fav = (bar.high - entry) * sign / risk
        adv = (entry - bar.low) * sign / risk
        mfe, mae = max(mfe, fav), max(mae, adv)
        hit_sl = bar.low <= sl if sign > 0 else bar.high >= sl
        hit_tp1 = levels["tp1"] is not None and (bar.high >= levels["tp1"] if sign > 0 else bar.low <= levels["tp1"])
        hit_tp2 = levels["tp2"] is not None and (bar.high >= levels["tp2"] if sign > 0 else bar.low <= levels["tp2"])
        target = "TP2" if hit_tp2 and not hit_tp1 else "TP1" if hit_tp1 else None
        if hit_sl and (hit_tp1 or hit_tp2):
            result, grade, gross = "AMBIGUOUS", "SL", -1.0
        elif hit_sl:
            result, grade, gross = "SL", "SL", -1.0
        elif target:
            result = grade = target
            gross = (levels[target.lower()] - entry) * sign / risk
        else:
            continue
        net = gross - spread_cost if spread_cost is not None else None
        mins = max(1, int((bar.time - fill.time).total_seconds() // 60) + 1)
        return {**common, "result": result, "grade": grade, "fill_time_utc": fill.time.isoformat(),
                "outcome_time_utc": (bar.time + dt.timedelta(minutes=1)).isoformat(), "minutes_to_outcome": mins,
                "gross_R": round(gross, 6), "net_R": round(net, 6) if net is not None else None,
                "spread_cost_R": round(spread_cost, 6) if spread_cost is not None else None,
                "mfe_R": round(mfe, 6), "mae_R": round(mae, 6)}

    return {**common, "result": "DATA_INSUFFICIENT", "reason": "OUTCOME_NOT_REACHED_IN_HISTORY",
            "fill_time_utc": fill.time.isoformat(), "mfe_R": round(mfe, 6), "mae_R": round(mae, 6), "net_R": None}


def cohort(record: Dict[str, Any]) -> Optional[str]:
    if record.get("state") in ("BLOCKED", "NO_TRADE") and _level_values(record):
        return "COUNTERFACTUAL"
    if record.get("state") in ("READY", "WATCH_READY") and _level_values(record):
        return "GRADED"
    return None


def replay(store: TicketStore, bars_by_symbol: Dict[str, Sequence[Bar]], start_date: dt.date, end_date: dt.date,
           *, expiry_minutes: int = 15, recorded_at: Optional[dt.datetime] = None) -> Dict[str, int]:
    """Append deterministic REPLAY grades for evaluations in [start_date, end_date]."""
    if end_date < start_date:
        raise ValueError("end date precedes start date")
    counts = {"evaluations_seen": 0, "graded": 0, "counterfactual": 0, "skipped": 0}
    selected: Dict[tuple, Dict[str, Any]] = {}
    rank = {"LEGACY": 0, LIVE: 1, REPLAY: 2}
    for rec in store.evaluations():
        day = (rec.get("evaluated_at_utc") or "")[:10]
        if not (start_date.isoformat() <= day <= end_date.isoformat()):
            continue
        key = (rec.get("strategy"), rec.get("symbol"), rec.get("session"), rec.get("evaluated_at_utc"))
        prior = selected.get(key)
        if prior is None or rank.get(rec.get("source"), -1) > rank.get(prior.get("source"), -1):
            selected[key] = rec
    for rec in selected.values():
        counts["evaluations_seen"] += 1
        kind = cohort(rec)
        if not kind:
            counts["skipped"] += 1
            continue
        bars = bars_by_symbol.get(rec.get("symbol"), ())
        payload = grade_record(rec, bars, expiry_minutes=expiry_minutes)
        payload["cohort"] = kind
        payload["evaluator"] = "AGP_GRADE_01"
        if payload.get("result") in ("DATA_INSUFFICIENT", "NOT_RESOLVABLE"):
            counts["skipped"] += 1
            continue
        # Recorded time is deterministic so rerunning the same pinned history is a no-op.
        outcome_time = _time(payload.get("outcome_time_utc"))
        stamp = outcome_time or _time(rec.get("evaluated_at_utc")) or recorded_at or dt.datetime.now(UTC)
        outcome = build_outcome(ticket_id=rec.get("ticket_id") or rec["evaluation_id"], source=REPLAY,
                                outcome_kind=COUNTERFACTUAL_KIND if kind == "COUNTERFACTUAL" else OUTCOME_KIND,
                                recorded_at_utc=stamp.isoformat(), result=payload.get("result"), payload=payload,
                                provenance={"evaluation_id": rec["evaluation_id"], "input_bar_sha256": _bar_sha(bars)})
        # Refuse replay drift. One ticket/cohort has one immutable grade per REPLAY source.
        existing = [o for o in store.outcomes(outcome["ticket_id"])
                    if o.get("source") == REPLAY and o.get("outcome_kind") == outcome["outcome_kind"]]
        if existing:
            if any(o.get("record_sha256") == outcome["record_sha256"] for o in existing):
                continue
            raise ValueError(f"existing immutable replay grade differs for {outcome['ticket_id']}")
        store.append_outcome(outcome)
        counts["counterfactual" if kind == "COUNTERFACTUAL" else "graded"] += 1
    return counts


def _bar_sha(bars: Sequence[Bar]) -> Optional[str]:
    if not bars:
        return None
    rows = [[b.time.isoformat(), b.open, b.high, b.low, b.close] for b in bars]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _quantile(values: Sequence[float], q: float) -> Optional[float]:
    if not values:
        return None
    data = sorted(values)
    pos = (len(data) - 1) * q
    low = int(pos)
    high = min(low + 1, len(data) - 1)
    return round(data[low] + (data[high] - data[low]) * (pos - low), 6)


def make_report(store: TicketStore) -> Dict[str, Any]:
    evaluations = store.evaluations()
    outcomes = store.outcomes()
    groups: Dict[tuple, Dict[str, Any]] = {}
    for rec in evaluations:
        key = (rec.get("strategy"), rec.get("symbol"), rec.get("session"))
        g = groups.setdefault(key, {"counts_by_state": {}, "block_reason_histogram": {}, "evaluations": 0})
        g["evaluations"] += 1
        state = str(rec.get("state"))
        g["counts_by_state"][state] = g["counts_by_state"].get(state, 0) + 1
        for reason in rec.get("block_reasons") or []:
            g["block_reason_histogram"][reason] = g["block_reason_histogram"].get(reason, 0) + 1
    for key, g in groups.items():
        relevant = [o for o in outcomes if o.get("payload", {}).get("strategy") == key[0]
                    and o.get("payload", {}).get("symbol") == key[1]
                    and o.get("payload", {}).get("session") == key[2]
                    and o.get("source") == REPLAY]
        actual = [o for o in relevant if o.get("outcome_kind") == OUTCOME_KIND]
        cf = [o for o in relevant if o.get("outcome_kind") == COUNTERFACTUAL_KIND]
        rs = [o["payload"]["net_R"] for o in actual if o.get("payload", {}).get("net_R") is not None]
        wins = sum(o.get("payload", {}).get("grade") in ("TP1", "TP2") for o in actual)
        g["n"] = len(rs)
        g["expectancy_R"] = round(sum(rs) / len(rs), 6) if rs else None
        g["win_pct"] = round(100 * wins / len(rs), 4) if rs else None
        g["mfe_R_quantiles"] = {str(q): _quantile([o["payload"]["mfe_R"] for o in actual if o.get("payload", {}).get("mfe_R") is not None], q)
                                 for q in (0.1, 0.5, 0.9)}
        g["mae_R_quantiles"] = {str(q): _quantile([o["payload"]["mae_R"] for o in actual if o.get("payload", {}).get("mae_R") is not None], q)
                                 for q in (0.1, 0.5, 0.9)}
        g["counterfactual_R_by_block_reason"] = {}
        for reason in sorted(g["block_reason_histogram"]):
            these = [o["payload"]["net_R"] for o in cf if reason in o.get("payload", {}).get("block_reasons", [])
                     and o.get("payload", {}).get("net_R") is not None]
            g["counterfactual_R_by_block_reason"][reason] = {"n": len(these),
                "expectancy_R": round(sum(these) / len(these), 6) if these else None}
        g["flag"] = "DIRECTIONAL_ONLY" if len(rs) < 100 else None
        g["outcome_flags"] = {"SPREAD_TIMING_GAP": sum("SPREAD_TIMING_GAP" in o.get("payload", {}).get("flags", []) for o in actual + cf)}
    return {"schema": "AGP_GRADE_REPORT_V1", "groups": [
        {"strategy": k[0], "symbol": k[1], "session": k[2], **v}
        for k, v in sorted(groups.items(), key=lambda item: tuple(str(v) for v in item[0]))],
        "replay_parity": replay_parity(evaluations)}


def replay_parity(evaluations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Compare LIVE and REPLAY bar hashes for the same strategy/symbol/session/time identity."""
    paired: Dict[tuple, Dict[str, Dict[str, Any]]] = {}
    for rec in evaluations:
        if rec.get("source") not in (LIVE, REPLAY):
            continue
        key = (rec.get("strategy"), rec.get("symbol"), rec.get("session"), rec.get("evaluated_at_utc"))
        paired.setdefault(key, {})[rec["source"]] = rec
    rows = []
    for key, pair in sorted(paired.items(), key=lambda kv: tuple(str(v) for v in kv[0])):
        if LIVE not in pair or REPLAY not in pair:
            continue
        live_hashes, replay_hashes = pair[LIVE].get("input_bar_hashes"), pair[REPLAY].get("input_bar_hashes")
        match = live_hashes is not None and replay_hashes is not None and live_hashes == replay_hashes
        rows.append({"strategy": key[0], "symbol": key[1], "session": key[2], "evaluated_at_utc": key[3],
                     "status": "BAR_HASH_MATCH" if match else "BAR_HASH_MISMATCH",
                     "live_input_bar_hashes": live_hashes, "replay_input_bar_hashes": replay_hashes})
    return rows


def resolve_day(store: TicketStore, day: dt.date, bars_by_symbol: Dict[str, Sequence[Bar]],
                *, expiry_minutes: int = 15) -> Dict[str, int]:
    """Accepted store-native day resolver; appends immutable REPLAY OUTCOME records."""
    return replay(store, bars_by_symbol, day, day, expiry_minutes=expiry_minutes)
