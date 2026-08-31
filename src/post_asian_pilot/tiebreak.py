"""Deterministic candidate ordering for daily-ledger slot assignment.

Under the two-slot ledger (governor.DailyTradeLedger), EURUSD and GBPUSD can BOTH be
SELECTED the same day -- there is no single "winner" to exclude the other. The only
thing that must be deterministic is the ORDER candidates attempt to claim a slot in
(which only matters for stable slot_index assignment and for genuine capacity
exhaustion, e.g. a 3rd candidate when max_slots=2): order by `ready_at` (the qualifying
CLOSED M15 candle's own timestamp -- NEVER `evaluation_time`, wall-clock/polling time),
and only fall back to the configured priority list when two candidates share the exact
same `ready_at` and would otherwise tie. Priority decides ordering ONLY -- it never
changes strategy qualification and, with ledger capacity >= 2, does not by itself block
either candidate (both still get a slot if capacity allows).
"""
from __future__ import annotations

from typing import Sequence, Tuple

from .decision import PostAsianDecision


def order_candidates(
    ready_decisions: Sequence[PostAsianDecision], priority: Tuple[str, ...] = (),
) -> Tuple[PostAsianDecision, ...]:
    if any(d.ready_at is None for d in ready_decisions):
        raise ValueError("order_candidates requires ready_at on every READY decision")

    def _priority_rank(symbol: str) -> int:
        return priority.index(symbol) if symbol in priority else len(priority)

    return tuple(sorted(ready_decisions, key=lambda d: (d.ready_at, _priority_rank(d.symbol), d.symbol)))
