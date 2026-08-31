#!/usr/bin/env python
"""AG_DAYTRADING_RUNTIME_V1: deterministic runtime entrypoint connecting closed-M5-bar
market timing/data -> ST_LIQUIDITY_SWEEP_RETEST_V1 strategy evaluation -> TradeProposal ->
ExecutionRuntimeContext/ExecutionCoordinator -> lifecycle reconciliation.

Forex (EURUSD, GBPUSD): DEMO + MANDATORY EXPLICIT CONFIRMATION. Reaching ENTRY_READY only
ever produces a CONFIRMATION_REQUIRED proposal -- this script NEVER auto-confirms. Use
`--confirm SYMBOL SETUP_ID` in a separate, deliberate invocation to explicitly confirm and
submit a pending ENTRY_READY setup (interactive y/N prompt; nothing here can bypass it).

Crypto (BTCUSDT, ETHUSDT): DISABLED BY DESIGN -- no crypto candle data source exists
anywhere in this repo (audited: no binance/bybit/ccxt/klines integration found). The
runtime interface is pluggable (see execution_runtime/crypto_feed.py) but this script
never constructs a feed, so the crypto path never runs and never sees fabricated candles.

Usage:
    python scripts/run_ag_execution_runtime.py --once [--json]
    python scripts/run_ag_execution_runtime.py --watch --interval 60
    python scripts/run_ag_execution_runtime.py --status
    python scripts/run_ag_execution_runtime.py --confirm EURUSD EURUSD:2026-01-05
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from execution.runtime_context import ExecutionRuntimeContext
from execution_runtime import data_provider
from execution_runtime.cycle import confirm_and_submit, evaluate_and_route
from execution_runtime.startup import DEFAULT_STRATEGY_PATH, StartupReconciliationFailed, start
from mt5.connection import MT5ConnectionError, connect

FOREX_SYMBOLS = ("EURUSD", "GBPUSD")


def main(argv=None) -> int:
    args = _parse_args(argv)

    if args.status:
        return _run_status(args)

    try:
        connect()
    except MT5ConnectionError as exc:
        _report(args, {"status": "MT5_NOT_CONNECTED", "reason_code": str(exc)})
        return 1

    try:
        startup = start(strategy_path=args.strategy_path)
    except StartupReconciliationFailed as exc:
        _report(args, {"status": "STARTUP_FAILED", "reason_code": "RECONCILIATION_FAILED", "detail": str(exc)})
        return 2
    except Exception as exc:  # noqa: BLE001 -- any config/state-store failure blocks startup (spec)
        _report(args, {"status": "STARTUP_FAILED", "reason_code": "STARTUP_ERROR", "detail": str(exc)})
        return 2

    _report(args, {
        "status": "RUNTIME_START", "forex_symbols": list(FOREX_SYMBOLS), "crypto_status": "DISABLED_NO_FEED",
        "reconciliation_results": startup.reconciliation_results,
    })

    if args.confirm:
        symbol, setup_id = args.confirm
        return _run_confirm(args, startup, symbol, setup_id)

    if args.watch:
        try:
            while True:
                _run_cycle(args, startup)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            _report(args, {"status": "RUNTIME_STOPPED", "reason_code": "KEYBOARD_INTERRUPT"})
            return 0
    else:
        _run_cycle(args, startup)
    return 0


def _run_cycle(args: argparse.Namespace, startup) -> None:
    # Reconciliation runs independently of signal evaluation on every cycle (spec
    # RECONCILIATION LOOP: "do not wait for a new M5 candle to detect a broker position
    # close") -- same ctx.coordinator.reconcile() call startup already used.
    reconcile_results = startup.ctx.coordinator.reconcile()
    equity = data_provider.fetch_equity()

    results = []
    for symbol in FOREX_SYMBOLS:
        profile_config = startup.strategy_config.profile_config_for_symbol(symbol)
        if profile_config is None:
            continue
        result = evaluate_and_route(
            symbol=symbol, profile_config=profile_config, strategy_config=startup.strategy_config,
            runtime=startup.runtime, bar_tracker=startup.bar_tracker, ctx=startup.ctx,
            fetch_m5_candles=data_provider.fetch_m5_candles, fetch_h1_candles=data_provider.fetch_h1_candles,
            fetch_reference_candles=data_provider.fetch_forex_reference_candles,
            symbol_meta=data_provider.fetch_symbol_meta(symbol),
            stop_buffer_price=data_provider.forex_stop_buffer_price(symbol, profile_config),
            reference_expected_bar_count=data_provider.reference_expected_bar_count(profile_config),
            equity=equity, user_confirmed=False,
        )
        results.append({"symbol": symbol, "status": result.status,
                         "setup_state": result.setup_state.state if result.setup_state else None})
    _report(args, {"status": "CYCLE_COMPLETE", "reconciliation_results": reconcile_results, "results": results})


def _run_confirm(args: argparse.Namespace, startup, symbol: str, setup_id: str) -> int:
    """The ONE mandatory human-in-the-loop step (spec: no auto-confirm flag anywhere) --
    always an interactive y/N prompt; --json mode still requires a real terminal
    confirmation and is not a way to script around it."""
    pending = startup.runtime.store.load(setup_id)
    if pending is None or pending.state != "ENTRY_READY":
        _report(args, {"status": "NO_PENDING_ENTRY_READY_SETUP", "setup_id": setup_id})
        return 1

    print(f"Pending {symbol} setup {setup_id}: {pending.direction} entry={pending.entry} "
          f"sl={pending.stop_loss} tp1={pending.tp1} tp2={pending.tp2} volume={pending.volume}")
    answer = input("Explicitly confirm and submit this order? [y/N] ").strip().lower()
    if answer != "y":
        _report(args, {"status": "CONFIRMATION_DECLINED", "setup_id": setup_id})
        return 0

    result = confirm_and_submit(symbol=symbol, setup_id=setup_id, runtime=startup.runtime, ctx=startup.ctx)
    _report(args, {"status": result.status, "setup_id": setup_id,
                    "coordinator_status": result.coordinator_result.status if result.coordinator_result else None})
    return 0


def _run_status(args: argparse.Namespace) -> int:
    ctx = ExecutionRuntimeContext.default()
    summary = {
        "open_positions": ctx.open_position_guard.open_count(),
        "open_position_blocked": ctx.open_position_guard.is_blocked(),
        "crypto_status": "DISABLED_NO_FEED",
    }
    _report(args, summary)
    return 0


def _report(args: argparse.Namespace, result: dict) -> None:
    if args.json:
        print(json.dumps(result, default=str))
        return
    print("AG Profit Trading -- Daytrading Execution Runtime (Forex demo + explicit confirmation)")
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            continue
        print(f"  {key} = {value}")
    for key, value in result.items():
        if isinstance(value, (dict, list)):
            print(f"  {key}: {json.dumps(value, default=str)[:800]}")


def _parse_args(argv) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode_group = parser.add_mutually_exclusive_group(required=False)
    mode_group.add_argument("--once", action="store_true")
    mode_group.add_argument("--watch", action="store_true")
    mode_group.add_argument("--status", action="store_true")
    parser.add_argument("--confirm", nargs=2, metavar=("SYMBOL", "SETUP_ID"), default=None,
                         help="Explicitly confirm and submit a pending ENTRY_READY setup (interactive prompt). "
                              "Runs startup/reconciliation first, same as --once, then confirms instead of polling.")
    parser.add_argument("--interval", type=int, default=60, help="seconds between cycles in --watch mode")
    parser.add_argument("--strategy-path", default=DEFAULT_STRATEGY_PATH, dest="strategy_path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not (args.once or args.watch or args.status or args.confirm):
        parser.error("one of --once, --watch, --status, or --confirm is required")
    return args


if __name__ == "__main__":
    sys.exit(main())
