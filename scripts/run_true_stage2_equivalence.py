"""TRUE_ENTRY_ONLY_REPLAY: runs stage2.evaluate_entry_stage over the 18-event
migration fixture (E3 events enriched with real LiquidityLevel references) and
compares against the known full-replay baseline (setups=54, arrays=9, ready=3).
"""
from __future__ import annotations

import json
import pickle
import sys
import time
import warnings
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
warnings.filterwarnings("ignore", category=FutureWarning)

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned  # noqa: E402
from historical_replay.candle_store import HistoricalDataError  # noqa: E402
from historical_replay.orchestrator import (  # noqa: E402
    D1_WARMUP_CANDLES, H1_WARMUP_CANDLES, M5_WARMUP_CANDLES, SetupLedger, _has_enough_history,
)
from historical_replay.stage2 import evaluate_entry_stage  # noqa: E402

WINDOW_HOURS = 192  # RESEARCH_ASSUMPTION, matches orchestrator.STAGE2_WINDOW_HOURS_RESEARCH_ASSUMPTION


def main() -> None:
    with open("artifacts/backtests/stage1_events_enriched.pkl", "rb") as f:
        events = pickle.load(f)

    candles, rep = load_mt5_export_csv(
        r"D:\EURUSD_M5_202504211715_202607310000.csv", "EURUSD", "M5")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series("EURUSD", tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series("EURUSD", tf, resample_broker_aligned(candles, rep.broker_times, "M5", tf))

    m5_by_time = {c.time: c for c in candles}
    sorted_times = sorted(m5_by_time)

    ledger = SetupLedger()
    steps = 0
    t0 = time.time()

    for event in events:
        window_end = event.qualification_time + timedelta(hours=WINDOW_HOURS)
        idx_start = 0
        # cheap bisect via linear scan is fine: 18 events only
        for t in sorted_times:
            as_of = t + timedelta(minutes=5)
            if as_of < event.qualification_time:
                continue
            if as_of >= window_end:
                break
            if not (_has_enough_history(store, "EURUSD", "D1", D1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, "EURUSD", "H1", H1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, "EURUSD", "M5", M5_WARMUP_CANDLES, as_of)):
                continue
            steps += 1
            from historical_replay.data_source_patch import historical_data_context
            with historical_data_context(store, as_of):
                analysis = evaluate_entry_stage("EURUSD", event, as_of)
            ledger.observe(analysis, as_of)

    elapsed = time.time() - t0
    rows = list(ledger.rows.values())
    result = {
        "events": len(events), "steps": steps, "elapsed_seconds": round(elapsed, 2),
        "setups": len(rows),
        "arrays": sum(1 for r in rows if r.entry_type not in (None, "NONE")),
        "ready": sum(1 for r in rows if r.ready_time is not None),
        "setup_ids": sorted(r.setup_id for r in rows),
        "rows": [dict(setup_id=r.setup_id, combination=r.combination, direction=r.direction,
                      entry_type=r.entry_type, entry_low=r.entry_low, entry_high=r.entry_high,
                      entry_reference=r.entry_reference, ready_time=str(r.ready_time) if r.ready_time else None)
                 for r in rows],
    }
    with open("artifacts/backtests/true_entry_only_result.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
