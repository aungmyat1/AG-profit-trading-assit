"""AG Large-SMC live-batch watcher CLI (ST_LARGE_SMC_V1, RESEARCH_ONLY).

AG_PROPOSAL_RUNTIME_LARGE_SMC_WATCH_AND_PERFORMANCE_HISTORY_V1, narrow-batch scope: a
true continuous/incremental live watcher would require porting E1/E2/E3 detection to
run bar-by-bar on freshly-closed live candles (not built here -- see this task's own
audit). This script instead re-runs the EXISTING, unmodified detection/replay machinery
(`historical_replay.orchestrator.run_replay`, the same engine
scripts/run_large_smc_discovery.py already uses against a frozen historical CSV) once
per invocation against a FRESH window of live MT5 candles, then folds the result into a
durable cross-run ledger (`large_smc_research.live_ledger.LargeSMCSetupLedger`) so
nothing observed is lost between runs. Intended to be invoked once daily (cron/Task
Scheduler), like scripts/run_btc_daily_report.py.

No E1/E2/E3/M1/M2/M3 detection logic is duplicated here -- this script only supplies
live-fetched candles to the unchanged `run_replay` engine and persists its unchanged
`SetupLedgerRow` output.

RESEARCH_ONLY / no execution authority: this script imports ONLY market-data and
research-ledger modules. It must NEVER import execution.executor, execution.coordinator,
execution.adapter, or mt5.management_gateway -- see
tests/test_large_smc_live_watch_execution_boundary.py for the enforced boundary. No
proposal, demo, or live order is possible from any path reachable here.

The rolling window overlaps the previous run by design (default 150 days, well beyond
the 60 D1 / 50 H1 / 200 M5 warmup candles `run_replay` itself requires) specifically so
a setup_id first observed near a prior window's start is re-observed and can progress in
this run too -- LargeSMCSetupLedger.upsert_many is idempotent, so re-observing an
unchanged row is a safe no-op (see its own "unchanged" counter).

Usage:
    python scripts/run_large_smc_live_watch.py [--symbol EURUSD] [--lookback-days 150] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay import HistoricalCandleStore, resample, resample_broker_aligned  # noqa: E402
from historical_replay.orchestrator import run_replay  # noqa: E402
from large_smc_research.engine import FROZEN_INSTRUMENT_UNIVERSE, STRATEGY_VERSION  # noqa: E402
from large_smc_research.decision import STRATEGY_ID  # noqa: E402
from large_smc_research.live_ledger import LargeSMCSetupLedger  # noqa: E402
from mt5.connection import connect  # noqa: E402
from mt5.market_data import get_candles  # noqa: E402

DEFAULT_LOOKBACK_DAYS = 150


def _build_store(symbol: str, m5_candles):
    store = HistoricalCandleStore()
    store.load_series(symbol, "M5", m5_candles)
    # Broker-time offsets are only needed for resample_broker_aligned; live M5 candles
    # already carry broker-server open times (mt5.market_data.get_candles), so we pass
    # each candle's own `.time` straight through -- identical inputs to what
    # historical_replay.mt5_export_loader.load_mt5_export_csv's ingestion_report.broker_times
    # would supply for a CSV covering the same window.
    broker_times = [c.time for c in m5_candles]
    for tf in ("M15", "H1"):
        store.load_series(symbol, tf, resample(m5_candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series(symbol, tf, resample_broker_aligned(m5_candles, broker_times, "M5", tf))
    return store


def run_once(symbol: str, lookback_days: int) -> dict:
    if symbol not in FROZEN_INSTRUMENT_UNIVERSE:
        raise SystemExit(
            f"SYMBOL_NOT_IN_FROZEN_UNIVERSE: {symbol!r} not in {FROZEN_INSTRUMENT_UNIVERSE} "
            "(C01 -- no dynamic or inferred symbol inclusion; see strategies/ST_LARGE_SMC_V1.yaml)"
        )

    connect()
    end_utc = datetime.now(timezone.utc)
    start_utc = end_utc - timedelta(days=lookback_days)
    m5_candles = get_candles(symbol, "M5", start_utc, end_utc)
    if not m5_candles:
        return {
            "STRATEGY_ID": STRATEGY_ID, "STRATEGY_VERSION": STRATEGY_VERSION, "SYMBOL": symbol,
            "STATE": "DATA_ERROR", "REASON": "NO_M5_CANDLES_RETURNED",
            "WINDOW": [start_utc.isoformat(), end_utc.isoformat()],
        }

    store = _build_store(symbol, m5_candles)
    result = run_replay(store, symbol, m5_candles, start_utc, end_utc)

    ledger = LargeSMCSetupLedger()
    fold_counts = ledger.upsert_many(result.setup_ledger)

    return {
        "STRATEGY_ID": STRATEGY_ID,
        "STRATEGY_VERSION": STRATEGY_VERSION,
        "AUTHORITY": "RESEARCH_ONLY -- no proposal/demo/live/execution/risk-sizing authority exercised",
        "SYMBOL": symbol,
        "WINDOW": [start_utc.isoformat(), end_utc.isoformat()],
        "STEPS": {"raw": result.steps, "warmup": result.warmup_steps, "valid": result.valid_steps},
        "THIS_RUN_SETUP_ROWS": len(result.setup_ledger),
        "LEDGER_FOLD": fold_counts,
        "LEDGER_TOTAL_ROWS": ledger.count(),
        "IDENTITY_COLLISIONS": result.identity_collisions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AG Large-SMC live-batch watcher (RESEARCH_ONLY)")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run_once(args.symbol, args.lookback_days)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        for key, value in report.items():
            print(f"{key} = {value}")


if __name__ == "__main__":
    main()
