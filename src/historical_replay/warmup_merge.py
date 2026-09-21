"""Mission-1 P2/P4 helper: merge a WARMUP_CONTEXT_ONLY leg with a decision-window leg
into one chronologically ordered candle series for the same (symbol, timeframe).

Read-only, deterministic, additive. Does not fabricate or interpolate any bar. The
decision-window leg is the canonical authority for any timestamp it covers (it is the
admitted derived dataset, e.g. SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001); the warmup leg
contributes only bars strictly before the decision window's first timestamp, so an
overlap never causes two different OHLC values to compete for the same timestamp.
"""
from __future__ import annotations

from typing import List, Sequence

from strategy_engine.session import Candle


def merge_warmup_and_decision_window(
    warmup_candles: Sequence[Candle], decision_candles: Sequence[Candle],
) -> List[Candle]:
    """Returns warmup bars strictly before the decision window's first bar, followed by
    every decision-window bar, both internally sorted -- i.e. one ascending series with
    no duplicate timestamps and no decision-window bar ever overridden by a warmup bar."""
    if not decision_candles:
        raise ValueError("decision_candles must be non-empty")
    decision_sorted = sorted(decision_candles, key=lambda c: c.time)
    decision_start = decision_sorted[0].time
    warmup_prefix = sorted(
        (c for c in warmup_candles if c.time < decision_start), key=lambda c: c.time,
    )
    merged = warmup_prefix + decision_sorted
    for a, b in zip(merged, merged[1:]):
        if b.time <= a.time:
            raise ValueError(f"non-increasing merged timestamps at {a.time} -> {b.time}")
    return merged
