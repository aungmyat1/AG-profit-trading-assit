"""SMC_3X3_DISCOVERY_BACKTEST_V1 -- low-cost full-dataset funnel discovery run.

Reuses run_replay (the same live entrypoint, no duplicate strategy logic). Does NOT
simulate fills or P&L (both remain BLOCKED/deferred). Writes a compact setup-ledger
artifact (parquet, jsonl fallback) plus a small summary JSON with funnel/3x3/monthly/
near-ready breakdowns -- all aggregation happens in code, not in conversation.

Usage:
    python scripts/run_discovery_backtest.py <csv_path> <symbol> <start_iso> <end_iso> <out_prefix>
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
warnings.filterwarnings("ignore", category=FutureWarning)  # smartmoneyconcepts pandas .resample() noise, non-blocking

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned  # noqa: E402
from historical_replay.orchestrator import run_replay  # noqa: E402

NEAR_READY_STATE = "WAITING_M5_ENTRY"  # entry array formed, one step from READY -- see EntryModelState


def _month_key(t: datetime) -> str:
    return f"{t.year:04d}-{t.month:02d}"


def _write_ledger(rows, out_prefix: str) -> str:
    records = [
        dict(setup_id=r.setup_id, symbol=r.symbol, combination=r.combination,
             entry_condition=r.entry_condition, maneuver=r.maneuver, direction=r.direction,
             reference_key=r.reference_key, first_seen_time=r.first_seen_time.isoformat(),
             last_seen_time=r.last_seen_time.isoformat(), ready_time=r.ready_time.isoformat() if r.ready_time else None,
             entry_type=r.entry_type, entry_low=r.entry_low, entry_high=r.entry_high,
             entry_reference=r.entry_reference, invalidation_price=r.invalidation_price,
             invalidation_source_type=r.invalidation_source_type, invalidation_trigger=r.invalidation_trigger,
             final_state=r.final_state, final_time=r.final_time.isoformat() if r.final_time else None,
             terminal=r.terminal)
        for r in rows
    ]
    try:
        import pandas as pd
        path = f"{out_prefix}_setup_ledger.parquet"
        pd.DataFrame.from_records(records).to_parquet(path, index=False)
        return path
    except ImportError:
        path = f"{out_prefix}_setup_ledger.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")
        return path


def main() -> None:
    csv_path, symbol, start_iso, end_iso, out_prefix = sys.argv[1:6]
    start_utc = datetime.fromisoformat(start_iso).replace(tzinfo=timezone.utc)
    end_utc = datetime.fromisoformat(end_iso).replace(tzinfo=timezone.utc)
    Path(out_prefix).parent.mkdir(parents=True, exist_ok=True)
    status_path = f"{out_prefix}_status.json"

    t0 = time.time()
    candles, ingestion_report = load_mt5_export_csv(csv_path, symbol, "M5")
    store = HistoricalCandleStore()
    store.load_series(symbol, "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series(symbol, tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series(symbol, tf, resample_broker_aligned(candles, ingestion_report.broker_times, "M5", tf))
    load_time = time.time() - t0

    def _progress(valid_steps, steps, as_of):
        elapsed = time.time() - t0 - load_time
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump({"status": "RUNNING", "valid_steps": valid_steps, "steps": steps,
                       "as_of": as_of.isoformat(), "elapsed_seconds": round(elapsed, 1)}, f)

    t0_replay = time.time()
    result = run_replay(store, symbol, candles, start_utc, end_utc, progress_callback=_progress)
    replay_time = time.time() - t0_replay

    # ---- derive all reports from the ledger in code (rule: aggregate in code) ----
    rows = result.setup_ledger
    monthly = defaultdict(lambda: {"setups": 0, "arrays": 0, "ready": 0})
    for r in rows:
        m = monthly[_month_key(r.first_seen_time)]
        m["setups"] += 1
        if r.entry_type not in (None, "NONE"):
            m["arrays"] += 1
        if r.ready_time is not None:
            m["ready"] += 1

    near_ready = [r for r in rows if r.final_state == NEAR_READY_STATE]
    failure_reasons = Counter(r.final_state for r in rows if r.ready_time is None)

    ledger_path = _write_ledger(rows, out_prefix)

    summary = {
        "STATUS": "REPLAY_COMPLETE",
        "DATA": {
            "SOURCE": csv_path, "SYMBOL": symbol, "RANGE": [start_iso, end_iso],
            "FULL_DATASET_RANGE": [ingestion_report.start_utc.isoformat(), ingestion_report.end_utc.isoformat()],
        },
        "REPLAY": {"STEPS": result.steps, "WARMUP_STEPS": result.warmup_steps,
                   "VALID_STEPS": result.valid_steps, "LOAD_SECONDS": round(load_time, 1),
                   "REPLAY_SECONDS": round(replay_time, 1)},
        "IDENTITY": {"COLLISIONS": result.identity_collisions},
        "SETUP_LEDGER": {"ROWS": len(rows), "UNIQUE_SETUPS": len({r.setup_id for r in rows}),
                         "READY": sum(1 for r in rows if r.ready_time is not None),
                         "ENTRY_ARRAYS": sum(1 for r in rows if r.entry_type not in (None, "NONE")),
                         "ARTIFACT": ledger_path},
        "PER_COMBINATION": result.per_combination,
        "PER_E": result.per_e,
        "PER_M": result.per_m,
        "FAILURE_REASONS": dict(failure_reasons.most_common()),
        "NEAR_READY": {
            "COUNT": len(near_ready),
            "SAMPLE": [dict(setup_id=r.setup_id, combination=r.combination, direction=r.direction,
                            failed_condition=r.final_state, last_seen_time=r.last_seen_time.isoformat())
                       for r in near_ready[:5]],
        },
        "MONTHLY": {k: monthly[k] for k in sorted(monthly)},
        "PNL": {"STATUS": "BLOCKED", "REASON": "EXIT_POLICY_NOT_FROZEN"},
    }

    with open(f"{out_prefix}_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"status": "REPLAY_COMPLETE", "summary_path": f"{out_prefix}_summary.json"}, f)

    print("REPLAY_COMPLETE")
    print(json.dumps(summary, indent=2, default=str)[:4000])  # capped -- full detail is in the file


if __name__ == "__main__":
    main()
