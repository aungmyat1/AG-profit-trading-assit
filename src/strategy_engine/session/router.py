"""Canonical simplified router (CANONICAL_SESSION_MIGRATION_REPORT.md section 7):

REFERENCE SESSION COMPLETE -> BUILD FROZEN BOX -> CLASSIFY -> TREND/RANGE
TREND            -> Entry 1 only
RANGE + sweep    -> Entry 2
RANGE + no sweep -> Entry 3 (may still be NO_SETUP)

Stateless and one-shot: called once per completed reference session, no post-session
observation loop.
"""
from __future__ import annotations

from datetime import date
from typing import Sequence

from .candles import Candle
from .classifier import Regime, classify
from .reference_box import ReferenceBox, build_reference_box
from .setups import SetupDecision, entry_1_trend, entry_2_sweep, entry_3_range


def route_completed_session(
    strategy_id: str,
    symbol: str,
    session_name: str,
    session_date: date,
    session_candles: Sequence[Candle],
    expected_bar_count: int,
    post_session_candles: Sequence[Candle] = (),
) -> tuple[ReferenceBox, Regime, SetupDecision]:
    box = build_reference_box(session_name, session_candles, expected_bar_count)
    if not box.session_complete:
        raise ValueError(
            f"route_completed_session requires a completed box: got {box.bar_count}/"
            f"{expected_bar_count} bars for {session_name} on {session_date}"
        )

    regime = classify(box)

    if regime is Regime.TREND:
        decision = entry_1_trend(strategy_id, symbol, box, session_date)
    else:
        decision = entry_2_sweep(strategy_id, symbol, box, session_date, post_session_candles)
        if decision.decision_status.value == "NO_SETUP":
            decision = entry_3_range(strategy_id, symbol, box, session_date, post_session_candles)

    return box, regime, decision
