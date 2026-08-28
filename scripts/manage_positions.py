#!/usr/bin/env python
"""Runs one (or repeated) trade-management cycles over every claimed ticket (Phase 6,
spec section 25). Ordinary deterministic Python -- no AI/model call per cycle.

Whether any action actually reaches the broker is controlled entirely by
config/trading.yaml's `trade_management:` block (mode: DRY_RUN|LIVE +
allow_live_management), not by a flag on this script -- a second, script-level gate
would risk contradicting the config one (spec section 32). This script only reports
which mode is currently active.

Usage:
    python scripts/manage_positions.py --once [--json]
    python scripts/manage_positions.py --watch --interval 15
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml

from mt5.connection import MT5ConnectionError, connect
from trade_management.claims import DEFAULT_CLAIMS_PATH, load_claims
from trade_management.manager import run_cycle_for_ticket

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "trading.yaml"


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, [{"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)}])
        return 1

    if args.watch:
        while True:
            _run_once(args)
            time.sleep(args.interval)
    else:
        _run_once(args)
    return 0


def _run_once(args: argparse.Namespace) -> None:
    mode = _current_mode()
    claims = load_claims(args.claims_path)
    results = [
        {
            "ticket": r.ticket,
            "outcome": r.outcome,
            "detail": r.detail,
            "action": r.intent.action if r.intent else None,
        }
        for r in (run_cycle_for_ticket(ticket, args.claims_path) for ticket in claims)
    ]
    _report(args, results, mode=mode)


def _current_mode() -> dict:
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    tm = config.get("trade_management", {}) or {}
    return {"mode": tm.get("mode"), "allow_live_management": tm.get("allow_live_management")}


def _report(args: argparse.Namespace, results: list, mode: dict = None) -> None:
    if args.json:
        print(json.dumps({"mode": mode, "results": results}))
        return
    print("AG Profit Trading -- Trade Management Cycle")
    if mode is not None:
        print(f"  trade_management.mode={mode['mode']} allow_live_management={mode['allow_live_management']}")
    if not results:
        print("  No claimed tickets.")
        return
    for r in results:
        print(f"  ticket={r['ticket']} outcome={r['outcome']} action={r['action']} detail={r['detail']}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument("--once", action="store_true")
    mode_group.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=15, help="seconds between cycles in --watch mode")
    parser.add_argument("--claims-path", default=DEFAULT_CLAIMS_PATH, dest="claims_path")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
