"""Runs SMC_3X3_HISTORICAL_VALIDATION_V1's chronological replay over a real historical
CSV export and writes the semantic-replay report as JSON.

Usage:
    python scripts/run_historical_replay.py <csv_path> <symbol> <start_iso> <end_iso> <out_json_path>

Example:
    python scripts/run_historical_replay.py D:\\EURUSD_M5_202504211715_202607310000.csv \\
        EURUSD 2025-08-01T00:00:00 2025-08-15T00:00:00 docs/status/replay_sample.json
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned  # noqa: E402
from historical_replay.orchestrator import run_replay  # noqa: E402


def main() -> None:
    csv_path, symbol, start_iso, end_iso, out_path = sys.argv[1:6]
    start_utc = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
    end_utc = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)

    t0 = time.time()
    candles, ingestion_report = load_mt5_export_csv(csv_path, symbol, "M5")
    store = HistoricalCandleStore()
    store.load_series(symbol, "M5", candles)
    derived = {}
    for tf in ("M15", "H1"):
        d = resample(candles, "M5", tf)
        store.load_series(symbol, tf, d)
        derived[tf] = len(d)
    for tf in ("H4", "D1"):
        # Broker-day-anchored, not UTC-midnight -- see historical_replay.resampler
        # module docstring: MT5's own D1/H4 candles are anchored to the broker's
        # calendar day/4h window, confirmed by cross-checking against a native MT5 D1
        # export (this phase's finding).
        d = resample_broker_aligned(candles, ingestion_report.broker_times, "M5", tf)
        store.load_series(symbol, tf, d)
        derived[tf] = len(d)
    load_time = time.time() - t0

    t0 = time.time()
    result = run_replay(store, symbol, candles, start_utc, end_utc)
    replay_time = time.time() - t0

    report = {
        "DATA": {
            "SOURCE": csv_path, "SYMBOL": symbol, "BASE_RESOLUTION": "M5",
            "DATE_RANGE_REQUESTED": [start_iso, end_iso],
            "FULL_DATASET_RANGE": [ingestion_report.start_utc.isoformat(), ingestion_report.end_utc.isoformat()],
            "SOURCE_TIMEZONE": ingestion_report.source_timezone, "NORMALIZED_TIMEZONE": "UTC",
            "TOTAL_M5_ROWS": ingestion_report.rows,
            "UNEXPECTED_GAPS": len(ingestion_report.unexpected_gaps),
            "DERIVED_TIMEFRAME_ROWS": derived,
        },
        "REPLAY": {
            "STEPS": result.steps, "WARMUP_STEPS": result.warmup_steps, "VALID_ANALYSIS_STEPS": result.valid_steps,
            "LOAD_TIME_SECONDS": round(load_time, 2), "REPLAY_TIME_SECONDS": round(replay_time, 2),
            "SECONDS_PER_STEP": round(replay_time / result.valid_steps, 4) if result.valid_steps else None,
        },
        "IDENTITY": {
            "IDENTITY_COLLISIONS": result.identity_collisions,
            "READY_LIFECYCLE_CREATED_EVENTS": result.ready_lifecycle_created_events,
        },
        "SETUP_LEDGER": {
            "ROWS": len(result.setup_ledger),
            "UNIQUE_SETUPS": len({r.setup_id for r in result.setup_ledger}),
            "READY_COUNT": sum(1 for r in result.setup_ledger if r.ready_time is not None),
        },
        "PER_COMBINATION": result.per_combination,
        "PER_E": result.per_e,
        "PER_M": result.per_m,
    }

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"Wrote {out_path}")
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
