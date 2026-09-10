#!/usr/bin/env python
"""Execute one frontend-confirmed MT5 order through the assistant authority boundary."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
os.environ.setdefault(
    "AG_TRADING_CONFIG_PATH",
    str(Path(__file__).resolve().parent.parent / "config" / "trading.demo.yaml"),
)

from assistant.commands import execute_command
from execution.models import ExecutionSource, TradeCommand
from mt5.connection import MT5ConnectionError, connect_configured


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", choices=("BUY", "SELL"), required=True)
    parser.add_argument("--volume", type=float, required=True)
    parser.add_argument("--entry", type=float)
    parser.add_argument("--sl", type=float, required=True)
    parser.add_argument("--tp", type=float)
    parser.add_argument("--strategy-id", default="FRONTEND_MANUAL")
    parser.add_argument("--command-id")
    parser.add_argument("--confirm", action="store_true")
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        connect_configured()
    except MT5ConnectionError as exc:
        print(json.dumps({"status": "REJECTED", "gate_reason_code": "MT5_NOT_CONNECTED", "reasons": [str(exc)]}))
        return 1

    command = TradeCommand(
        command_id=args.command_id or str(uuid.uuid4()),
        action="OPEN",
        symbol=args.symbol,
        source=ExecutionSource.USER_EXPLICIT_ORDER,
        side=args.side,
        order_type="MARKET",
        volume=args.volume,
        entry=args.entry,
        sl=args.sl,
        tp=args.tp,
        comment=f"AG web | {args.strategy_id}",
    )
    report = execute_command(command, user_confirmed=args.confirm)
    payload = {
        "command_id": report.command_id,
        "status": report.status,
        "gate_reason_code": report.gate_reason_code,
        "reasons": list(report.reasons),
    }
    if report.result is not None:
        payload["order"] = {
            "status": report.result.status,
            "reason_code": report.result.reason_code,
            "symbol": report.result.symbol,
            "side": report.result.side,
            "requested_volume": report.result.requested_volume,
            "filled_volume": report.result.filled_volume,
            "requested_price": report.result.requested_price,
            "fill_price": report.result.fill_price,
            "sl": report.result.sl,
            "tp": report.result.tp,
            "ticket": report.result.ticket,
            "deal_id": report.result.deal_id,
            "broker_retcode": report.result.broker_retcode,
            "broker_comment": report.result.broker_comment,
        }
    print(json.dumps(payload, default=str))
    return 0 if report.status == "EXECUTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
