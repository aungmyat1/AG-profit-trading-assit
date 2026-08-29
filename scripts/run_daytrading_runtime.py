#!/usr/bin/env python
"""Read-only runtime for the two DUAL_DAYTRADING_WORKFLOW_V1 strategies (SESSION_TRADE
completion proposals + SMC_CONDITIONAL alerts). Persists state under journal/runtime/
so restarting this script never re-evaluates a completed session or re-alerts an
already-triggered SMC condition.

NO ORDER SEND. NO order_check. execution_submission is always DISABLED.

Usage:
    python scripts/run_daytrading_runtime.py --once [--json]
    python scripts/run_daytrading_runtime.py --watch --interval 60
    python scripts/run_daytrading_runtime.py --status
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from alerting.sink import JsonlAlertSink, LogAlertSink
from daytrading_runtime.coordinator import DEFAULT_STATE_DIR, RuntimeCoordinator
from daytrading_workflow.universe import DEFAULT_STRATEGY_PATH, load_session_universe
from mt5.connection import MT5ConnectionError, connect
from runtime_state.store import JsonKeyValueStore, StateStoreCorrupted


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.status:
        return _run_status(args)

    try:
        universe = load_session_universe(args.strategy_path)
    except Exception as exc:  # noqa: BLE001 -- any config load failure blocks startup, spec section 29
        _report(args, {"status": "STARTUP_FAILED", "reason_code": "STRATEGY_CONFIG_INVALID", "detail": str(exc)})
        return 2

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_code": str(exc),
                        "execution_submission": "DISABLED"})
        return 1

    try:
        coordinator = RuntimeCoordinator(
            session_strategy_path=args.strategy_path, state_dir=args.state_dir,
            alert_sink=JsonlAlertSink(path=f"{args.state_dir}/smc_alerts_log.jsonl"),
        )
    except StateStoreCorrupted as exc:
        _report(args, {"status": "STATE_STORE_UNAVAILABLE", "reason_code": str(exc)})
        return 1

    _report(args, {"status": "RUNTIME_START", "configured_symbol_count": len(universe.configured_symbols)})

    if args.watch:
        try:
            while True:
                _run_once(args, coordinator)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            # No in-flight state to lose: every write is already atomic (temp-file +
            # os.replace) and persisted before publish, so a bare interrupt here never
            # needs special cleanup -- just exit without a stack trace.
            _report(args, {"status": "RUNTIME_STOPPED", "reason_code": "KEYBOARD_INTERRUPT"})
            return 0
    else:
        _run_once(args, coordinator)
    return 0


def _run_once(args: argparse.Namespace, coordinator: RuntimeCoordinator) -> None:
    try:
        report = coordinator.run_cycle()
    except StateStoreCorrupted as exc:
        _report(args, {"status": "STATE_STORE_UNAVAILABLE", "reason_code": str(exc)})
        return
    _report(args, report)


def _run_status(args: argparse.Namespace) -> int:
    session_store = JsonKeyValueStore(f"{args.state_dir}/session_events.json")
    alert_store = JsonKeyValueStore(f"{args.state_dir}/smc_alerts.json")
    try:
        summary = {
            "state_dir": args.state_dir,
            "session_events_recorded": len(session_store.all()),
            "smc_alerts_recorded": len(alert_store.all()),
            "active_m5_candidates": sum(
                1 for a in alert_store.all().values() if a.get("alert_state") == "WAITING_M5_CONFIRMATION"
            ),
        }
    except StateStoreCorrupted as exc:
        _report(args, {"status": "STATE_STORE_UNAVAILABLE", "reason_code": str(exc)})
        return 1
    _report(args, summary)
    return 0


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result, default=str))
        return
    print("AG Profit Trading -- Daytrading Runtime (READ-ONLY)")
    print(f"  execution_submission = DISABLED")
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            continue
        print(f"  {key} = {value}")
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            print(f"  {key}: {json.dumps(value, default=str)[:500]}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--once", action="store_true")
    mode_group.add_argument("--watch", action="store_true")
    mode_group.add_argument("--status", action="store_true")
    parser.add_argument("--interval", type=int, default=60, help="seconds between cycles in --watch mode")
    parser.add_argument("--strategy-path", default=DEFAULT_STRATEGY_PATH, dest="strategy_path")
    parser.add_argument("--state-dir", default=DEFAULT_STATE_DIR, dest="state_dir")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
