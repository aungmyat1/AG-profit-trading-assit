#!/usr/bin/env python
"""ANALYSIS-mode runtime:

MT5 M15 candles -> canonical Candle -> strategy_engine.evaluate() -> compact report.

NO ORDER SEND. NO order_check. NO risk sizing. This script only ever reads market data
and reports what the strategy engine would signal.

Usage:
    python scripts/run_strategy.py --symbol EURUSD [--strategy ST_ASIAN_SWEEP_5R_V1]
        [--pair ASIAN_LONDON] [--date 2026-08-26] [--json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))  # src/, for the top-level packages below

import session_clock as sc
from mt5.account import account
from mt5.connection import MT5ConnectionError, connect
from mt5.market_data import MarketDataError, get_candles
from strategy_engine import evaluate, load_strategy

REGISTRY_PATH = Path(__file__).resolve().parent.parent / "strategies" / "registry.yaml"


def _check_registry_active(strategy_id: str) -> str | None:
    """Return a reason code if strategy_id is not registry-active, else None.

    This script never sizes risk or sends orders, but it can still print a
    signal-shaped result (direction/entry/stop_loss); a non-ACTIVE strategy (e.g.
    ST_LARGE_SMC_V1, RESEARCH_DRAFT) must not be evaluated here either, so this
    gate fails closed on the same registry.yaml the rest of the project treats as
    authoritative rather than relying on incidental schema mismatches.
    """
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        registry = (yaml.safe_load(f) or {}).get("strategies", {})
    entry = registry.get(strategy_id)
    if entry is None or not entry.get("registered"):
        return "STRATEGY_NOT_REGISTERED"
    if not entry.get("active"):
        return "STRATEGY_NOT_ACTIVE"
    return None

# Maps a strategy's own reference_session.name to session_clock's canonical session
# name -- only names that ARE genuinely one of canonical_sessions.yaml's frozen boxes
# belong here. A strategy's trade_session is its own execution window, not a canonical
# box, and is read directly from the strategy config instead (see main()).
_CANONICAL_REFERENCE_SESSION = {
    "Asian": "asian",
    "London": "london_am",
}


def main(argv=None) -> int:
    args = _parse_args(argv)

    block_reason = _check_registry_active(args.strategy)
    if block_reason is not None:
        _report(args, {
            "status": "BLOCKED",
            "reason_code": block_reason,
            "strategy_id": args.strategy,
            "symbol": args.symbol,
            "reference_session": "-",
        })
        return 2

    strategy = load_strategy(f"strategies/{args.strategy}.yaml")
    pair = next((p for p in strategy.session_pairs if p.pair_id == args.pair), None)
    if pair is None:
        known = [p.pair_id for p in strategy.session_pairs]
        print(f"UNKNOWN_PAIR_ID: {args.pair!r} not in {known}", file=sys.stderr)
        return 2

    canonical_name = _CANONICAL_REFERENCE_SESSION.get(pair.reference_session.name)
    if canonical_name is None:
        print(
            f"NO_CANONICAL_MAPPING: {pair.reference_session.name!r} has no entry in "
            f"_CANONICAL_REFERENCE_SESSION; refusing to guess its bounds",
            file=sys.stderr,
        )
        return 2

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_UNAVAILABLE", "reason_code": str(exc)})
        return 1

    now_utc = dt.datetime.now(dt.timezone.utc)
    session_date = args.date or now_utc.date()

    ref_start, ref_end = sc.get_session_bounds(session_date, canonical_name)
    expected_bars = sc.expected_bar_count(canonical_name, strategy.timeframe)

    if not sc.session_complete(now_utc, session_date, canonical_name):
        _report(args, {
            "status": "SESSION_INCOMPLETE",
            "reason_code": "SESSION_INCOMPLETE",
            "reference_session": pair.reference_session.name,
            "session_date": str(session_date),
        })
        return 0

    try:
        ref_candles = get_candles(args.symbol, strategy.timeframe, ref_start, ref_end)
    except MarketDataError as exc:
        _report(args, {"status": "DATA_ERROR", "reason_code": exc.reason_code})
        return 1

    if len(ref_candles) < expected_bars:
        _report(args, {
            "status": "INSUFFICIENT_CANDLES",
            "reason_code": "INSUFFICIENT_CANDLES",
            "got": len(ref_candles),
            "expected": expected_bars,
        })
        return 0

    trade_start = _combine_utc(session_date, pair.trade_session.start_time_gmt)
    trade_end_configured = _combine_utc(session_date, pair.trade_session.end_time_gmt)
    trade_end = min(trade_end_configured, now_utc)

    post_candles = []
    if trade_end > trade_start:
        try:
            post_candles = get_candles(args.symbol, strategy.timeframe, trade_start, trade_end)
        except MarketDataError as exc:
            if exc.reason_code != "DATA_MISSING":  # no candles yet in the trade window is not an error
                _report(args, {"status": "DATA_ERROR", "reason_code": exc.reason_code})
                return 1

    signal = evaluate(strategy, pair.pair_id, args.symbol, session_date, ref_candles, expected_bars, post_candles)
    acct = account()

    _report(args, {
        "status": signal.status,
        "reason_code": signal.reason_code,
        "strategy_id": signal.strategy_id,
        "strategy_version": strategy.version,
        "symbol": signal.symbol,
        "pair_id": signal.pair_id,
        "reference_session": signal.reference_session,
        "regime": signal.regime,
        "setup": signal.setup,
        "direction": signal.direction,
        "entry": signal.entry,
        "stop_loss": signal.stop_loss,
        "risk_distance": signal.risk_distance,
        "mt5_account": acct.login,
        "mt5_server": acct.server,
        "mt5_demo": acct.is_demo,
        "order_sent": False,
    })
    return 0


def _combine_utc(session_date: dt.date, hhmm: str) -> dt.datetime:
    hour, minute = (int(x) for x in hhmm.split(":"))
    return dt.datetime.combine(session_date, dt.time(hour, minute), tzinfo=dt.timezone.utc)


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result))
        return

    print("AG Profit Trading\n")
    print(f"Mode: ANALYSIS")
    if "mt5_server" in result:
        print(f"MT5: CONNECTED ({result['mt5_server']}, {'DEMO' if result['mt5_demo'] else 'LIVE?'})")
    if "strategy_id" in result:
        print(f"\nStrategy: {result['strategy_id']} v{result.get('strategy_version', '?')}")
        print(f"Symbol: {result['symbol']}")
        print(f"Reference: {result['reference_session']}")
        print(f"\nRegime: {result.get('regime', '-')}")
        print(f"Setup: {result.get('setup', '-')}")
        if result.get("direction"):
            print(f"Direction: {result['direction']}")
            print(f"Entry: {result['entry']}")
            print(f"Stop loss: {result['stop_loss']}")
    print(f"\nStatus: {result['status']}")
    print(f"Reason: {result['reason_code']}")
    print(f"Order sent: {'YES' if result.get('order_sent') else 'NO'}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategy", default="ST_ASIAN_SWEEP_5R_V1")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--pair", default="ASIAN_LONDON")
    parser.add_argument("--date", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
