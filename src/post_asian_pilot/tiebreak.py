"""Simultaneous-READY tie-break: no existing policy anywhere in this repo resolves which
symbol claims the one daily trade slot when two become READY together (confirmed by
audit: no priority/tie_break/first_qualified concept in strategy_engine or elsewhere).
Per spec, this must fail closed rather than have code silently pick one by iteration
order (which would otherwise be an unintentional, undocumented "alphabetical"/list-order
bias -- exactly what's forbidden).

The orchestrator must call resolve_tiebreak() once per evaluation cycle across the FULL
set of decisions that went READY in that same pass, BEFORE calling
governor.DailyTradeSlot.claim() for any of them -- claiming per-symbol independently
would let loop order silently break the tie instead of this function.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .decision import PostAsianDecision

RESULT_CLAIMED = "CLAIMED"
RESULT_NONE_READY = "NONE_READY"
RESULT_UNRESOLVED = "SIMULTANEOUS_READY_POLICY_UNRESOLVED"


@dataclass(frozen=True)
class TieBreakResult:
    status: str  # RESULT_CLAIMED / RESULT_NONE_READY / RESULT_UNRESOLVED
    claimed_symbol: Optional[str] = None
    reason_code: Optional[str] = None


def resolve_tiebreak(ready_decisions: Sequence[PostAsianDecision]) -> TieBreakResult:
    if not ready_decisions:
        return TieBreakResult(status=RESULT_NONE_READY)
    if len(ready_decisions) == 1:
        return TieBreakResult(status=RESULT_CLAIMED, claimed_symbol=ready_decisions[0].symbol)

    timestamps = {d.evaluation_time for d in ready_decisions}
    if len(timestamps) == 1:
        # Same closed-M15 timestamp, no existing frozen priority -- fail closed, per spec.
        return TieBreakResult(status=RESULT_UNRESOLVED, reason_code=RESULT_UNRESOLVED)

    # Timestamps differ: earliest valid READY claims the slot -- the natural, deterministic
    # consequence of processing closed candles in chronological order (never an AI choice
    # among simultaneous candidates), matching spec section 24's "first-qualified" case.
    earliest = min(ready_decisions, key=lambda d: d.evaluation_time)
    return TieBreakResult(status=RESULT_CLAIMED, claimed_symbol=earliest.symbol)
