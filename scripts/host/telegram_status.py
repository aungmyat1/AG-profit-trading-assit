"""Telegram report status for the AG V1 host (read-only; never sends a message).

  py scripts\\host\\telegram_status.py            # human-readable report
  py scripts\\host\\telegram_status.py --json     # machine-readable

Standard library only, so it still runs when the host .venv is missing (that is one of the
faults it reports). It reads, and never writes:
- config/local/delivery_override.yaml   delivery mode + scopes (absent = ARCHIVE_ONLY)
- TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID  presence only (process and Windows User scope);
                                         values are never read into the report or printed
- logs/telegram.log                      last TELEGRAM_SENT_OK / TELEGRAM_SEND_FAILED lines
- logs/ag_v1_<mode>.log                 newest scheduled-runner activity (not ag_v1_smoke)
- .venv/Scripts/python.exe               the interpreter the AG-V1-* tasks launch

Overall status:
  DISABLED  delivery is ARCHIVE_ONLY (repo default) -- nothing is expected to be sent
  DOWN      enabled, but reports cannot go out (no interpreter, or credentials missing)
  DEGRADED  enabled, but the last send failed or the runners have been silent too long
  OK        enabled and nothing above applies
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OVERRIDE = os.path.join("config", "local", "delivery_override.yaml")
SCOPES = ("TICKET_READY", "LSMC_OPPORTUNITY")
# Scheduled-runner logs (logs/ag_v1_<mode>.log); ag_v1_smoke.log is the manual smoke run.
MANUAL_LOGS = ("ag_v1_smoke.log",)
CRED_VARS = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
# The crypto task runs every day, so a healthy host writes a runner log at least daily.
RUNNER_SILENT_AFTER = dt.timedelta(hours=26)
_TS = re.compile(r"^(\S+)\s+(.*)$")


def read_mode(root: str) -> Dict[str, Any]:
    """Same contract as host_delivery.telegram_message.load_mode, without PyYAML."""
    try:
        with open(os.path.join(root, OVERRIDE), encoding="utf-8-sig") as f:
            text = f.read()
    except OSError:
        return {"mode": "ARCHIVE_ONLY", "scopes": []}
    mode = re.search(r"^mode:\s*(\S+)", text, re.M)
    if not mode or mode.group(1) != "MESSAGE_DELIVERY":
        return {"mode": "ARCHIVE_ONLY", "scopes": []}
    scopes = re.search(r"^scopes:\s*\[([^\]]*)\]", text, re.M)
    names = [s.strip() for s in scopes.group(1).split(",")] if scopes else []
    return {"mode": "MESSAGE_DELIVERY", "scopes": [s for s in names if s in SCOPES]}


def _user_env_present(name: str) -> Optional[bool]:
    """Windows User-scope variable presence (what scheduled tasks see); None off Windows."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return bool(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return False


def credentials() -> Dict[str, Dict[str, Optional[bool]]]:
    return {n: {"process": bool(os.environ.get(n)), "user": _user_env_present(n)} for n in CRED_VARS}


def _parse_ts(raw: str) -> Optional[dt.datetime]:
    try:
        ts = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)


def last_events(path: str) -> Dict[str, Optional[Dict[str, str]]]:
    out: Dict[str, Optional[Dict[str, str]]] = {"last_ok": None, "last_failure": None}
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        m = _TS.match(line.strip())
        if not m or _parse_ts(m.group(1)) is None:
            continue
        if "TELEGRAM_SENT_OK" in m.group(2):
            out["last_ok"] = {"at": m.group(1), "detail": m.group(2)}
        elif "TELEGRAM_SEND_FAILED" in m.group(2):
            out["last_failure"] = {"at": m.group(1), "detail": m.group(2)}
    return out


def runner_activity(log_dir: str) -> Optional[dt.datetime]:
    times = [os.path.getmtime(p) for p in glob.glob(os.path.join(log_dir, "ag_v1_*.log"))
             if os.path.basename(p) not in MANUAL_LOGS]
    return dt.datetime.fromtimestamp(max(times), dt.timezone.utc) if times else None


def build_report(root: str = REPO_ROOT, now: Optional[dt.datetime] = None,
                 creds: Optional[Dict[str, Dict[str, Optional[bool]]]] = None) -> Dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    creds = creds if creds is not None else credentials()
    log_dir = os.path.join(root, "logs")
    mode = read_mode(root)
    events = last_events(os.path.join(log_dir, "telegram.log"))
    runner = runner_activity(log_dir)
    venv = os.path.exists(os.path.join(root, ".venv", "Scripts", "python.exe"))

    down: List[str] = []
    degraded: List[str] = []
    if mode["mode"] == "MESSAGE_DELIVERY":
        if not venv:
            down.append("host .venv\\Scripts\\python.exe missing: every AG-V1-* task fails to start")
        for name, seen in creds.items():
            # Scheduled tasks only see User-scope variables; fall back to the process where
            # the User scope cannot be inspected (non-Windows).
            if not (seen["user"] if seen["user"] is not None else seen["process"]):
                down.append(f"{name} not set as a User environment variable")
        if not mode["scopes"]:
            degraded.append("MESSAGE_DELIVERY has no valid scopes: nothing will be sent")
        ok_at = _parse_ts(events["last_ok"]["at"]) if events["last_ok"] else None
        fail_at = _parse_ts(events["last_failure"]["at"]) if events["last_failure"] else None
        if fail_at and (ok_at is None or fail_at > ok_at):
            degraded.append("last send attempt failed: " + events["last_failure"]["detail"])
        if runner is None or now - runner > RUNNER_SILENT_AFTER:
            degraded.append("no scheduled-runner activity for over 26h"
                            + (f" (last {runner.isoformat(timespec='seconds')})" if runner else ""))

    status = ("DISABLED" if mode["mode"] != "MESSAGE_DELIVERY"
              else "DOWN" if down else "DEGRADED" if degraded else "OK")
    return {
        "status": status,
        "checked_at": now.isoformat(timespec="seconds"),
        "delivery": mode,
        "credentials": creds,
        "host_venv_present": venv,
        "telegram_log": events,
        "runner_last_activity": runner.isoformat(timespec="seconds") if runner else None,
        "reasons": down + degraded,
    }


def _yn(v: Optional[bool]) -> str:
    return "n/a" if v is None else ("set" if v else "MISSING")


def render(r: Dict[str, Any]) -> str:
    ok, fail = r["telegram_log"]["last_ok"], r["telegram_log"]["last_failure"]
    lines = [
        f"TELEGRAM_REPORT_STATUS: {r['status']}  (checked {r['checked_at']})",
        f"  delivery mode   : {r['delivery']['mode']}  scopes={','.join(r['delivery']['scopes']) or '-'}",
    ]
    lines += [f"  {n:<18}: process={_yn(c['process'])} user={_yn(c['user'])}"
              for n, c in r["credentials"].items()]
    lines += [
        f"  host .venv      : {'present' if r['host_venv_present'] else 'MISSING'}",
        f"  last sent OK    : {ok['at'] + '  ' + ok['detail'] if ok else 'none logged'}",
        f"  last failure    : {fail['at'] + '  ' + fail['detail'] if fail else 'none logged'}",
        f"  runner activity : {r['runner_last_activity'] or 'none logged'}",
    ]
    lines += [f"  ! {reason}" for reason in r["reasons"]]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Report Telegram delivery status (read-only, sends nothing).")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--root", default=REPO_ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    report = build_report(args.root)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0 if report["status"] in ("OK", "DISABLED") else 1


if __name__ == "__main__":
    sys.exit(main())
