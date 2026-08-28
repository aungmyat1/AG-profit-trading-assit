#!/usr/bin/env python
"""Phase 1 (Market Data) health/report tool. Read-only: connection, account, current
Bid/Ask, latest candles, session-window completeness/high-low, data freshness.

No strategy interpretation (no regime/setup/signal) -- that's strategy_engine's job,
exercised by scripts/run_strategy.py instead.

Usage:
    python scripts/check_mt5.py --symbol EURUSD [--candles 5] [--session asian] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import session_clock as sc
from mt5.account import account
from mt5.connection import MT5ConnectionError, connect
from mt5.market_data import MarketDataError, check_freshness, get_latest_candles, get_tick

MAX_TICK_AGE_SECONDS = 120


def main(argv=None) -> int:
    args = _parse_args(argv)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)})
        return 1

    acct = account()
    result = {
        "status": "OK",
        "mt5_account": acct.login,
        "mt5_server": acct.server,
        "mt5_demo": acct.is_demo,
        "mt5_equity": acct.equity,
        "symbol": args.symbol,
    }

    now_utc = dt.datetime.now(dt.timezone.utc)

    try:
        tick = get_tick(args.symbol)
        staleness = check_freshness(tick.time_utc, now_utc, MAX_TICK_AGE_SECONDS)
        result.update({
            "bid": tick.bid, "ask": tick.ask, "spread_points": tick.spread_points,
            "tick_time_utc": tick.time_utc.isoformat(),
            "data_freshness": staleness or "OK",
        })
    except MarketDataError as exc:
        result.update({"status": "DATA_ERROR", "reason_code": exc.reason_code})
        _report(args, result)
        return 1

    try:
        candles = get_latest_candles(args.symbol, "M15", args.candles)
        result["latest_candles"] = [
            {"time": c.time.isoformat(), "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume}
            for c in candles
        ]
    except MarketDataError as exc:
        result.update({"status": "DATA_ERROR", "reason_code": exc.reason_code})
        _report(args, result)
        return 1

    if args.session:
        session_date = now_utc.date()
        start, end = sc.get_session_bounds(session_date, args.session)
        complete = sc.session_complete(now_utc, session_date, args.session)
        result["session"] = {"name": args.session, "date": str(session_date), "complete": complete}
        if complete:
            try:
                from mt5.market_data import get_candles
                session_candles = get_candles(args.symbol, "M15", start, end)
                result["session"]["bar_count"] = len(session_candles)
                result["session"]["expected_bar_count"] = sc.expected_bar_count(args.session, "M15")
                result["session"]["high"] = max(c.high for c in session_candles)
                result["session"]["low"] = min(c.low for c in session_candles)
            except MarketDataError as exc:
                result["session"]["reason_code"] = exc.reason_code

    _report(args, result)
    return 0


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result))
        return

    print("AG Profit Trading -- Market Data Check\n")
    if result["status"] != "OK" and "mt5_account" not in result:
        print(f"Status: {result['status']}")
        print(f"Reason: {result.get('reason_code', '-')}")
        return

    print(f"MT5: CONNECTED ({result['mt5_server']}, {'DEMO' if result['mt5_demo'] else 'LIVE?'})")
    print(f"Account: {result['mt5_account']}  Equity: {result['mt5_equity']}\n")

    if result["status"] != "OK":
        print(f"Status: {result['status']}")
        print(f"Reason: {result.get('reason_code', '-')}")
        return

    print(f"{result['symbol']}")
    print(f"Bid/Ask: {result['bid']} / {result['ask']}  Spread(pts): {result['spread_points']}")
    print(f"Tick time: {result['tick_time_utc']}  Freshness: {result['data_freshness']}\n")

    print(f"Latest {len(result['latest_candles'])} M15 candles:")
    for c in result["latest_candles"]:
        print(f"  {c['time']}  O:{c['open']} H:{c['high']} L:{c['low']} C:{c['close']} V:{c['volume']}")

    if "session" in result:
        s = result["session"]
        print(f"\nSession ({s['name']}, {s['date']}): {'COMPLETE' if s['complete'] else 'INCOMPLETE'}")
        if "high" in s:
            print(f"  Bars: {s['bar_count']}/{s['expected_bar_count']}  High: {s['high']}  Low: {s['low']}")
        elif "reason_code" in s:
            print(f"  Reason: {s['reason_code']}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--candles", type=int, default=5)
    parser.add_argument("--session", choices=["asian", "london_am", "new_york_am"], default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
