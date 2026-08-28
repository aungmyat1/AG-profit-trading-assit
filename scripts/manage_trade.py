#!/usr/bin/env python
"""Claim a manually-opened MT5 position for automatic trade management (Phase 6, spec
section 7/26). This is the ONLY way a ticket becomes eligible for
scripts/manage_positions.py -- an unclaimed position is never touched.

Usage:
    python scripts/manage_trade.py claim <ticket> --tp1 1.17650 --final-r 5 \\
        [--strategy SESSION_TRADE_V1] [--setup SWEEP] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mt5.account import account, positions
from mt5.connection import MT5ConnectionError, connect
from mt5.market_data import get_tick
from trade_management.claims import DEFAULT_CLAIMS_PATH, claim_position
from trade_management.position_monitor import normalize_position


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)})
        return 1

    acct = account()
    raw = positions(ticket=args.ticket)
    if not raw:
        _report(args, {"status": "POSITION_NOT_FOUND", "ticket": args.ticket})
        return 1

    tick = get_tick(raw[0].symbol)
    position = normalize_position(raw[0], tick, acct)

    claim, reason_code = claim_position(
        position,
        tp1=args.tp1,
        final_r_multiple=args.final_r,
        strategy=args.strategy,
        setup=args.setup,
        path=args.claims_path,
    )

    if claim is None:
        _report(args, {"status": "CLAIM_REJECTED", "reason_code": reason_code, "ticket": args.ticket})
        return 1

    _report(
        args,
        {
            "status": "CLAIMED",
            "ticket": claim.ticket,
            "symbol": claim.symbol,
            "direction": claim.direction,
            "entry_price": claim.entry_price,
            "initial_sl": claim.initial_sl,
            "initial_r_distance": claim.initial_r_distance,
            "tp1": claim.tp1,
            "final_r_multiple": claim.final_r_multiple,
        },
    )
    return 0


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result))
        return
    print("AG Profit Trading -- Manual Trade Claim\n")
    for key, value in result.items():
        print(f"  {key}: {value}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    claim_parser = subparsers.add_parser("claim", help="claim an existing MT5 ticket for management")
    claim_parser.add_argument("ticket", type=int)
    claim_parser.add_argument("--tp1", type=float, default=None, help="TP1 price for the 75%% partial")
    claim_parser.add_argument("--final-r", type=float, required=True, dest="final_r", help="R multiple for the final runner exit (e.g. 5)")
    claim_parser.add_argument("--strategy", default=None)
    claim_parser.add_argument("--setup", default=None)
    claim_parser.add_argument("--claims-path", default=DEFAULT_CLAIMS_PATH, dest="claims_path")
    claim_parser.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
