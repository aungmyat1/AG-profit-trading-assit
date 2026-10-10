"""AG V1 host heartbeat (DOCS-LIVE-3A). Read-only; writes one local JSON file outside any repo.

    .venv\\Scripts\\python.exe scripts\\host\\heartbeat.py
    .venv\\Scripts\\python.exe scripts\\host\\heartbeat.py --host-repo D:\\wp3-main-integ --out D:\\ag-telemetry\\heartbeat.json

    --history-backend attach|mcp|none   broker history source (default attach)

Never sends or publishes anything, never touches orders or positions. Broker history (counts only):
- attach (default): the MetaTrader5 package attaches to the already-running terminal exactly like the
  AG runners (initialize() with no login/password/server, MT5_TERMINAL_PATH rule, host-wide MT5 lock,
  shutdown() in finally), touching only MT5_ATTRIBUTE_ALLOWLIST. Source label LIVE_ATTACH.
- mcp (optional): the read-only mt5ReadOnly MCP proxy (web/scripts/start_mt5_mcp.mjs), only the
  tools in MCP_TOOL_ALLOWLIST. Needs proxy credentials; source label MCP_PROXY.
Both allowlists are enforced by AST tests in tests/test_host_heartbeat.py.
Sources (all read-only), each reported "UNKNOWN" when absent or unreadable -- never inferred:
- <host-repo>/logs/ag_v1_{fx,crypto,lsmc,lsmc-weekend}.log    last-24h counts, runner errors, mt5_connected
- <host-repo>/journal/ticket_delivery/delivery_status/*.jsonl  same-ref Telegram sends (duplicates)
- <host-repo>/journal/ticket_delivery/archive/.../ST_LARGE_SMC_V1   unique LSMC opportunities
- Get-ScheduledTask 'AG-*' | Get-ScheduledTaskInfo           LastTaskResult / LastRunTime / NextRunTime
- git -C <host-repo> rev-parse / symbolic-ref                host_head_sha, host_ref, host_on_main
- v1_tickets.fx.session_windows_utc (frozen config)          FX trade windows for missed_windows
- MetaTrader5 attach history_orders_get / history_deals_get  broker_history_24h (counts only)
- GlobalMemoryStatusEx, shutil.disk_usage (fixed drives)      host_resources
Log counts are lines (one per symbol per runner pass, "per_cycle"), not unique tickets.

Redaction: no account number, server name, ticket, price or log text is copied out.

broker_order_calls = broker_history_24h.orders (every execution path in EXECUTION_PATHS, logged or
not, lands in the account's order history), or "UNKNOWN" when that history cannot be read.
observed_broker_order_calls is separately what the AG-V1 runner logs show.

Source staleness is power-mode aware (--host-power-mode). Under `wake_sleep` (the mode the host was
observed in on 2026-10-08) each runner log keeps its declared SOURCE_WINDOWS (Myanmar time): outside
them a quiet log is INACTIVE_EXPECTED, inside one it is STALE after 2 h without a line. Under
`always_on` (SCHED-R1-B target) there is no sleep span at all, so every minute is an expected-active
minute and overnight runner silence is STALE -- never INACTIVE_EXPECTED. The mode is recorded in
`host_power_mode` and the windows actually used are recorded in `source_windows`, so a reader can
always see which rule produced a status instead of having to infer it.
Top-level status: first of status_reasons [HOST_NOT_ON_MAIN, DEGRADED_RESOURCES], else OK (UNKNOWN when
the host ref cannot be read). DEGRADED_RESOURCES thresholds are PROPOSED_OWNER_CONFIRM.

READER-SIDE RULE (consumers of heartbeat.json):
    age_seconds = now_utc - observed_at_utc
    age_seconds > 7200 while the host is expected active  ->  treat the heartbeat as STALE
    (`wake_sleep`: the host sleeps between AG-Sleep-Night and AG-Wake-MT5, so a stale file in that
    span is expected, not a fault. `always_on`: no such span exists, so the exemption never applies).
    A STALE heartbeat's fields must not be read as current.
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
from _host_common import (  # noqa: E402  (also puts this checkout's src/ on sys.path)
    MT5_INIT_TIMEOUT_S, REPO_ROOT, CallTimeout, Mt5Busy, _mt5_server_wall, call_with_timeout, import_mt5,
    mt5_access_lock, utcnow,
)

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
# Host power modes. `wake_sleep` is what the host was observed running on 2026-10-08 (AG-Wake-MT5 /
# AG-Sleep-Night registered). `always_on` is the SCHED-R1-B declared target, in which those wake and
# sleep tasks are retired: the host never sleeps, so no minute may be classified INACTIVE_EXPECTED.
POWER_MODES = ("wake_sleep", "always_on")
DEFAULT_POWER_MODE = "wake_sleep"                 # observed host state; the target needs an explicit flag
ALWAYS_ON_WINDOWS = ((tuple(range(7)), "00:00", 24 * 60),)   # every minute is an expected-active minute
POWER_MODE_SOURCE = {
    "wake_sleep": "observed host state 2026-10-08: AG-Wake-MT5 / AG-Sleep-Night still registered",
    "always_on": "SCHED-R1-B declared target (scripts/host/install_tasks.ps1 $HostPowerPolicy)",
}


def source_windows(power_mode: str, name: str) -> tuple:
    """Declared source windows for `name` under `power_mode`; unknown modes fail closed to always_on.

    Failing closed matters: a mode we do not recognise must never manufacture a sleep span that would
    relabel a stopped runner as INACTIVE_EXPECTED.
    """
    if power_mode not in POWER_MODES:
        return ALWAYS_ON_WINDOWS
    if power_mode == "always_on":
        return ALWAYS_ON_WINDOWS
    return SOURCE_WINDOWS[name]
# The only MCP tool names this module may invoke (tests/test_host_heartbeat.py enforces that no other
# tool-shaped name appears in this file): history orders/deals plus connection-status tools.
MCP_TOOL_ALLOWLIST = frozenset({
    "readonly_get_orders", "readonly_get_deals",            # history (called)
    "readonly_get_account_info", "mt5_setup_status",        # terminal/account connection status (not called)
})
HISTORY_TOOLS = ("readonly_get_orders", "readonly_get_deals")
# The only MetaTrader5 attributes the attach backend may touch (test-enforced via AST): connection,
# connection-status and history reads. Nothing that lists live orders/positions or sends anything.
MT5_ATTRIBUTE_ALLOWLIST = frozenset({"initialize", "shutdown", "terminal_info", "account_info",
                                     "history_orders_get", "history_deals_get", "last_error"})
HISTORY_BACKENDS = ("attach", "mcp", "none")
# PROPOSED_OWNER_CONFIRM: DEGRADED_RESOURCES thresholds. 1200 MB = resource class R1 gate
# (docs/governance/AG_RESOURCE_MANAGEMENT_POLICY_V1.md); 10 GB free per fixed drive is a proposal.
FREE_RAM_MIN_MB = 1200
FREE_DISK_MIN_GB = 10
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


def source_status(lines: Optional[list], now: dt.datetime, windows=(AWAKE_DAILY,),
                  power_mode: str = DEFAULT_POWER_MODE) -> Dict[str, Any]:
    """OK / STALE / INACTIVE_EXPECTED / MISSING for one runner log.

    `windows` is the resolved window tuple (see source_windows). Under `always_on` the resolved
    window covers the whole day, so a quiet log can only ever be OK or STALE -- overnight silence is
    never INACTIVE_EXPECTED just because the retired sleep window used to cover it.
    """
    if lines is None:
        return {"status": "MISSING", "last_line_utc": UNKNOWN, "power_mode": power_mode}
    last = max((t for t, _ in lines), default=None)
    out = {"last_line_utc": last.isoformat() if last else UNKNOWN}
    start = active_window_start(windows, now)
    if start is None:
        return {"status": "INACTIVE_EXPECTED", "power_mode": power_mode, **out}
    quiet_since = max(last, start) if last else start
    return {"status": "STALE" if now - quiet_since > SOURCE_STALE_AFTER else "OK",
            "power_mode": power_mode, **out}


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


def count_history(orders: List[Tuple[Optional[dt.datetime], str]], deals: List[Tuple[Optional[dt.datetime], str]],
                  now: dt.datetime, source: str) -> Dict[str, Any]:
    """Counts only, from (utc_time, magic) orders and (utc_time, deal_type) deals. Deals count trade
    deals only (type 0 buy / 1 sell; balance and credit rows are excluded)."""
    since = now - dt.timedelta(hours=24)
    recent = [m.strip() for t, m in orders if t is not None and since <= t <= now]
    by_magic: Dict[str, int] = {}
    for m in recent:
        if m not in ("", "0"):
            by_magic[m] = by_magic.get(m, 0) + 1
    n_deals = sum(1 for t, k in deals if t is not None and since <= t <= now and k.strip() in ("0", "1"))
    return {"source": source, "orders": len(recent), "deals": n_deals, "by_magic": dict(sorted(by_magic.items())),
            "manual_or_zero_magic": sum(1 for m in recent if m in ("", "0"))}


def summarize_history(orders_csv: Optional[str], deals_csv: Optional[str], now: dt.datetime) -> Any:
    """MCP proxy CSV (broker server wall-clock text) -> count_history."""
    if orders_csv is None or deals_csv is None:
        return UNKNOWN

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
    return count_history([(_server_to_utc(o["time_setup"]), o["magic"]) for o in orders],
                         [(_server_to_utc(d["time"]), d["type"]) for d in deals], now, "MCP_PROXY")


def attach_history(now: dt.datetime, terminal_path: Optional[str] = None) -> Any:
    """LIVE_ATTACH backend, mirroring the AG runners' mt5_initialize: initialize() with NO login /
    password / server (attach to the terminal session already running), same terminal path rule
    (MT5_TERMINAL_PATH, else the package default), under the host-wide MT5 lock, shutdown() always.
    Only MT5_ATTRIBUTE_ALLOWLIST attributes are touched (tests/test_host_heartbeat.py enforces it)."""
    from host_evidence.symbol_metadata import server_time_to_utc
    mt5 = import_mt5()
    if mt5 is None:
        return {"error": "MT5_PACKAGE_MISSING"}
    path = terminal_path or os.environ.get("MT5_TERMINAL_PATH", "")
    kwargs: Dict[str, Any] = {"timeout": MT5_INIT_TIMEOUT_S * 1000}
    if path:
        kwargs["path"] = path

    def utc(raw: Any) -> Optional[dt.datetime]:
        try:
            return server_time_to_utc(_mt5_server_wall(int(raw)))
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    try:
        with mt5_access_lock():
            try:
                if not call_with_timeout(mt5.initialize, limit_s=MT5_INIT_TIMEOUT_S + 2, **kwargs):
                    return {"error": f"INITIALIZE_FAILED {_last_error(mt5)}"}
                term = call_with_timeout(mt5.terminal_info)
                acct = call_with_timeout(mt5.account_info)
                lo, hi = now - dt.timedelta(days=3), now + dt.timedelta(days=2)   # wide: server-time offset
                orders = call_with_timeout(mt5.history_orders_get, lo, hi)
                deals = call_with_timeout(mt5.history_deals_get, lo, hi)
                if orders is None or deals is None:          # None = error; () = no rows
                    return {"error": f"HISTORY_READ_FAILED {_last_error(mt5)}"}
                out = count_history([(utc(o.time_setup), str(o.magic)) for o in orders],
                                    [(utc(d.time), str(d.type)) for d in deals], now, "LIVE_ATTACH")
                out["connection"] = {"terminal_connected": bool(getattr(term, "connected", False)),
                                     "account_attached": acct is not None,
                                     "terminal_path": getattr(term, "path", UNKNOWN)}
                return out
            finally:
                try:
                    call_with_timeout(mt5.shutdown)
                except Exception:  # noqa: BLE001 -- a stuck shutdown must not hold the run
                    pass
    except (Mt5Busy, CallTimeout, OSError, AttributeError) as exc:
        return {"error": type(exc).__name__}


def _last_error(mt5) -> str:
    try:
        code, _msg = call_with_timeout(mt5.last_error)
    except Exception:  # noqa: BLE001
        return "code=UNKNOWN"
    return f"code={code}"          # code only: MT5 messages can carry account text


def host_resources(thresholds: Tuple[int, int] = (FREE_RAM_MIN_MB, FREE_DISK_MIN_GB)) -> Dict[str, Any]:
    """Free physical RAM (GlobalMemoryStatusEx) and free space on every fixed drive (stdlib only)."""
    import ctypes
    import shutil
    import string

    class MemStatus(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    ram: Any = UNKNOWN
    disks: Dict[str, Any] = {}
    try:
        st = MemStatus()
        st.dwLength = ctypes.sizeof(MemStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            ram = int(st.ullAvailPhys // 2**20)
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i) and ctypes.windll.kernel32.GetDriveTypeW(f"{letter}:\\") == 3:   # DRIVE_FIXED
                try:
                    disks[letter] = round(shutil.disk_usage(f"{letter}:\\").free / 2**30, 1)
                except OSError:
                    disks[letter] = UNKNOWN
    except (AttributeError, OSError):          # not Windows
        pass
    return assess_resources(ram, disks or UNKNOWN, thresholds)


def assess_resources(free_ram_mb: Any, free_disk_gb: Any, thresholds: Tuple[int, int] = (FREE_RAM_MIN_MB, FREE_DISK_MIN_GB)) -> Dict[str, Any]:
    ram_min, disk_min = thresholds
    reasons = []
    if isinstance(free_ram_mb, int) and free_ram_mb < ram_min:
        reasons.append(f"RAM<{ram_min}MB")
    if isinstance(free_disk_gb, dict):
        reasons += [f"{d}:<{disk_min}GB" for d, gb in sorted(free_disk_gb.items()) if isinstance(gb, float) and gb < disk_min]
    known = isinstance(free_ram_mb, int) and isinstance(free_disk_gb, dict)
    return {"free_ram_mb": free_ram_mb, "free_disk_gb": free_disk_gb,
            "thresholds": {"free_ram_mb": ram_min, "free_disk_gb": disk_min, "state": "PROPOSED_OWNER_CONFIRM"},
            "status": "DEGRADED_RESOURCES" if reasons else ("OK" if known else UNKNOWN), "reasons": reasons}


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


def _window_names(windows: tuple) -> list:
    """Readable names for the resolved windows, so the applied rule is auditable in the output."""
    names = []
    for window in windows:
        if window == ALWAYS_ON_WINDOWS[0]:
            names.append("ALWAYS_ON")
        elif window == AWAKE_DAILY:
            names.append("AWAKE_DAILY")
        elif window == WEEKEND_CRYPTO:
            names.append("WEEKEND_CRYPTO")
        else:
            names.append("UNKNOWN")
    return names


def reader_rule(power_mode: str) -> str:
    """Reader-side staleness rule text, stated for the power mode actually in force."""
    if power_mode == "always_on":
        return (f"age_seconds = now - observed_at_utc; > {READER_STALE_AFTER_S} while the host is "
                "expected active -> STALE (always_on: no sleep span, so no exemption applies)")
    return (f"age_seconds = now - observed_at_utc; > {READER_STALE_AFTER_S} while the host is "
            "scheduled awake -> STALE (wake_sleep: asleep between AG-Sleep-Night and AG-Wake-MT5)")


def build(host_repo: str = DEFAULT_HOST_REPO, now: Optional[dt.datetime] = None, tasks: Any = None,
          history: Optional[Callable[[dt.datetime], Any]] = None, resources: Any = None,
          power_mode: str = DEFAULT_POWER_MODE) -> Dict[str, Any]:
    """`history(now)` -> count_history dict, {"error": ...} or UNKNOWN; None = not read.

    `power_mode` selects the staleness rule (see source_windows). An unrecognised value fails closed
    to the always_on rule rather than inventing a sleep span.
    """
    if power_mode not in POWER_MODES:
        power_mode = "always_on"
    now = (now or utcnow()).astimezone(UTC)
    since = now - dt.timedelta(hours=24)
    full = {name: read_log(host_repo, f"ag_v1_{name}") for name in RUNNER_LOGS}
    logs = {name: _since(v, since) for name, v in full.items()}
    sha = head_sha(host_repo)
    ref, on_main = host_ref(host_repo, sha)
    raw = history(now) if history is not None else UNKNOWN
    hist = raw if isinstance(raw, dict) and "orders" in raw else UNKNOWN
    res = host_resources() if resources is None else resources
    reasons = (["HOST_NOT_ON_MAIN"] if on_main is False else []) + (
        ["DEGRADED_RESOURCES"] if isinstance(res, dict) and res.get("status") == "DEGRADED_RESOURCES" else [])
    return {
        "schema": SCHEMA,
        "status": reasons[0] if reasons else (UNKNOWN if on_main == UNKNOWN else "OK"),
        "status_reasons": reasons,
        "observed_at_utc": now.isoformat(),
        "host_power_mode": power_mode,
        "host_power_mode_source": POWER_MODE_SOURCE[power_mode],
        "reader_rule": reader_rule(power_mode),
        "host_head_sha": sha,
        "host_ref": ref,
        "host_on_main": on_main,
        "mt5_connected": mt5_connected(logs, now),
        "host_resources": res,
        "tasks": scheduled_tasks() if tasks is None else tasks,
        "source_windows": {n: _window_names(source_windows(power_mode, n)) for n in RUNNER_LOGS},
        "sources": {f"ag_v1_{n}.log": source_status(v, now, source_windows(power_mode, n), power_mode)
                    for n, v in full.items()},
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
        "broker_history_24h": hist,
        "broker_history_error": raw.get("error", UNKNOWN) if isinstance(raw, dict) and hist == UNKNOWN else None,
        "broker_order_calls": hist["orders"] if isinstance(hist, dict) else UNKNOWN,
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


def _is_inside(path: str, root: str, pathmod=os.path) -> bool:
    """True when ``path`` is ``root`` or under it. Paths on different drives (Windows
    commonpath ValueError) are not inside the repo."""
    path, root = pathmod.abspath(path), pathmod.abspath(root)
    try:
        return pathmod.normcase(pathmod.commonpath([path, root])) == pathmod.normcase(root)
    except ValueError:
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host-repo", default=DEFAULT_HOST_REPO)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--history-backend", choices=HISTORY_BACKENDS, default="attach",
                    help="attach (default): MetaTrader5 attach like the runners; mcp: mt5ReadOnly proxy; none: skip")
    ap.add_argument("--mcp-launcher", default=DEFAULT_MCP_LAUNCHER, help="mt5ReadOnly MCP launcher (start_mt5_mcp.mjs)")
    ap.add_argument("--no-broker-history", action="store_true", help="same as --history-backend none")
    ap.add_argument("--host-power-mode", choices=POWER_MODES, default=DEFAULT_POWER_MODE,
                    help="staleness rule to apply. wake_sleep (default) = the host state observed "
                         "2026-10-08; always_on = the SCHED-R1-B target, where retired wake/sleep "
                         "tasks mean overnight runner silence is STALE, never INACTIVE_EXPECTED")
    args = ap.parse_args(argv)
    if _is_inside(args.out, args.host_repo):
        print("REFUSED --out is inside the host repo")
        return 2
    backend = "none" if args.no_broker_history else args.history_backend
    history = {"attach": attach_history,
               "mcp": lambda now: broker_history(now, lambda a, b: mcp_history(args.mcp_launcher, a, b)),
               "none": None}[backend]
    payload = build(args.host_repo, history=history, power_mode=args.host_power_mode)
    print(f"HEARTBEAT_WRITTEN {write(payload, args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
