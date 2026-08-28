#!/usr/bin/env python
"""Phase 2 (Market Structure) report tool. Read-only, advisory: swing highs/lows, BOS,
CHoCH, previous high/low, and a deterministic BULLISH/BEARISH/STRUCTURE_STATE_UNDEFINED
summary for one symbol+timeframe -- via market_structure.analyze_structure().

Does not authorize trades. See PROJECT_STATUS.md 'Authority order'.

Usage:
    python scripts/analyze_structure.py --symbol EURUSD --timeframe H1 [--count 200] [--json]
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_structure import analyze_structure
from mt5.connection import MT5ConnectionError, connect


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_codes": [str(exc)]})
        return 1

    result = analyze_structure(args.symbol, args.timeframe, count=args.count)
    _report(args, _to_dict(result))
    return 0 if result.status == "VALID" else 1


def _to_dict(result) -> dict:
    d = dataclasses.asdict(result)
    d["config"] = dataclasses.asdict(result.config) if result.config else None
    return d


def _report(args: argparse.Namespace, d: dict) -> None:
    if args.json:
        print(json.dumps(d, default=str))
        return

    print(f"{d.get('symbol', args.symbol)} {d.get('timeframe', args.timeframe)}\n")
    if d["status"] != "VALID":
        print(f"Status: {d['status']}")
        print(f"Reason: {d.get('reason_codes', ())}")
        return

    print(f"Structure: {d['state']}")
    if d["latest_swing_high"]:
        print(f"Last Swing High: {d['latest_swing_high']['price']} @ {d['latest_swing_high']['time_utc']}")
    if d["latest_swing_low"]:
        print(f"Last Swing Low: {d['latest_swing_low']['price']} @ {d['latest_swing_low']['time_utc']}")
    if d["latest_bos"]:
        kind = getattr(d["latest_bos"]["kind"], "value", d["latest_bos"]["kind"])
        print(f"Latest BOS: {kind} @ {d['latest_bos']['price']} ({d['latest_bos']['time_utc']})")
    else:
        print("Latest BOS: None")
    if d["latest_choch"]:
        kind = getattr(d["latest_choch"]["kind"], "value", d["latest_choch"]["kind"])
        print(f"Latest CHOCH: {kind} @ {d['latest_choch']['price']} ({d['latest_choch']['time_utc']})")
    else:
        print("Latest CHOCH: None")
    if d["previous_high"] is not None:
        print(f"Previous High/Low: {d['previous_high']} / {d['previous_low']}")
    if d["reason_codes"]:
        print(f"Notes: {d['reason_codes']}")

    print(f"\nData:")
    print(f"{d['closed_candle_count']} closed {d.get('timeframe', args.timeframe)} candles")
    print(f"Last candle: {d['data_end_utc']}")
    print(f"Status: {d['status']}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True, choices=["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
