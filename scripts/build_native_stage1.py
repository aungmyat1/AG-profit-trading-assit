"""Builds the canonical QualifiedEEvent dataset from the three already-computed
artifacts this phase produced (reference geometry, eligibility intervals, E3 liquidity
references) and persists it. No new 3-hour replay -- this reuses existing outputs.
"""
from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from historical_replay.stage1 import build_qualified_e_events, save_qualified_e_events  # noqa: E402

SYMBOL = "EURUSD"
OUT_PATH = "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json"


def main() -> None:
    Path(OUT_PATH).parent.mkdir(parents=True, exist_ok=True)

    with open("artifacts/backtests/stage1_events_aug_sep2025.json") as f:
        reference_geometry = json.load(f)
    with open("artifacts/backtests/stage1_eligibility_intervals.json") as f:
        eligibility = json.load(f)["events"]
    with open("artifacts/backtests/stage1_events_enriched.pkl", "rb") as f:
        enriched = pickle.load(f)

    liquidity_refs = {
        (e.entry_condition, e.reference_key, e.direction): e.liquidity_reference
        for e in enriched if e.liquidity_reference is not None
    }

    events = build_qualified_e_events(reference_geometry, eligibility, liquidity_refs, SYMBOL)

    metadata = {
        "symbol": SYMBOL, "period_start": "2025-08-01T00:00:00+00:00", "period_end": "2025-10-01T00:00:00+00:00",
        "feed": r"D:\EURUSD_M5_202504211715_202607310000.csv",
        "broker_timezone_contract": "BROKER_SERVER_TIME(UTC+2/UTC+3 seasonal DST, empirically detected)",
        "broker_day_anchor_policy": "resample_broker_aligned (D1/H4 anchored to broker calendar day/4h window)",
        "session_contract_version": "config/canonical_sessions.yaml (unchanged)",
        "closed_bar_policy": "HistoricalCandleStore.closed_candles: bar_open_time + timeframe_duration <= as_of",
        "strategy_context_version": "SMC_CONDITIONAL_ENTRY_V2",
    }
    save_qualified_e_events(events, OUT_PATH, metadata)

    print(f"wrote {len(events)} events to {OUT_PATH}")
    from collections import Counter
    print(Counter(e.entry_condition for e in events))
    print("multi-interval events:", sum(1 for e in events if len(e.eligibility_intervals) > 1))
    print("E3 with liquidity ref:", sum(1 for e in events if e.entry_condition == "E3" and e.htf_liquidity_reference is not None))


if __name__ == "__main__":
    main()
