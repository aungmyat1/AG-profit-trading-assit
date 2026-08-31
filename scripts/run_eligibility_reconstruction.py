"""Reconstructs the exact time-varying eligibility timeline (eligible_for_confirmation
==True) for the 18 known Aug-Sep 2025 EURUSD events, by re-walking the SAME continuous
2-month window with the SAME live entrypoint used by the original full discovery
replay (build_symbol_conditional_entry_analysis) -- no new E1/E2/E3 logic, this is
pure observation of the frozen live evaluator's own per-poll output.

Root cause this repairs: TRUE_STAGE2's migration fixture only carried a single
qualification_time per event and Stage 2 assumed eligibility held for an artificial
research window -- which produced results (e.g. a false 2025-08-19 READY for
SETUP-EURUSD-E3M2-4942255764efb736) the original continuous replay never found,
because the real E-eligibility window for that event was only ~55 minutes.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
warnings.filterwarnings("ignore", category=FutureWarning)

from daytrading_runtime.conditional_entry_snapshot import build_symbol_conditional_entry_analysis  # noqa: E402
from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned  # noqa: E402
from historical_replay.data_source_patch import historical_data_context  # noqa: E402
from historical_replay.orchestrator import (  # noqa: E402
    D1_WARMUP_CANDLES, H1_WARMUP_CANDLES, M5_WARMUP_CANDLES, _has_enough_history,
)
from proposals.identity import reference_key_for  # noqa: E402

SYMBOL = "EURUSD"
START = datetime(2025, 8, 1, tzinfo=timezone.utc)
END = datetime(2025, 10, 1, tzinfo=timezone.utc)
CHECKPOINT_PATH = "artifacts/backtests/eligibility_checkpoint.json"
OUT_PATH = "artifacts/backtests/stage1_eligibility_intervals.json"


def main() -> None:
    with open("artifacts/backtests/stage1_events_aug_sep2025.json") as f:
        events_raw = json.load(f)
    target_keys = {(e["entry_condition"], e["reference_key"], e["direction"]) for e in events_raw}

    candles, rep = load_mt5_export_csv(
        r"D:\EURUSD_M5_202504211715_202607310000.csv", SYMBOL, "M5")
    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series(SYMBOL, tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series(SYMBOL, tf, resample_broker_aligned(candles, rep.broker_times, "M5", tf))

    eligible_polls: dict = {k: [] for k in target_keys}  # key -> list of as_of timestamps
    steps = valid_steps = 0
    warmup_cleared = False
    t0 = time.time()

    for candle in candles:
        as_of = candle.time + timedelta(minutes=5)
        if as_of < START or as_of >= END:
            continue
        steps += 1

        if not warmup_cleared:
            if (_has_enough_history(store, SYMBOL, "D1", D1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, SYMBOL, "H1", H1_WARMUP_CANDLES, as_of)
                    and _has_enough_history(store, SYMBOL, "M5", M5_WARMUP_CANDLES, as_of)):
                warmup_cleared = True
            else:
                continue

        valid_steps += 1
        with historical_data_context(store, as_of):
            analysis = build_symbol_conditional_entry_analysis(SYMBOL)

        for cond_name, econd in analysis.e_conditions.items():
            if not econd.eligible_for_confirmation:
                continue
            rk = reference_key_for(econd.reference_type, econd.reference_low,
                                   econd.reference_high, econd.reference_level)
            key = (cond_name, rk, econd.direction)
            if key in eligible_polls:
                eligible_polls[key].append(as_of.isoformat())

        if valid_steps % 2000 == 0:
            with open(CHECKPOINT_PATH, "w") as f:
                json.dump({"valid_steps": valid_steps, "steps": steps, "as_of": as_of.isoformat(),
                          "elapsed_seconds": round(time.time() - t0, 1),
                          "events_with_any_eligibility_so_far": sum(1 for v in eligible_polls.values() if v)},
                         f, indent=2)

    # collapse consecutive (5-min-spaced) polls into intervals
    intervals_by_key = {}
    for key, polls in eligible_polls.items():
        times = sorted(datetime.fromisoformat(p) for p in polls)
        intervals = []
        for t in times:
            if intervals and t - intervals[-1][1] == timedelta(minutes=5):
                intervals[-1] = (intervals[-1][0], t)
            else:
                intervals.append((t, t))
        # interval end = last eligible poll's as_of + 5min (half-open [start, end))
        intervals_by_key[key] = [(s.isoformat(), (e + timedelta(minutes=5)).isoformat()) for s, e in intervals]

    result = {
        "symbol": SYMBOL, "range": [START.isoformat(), END.isoformat()],
        "steps": steps, "valid_steps": valid_steps, "elapsed_seconds": round(time.time() - t0, 2),
        "events": [
            {"entry_condition": k[0], "reference_key": k[1], "direction": k[2],
            "eligibility_intervals": intervals_by_key[k], "num_intervals": len(intervals_by_key[k])}
            for k in target_keys
        ],
    }
    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in result.items() if k != "events"}, indent=2))
    print("events_summary:")
    for e in result["events"]:
        print(e["entry_condition"], e["direction"], e["reference_key"], "intervals=", e["num_intervals"])


if __name__ == "__main__":
    main()
