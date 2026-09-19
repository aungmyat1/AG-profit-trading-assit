from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

import session_clock as sc
from historical_replay.evaluation_context import ReplayEvaluationContext, ReplayEvaluationError
from post_asian_pilot.snapshot import AsianSessionSnapshot, build_asian_session_snapshot
from strategy_engine.engine import evaluate
from strategy_engine.models import StrategyConfig, TradeSignal


@dataclass(frozen=True)
class AsianReplayResult:
    event_id: str
    signal: Optional[TradeSignal]
    session_snapshot: Optional[AsianSessionSnapshot]
    status: str
    reason_codes: tuple[str, ...] = ()


def evaluate_asian_replay(context: ReplayEvaluationContext, *, strategy: StrategyConfig,
                          pair_id: str, trading_date: date, reference_session: str,
                          execution_window_start: datetime, execution_window_end: datetime) -> AsianReplayResult:
    """Derive native Asian inputs from one context; never enters the live pilot."""
    if context.as_of.tzinfo is None or execution_window_start.tzinfo is None or execution_window_end.tzinfo is None:
        raise ReplayEvaluationError("Asian replay requires timezone-aware times")
    ref_start, ref_end = sc.get_session_bounds(trading_date, reference_session)
    expected = sc.expected_bar_count(reference_session, "M15")
    ref = context.candles("M15", effective_cutoff=min(context.as_of, ref_end))
    ref = tuple(c for c in ref if ref_start <= c.time < ref_end)
    snap = build_asian_session_snapshot(strategy.strategy_id, context.symbol, trading_date,
                                        reference_session, ref_start, ref_end, ref, expected, as_of=context.as_of)
    if snap.status != "VALID":
        return AsianReplayResult(context.event_id, None, None, "DEFERRED", snap.reason_codes)
    post_end = min(context.as_of, execution_window_end)
    post = tuple(c for c in context.candles("M15", effective_cutoff=post_end)
                 if execution_window_start <= c.time < execution_window_end)
    if context.as_of < execution_window_start:
        return AsianReplayResult(context.event_id, None, snap.snapshot, "DEFERRED", ("EXECUTION_WINDOW_NOT_OPEN",))
    signal = evaluate(strategy, pair_id, context.symbol, trading_date, list(ref), expected,
                      post_session_candles=list(post))
    return AsianReplayResult(context.event_id, signal, snap.snapshot, "COMPLETE")
