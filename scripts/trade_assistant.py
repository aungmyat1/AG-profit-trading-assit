#!/usr/bin/env python
"""ASSISTANT_RUNTIME_V1 CLI entry point. Runs the Trade Assistant against a registered
strategy/symbol/cycle in one of the three explicit modes.

Usage:
    python scripts/trade_assistant.py --strategy SESSION_TRADE_V1 --symbol EURUSD \\
        --cycle ASIAN_LONDON --mode ANALYZE_ONLY [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from assistant import report as assistant_report
from assistant import runtime
from assistant.models import ALL_MODES
from mt5.connection import MT5ConnectionError, connect


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)})
        return 1

    decision = runtime.evaluate(args.strategy, args.symbol, args.cycle, args.mode)

    if args.json:
        print(json.dumps({
            "run_id": decision.run_id, "status": decision.status,
            "strategy_status": decision.strategy_status, "setup": decision.setup,
            "direction": decision.direction, "entry": decision.entry, "stop_loss": decision.stop_loss,
            "target": decision.target, "signal_id": decision.signal_id,
            "reason_codes": list(decision.reason_codes), "execution_mode": decision.execution_mode,
        }))
    else:
        print(assistant_report.render(decision))
    return 0


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result))
    else:
        print(f"Status: {result['status']}")
        print(f"Reason: {result.get('reason_code', '-')}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--cycle", required=True)
    parser.add_argument("--mode", required=True, choices=ALL_MODES)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
