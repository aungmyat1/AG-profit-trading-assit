"""Boot/crash recovery (spec section 10): detect current UTC time, load persisted
checkpoint, identify expected cycles since the checkpoint, compare against completed
cycles, and reconstruct missing ones as CATCH_UP -- execution_allowed permanently false
for every reconstructed occurrence.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Iterable, Sequence

from ag_scheduler_v2.cycle_identity import CATCH_UP, LIVE_WINDOW, CompletedCycleStore, cycle_id


@dataclass(frozen=True)
class ExpectedCycle:
    strategy_id: str
    symbol: str
    session_pair: str
    bar_close_utc: dt.datetime


@dataclass(frozen=True)
class RecoveryOutcome:
    reconstructed: tuple  # ExpectedCycle entries reconstructed as CATCH_UP
    already_completed: tuple  # ExpectedCycle entries already completed (no action)
    execution_allowed: bool  # always False for anything this module touches


def expected_m15_cycles(
    *,
    strategy_id: str,
    symbols: Sequence[str],
    session_pair: str,
    window_start_utc: dt.datetime,
    window_end_utc: dt.datetime,
) -> tuple:
    """Every M15 bar-close inside [window_start_utc, window_end_utc) for each symbol,
    in deterministic (symbol, then time) order."""
    if window_start_utc.tzinfo is None or window_end_utc.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: recovery window bounds must be tz-aware UTC")
    closes = []
    cursor = window_start_utc.astimezone(dt.timezone.utc)
    # Align to the first M15 boundary at or after window_start_utc.
    remainder = cursor.minute % 15
    if remainder or cursor.second or cursor.microsecond:
        cursor = (cursor + dt.timedelta(minutes=15 - remainder)).replace(second=0, microsecond=0)
    while cursor < window_end_utc:
        closes.append(cursor)
        cursor += dt.timedelta(minutes=15)

    expected = []
    for symbol in symbols:
        for close in closes:
            expected.append(ExpectedCycle(strategy_id, symbol, session_pair, close))
    return tuple(expected)


def reconcile_on_boot(
    *,
    expected: Iterable[ExpectedCycle],
    store: CompletedCycleStore,
    now_utc: dt.datetime,
) -> RecoveryOutcome:
    """Any expected cycle not already marked completed is reconstructed here as
    CATCH_UP and immediately persisted that way -- it never becomes a stale live
    execution path, and its observation_mode is fixed at write time (never inferred
    later from timestamps, spec section 11)."""
    reconstructed = []
    already_completed = []
    for cyc in expected:
        if cyc.bar_close_utc > now_utc:
            # Not yet due -- this is a future live cycle, not a missed one; recovery
            # must never manufacture CATCH_UP evidence for a bar that hasn't closed.
            continue
        cid = cycle_id(
            strategy_id=cyc.strategy_id, symbol=cyc.symbol, session_pair=cyc.session_pair, bar_close_utc=cyc.bar_close_utc,
        )
        if store.is_completed(cid):
            already_completed.append(cyc)
            continue
        store.mark_completed(
            strategy_id=cyc.strategy_id,
            symbol=cyc.symbol,
            session_pair=cyc.session_pair,
            bar_close_utc=cyc.bar_close_utc,
            observation_mode=CATCH_UP,
            now_utc=now_utc,
        )
        reconstructed.append(cyc)
    return RecoveryOutcome(reconstructed=tuple(reconstructed), already_completed=tuple(already_completed), execution_allowed=False)
