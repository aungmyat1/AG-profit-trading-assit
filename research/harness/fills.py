"""Bar-level exit resolution for engine-supplied levels (fill mechanics only, no rules).

Same-bar precedence: when one bar's range touches both stop and target, the STOP is taken
(conservative, since intrabar order is unknown). A bar that opens beyond the stop fills at
its open (gap loss); a bar that opens beyond the target fills at the target (no gap credit).
"""
from __future__ import annotations

import pandas as pd

from research.harness.ledger import DIRECTIONS


def resolve_exit(bars: pd.DataFrame, entry_idx: int, direction: str, stop: float, target: float,
                 max_bars: int | None = None) -> dict:
    """Walk bars from entry_idx (the entry bar itself is included) until stop or target."""
    s = DIRECTIONS[direction]
    last = len(bars) if max_bars is None else min(len(bars), entry_idx + max_bars)
    for i in range(entry_idx, last):
        b = bars.iloc[i]
        hit_stop = (b["low"] <= stop) if s > 0 else (b["high"] >= stop)
        hit_target = (b["high"] >= target) if s > 0 else (b["low"] <= target)
        if hit_stop:  # checked first: stop wins a same-bar tie
            gapped = (b["open"] < stop) if s > 0 else (b["open"] > stop)
            return {"exit_idx": i, "exit_time": b["ts"], "exit_price": float(b["open"] if gapped else stop),
                    "exit_reason": "STOP", "same_bar_conflict": bool(hit_target)}
        if hit_target:
            return {"exit_idx": i, "exit_time": b["ts"], "exit_price": float(target),
                    "exit_reason": "TARGET", "same_bar_conflict": False}
    b = bars.iloc[last - 1]
    return {"exit_idx": last - 1, "exit_time": b["ts"], "exit_price": float(b["close"]),
            "exit_reason": "END_OF_DATA" if max_bars is None else "TIME", "same_bar_conflict": False}


def delay_entry(trade, bars: pd.DataFrame, delay: int, max_bars: int | None = None) -> dict | None:
    """Re-fill an engine trade `delay` bars after its original entry bar at that bar's open,
    keeping the engine's stop/target. Returns None when the delayed open is already at/through
    the stop or target (no valid fill -- reported as skipped, never re-priced)."""
    bars = bars.reset_index(drop=True)
    idx = bars.index[bars["ts"] == trade.entry_time]
    if len(idx) == 0:
        raise ValueError(f"entry_time {trade.entry_time} of {trade.trade_id} not found in bars")
    j = int(idx[0]) + delay
    if j >= len(bars):
        return None
    entry = float(bars.iloc[j]["open"])
    s = DIRECTIONS[trade.direction]
    if (entry - trade.stop_price) * s <= 0 or (trade.target_price - entry) * s <= 0:
        return None
    ex = resolve_exit(bars, j, trade.direction, trade.stop_price, trade.target_price, max_bars)
    return {"entry_time": bars.iloc[j]["ts"], "entry_price": entry, "risk_price": (entry - trade.stop_price) * s,
            **{k: ex[k] for k in ("exit_time", "exit_price", "exit_reason")}}
