#!/usr/bin/env python
"""Open or close an MT5 position through the central Trade Assistant execution layer
(execution/executor.py, Execution authority restructure 2026-08-28).

Without --confirm, runs the full gate/validation pipeline in dry-run mode and reports
the exact broker request that would be sent, touching no live order (mirrors
mt5.management_gateway's existing dry-run-by-default behavior). --confirm is the literal
encoding of "explicit user execution command" -- pass it only when the user has just
given an explicit instruction to execute.

Usage:
    python scripts/execute_trade.py open --symbol EURUSD --side SELL --volume 0.31 \\
        --sl 1.16460 --tp 1.16332 --source USER_EXPLICIT_ORDER [--confirm] [--json]

    python scripts/execute_trade.py open --symbol EURUSD --side SELL --risk-percent 1.0 \\
        --sl 1.16460 --tp 1.16332 --source USER_EXPLICIT_ORDER [--confirm] [--json]

    # ASSISTANT_PROPOSAL: side/SL/TP/risk_percent resolved FROM the stored proposal --
    # do not retype them. Requires the proposal to have been built in this SAME process
    # (the proposal store is in-memory/process-local -- see execution/executor.py's
    # ProposalStore docstring).
    python scripts/execute_trade.py open --proposal-id <id> --source ASSISTANT_PROPOSAL \\
        [--confirm] [--json]

    python scripts/execute_trade.py close --ticket 12345678 [--confirm] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from execution.executor import execute
from execution.models import ExecutionSource, TradeCommand
from mt5.connection import MT5ConnectionError, connect


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)})
        return 1

    command_id = args.command_id or str(uuid.uuid4())

    if args.command == "open":
        if not args.proposal_id and (args.side is None or args.sl is None or args.symbol is None):
            _report(args, {"status": "INVALID_ARGS",
                            "reason_code": "SYMBOL_SIDE_AND_SL_REQUIRED_WITHOUT_PROPOSAL_ID"})
            return 1
        command = TradeCommand(
            command_id=command_id,
            action="OPEN",
            symbol=args.symbol or "",
            side=args.side,
            order_type="MARKET",
            volume=args.volume,
            entry=args.entry,
            sl=args.sl,
            tp=args.tp,
            risk_percent=args.risk_percent,
            source=ExecutionSource(args.source),
            proposal_id=args.proposal_id,
            comment=args.comment or "",
            magic_number=args.magic,
        )
    else:
        command = TradeCommand(
            command_id=command_id,
            action="CLOSE",
            symbol=args.symbol or "",
            side=None,
            source=ExecutionSource(args.source),
            volume=args.volume,
            position_ticket=args.ticket,
        )

    report = execute(command, user_confirmed=args.confirm)

    result = {
        "command_id": report.command_id,
        "source": report.source.value,
        "status": report.status,
        "gate_reason_code": report.gate_reason_code,
    }
    if report.result is not None:
        result["order"] = {
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
            "request": report.result.request,
        }

    _report(args, result)
    return 0 if report.status == "EXECUTED" or not args.confirm else 1


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result, default=str))
        return
    print("AG Profit Trading -- Execute Trade\n")
    print(json.dumps(result, indent=2, default=str))


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    open_parser = subparsers.add_parser("open", help="open a new position")
    open_parser.add_argument("--symbol", default=None, help="required unless --proposal-id is given")
    open_parser.add_argument("--side", choices=["BUY", "SELL"], default=None, help="required unless --proposal-id is given")
    open_parser.add_argument("--volume", type=float, default=None, help="explicit lot size; omit to size from --risk-percent")
    open_parser.add_argument("--risk-percent", type=float, default=None, dest="risk_percent")
    open_parser.add_argument("--entry", type=float, default=None, help="omit for market price")
    open_parser.add_argument("--sl", type=float, default=None, help="required unless --proposal-id is given")
    open_parser.add_argument("--tp", type=float, default=None)
    open_parser.add_argument("--source", choices=[s.value for s in ExecutionSource], default=ExecutionSource.USER_EXPLICIT_ORDER.value)
    open_parser.add_argument("--proposal-id", default=None, dest="proposal_id")
    open_parser.add_argument("--comment", default=None)
    open_parser.add_argument("--magic", type=int, default=0)
    open_parser.add_argument("--command-id", default=None, dest="command_id")
    open_parser.add_argument("--confirm", action="store_true")
    open_parser.add_argument("--json", action="store_true")

    close_parser = subparsers.add_parser("close", help="close an existing position")
    close_parser.add_argument("--ticket", type=int, required=True)
    close_parser.add_argument("--symbol", default=None)
    close_parser.add_argument("--volume", type=float, default=None, help="omit for full close")
    close_parser.add_argument("--source", choices=[s.value for s in ExecutionSource], default=ExecutionSource.USER_EXPLICIT_ORDER.value)
    close_parser.add_argument("--command-id", default=None, dest="command_id")
    close_parser.add_argument("--confirm", action="store_true")
    close_parser.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
