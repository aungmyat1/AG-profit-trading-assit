"""Step 1 of scripts/host/GO_LIVE.md: diagnose the MT5 host (read-only).

    .venv\\Scripts\\python.exe scripts\\host\\diagnose_mt5.py [--terminal-path "C:\\...\\terminal64.exe"]

Checks, in order: Python architecture, MetaTrader5 package, terminal path, initialize()
against the VT Markets demo terminal, account_info, the live server-time offset, and
last_error, plus a checklist for
the Claude Desktop mt5ReadOnly MCP entry. account_info prints ONLY login, server and
trade_mode; balances and equity are never printed or logged. It prints an exact fix for
each failure. Exit code 0 = all checks OK.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _host_common import import_mt5, mt5_initialize, redact  # noqa: E402

FIXES = {
    "PYTHON_ARCH": "MetaTrader5 wheels are 64-bit only: install 64-bit Python 3.11 and recreate .venv "
                   "(py -3.11 -m venv .venv; .venv\\Scripts\\pip install -r requirements.txt).",
    "PACKAGE_MISSING": ".venv\\Scripts\\pip install MetaTrader5==5.0.5735 (Windows only).",
    "TERMINAL_PATH": "Pass --terminal-path to the VT Markets terminal64.exe (right-click the MT5 shortcut -> "
                     "Open file location), or set MT5_TERMINAL_PATH.",
    "TERMINAL_NOT_RUNNING": "Start the VT Markets MT5 terminal, log in to the DEMO account and keep it open "
                            "and connected. 'Allow algorithmic trading' does NOT need to be enabled for read-only use.",
    "NOT_LOGGED_IN": "In MT5: File > Login to Trade Account with the VT Markets DEMO login/server "
                     "(or set VTMARKETS-DEMO-LOGIN / -PASSWORD / -SERVER in src/.env).",
    "NOT_DEMO": "The connected account is not a DEMO account. V1 is informational-only; log in to the "
                "VT Markets DEMO account before continuing.",
    "SERVER_OFFSET": "MT5 tick.time - time.time() disagrees with the owner rule (server midnight = New York "
                     "17:00, i.e. UTC+3 in US DST, UTC+2 otherwise). Check the host clock (w32tm /resync) and the "
                     "broker's server-time convention before trusting any session box; do not patch the offset.",
    "SERVER_OFFSET_NO_TICK": "No fresh tick on any probe symbol (market closed or symbols hidden). Re-run while "
                             "BTCUSD is quoting (it trades 24/7) with the terminal connected.",
    "MCP_CONFIG": "Run: node web\\scripts\\claude_desktop_config.mjs --write  (adds mt5ReadOnly with absolute "
                  "paths), then fully quit and restart Claude Desktop.",
}


def check_python() -> dict:
    bits = struct.calcsize("P") * 8
    return {"check": "python_arch", "ok": bits == 64, "detail": f"{platform.python_version()} {bits}-bit",
            "fix": None if bits == 64 else FIXES["PYTHON_ARCH"]}


def check_terminal_path(path: str) -> dict:
    if not path:
        return {"check": "terminal_path", "ok": True, "detail": "not given; initialize() will auto-detect", "fix": None}
    ok = os.path.isfile(path) and path.lower().endswith("terminal64.exe")
    return {"check": "terminal_path", "ok": ok, "detail": path, "fix": None if ok else FIXES["TERMINAL_PATH"]}


OFFSET_PROBES = ("BTCUSD", "ETHUSD", "EURUSD-VIP")   # 24/7 crypto first: a fresh tick even on FX-closed days


def check_server_offset(mt5, now_ts: "float | None" = None) -> dict:
    """Live check: the offset measured from a fresh tick (MT5 tick.time is broker SERVER wall
    clock as epoch seconds) must equal the owner-rule offset used by the single conversion
    server_time_to_utc. Mismatch or no fresh tick = FAIL."""
    from host_evidence.symbol_metadata import measured_server_offset_hours, server_utc_offset_hours
    now_ts = time.time() if now_ts is None else now_ts
    rule = server_utc_offset_hours(dt.datetime.fromtimestamp(now_ts, dt.timezone.utc))
    for symbol in OFFSET_PROBES:
        tick = mt5.symbol_info_tick(symbol) if hasattr(mt5, "symbol_info_tick") else None
        if tick is None or not getattr(tick, "time", 0):
            continue
        measured = measured_server_offset_hours(tick.time, now_ts)
        if measured is None:  # stale tick: not within 5 min of a whole hour -- try the next probe
            continue
        ok = measured == rule
        return {"check": "server_time_offset", "ok": ok,
                "detail": f"probe={symbol} tick.time-time.time()={tick.time - now_ts:+.0f}s measured=UTC{measured:+d} "
                          f"rule=UTC{rule:+d}", "fix": None if ok else FIXES["SERVER_OFFSET"]}
    return {"check": "server_time_offset", "ok": False, "detail": f"no fresh tick on {list(OFFSET_PROBES)}",
            "fix": FIXES["SERVER_OFFSET_NO_TICK"]}


def check_mt5(mt5, terminal_path: str) -> list:
    if mt5 is None:
        return [{"check": "metatrader5_package", "ok": False, "detail": "not importable", "fix": FIXES["PACKAGE_MISSING"]}]
    out = [{"check": "metatrader5_package", "ok": True, "detail": getattr(mt5, "__version__", "?"), "fix": None}]
    ok, err = mt5_initialize(mt5, terminal_path)
    out.append({"check": "initialize", "ok": ok, "detail": err,
                "fix": None if ok else (FIXES["TERMINAL_PATH"] if "path" in err.lower() else FIXES["TERMINAL_NOT_RUNNING"])})
    if not ok:
        return out
    acct = mt5.account_info()
    if acct is None:
        out.append({"check": "account_info", "ok": False, "detail": redact(str(mt5.last_error())), "fix": FIXES["NOT_LOGGED_IN"]})
    else:
        demo = int(getattr(acct, "trade_mode", -1)) == int(getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
        out.append({"check": "account_info", "ok": True,
                    "detail": f"login={acct.login} server={acct.server} trade_mode={acct.trade_mode}", "fix": None})
        out.append({"check": "demo_account", "ok": demo, "detail": "DEMO" if demo else "NOT DEMO",
                    "fix": None if demo else FIXES["NOT_DEMO"]})
    out.append(check_server_offset(mt5))
    out.append({"check": "last_error", "ok": True, "detail": redact(str(mt5.last_error())), "fix": None})
    mt5.shutdown()
    return out


def check_claude_desktop(appdata: str) -> list:
    cfg = os.path.join(appdata, "Claude", "claude_desktop_config.json")
    logs = os.path.join(appdata, "Claude", "logs")
    out = []
    try:
        with open(cfg, encoding="utf-8") as f:
            entry = (json.load(f).get("mcpServers") or {}).get("mt5ReadOnly")
    except (OSError, ValueError):
        entry = None
    if entry is None:
        out.append({"check": "claude_desktop_mt5ReadOnly", "ok": False, "detail": f"missing in {cfg}", "fix": FIXES["MCP_CONFIG"]})
    else:
        args = entry.get("args") or []
        absolute = bool(args) and all(os.path.isabs(a) for a in args if a.endswith((".mjs", ".js")))
        out.append({"check": "claude_desktop_mt5ReadOnly", "ok": absolute,
                    "detail": f"command={entry.get('command')} args={args}", "fix": None if absolute else FIXES["MCP_CONFIG"]})
    newest = None
    if os.path.isdir(logs):
        mcp = [os.path.join(logs, n) for n in os.listdir(logs) if "mt5" in n.lower() or n.lower().startswith("mcp")]
        newest = max(mcp, key=os.path.getmtime) if mcp else None
    out.append({"check": "claude_desktop_logs", "ok": True, "detail": newest or f"no MCP logs under {logs}", "fix": None})
    return out


def run(mt5, terminal_path: str, appdata: str) -> list:
    return [check_python(), check_terminal_path(terminal_path), *check_mt5(mt5, terminal_path), *check_claude_desktop(appdata)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH", ""))
    args = ap.parse_args(argv)
    results = run(import_mt5(), args.terminal_path, os.environ.get("APPDATA", os.path.expanduser("~")))
    for r in results:
        print(f"[{'OK ' if r['ok'] else 'FAIL'}] {r['check']}: {r['detail']}")
        if r["fix"]:
            print(f"       FIX: {r['fix']}")
    failed = [r for r in results if not r["ok"]]
    print("RESULT:", "ALL_OK" if not failed else f"{len(failed)} FAILED")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
