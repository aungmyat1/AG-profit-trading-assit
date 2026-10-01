"""Compatibility entry point for one read-only MT5 Demo FX scanner cycle.

The former runner depended on packages and a delegated pilot script that are not part of
this checkout.  The maintained host runtime is ``scripts/host/live_candles_smoke.py``;
this entry point now delegates to that implementation so existing scheduled tasks keep
working.  The maintained runtime:

* requires a connected MT5 DEMO account;
* archives READY, NO_TRADE, BLOCKED and DATA_ERROR results before notification;
* creates an R-multiple paper record only for fresh, complete READY tickets;
* contains no broker order or position mutation path.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import io
import json
import os
import sys

HOST_DIR = os.path.join(os.path.dirname(__file__), "host")
if HOST_DIR not in sys.path:
    sys.path.insert(0, HOST_DIR)

# A third-party analysis dependency prints a promotional banner at import time.  Keep
# scheduler/--json output machine-readable without suppressing any runtime output.
with contextlib.redirect_stdout(io.StringIO()):
    import live_candles_smoke as scanner  # noqa: E402

UTC = dt.timezone.utc


def _parse_now(value: str | None) -> dt.datetime:
    now = dt.datetime.fromisoformat(value) if value else dt.datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def _dry_run(cycle: str, now: dt.datetime) -> dict:
    window = scanner.cycle_windows(now)[cycle]["trade"]
    start, end = window
    inside = start <= now <= end + dt.timedelta(minutes=30)
    weekday = now.isoweekday() <= 5
    return {
        "cycle": cycle,
        "evaluated_at_utc": now.isoformat(),
        "window_utc": [start.isoformat(), end.isoformat()],
        "result": "PASS_DRY_RUN" if inside and weekday else "REFUSED",
        "reason": "" if inside and weekday else (
            "REFUSED_WEEKEND_MARKET_CLOSED" if not weekday else "REFUSED_OUTSIDE_EXECUTION_WINDOW"
        ),
        "data_source": "MT5_VT_MARKETS_DEMO",
        "execution_authority": "NONE_PAPER_ONLY",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one archived, paper-only MT5 Demo FX cycle")
    parser.add_argument("--cycle", required=True, choices=scanner.fx_tickets.V1_CYCLES)
    parser.add_argument("--terminal-path", default=os.environ.get("MT5_TERMINAL_PATH", ""))
    parser.add_argument("--dry-run", action="store_true", help="check the UTC window without opening MT5")
    parser.add_argument("--now", default=None, help="ISO-8601 clock override; accepted only with --dry-run")
    parser.add_argument("--json", action="store_true", help="JSON output for --dry-run")
    parser.add_argument("--watch", action="store_true", help="rejected: this runner performs one bounded cycle")
    args = parser.parse_args(argv)

    if args.watch:
        print("REFUSED_WATCH_NOT_SUPPORTED: use one bounded scheduled invocation", file=sys.stderr)
        return 1
    if args.now and not args.dry_run:
        parser.error("--now is test/diagnostic input and requires --dry-run")
    if args.dry_run:
        report = _dry_run(args.cycle, _parse_now(args.now))
        print(json.dumps(report, indent=2, sort_keys=True) if args.json else " ".join(f"{k}={v}" for k, v in report.items()))
        return 0 if report["result"] == "PASS_DRY_RUN" else 2

    # Keep all MT5 access, locking, DEMO verification, archive-before-paper behavior,
    # and shutdown handling in the one maintained runtime.
    delegated = ["--mode", "fx", "--cycle", args.cycle]
    if args.terminal_path:
        delegated += ["--terminal-path", args.terminal_path]
    return scanner.main(delegated)


if __name__ == "__main__":
    raise SystemExit(main())
