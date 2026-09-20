"""AG Large-SMC live-batch watcher CLI (ST_LARGE_SMC_V1, RESEARCH_ONLY).

AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1 (P4). This script previously contained
two confirmed defects, both now fixed in `large_smc_research.live_watch` (see that
module's docstring for the full analysis and the fix rationale):

  DEFECT 1 (time alignment) -- it passed true-UTC candle times to
  `resample_broker_aligned`, which requires BROKER WALL-CLOCK readings, so H4/D1 were
  bucketed on the wrong boundaries (the exact failure that function exists to prevent).
  Fixed by reconstructing broker wall-clock times from the broker's own detected UTC
  offset.

  DEFECT 2 (no incrementality) -- it re-ran a full 150-day replay on EVERY invocation,
  re-evaluating the entire window forever. Fixed with a persisted watermark, while the
  warm-up lookback is still fetched and loaded in full so warm-up is preserved.

This CLI is now a thin adapter: connect -> fetch -> hand candles to
`live_watch.evaluate_increment` -> fold into the durable ledger -> persist the
watermark. All correctness logic lives in the tested module.

NOT SCHEDULED: this watcher is deliberately not registered with Task Scheduler until
its correctness tests pass and the mission's own gate allows it. Run it manually.

RESEARCH_ONLY / no execution authority: imports ONLY market-data, replay, and
research-ledger modules. Must NEVER import execution.executor, execution.coordinator,
execution.adapter, or mt5.management_gateway -- enforced by
tests/test_large_smc_live_watch_hardening.py.

Usage:
    python scripts/run_large_smc_live_watch.py [--symbol EURUSD] [--json]
                                               [--warmup-lookback-days 150]
                                               [--reset-watermark]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from large_smc_research.decision import STRATEGY_ID  # noqa: E402
from large_smc_research.engine import FROZEN_INSTRUMENT_UNIVERSE, STRATEGY_VERSION  # noqa: E402
from large_smc_research.live_ledger import LargeSMCSetupLedger  # noqa: E402
from large_smc_research.live_watch import (  # noqa: E402
    DEFAULT_WARMUP_LOOKBACK_DAYS,
    LiveWatchError,
    WatchState,
    WatchStateStore,
    build_store,
    check_freshness,
    evaluate_increment,
    next_watermark,
)
from large_smc_research.watch_lifecycle import (  # noqa: E402
    funnel_advances,
    project_setup_rows,
    stage_counts,
)
from historical_replay.orchestrator import run_replay  # noqa: E402
from mt5.broker_time import detect_broker_utc_offset_hours  # noqa: E402
from mt5.connection import connect  # noqa: E402
from mt5.market_data import get_candles  # noqa: E402


def run_once(symbol: str, warmup_lookback_days: int, reset_watermark: bool = False) -> dict:
    if symbol not in FROZEN_INSTRUMENT_UNIVERSE:
        raise SystemExit(
            f"SYMBOL_NOT_IN_FROZEN_UNIVERSE: {symbol!r} not in {FROZEN_INSTRUMENT_UNIVERSE} "
            "(C01 -- no dynamic or inferred symbol inclusion; see strategies/ST_LARGE_SMC_V1.yaml)"
        )

    state_store = WatchStateStore()
    state = state_store.load(STRATEGY_ID, STRATEGY_VERSION, symbol)
    if reset_watermark:
        state = WatchState(STRATEGY_ID, STRATEGY_VERSION, symbol, None, None, 0, None, None)

    connect()

    # The broker's UTC offset is re-detected on EVERY run (never cached across runs):
    # the broker shifts seasonally (UTC+2 winter / +3 summer), so a stored offset would
    # silently misalign D1/H4 after a DST change.
    broker_offset = detect_broker_utc_offset_hours(symbol)

    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc
    start_utc = end_utc - timedelta(days=warmup_lookback_days)
    m5_candles = get_candles(symbol, "M5", start_utc, end_utc)

    if not m5_candles:
        return _report(symbol, state, broker_offset, None, {
            "STATE": "DATA_ERROR", "REASON": "NO_M5_CANDLES_RETURNED",
            "WINDOW": [start_utc.isoformat(), end_utc.isoformat()],
        })

    check_freshness(m5_candles, now_utc)

    result = evaluate_increment(symbol, m5_candles, broker_offset, state)

    # Local initialization: the variables below are only populated on the evaluated
    # path, and must exist (as None) on the no-new-bars path.
    fold_counts = None
    ledger_total = 0
    lifecycle_stages = None
    lifecycle_advances = None
    if not result.skipped_no_new_bars:
        # Same window as the evaluated increment, so this is a deterministic re-derivation
        # of the rows to persist -- kept separate so `evaluate_increment`'s tested
        # contract (no ledger, no I/O) stays exactly what its tests assert.
        store = build_store(symbol, m5_candles, broker_offset)
        replay = run_replay(store, symbol, list(m5_candles),
                            result.window.start_utc, result.window.end_utc)
        ledger = LargeSMCSetupLedger()
        fold_counts = ledger.upsert_many(replay.setup_ledger)
        ledger_total = ledger.count()

        lifecycle_records = project_setup_rows(replay.setup_ledger)
        lifecycle_stages = stage_counts(lifecycle_records)
        lifecycle_advances = funnel_advances(lifecycle_records)

        last_as_of, next_start = next_watermark(result.window, m5_candles)
        state_store.save(WatchState(
            strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION, symbol=symbol,
            last_evaluated_as_of_utc=last_as_of, next_start_utc=next_start,
            runs=state.runs + 1, last_run_utc=now_utc,
            broker_utc_offset_hours=broker_offset,
        ))

    return _report(symbol, state, broker_offset, result, {
        "STATE": "EVALUATED" if not result.skipped_no_new_bars else "NO_NEW_BARS",
        "LEDGER_FOLD": fold_counts,
        "LEDGER_TOTAL_ROWS": ledger_total,
        "LIFECYCLE_STAGE_COUNTS": lifecycle_stages if not result.skipped_no_new_bars else None,
        "LIFECYCLE_FUNNEL_ADVANCES": lifecycle_advances if not result.skipped_no_new_bars else None,
    })


def _report(symbol: str, state: WatchState, broker_offset: int, result, extra: dict) -> dict:
    report = {
        "STRATEGY_ID": STRATEGY_ID,
        "STRATEGY_VERSION": STRATEGY_VERSION,
        "AUTHORITY": "RESEARCH_ONLY -- no proposal/demo/live/execution/risk-sizing authority exercised",
        "SYMBOL": symbol,
        "BROKER_UTC_OFFSET_HOURS": broker_offset,
        "PRIOR_WATERMARK_UTC": state.next_start_utc.isoformat() if state.has_watermark else None,
        "RUNS": state.runs,
    }
    if result is not None:
        report.update({
            "EVALUATION_WINDOW": [result.window.start_utc.isoformat(),
                                  result.window.end_utc.isoformat()],
            "WARMUP_FLOOR_UTC": result.window.warmup_floor_utc.isoformat(),
            "INCREMENTAL_STEPS": result.window.steps,
            "STEPS": {"raw": result.steps, "warmup": result.warmup_steps,
                      "valid": result.valid_steps},
            "THIS_RUN_SETUP_ROWS": result.setup_rows,
            "IDENTITY_COLLISIONS": result.identity_collisions,
            "SKIPPED_NO_NEW_BARS": result.skipped_no_new_bars,
        })
    report.update(extra)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="AG Large-SMC live-batch watcher (RESEARCH_ONLY)")
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--warmup-lookback-days", type=int, default=DEFAULT_WARMUP_LOOKBACK_DAYS)
    parser.add_argument("--reset-watermark", action="store_true",
                        help="discard the persisted watermark and re-evaluate from the warm-up floor")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        report = run_once(args.symbol, args.warmup_lookback_days, args.reset_watermark)
    except LiveWatchError as exc:
        payload = {
            "STRATEGY_ID": STRATEGY_ID, "STRATEGY_VERSION": STRATEGY_VERSION,
            "SYMBOL": args.symbol, "STATE": "REFUSED",
            "REASON_CODE": exc.reason_code, "REASON": str(exc),
            "AUTHORITY": "RESEARCH_ONLY",
        }
        print(json.dumps(payload, indent=2, default=str) if args.json
              else "\n".join(f"{k} = {v}" for k, v in payload.items()))
        sys.exit(2)

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        for key, value in report.items():
            print(f"{key} = {value}")


if __name__ == "__main__":
    main()
