#!/usr/bin/env python
"""Run one explicitly requested management action through the claimed-position manager."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("AG_TRADING_CONFIG_PATH", str(ROOT / "config" / "trading.demo.yaml"))

from mt5.connection import MT5ConnectionError, connect_configured
from trade_management.manager import run_cycle_for_ticket


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticket", type=int, required=True)
    parser.add_argument("--action", choices=("BREAKEVEN", "PARTIAL_CLOSE", "CLOSE"), required=True)
    args = parser.parse_args(argv)
    try:
        connect_configured()
    except MT5ConnectionError as exc:
        print(json.dumps({"outcome": "BLOCKED", "detail": str(exc), "ticket": args.ticket}))
        return 1

    expected = {"BREAKEVEN": "MOVE_SL", "PARTIAL_CLOSE": "PARTIAL_CLOSE", "CLOSE": "CLOSE"}[args.action]
    result = run_cycle_for_ticket(args.ticket, expected_action=expected)
    payload = {
        "ticket": result.ticket,
        "outcome": result.outcome,
        "detail": result.detail,
        "action": result.intent.action if result.intent else None,
        "reason_code": result.intent.reason_code if result.intent else None,
    }
    print(json.dumps(payload))
    return 0 if result.outcome == "EXECUTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
