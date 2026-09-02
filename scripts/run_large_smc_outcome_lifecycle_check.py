"""OUTCOME_LIFECYCLE_V1 Stage-1 check (task section 26): reproduces the three
previously-known September 2025 READY-equivalent occurrences (E1M2, E1M3, E3M3) through
`LargeSMCResearchEngine`, then extends each through the new pending-entry lifecycle
(`large_smc_research.pending_entry`).

Reuses existing artifacts rather than re-running the ~90-minute full-month replay:
- `artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json` +
  `artifacts/backtests/directional_liquidity_timeline.json` -- the already-computed
  Stage1Dataset (QualifiedEEvent set + DirectionalLiquidityTimeline) for this exact
  window, built by `scripts/build_native_stage1.py` in a prior phase.
- The known ready_time timestamps already recorded in
  `artifacts/backtests/discovery_2mo_aug_sep2025_setup_ledger.parquet` (E1M3/E3M3 both
  ready at 2025-09-15T12:10 UTC; E1M2 ready at 2025-09-23T14:55 UTC).

`historical_replay.stage2.evaluate_entry_stage_canonical_v2` re-derives M1/M2/M3 fresh
from historical data as of a given evaluation_time (it is a pure function of
(symbol, event, evaluation_time, liquidity_timeline), not a stateful stepper) -- so
calling the engine at exactly these two timestamps reproduces the same result a full
per-M5-bar replay would have produced at those same moments, at a small fraction of the
compute cost. This is the targeted check task section 26 asks for, not the full-month
funnel re-run (section 27), which is not re-run here because nothing in this phase
touches any detection module it depends on -- see the OUTCOME_LIFECYCLE_V1 status doc.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay import HistoricalCandleStore, historical_data_context, load_mt5_export_csv  # noqa: E402
from historical_replay.stage1 import load_stage1_dataset  # noqa: E402
from large_smc_research import LargeSMCResearchEngine, simulate_pending_entry  # noqa: E402
from large_smc_research.decision import LargeSMCDecisionState  # noqa: E402

SYMBOL = "EURUSD"
CSV_PATH = r"D:\EURUSD_M5_202504211715_202607310000.csv"
EVENTS_PATH = "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json"
LIQUIDITY_PATH = "artifacts/backtests/directional_liquidity_timeline.json"

# From artifacts/backtests/discovery_2mo_aug_sep2025_setup_ledger.parquet (prior phase).
KNOWN_READY_TIMES = [
    datetime(2025, 9, 15, 12, 10, tzinfo=timezone.utc),
    datetime(2025, 9, 23, 14, 55, tzinfo=timezone.utc),
]
EXPECTED_COMBINATIONS = {"E1M2", "E1M3", "E3M3"}


def main() -> None:
    dataset = load_stage1_dataset(EVENTS_PATH, LIQUIDITY_PATH)
    print(f"Loaded {len(dataset.events)} QualifiedEEvents from {EVENTS_PATH}")

    candles, _ingestion_report = load_mt5_export_csv(CSV_PATH, SYMBOL, "M5")
    store = HistoricalCandleStore()
    store.load_series(SYMBOL, "M5", candles)

    engine = LargeSMCResearchEngine()
    all_decisions = []
    for t in KNOWN_READY_TIMES:
        with historical_data_context(store, t):
            decisions = engine.evaluate(SYMBOL, t, dataset)
        all_decisions.extend(decisions)
        print(f"\n=== evaluation_time={t.isoformat()} -> {len(decisions)} decision(s) ===")
        for d in decisions:
            print(f"  combo={d.combination} dir={d.direction} state={d.state} "
                  f"entry={d.entry_price} inval={d.structural_invalidation_price} "
                  f"target={d.target_price} occurrence_id={d.candidate_occurrence_id} "
                  f"reasons={d.reason_codes}")

    blocked = [d for d in all_decisions if d.state == LargeSMCDecisionState.BLOCKED.value]
    combos_found = {d.combination for d in blocked}
    occurrence_ids = [d.candidate_occurrence_id for d in blocked]

    print("\n=== IDENTITY CHECK ===")
    print(f"BLOCKED (READY-equivalent) decisions: {len(blocked)}")
    print(f"Combinations found: {sorted(combos_found)} (expected superset of {sorted(EXPECTED_COMBINATIONS)})")
    print(f"Occurrence-id collisions: {len(occurrence_ids) - len(set(occurrence_ids))}")

    print("\n=== PENDING-ENTRY LIFECYCLE ===")
    for d in blocked:
        forward = [c for c in candles if c.time >= d.evaluation_timestamp]
        outcome = simulate_pending_entry(d, forward)
        print(f"  {d.combination:5s} occurrence={d.candidate_occurrence_id} status={outcome.status} "
              f"fill_time={outcome.fill_time} fill_price={outcome.fill_price} "
              f"invalidation_time={outcome.invalidation_time}")


if __name__ == "__main__":
    main()
