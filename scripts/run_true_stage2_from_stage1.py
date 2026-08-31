"""TRUE_STAGE2_VERIFICATION_FROM_FROZEN_STAGE1: consumes the canonical
QUALIFIED_E_EVENT_V1 artifact directly (not the 192h research-window fixture) and
gates M5 evaluation strictly by QualifiedEEvent.is_eligible_at() -- eligibility
comes exclusively from Stage-1's reconstructed intervals, never a research window.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
warnings.filterwarnings("ignore", category=FutureWarning)

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned  # noqa: E402
from historical_replay.data_source_patch import historical_data_context  # noqa: E402
from historical_replay.orchestrator import (  # noqa: E402
    D1_WARMUP_CANDLES, H1_WARMUP_CANDLES, M5_WARMUP_CANDLES, SetupLedger, Stage1Event, _has_enough_history,
)
from historical_replay.stage1 import load_directional_liquidity_timeline, load_qualified_e_events  # noqa: E402
from historical_replay.stage2 import evaluate_entry_stage  # noqa: E402

ARTIFACT = "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json"
CHECKPOINT_PATH = "artifacts/backtests/true_stage2_from_stage1_checkpoint.json"
RESULT_PATH = "artifacts/backtests/true_stage2_from_stage1_result.json"

_call_counts = {"D1_or_H1_discovery": 0, "E_evaluator": 0, "build_symbol_conditional_entry_analysis": 0}


def _counting_wrapper(name, real, forbidden_timeframes=None):
    def _wrapped(*args, **kwargs):
        if forbidden_timeframes is not None:
            tf = kwargs.get("timeframe", args[1] if len(args) > 1 else None)
            if tf in forbidden_timeframes:
                _call_counts["D1_or_H1_discovery"] += 1
        else:
            _call_counts[name] += 1
        return real(*args, **kwargs)
    return _wrapped


def _to_stage1_event(qe):
    """Adapter: QualifiedEEvent -> the Stage1Event shape evaluate_entry_stage()
    already accepts. No new evaluation logic -- just field renaming."""
    return Stage1Event(entry_condition=qe.entry_condition, reference_key=qe.reference_key,
                       direction=qe.direction, qualification_time=qe.qualification_time,
                       liquidity_reference=qe.htf_liquidity_reference,
                       eligibility_intervals=qe.eligibility_intervals)


def main() -> None:
    events, metadata = load_qualified_e_events(ARTIFACT)
    liquidity_timeline = load_directional_liquidity_timeline(
        "artifacts/backtests/directional_liquidity_timeline.json")

    candles, rep = load_mt5_export_csv(
        r"D:\EURUSD_M5_202504211715_202607310000.csv", "EURUSD", "M5")
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        store.load_series("EURUSD", tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        store.load_series("EURUSD", tf, resample_broker_aligned(candles, rep.broker_times, "M5", tf))

    sorted_times = sorted(c.time for c in candles)

    import supply_demand.analyzer as sda
    import liquidity.analyzer as la
    import daytrading_runtime.conditional_entry_snapshot as ces
    import entry_confirmation.route as route

    patches = [
        patch.object(sda, "fair_value_gaps_for", _counting_wrapper("fvg", sda.fair_value_gaps_for, {"D1"})),
        patch.object(sda, "order_blocks_for", _counting_wrapper("ob", sda.order_blocks_for, {"H1"})),
        patch.object(la, "liquidity_result", _counting_wrapper("liq", la.liquidity_result, {"H1"})),
        patch.object(ces, "build_symbol_conditional_entry_analysis",
                    _counting_wrapper("build_symbol_conditional_entry_analysis", ces.build_symbol_conditional_entry_analysis)),
        patch.object(route, "evaluate_e1", _counting_wrapper("E_evaluator", route.evaluate_e1)),
        patch.object(route, "evaluate_e2", _counting_wrapper("E_evaluator", route.evaluate_e2)),
        patch.object(route, "evaluate_e3", _counting_wrapper("E_evaluator", route.evaluate_e3)),
    ]

    ledger = SetupLedger()
    steps = 0
    t0 = time.time()

    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        for i, qe in enumerate(events):
            stage1_event = _to_stage1_event(qe)
            for t in sorted_times:
                as_of = t + timedelta(minutes=5)
                if not qe.is_eligible_at(as_of):  # ELIGIBILITY GATE -- canonical intervals only
                    continue
                if not (_has_enough_history(store, "EURUSD", "D1", D1_WARMUP_CANDLES, as_of)
                        and _has_enough_history(store, "EURUSD", "H1", H1_WARMUP_CANDLES, as_of)
                        and _has_enough_history(store, "EURUSD", "M5", M5_WARMUP_CANDLES, as_of)):
                    continue
                steps += 1
                with historical_data_context(store, as_of):
                    analysis = evaluate_entry_stage("EURUSD", stage1_event, as_of,
                                                    liquidity_timeline=liquidity_timeline)
                ledger.observe(analysis, as_of)

            rows = list(ledger.rows.values())
            with open(CHECKPOINT_PATH, "w") as f:
                json.dump({
                    "event_index": i, "event_id": qe.event_id,
                    "setups_seen": len(rows),
                    "arrays_seen": sum(1 for r in rows if r.entry_type not in (None, "NONE")),
                    "ready_seen": sum(1 for r in rows if r.ready_time is not None),
                    "elapsed_seconds": round(time.time() - t0, 1),
                    "call_counts": dict(_call_counts),
                }, f, indent=2)

    elapsed = time.time() - t0
    rows = list(ledger.rows.values())
    result = {
        "events": len(events), "steps": steps, "elapsed_seconds": round(elapsed, 2),
        "setups": len(rows),
        "arrays": sum(1 for r in rows if r.entry_type not in (None, "NONE")),
        "ready": sum(1 for r in rows if r.ready_time is not None),
        "call_counts": dict(_call_counts),
        "setup_ids": sorted(r.setup_id for r in rows),
        "rows": [dict(setup_id=r.setup_id, combination=r.combination, direction=r.direction,
                      entry_type=r.entry_type, entry_low=r.entry_low, entry_high=r.entry_high,
                      entry_reference=r.entry_reference, ready_time=str(r.ready_time) if r.ready_time else None)
                 for r in rows],
    }
    with open(RESULT_PATH, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    main()
