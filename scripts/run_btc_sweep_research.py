"""AG BTC Sweep Research CLI entrypoint (Binance USDT-M perpetual, BTCUSDT,
ST_LIQUIDITY_SWEEP_RETEST_V1 CRYPTO_PERP profile).

RESEARCH_ONLY / SHADOW / PROPOSAL_ONLY, always. This script imports ONLY: the Binance
public-market-data feed adapter, and btc_sweep_research's own orchestration -- it must
NEVER import execution.executor, mt5.management_gateway, execution.coordinator, or
execution.adapter (see src/btc_sweep_research/pipeline.py's module docstring for why; see
tests/test_btc_proposal_execution_boundary.py for the enforced boundary). No code path
reachable from this script can submit a real or demo order on any exchange.

Modeled on scripts/run_post_asian_pilot.py's --once/--watch split, scaled to this
package's single-symbol scope.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from btc_sweep_research.pipeline import run_research_cycle  # noqa: E402
from btc_sweep_research.report import cycle_to_dict, human_readable_report  # noqa: E402
from execution_runtime.binance_usdtm_feed import BinanceUSDTMFeed  # noqa: E402


def _run_once(as_json: bool):
    feed = BinanceUSDTMFeed()
    result = run_research_cycle(feed)
    if as_json:
        print(json.dumps(cycle_to_dict(result), indent=2, default=str))
    else:
        print(human_readable_report(result))
    return result


def _watch_signature(report):
    if report.container_state is not None:
        return ("CONTAINER", report.container_state.state, report.container_state.reason_code)
    return tuple((o.setup_state.setup_id, o.setup_state.state, o.setup_state.reason_code, o.ledger_new_row)
                for o in report.occurrences)


def _run_watch(as_json: bool, interval: int) -> None:
    feed = BinanceUSDTMFeed()
    last_signature = None
    while True:
        try:
            report = run_research_cycle(feed)
        except Exception as exc:  # noqa: BLE001 -- an operational error is itself an event to report
            print(f"[{datetime.now(timezone.utc).isoformat()}] ERROR: {exc}")
            time.sleep(interval)
            continue

        signature = _watch_signature(report)
        if signature != last_signature:
            if as_json:
                print(json.dumps(cycle_to_dict(report), indent=2, default=str))
            else:
                print(human_readable_report(report))
            last_signature = signature
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AG BTC Sweep Research (Binance USDT-M BTCUSDT, RESEARCH_ONLY, PROPOSAL_ONLY)"
    )
    parser.add_argument("--once", action="store_true", help="run a single evaluation cycle (default)")
    parser.add_argument("--watch", action="store_true", help="continuous, event-driven observation")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of the human-readable report")
    args = parser.parse_args()

    if args.watch:
        _run_watch(args.json, args.interval)
    else:
        _run_once(args.json)


if __name__ == "__main__":
    main()
