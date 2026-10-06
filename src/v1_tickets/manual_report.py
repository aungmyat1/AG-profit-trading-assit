"""Manual Trade Ticket V1 Phase 8 -- daily report (read-only over the journal store).

Sections: system health; per-session per-symbol states with reason codes; tickets issued;
owner decisions; yesterday's VIRTUAL_FORWARD outcomes (taken vs not taken, net R);
EDGE_VERIFIED FALSE; orders sent by system: 0. Local London/New York time is display only.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Sequence, Tuple

from session_clock import local_time_diagnostics
from v1_tickets.manual_ticket import ticket_path
from v1_tickets.outcome import outcome_path
from v1_tickets.owner_decision import load_decisions
from v1_tickets.scan_record import NOT_RUN, STATES, coverage, read_jsonl, scan_path

DATA_ERROR = "DATA_ERROR"

REPORT_TYPE = "manual_ticket_daily"


def previous_trading_day(day: dt.date) -> dt.date:
    prev = day - dt.timedelta(days=1)
    while prev.isoweekday() > 5:
        prev -= dt.timedelta(days=1)
    return prev


def build_report(journal: str, day: dt.date, *, now: dt.datetime,
                 expected: Dict[Tuple[str, str], Sequence[str]]) -> Dict[str, Any]:
    """expected: (strategy@version, session) -> configured symbols for every run of that session."""
    scans = read_jsonl(scan_path(journal, day))
    runs: Dict[str, set] = {}
    for r in scans:
        runs.setdefault(r["scheduler_run_id"], set()).add(r["session"])
    gaps = []
    for run_id, sessions in sorted(runs.items()):
        keys = [(s, sess, sym) for (s, sess), syms in expected.items() if sess in sessions for sym in syms]
        gaps += [{"run": run_id, "strategy": k[0], "session": k[1], "symbol": k[2]}
                 for k, v in coverage(scans, run_id, keys).items() if v == NOT_RUN]
    latest: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for r in scans:
        latest[(r["strategy"], r["session"], r["symbol"])] = r
    states = [{"strategy": k[0], "session": k[1], "symbol": k[2], "state": r["state"], "reason": r["stop_reason"],
               "stage": r["stage_reached"], "window_utc": [r["window_start_utc"], r["window_end_utc"]],
               "window_local": local_time_diagnostics(dt.datetime.fromisoformat(r["window_start_utc"]))
               if r["window_start_utc"] else None}
              for k, r in sorted(latest.items())]
    sessions_run = {(s, sess) for s, sess, _ in latest}
    never_run = [{"strategy": s, "session": sess} for (s, sess) in expected if (s, sess) not in sessions_run]
    # DATA_ERROR is counted on its own (not folded into TICKET_BLOCKED); records keep stage/reason.
    counts = {k: 0 for k in (*STATES, DATA_ERROR, NOT_RUN)}
    for r in latest.values():
        counts[DATA_ERROR if str(r.get("stop_reason") or "").startswith(DATA_ERROR + ":") else r["state"]] += 1
    counts[NOT_RUN] = len(gaps) + sum(len(expected[(n["strategy"], n["session"])]) for n in never_run)

    tickets: Dict[str, Dict[str, Any]] = {}
    for t in read_jsonl(ticket_path(journal, day)):
        if t.get("direction") is not None:
            prev = tickets.get(t["ticket_id"])
            tickets[t["ticket_id"]] = t if prev is None or prev.get("state") != "TICKET_READY" else prev
    decisions = load_decisions(journal)
    issued = [{"ticket_id": tid, "strategy": t["strategy"], "symbol": t["symbol"], "session": t["session"],
               "direction": t["direction"], "state": t["state"], "reason": t.get("stop_reason"),
               "logic_gate": {g: v["status"] for g, v in t["logic_gate"].items()}, "valid_until": t["valid_until"]}
              for tid, t in sorted(tickets.items())]
    owner = [{"ticket_id": tid, **{k: decisions[tid].get(k) for k in ("decision", "skip_reason", "source", "recorded_at")}}
             for tid in sorted(tickets) if tid in decisions]

    yday = previous_trading_day(day)
    outcomes = read_jsonl(outcome_path(journal, yday))

    def bucket(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        nets = [o["virtual_outcome"].get("net_R") for o in rows]
        known = [n for n in nets if n is not None]
        return {"count": len(rows), "net_R_sum": round(sum(known), 4) if known else None,
                "net_R_unavailable": len(nets) - len(known),
                "results": sorted(o["virtual_outcome"]["result"] for o in rows)}
    taken = [o for o in outcomes if (o.get("owner_decision") or {}).get("decision") == "TAKEN"]
    not_taken = [o for o in outcomes if o not in taken]
    return {
        "report": REPORT_TYPE, "date": day.isoformat(), "generated_at": now.isoformat(),
        "system_health": {"scheduled_runs": len(runs), "scan_records": len(scans), "missing_records": gaps,
                          "sessions_without_any_run": never_run,
                          "data_blocked": sum(1 for r in latest.values() if r["stage_reached"] == "DATA")},
        "state_counts": counts,
        "session_states": states,
        "tickets_issued": issued,
        "tickets_ready": sum(1 for t in issued if t["state"] == "TICKET_READY"),
        "owner_decisions": owner,
        "yesterday_outcomes": {"session_date": yday.isoformat(), "tag": "VIRTUAL_FORWARD",
                               "note": "reconstructed from bars; not demo or live performance",
                               "taken": bucket(taken), "not_taken": bucket(not_taken)},
        "EDGE_VERIFIED": False,
        "orders_sent_by_system": 0,
    }


def render_report(rep: Dict[str, Any]) -> str:
    h = rep["system_health"]
    out = [f"AG MANUAL TICKET DAILY REPORT — {rep['date']}",
           f"SYSTEM HEALTH: runs {h['scheduled_runs']}, scan records {h['scan_records']}, "
           f"missing records {len(h['missing_records'])}, sessions never run {len(h['sessions_without_any_run'])}, "
           f"data-blocked {h['data_blocked']}",
           "STATES: " + ", ".join(f"{k} {v}" for k, v in rep["state_counts"].items()),
           "SESSIONS:"]
    for s in rep["session_states"]:
        local = s["window_local"]
        when = f" (London {local['london']['local'][11:]}, NY {local['new_york']['local'][11:]})" if local else ""
        out.append(f"  {s['session']} {s['symbol']} {s['strategy']}: {s['state']}"
                   f"{' — ' + s['reason'] if s['reason'] else ''}{when}")
    out.append(f"TICKETS ISSUED: {len(rep['tickets_issued'])} (TICKET_READY {rep['tickets_ready']})")
    for t in rep["tickets_issued"]:
        out.append(f"  {t['ticket_id']} {t['symbol']} {t['direction']} {t['state']}"
                   f"{' — ' + t['reason'] if t['reason'] else ''}")
    out.append(f"OWNER DECISIONS: {len(rep['owner_decisions'])}")
    for d in rep["owner_decisions"]:
        out.append(f"  {d['ticket_id']} {d['decision']}{' ' + d['skip_reason'] if d['skip_reason'] else ''}")
    y = rep["yesterday_outcomes"]
    out.append(f"YESTERDAY ({y['session_date']}) OUTCOMES [{y['tag']} — {y['note']}]:")
    for name in ("taken", "not_taken"):
        b = y[name]
        out.append(f"  {name}: {b['count']} net R {b['net_R_sum'] if b['net_R_sum'] is not None else '-'}"
                   f" ({', '.join(b['results']) or 'none'})")
    out += ["EDGE_VERIFIED FALSE", "Orders sent by system: 0"]
    return "\n".join(out)
