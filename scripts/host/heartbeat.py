"""AG V1 host heartbeat (DOCS-LIVE-3A). Read-only; writes one local JSON file outside any repo.

    .venv\\Scripts\\python.exe scripts\\host\\heartbeat.py
    .venv\\Scripts\\python.exe scripts\\host\\heartbeat.py --host-repo D:\\wp3-main-integ --out D:\\ag-telemetry\\heartbeat.json

    --no-broker-history   skip the MT5 history read (broker_history_24h / broker_order_calls -> UNKNOWN)

Never imports MetaTrader5 and never sends or publishes anything. Its only broker contact is the
existing read-only mt5ReadOnly MCP proxy (web/scripts/start_mt5_mcp.mjs), calling only the
history tools in HISTORY_TOOLS, under the host-wide MT5 access lock.
Sources (all read-only), each reported "UNKNOWN" when absent or unreadable -- never inferred:
- <host-repo>/logs/ag_v1_{fx,crypto,lsmc,lsmc-weekend}.log    last-24h counts, runner errors, mt5_connected
- <host-repo>/journal/ticket_delivery/delivery_status/*.jsonl  same-ref Telegram sends (duplicates)
- <host-repo>/journal/ticket_delivery/archive/.../ST_LARGE_SMC_V1   unique LSMC opportunities
- Get-ScheduledTask 'AG-*' | Get-ScheduledTaskInfo           LastTaskResult / LastRunTime / NextRunTime
- git -C <host-repo> rev-parse / symbolic-ref                host_head_sha, host_ref, host_on_main
- v1_tickets.fx.session_windows_utc (frozen config)          FX trade windows for missed_windows
- mt5ReadOnly MCP readonly_get_orders / readonly_get_deals    broker_history_24h (counts only)
Log counts are lines (one per symbol per runner pass, "per_cycle"), not unique tickets.

Redaction: no account number, server name, ticket, price or log text is copied out.

broker_order_calls = broker_history_24h.orders (every execution path in EXECUTION_PATHS, logged or
not, lands in the account's order history), or "UNKNOWN" when that history cannot be read.
observed_broker_order_calls is separately what the AG-V1 runner logs show.

Source staleness is schedule-aware: each runner log declares SOURCE_WINDOWS (Myanmar time). Outside
them a quiet log is INACTIVE_EXPECTED; inside one it is STALE after 2 h without a line.
Top-level status is HOST_NOT_ON_MAIN when the host checkout is not on branch main.

READER-SIDE RULE (consumers of heartbeat.json):
    age_seconds = now_utc - observed_at_utc
    age_seconds > 7200 while the host is scheduled awake  ->  treat the heartbeat as STALE
    (the host is scheduled asleep between AG-Sleep-Night and AG-Wake-MT5; a stale file in that
    span is expected, not a fault). A STALE heartbeat's fields must not be read as current.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import REPO_ROOT, Mt5Busy, mt5_access_lock, utcnow  # noqa: E402  (also puts src/ on sys.path)

UNKNOWN = "UNKNOWN"
UTC = dt.timezone.utc
SCHEMA = "ag.host.heartbeat.v1"
DEFAULT_HOST_REPO = r"D:\wp3-main-integ"
DEFAULT_OUT = r"D:\ag-telemetry\heartbeat.json"
READER_STALE_AFTER_S = 7200
SOURCE_STALE_AFTER = dt.timedelta(hours=2)        # a runner log with no line for 2 h is a STALE source
MT5_STATUS_MAX_AGE = dt.timedelta(minutes=30)     # mt5_connected only from a runner line this recent
MMT = dt.timezone(dt.timedelta(hours=6, minutes=30))
# (weekdays of the window start in MMT with Mon=0, start HH:MM MMT, duration minutes), from the host tasks.
AWAKE_DAILY = (tuple(range(7)), "12:25", 740)     # AG-Wake-MT5 12:25 -> AG-Sleep-Night 00:45 next day
WEEKEND_CRYPTO = ((6, 0), "03:10", 155)           # AG-Wake-Weekend-Crypto Sun+Mon 03:10 -> sleep 05:45
SOURCE_WINDOWS = {"fx": (AWAKE_DAILY, WEEKEND_CRYPTO), "crypto": (AWAKE_DAILY, WEEKEND_CRYPTO),
                  "lsmc": (AWAKE_DAILY, WEEKEND_CRYPTO), "lsmc-weekend": (WEEKEND_CRYPTO,)}
# The only MCP tool names this module may invoke (tests/test_host_heartbeat.py enforces that no other
# tool-shaped name appears in this file): history orders/deals plus connection-status tools.
MCP_TOOL_ALLOWLIST = frozenset({
    "readonly_get_orders", "readonly_get_deals",            # history (called)
    "readonly_get_account_info", "mt5_setup_status",        # terminal/account connection status (not called)
})
HISTORY_TOOLS = ("readonly_get_orders", "readonly_get_deals")
DEFAULT_MCP_LAUNCHER = os.path.join(REPO_ROOT, "web", "scripts", "start_mt5_mcp.mjs")
MCP_TIMEOUT_S = 60
LSMC_ARCHIVE = os.path.join("journal", "ticket_delivery", "archive", "fx_ticket_archive", "ST_LARGE_SMC_V1")
WINDOW_GRACE = dt.timedelta(minutes=30)           # install_tasks.ps1: runner acts in trade sessions + 30 min grace
RUNNER_LOGS = ("fx", "crypto", "lsmc", "lsmc-weekend")
DECISIONS = ("READY", "NO_TRADE", "STALE", "SPREAD_TOO_WIDE")
RUNNER_ERRORS = ("TIMEOUT", "MT5_INITIALIZE_FAILED", "MT5_BUSY", "DEMO_ACCOUNT_REQUIRED", "MT5_PACKAGE_MISSING")
MT5_DOWN = ("MT5_INITIALIZE_FAILED", "DEMO_ACCOUNT_REQUIRED", "MT5_PACKAGE_MISSING")
ORDER_CALL_RE = re.compile(r"order_(send|check)|ORDER_SEND|position_close", re.IGNORECASE)
LINE_RE = re.compile(r"^(\S+) (.*)$")

# Every path that can place, check or modify an order on the host's MT5 terminal, and whether its
# calls reach the runner logs. Reviewed 2026-10-08 against host HEAD 9419b21 and the dev checkout
# D:\ddev\AG profit trading. Informational: the unlogged ones are why broker_order_calls comes from
# the broker history and not from the logs.
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


def active_window_start(windows, now: dt.datetime) -> Optional[dt.datetime]:
    """Start (UTC) of the declared window containing `now`, or None when outside all of them."""
    local = now.astimezone(MMT)
    for days, start, minutes in windows:
        h, m = map(int, start.split(":"))
        for back in (0, 1):
            d = local.date() - dt.timedelta(days=back)
            if d.weekday() not in days:
                continue
            begin = dt.datetime.combine(d, dt.time(h, m), tzinfo=MMT)
            if begin <= local < begin + dt.timedelta(minutes=minutes):
                return begin.astimezone(UTC)
    return None


def source_status(lines: Optional[list], now: dt.datetime, windows=(AWAKE_DAILY,)) -> Dict[str, Any]:
    if lines is None:
        return {"status": "MISSING", "last_line_utc": UNKNOWN}
    last = max((t for t, _ in lines), default=None)
    out = {"last_line_utc": last.isoformat() if last else UNKNOWN}
    start = active_window_start(windows, now)
    if start is None:
        return {"status": "INACTIVE_EXPECTED", **out}
    quiet_since = max(last, start) if last else start
    return {"status": "STALE" if now - quiet_since > SOURCE_STALE_AFTER else "OK", **out}


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


def lsmc_unique_opportunities(root: str, now: dt.datetime) -> Any:
    """Distinct (symbol, reference_id) whose archived watch transition reached OPPORTUNITY in the
    last 24 h. reference_id is the opportunity id, else the POI id (WatchTracker.poll)."""
    base = os.path.join(root, LSMC_ARCHIVE)
    if not os.path.isdir(base):
        return UNKNOWN
    since = now - dt.timedelta(hours=24)
    keys = set()
    for back in (0, 1, 2):
        d = (now - dt.timedelta(days=back)).date()
        for path in glob.glob(os.path.join(base, "*", "LSMC_WATCH-*", str(d.year), f"{d.isoformat()}.json")):
            try:
                with open(path, encoding="utf-8") as f:
                    ev = (json.load(f) or {}).get("payload") or {}
            except (OSError, ValueError):
                return UNKNOWN
            at = _parse_ts(str(ev.get("evaluated_at", "")))
            if ev.get("to_state") == "OPPORTUNITY" and at and since <= at <= now:
                keys.add((ev.get("symbol"), ev.get("reference_id")))
    by_symbol: Dict[str, int] = {}
    for symbol, _ in keys:
        by_symbol[symbol] = by_symbol.get(symbol, 0) + 1
    return {"count": len(keys), "by_symbol": dict(sorted(by_symbol.items()))}


def _server_to_utc(text: str) -> Optional[dt.datetime]:
    from host_evidence.symbol_metadata import server_time_to_utc
    try:
        return server_time_to_utc(dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return None


def summarize_history(orders_csv: Optional[str], deals_csv: Optional[str], now: dt.datetime) -> Any:
    """Counts only. Orders by time_setup, deals by time (broker server wall-clock -> UTC). Deals count
    trade deals only (type 0 buy / 1 sell; balance and credit rows are excluded)."""
    if orders_csv is None or deals_csv is None:
        return UNKNOWN
    since = now - dt.timedelta(hours=24)

    def rows(text: str, need: Tuple[str, ...]) -> Optional[list]:
        text = text.strip()
        if text in ("", '""'):
            return []
        reader = csv.DictReader(io.StringIO(text))
        if not set(need) <= set(reader.fieldnames or ()):
            return None
        return list(reader)

    orders = rows(orders_csv, ("time_setup", "magic"))
    deals = rows(deals_csv, ("time", "type"))
    if orders is None or deals is None:
        return UNKNOWN
    def within(server_time: str) -> bool:
        t = _server_to_utc(server_time)
        return t is not None and since <= t <= now

    recent = [o for o in orders if within(o["time_setup"])]
    by_magic: Dict[str, int] = {}
    for o in recent:
        if o["magic"].strip() not in ("", "0"):
            by_magic[o["magic"].strip()] = by_magic.get(o["magic"].strip(), 0) + 1
    n_deals = sum(1 for d in deals if d["type"].strip() in ("0", "1") and within(d["time"]))
    return {"orders": len(recent), "deals": n_deals, "by_magic": dict(sorted(by_magic.items())),
            "manual_or_zero_magic": sum(1 for o in recent if o["magic"].strip() in ("", "0"))}


def mcp_history(launcher: str, from_date: str, to_date: str, timeout: float = MCP_TIMEOUT_S) -> Optional[Dict[str, str]]:
    """{tool: csv} from the read-only mt5ReadOnly MCP proxy over stdio, or None when unreachable.
    Only HISTORY_TOOLS are ever called. Holds the host-wide MT5 lock for the whole session."""
    if not os.path.isfile(launcher):
        return None
    try:
        with mt5_access_lock():
            return _mcp_session(launcher, from_date, to_date, timeout)
    except (Mt5Busy, OSError):
        return None


def _mcp_session(launcher: str, from_date: str, to_date: str, timeout: float) -> Optional[Dict[str, str]]:
    root = os.path.abspath(os.path.join(os.path.dirname(launcher), "..", ".."))
    proc = subprocess.Popen(["node", launcher], cwd=root, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    lines: "queue.Queue[str]" = queue.Queue()
    threading.Thread(target=lambda: [lines.put(l) for l in proc.stdout], daemon=True).start()
    deadline = dt.datetime.now().timestamp() + timeout

    def send(msg: dict) -> None:
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()

    def reply(rid: int) -> Optional[dict]:
        while True:
            left = deadline - dt.datetime.now().timestamp()
            if left <= 0:
                return None
            try:
                msg = json.loads(lines.get(timeout=left))
            except queue.Empty:
                return None
            except ValueError:
                continue
            if msg.get("id") == rid:
                return msg

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "ag-heartbeat", "version": "1"}}})
        if not (reply(1) or {}).get("result"):
            return None
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        out: Dict[str, str] = {}
        for rid, tool in enumerate(HISTORY_TOOLS, start=2):
            if tool not in MCP_TOOL_ALLOWLIST:
                return None
            send({"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                  "params": {"name": tool, "arguments": {"from_date": from_date, "to_date": to_date}}})
            res = (reply(rid) or {}).get("result") or {}
            content = res.get("content") or []
            if res.get("isError") or not content:
                return None
            try:
                out[tool] = json.loads(content[0].get("text", ""))["result"]
            except (ValueError, KeyError, TypeError):
                return None
        return out
    except OSError:
        return None
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)


def broker_history(now: dt.datetime, fetch: Optional[Callable[[str, str], Optional[Dict[str, str]]]]) -> Any:
    if fetch is None:
        return UNKNOWN
    got = fetch((now - dt.timedelta(days=2)).date().isoformat(), (now + dt.timedelta(days=1)).date().isoformat())
    if not got:
        return UNKNOWN
    return summarize_history(got.get(HISTORY_TOOLS[0]), got.get(HISTORY_TOOLS[1]), now)


def host_ref(root: str, sha: Any) -> Tuple[Any, Any]:
    """(host_ref, host_on_main): the checked-out branch, or "DETACHED@<sha7>"."""
    if sha == UNKNOWN:
        return UNKNOWN, UNKNOWN
    try:
        r = subprocess.run(["git", "-C", root, "symbolic-ref", "-q", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return UNKNOWN, UNKNOWN
    if r.returncode == 0 and r.stdout.strip():
        branch = r.stdout.strip()
        return branch, branch == "main"
    return (f"DETACHED@{sha[:7]}", False) if r.returncode == 1 else (UNKNOWN, UNKNOWN)


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


def build(host_repo: str = DEFAULT_HOST_REPO, now: Optional[dt.datetime] = None, tasks: Any = None,
          history_fetch: Optional[Callable[[str, str], Optional[Dict[str, str]]]] = None) -> Dict[str, Any]:
    now = (now or utcnow()).astimezone(UTC)
    since = now - dt.timedelta(hours=24)
    full = {name: read_log(host_repo, f"ag_v1_{name}") for name in RUNNER_LOGS}
    logs = {name: _since(v, since) for name, v in full.items()}
    sha = head_sha(host_repo)
    ref, on_main = host_ref(host_repo, sha)
    history = broker_history(now, history_fetch)
    return {
        "schema": SCHEMA,
        "status": UNKNOWN if on_main == UNKNOWN else ("OK" if on_main else "HOST_NOT_ON_MAIN"),
        "observed_at_utc": now.isoformat(),
        "reader_rule": f"age_seconds = now - observed_at_utc; > {READER_STALE_AFTER_S} while scheduled awake -> STALE",
        "host_head_sha": sha,
        "host_ref": ref,
        "host_on_main": on_main,
        "mt5_connected": mt5_connected(logs, now),
        "tasks": scheduled_tasks() if tasks is None else tasks,
        "sources": {f"ag_v1_{n}.log": source_status(v, now, SOURCE_WINDOWS[n]) for n, v in full.items()},
        "last_24h": {
            "fx_by_window_per_cycle": fx_counts(logs["fx"]),
            "lsmc_states_per_cycle": state_counts(logs["lsmc"], "LSMC", "state"),
            "lsmc_unique_opportunities_24h": lsmc_unique_opportunities(host_repo, now),
            "crypto_decisions_per_cycle": state_counts(logs["crypto"], "CRYPTO", "decision"),
            "runner_errors": runner_errors(logs),
        },
        "duplicates": {"fx_archive": fx_archive_duplicates(logs["fx"]),
                       "telegram_same_ref_sends": telegram_duplicates(host_repo, since)},
        "missed_windows": missed_windows(logs["fx"], now),
        "broker_history_24h": history,
        "broker_order_calls": history["orders"] if isinstance(history, dict) else UNKNOWN,
        "observed_broker_order_calls": observed_order_calls(logs),
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
    ap.add_argument("--mcp-launcher", default=DEFAULT_MCP_LAUNCHER, help="mt5ReadOnly MCP launcher (start_mt5_mcp.mjs)")
    ap.add_argument("--no-broker-history", action="store_true")
    args = ap.parse_args(argv)
    if os.path.commonpath([os.path.abspath(args.out), os.path.abspath(args.host_repo)]) == os.path.abspath(args.host_repo):
        print("REFUSED --out is inside the host repo")
        return 2
    fetch = None if args.no_broker_history else (lambda a, b: mcp_history(args.mcp_launcher, a, b))
    print(f"HEARTBEAT_WRITTEN {write(build(args.host_repo, history_fetch=fetch), args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
