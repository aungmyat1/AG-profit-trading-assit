"""AG V1 host heartbeat (DOCS-LIVE-3A). Read-only; writes one local JSON file outside any repo.

    .venv\\Scripts\\python.exe scripts\\host\\heartbeat.py
    .venv\\Scripts\\python.exe scripts\\host\\heartbeat.py --host-repo D:\\wp3-main-integ --out D:\\ag-telemetry\\heartbeat.json

Never imports MetaTrader5, never talks to the broker, never sends or publishes anything.
Sources (all read-only), each reported "UNKNOWN" when absent or unreadable -- never inferred:
- <host-repo>/logs/ag_v1_{fx,crypto,lsmc,lsmc-weekend}.log    last-24h counts, runner errors, mt5_connected
- <host-repo>/journal/ticket_delivery/delivery_status/*.jsonl  same-ref Telegram sends (duplicates)
- Get-ScheduledTask 'AG-*' | Get-ScheduledTaskInfo           LastTaskResult / LastRunTime / NextRunTime
- git -C <host-repo> rev-parse HEAD                          host_head_sha
- v1_tickets.fx.session_windows_utc (frozen config)          FX trade windows for missed_windows
Counts are log lines (one per symbol per runner pass), not unique tickets.

Redaction: no account number and no server name are collected; no log text is copied.

broker_order_calls is "UNKNOWN" unless every execution path in EXECUTION_PATHS is logged to a
source this script reads. observed_broker_order_calls is only what the AG-V1 runner logs show.

READER-SIDE RULE (consumers of heartbeat.json):
    age_seconds = now_utc - observed_at_utc
    age_seconds > 7200 while the host is scheduled awake  ->  treat the heartbeat as STALE
    (the host is scheduled asleep between AG-Sleep-Night and AG-Wake-MT5; a stale file in that
    span is expected, not a fault). A STALE heartbeat's fields must not be read as current.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import utcnow  # noqa: E402  (also puts this checkout's src/ on sys.path)

UNKNOWN = "UNKNOWN"
UTC = dt.timezone.utc
SCHEMA = "ag.host.heartbeat.v1"
DEFAULT_HOST_REPO = r"D:\wp3-main-integ"
DEFAULT_OUT = r"D:\ag-telemetry\heartbeat.json"
READER_STALE_AFTER_S = 7200
SOURCE_STALE_AFTER = dt.timedelta(hours=2)        # a runner log with no line for 2 h is a STALE source
MT5_STATUS_MAX_AGE = dt.timedelta(minutes=30)     # mt5_connected only from a runner line this recent
WINDOW_GRACE = dt.timedelta(minutes=30)           # install_tasks.ps1: runner acts in trade sessions + 30 min grace
RUNNER_LOGS = ("fx", "crypto", "lsmc", "lsmc-weekend")
DECISIONS = ("READY", "NO_TRADE", "STALE", "SPREAD_TOO_WIDE")
RUNNER_ERRORS = ("TIMEOUT", "MT5_INITIALIZE_FAILED", "MT5_BUSY", "DEMO_ACCOUNT_REQUIRED", "MT5_PACKAGE_MISSING")
MT5_DOWN = ("MT5_INITIALIZE_FAILED", "DEMO_ACCOUNT_REQUIRED", "MT5_PACKAGE_MISSING")
ORDER_CALL_RE = re.compile(r"order_(send|check)|ORDER_SEND|position_close", re.IGNORECASE)
LINE_RE = re.compile(r"^(\S+) (.*)$")

# Every path that can place, check or modify an order on the host's MT5 terminal, and whether its
# calls reach a source this script reads. Reviewed 2026-10-08 against host HEAD 9419b21 and the
# dev checkout D:\ddev\AG profit trading. Any logged=False entry forces broker_order_calls=UNKNOWN.
EXECUTION_PATHS = (
    {"path": "D:/wp3-main-integ scheduled AG-V1 runners (scripts/host/*)", "order_capable": False,
     "logged": True, "note": "no order/position call sites in host HEAD; tests/test_host_go_live_kit.py guards it"},
    {"path": "dev checkout src/execution/mt5_gateway.py (assistant.commands.execute_command)", "order_capable": True,
     "logged": False, "note": "calls mt5.order_send; writes nothing to the AG-V1 runner logs"},
    {"path": "dev checkout src/mt5/management_gateway.py (trade_management.manager)", "order_capable": True,
     "logged": False, "note": "calls mt5.order_send for SL modify / partial / close; not in runner logs"},
    {"path": "dev checkout web/server.ts -> management_gateway", "order_capable": True,
     "logged": False, "note": "server-side bridge to the management gateway; not in runner logs"},
    {"path": "MT5 terminal manual trading (owner)", "order_capable": True, "logged": False,
     "note": "terminal journal only; not read by this script"},
    {"path": "MT5 Expert Advisors (MQL5/Experts, e.g. ContinuationBreakout_EA.ex5)", "order_capable": True,
     "logged": False, "note": "attachment state not observable here"},
    {"path": "mt5ReadOnly MCP proxy", "order_capable": False, "logged": True,
     "note": "read-only proxy refuses order_send (web/tests/readonly_mcp_proxy.test.mjs)"},
)


def _parse_ts(s: str) -> Optional[dt.datetime]:
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t if t.tzinfo else None


def read_log(root: str, name: str) -> Optional[List[Tuple[dt.datetime, str]]]:
    """[(ts, message)] for every timestamped line, or None when missing/unreadable."""
    try:
        with open(os.path.join(root, "logs", f"{name}.log"), encoding="utf-8", errors="replace") as f:
            raw = f.readlines()
    except OSError:
        return None
    out = []
    for line in raw:
        m = LINE_RE.match(line.rstrip("\n"))
        ts = _parse_ts(m.group(1)) if m else None
        if ts is not None:
            out.append((ts, m.group(2)))
    return out


def _since(lines: Optional[list], since: dt.datetime) -> Optional[list]:
    return None if lines is None else [(t, m) for t, m in lines if t >= since]


def source_status(lines: Optional[list], now: dt.datetime) -> Dict[str, Any]:
    if lines is None:
        return {"status": "MISSING", "last_line_utc": UNKNOWN}
    if not lines:
        return {"status": "EMPTY", "last_line_utc": UNKNOWN}
    last = max(t for t, _ in lines)
    return {"status": "STALE" if now - last > SOURCE_STALE_AFTER else "OK", "last_line_utc": last.isoformat()}


def _decision(msg: str) -> Optional[str]:
    m = re.search(r"\bdecision=([A-Z_]+)", msg)
    return m.group(1) if m else None


def fx_counts(lines: Optional[list]) -> Any:
    if lines is None:
        return UNKNOWN
    out: Dict[str, Dict[str, int]] = {}
    for _, msg in lines:
        parts = msg.split()
        if len(parts) < 4 or parts[0] != "FX" or "LONDON" not in parts[3]:
            continue
        c = out.setdefault(parts[3], {k: 0 for k in DECISIONS + ("errors", "other")})
        d = _decision(msg)
        if d in DECISIONS:
            c[d] += 1
        elif d == "DATA_ERROR":
            c["errors"] += 1
        else:
            c["other"] += 1
    return out


def state_counts(lines: Optional[list], prefix: str, key: str) -> Any:
    if lines is None:
        return UNKNOWN
    out: Dict[str, int] = {}
    for _, msg in lines:
        parts = msg.split()
        if not parts or parts[0] != prefix:
            continue
        m = re.search(rf"\b{key}=([A-Z_]+)", msg)
        v = m.group(1) if m else (parts[2] if len(parts) > 2 else "OTHER")
        out[v] = out.get(v, 0) + 1
    return out


def runner_errors(logs: Dict[str, Optional[list]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, lines in logs.items():
        if lines is None:
            out[name] = UNKNOWN
            continue
        c = {k: 0 for k in RUNNER_ERRORS}
        for _, msg in lines:
            tok = msg.split(" ", 1)[0]
            if tok in c:
                c[tok] += 1
        out[name] = c
    return out


def fx_archive_duplicates(lines: Optional[list]) -> Any:
    """Identical ARCHIVED FX lines repeated on one UTC day. Only READY repeats count as duplicate
    tickets: the runner legitimately re-archives an unchanged STALE/NO_TRADE decision each pass
    (its archived content, not its log summary, changed), so those are reported separately."""
    if lines is None:
        return UNKNOWN
    seen: Dict[Tuple[dt.date, str], int] = {}
    for ts, msg in lines:
        if msg.startswith("FX ") and msg.endswith(" ARCHIVED"):
            seen[(ts.date(), msg)] = seen.get((ts.date(), msg), 0) + 1
    ready = sum(n - 1 for (_, m), n in seen.items() if n > 1 and _decision(m) == "READY")
    other = sum(n - 1 for (_, m), n in seen.items() if n > 1 and _decision(m) != "READY")
    return {"ready_ticket_duplicates": ready, "non_ready_rearchives": other}


def telegram_duplicates(root: str, since: dt.datetime) -> Any:
    files = glob.glob(os.path.join(root, "journal", "ticket_delivery", "delivery_status", "*.jsonl"))
    if not files:
        return UNKNOWN
    refs: Dict[str, int] = {}
    for p in files:
        try:
            with open(p, encoding="utf-8") as f:
                rows = f.readlines()
        except OSError:
            return UNKNOWN
        for row in rows:
            try:
                r = json.loads(row)
            except ValueError:
                continue
            at = _parse_ts(str(r.get("recorded_at", "")))
            if r.get("status") == "SENT" and r.get("ref") and at and at >= since:
                refs[r["ref"]] = refs.get(r["ref"], 0) + 1
    return sum(n - 1 for n in refs.values() if n > 1)


def missed_windows(fx_lines: Optional[list], now: dt.datetime) -> Any:
    """Frozen FX trade windows that closed (+grace) in the last 24 h on an open FX market with no
    ag_v1_fx.log line for their cycle inside [start, end + grace]."""
    if fx_lines is None:
        return UNKNOWN
    try:
        from large_smc_watch.watch import fx_market_closed
        from v1_tickets.fx import V1_CYCLES, session_windows_utc
    except Exception:  # noqa: BLE001 -- no window authority -> UNKNOWN, never guessed
        return UNKNOWN
    missed = []
    for back in (2, 1, 0):
        day = (now - dt.timedelta(days=back)).date()
        try:
            windows = session_windows_utc(day)
        except Exception:  # noqa: BLE001
            return UNKNOWN
        for cycle in V1_CYCLES:
            start, end = windows[cycle]["trade"]
            close = end + WINDOW_GRACE
            if not (now - dt.timedelta(hours=24) < close <= now) or fx_market_closed(start):
                continue
            if not any(start <= ts <= close and f" {cycle} " in f" {msg} " for ts, msg in fx_lines):
                missed.append(f"{cycle}:{day.isoformat()}")
    return missed


def observed_order_calls(logs: Dict[str, Optional[list]]) -> Any:
    if all(v is None for v in logs.values()):
        return UNKNOWN
    return sum(1 for lines in logs.values() if lines for _, m in lines if ORDER_CALL_RE.search(m))


def broker_order_calls(observed: Any, paths=EXECUTION_PATHS) -> Any:
    if observed == UNKNOWN or any(p["order_capable"] and not p["logged"] for p in paths):
        return UNKNOWN
    return observed


def mt5_connected(logs: Dict[str, Optional[list]], now: dt.datetime) -> Dict[str, Any]:
    """From the newest MT5-touching runner line no older than MT5_STATUS_MAX_AGE: a connect
    failure -> false; a line carrying MT5 data (data=/source=MT5) -> true; otherwise UNKNOWN."""
    best: Optional[Tuple[dt.datetime, bool]] = None
    for lines in logs.values():
        for ts, msg in lines or ():
            tok = msg.split(" ", 1)[0]
            if tok in MT5_DOWN:
                v = False
            elif "data=FRESH" in msg or "data=STALE" in msg or "source=MT5" in msg:
                v = True
            else:
                continue
            if best is None or ts > best[0]:
                best = (ts, v)
    if best is None or now - best[0] > MT5_STATUS_MAX_AGE:
        return {"value": UNKNOWN, "as_of_utc": best[0].isoformat() if best else UNKNOWN}
    return {"value": best[1], "as_of_utc": best[0].isoformat()}


def scheduled_tasks() -> Any:
    ps = ("Get-ScheduledTask -TaskName 'AG-*' | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; "
          "[pscustomobject]@{name=$_.TaskName; LastTaskResult=$i.LastTaskResult; "
          "LastRunTime=$(if ($i.LastRunTime) { $i.LastRunTime.ToUniversalTime().ToString('o') } else { $null }); "
          "NextRunTime=$(if ($i.NextRunTime) { $i.NextRunTime.ToUniversalTime().ToString('o') } else { $null })} } "
          "| ConvertTo-Json -Compress")
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                           capture_output=True, text=True, timeout=60)
        rows = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return UNKNOWN
    if rows is None:
        return UNKNOWN
    rows = rows if isinstance(rows, list) else [rows]
    return {row["name"]: {k: (UNKNOWN if row.get(k) is None else row[k])
                          for k in ("LastTaskResult", "LastRunTime", "NextRunTime")} for row in rows}


def head_sha(root: str) -> Any:
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else UNKNOWN


def build(host_repo: str = DEFAULT_HOST_REPO, now: Optional[dt.datetime] = None, tasks: Any = None) -> Dict[str, Any]:
    now = (now or utcnow()).astimezone(UTC)
    since = now - dt.timedelta(hours=24)
    full = {name: read_log(host_repo, f"ag_v1_{name}") for name in RUNNER_LOGS}
    logs = {name: _since(v, since) for name, v in full.items()}
    observed = observed_order_calls(logs)
    return {
        "schema": SCHEMA,
        "observed_at_utc": now.isoformat(),
        "reader_rule": f"age_seconds = now - observed_at_utc; > {READER_STALE_AFTER_S} while scheduled awake -> STALE",
        "host_head_sha": head_sha(host_repo),
        "mt5_connected": mt5_connected(logs, now),
        "tasks": scheduled_tasks() if tasks is None else tasks,
        "sources": {f"ag_v1_{n}.log": source_status(v, now) for n, v in full.items()},
        "last_24h": {
            "fx_by_window": fx_counts(logs["fx"]),
            "lsmc_states": state_counts(logs["lsmc"], "LSMC", "state"),
            "crypto_decisions": state_counts(logs["crypto"], "CRYPTO", "decision"),
            "runner_errors": runner_errors(logs),
        },
        "duplicates": {"fx_archive": fx_archive_duplicates(logs["fx"]),
                       "telegram_same_ref_sends": telegram_duplicates(host_repo, since)},
        "missed_windows": missed_windows(logs["fx"], now),
        "observed_broker_order_calls": observed,
        "broker_order_calls": broker_order_calls(observed),
        "execution_paths": list(EXECUTION_PATHS),
    }


def write(hb: Dict[str, Any], out: str = DEFAULT_OUT) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(hb, f, indent=1)
        f.write("\n")
    os.replace(tmp, out)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host-repo", default=DEFAULT_HOST_REPO)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    if os.path.commonpath([os.path.abspath(args.out), os.path.abspath(args.host_repo)]) == os.path.abspath(args.host_repo):
        print("REFUSED --out is inside the host repo")
        return 2
    print(f"HEARTBEAT_WRITTEN {write(build(args.host_repo), args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
