"""Persistence-backed SESSION_TRADE runtime (spec sections 7-11). Wraps
daytrading_workflow.session_workflow.SessionCompletionDispatcher unchanged -- the
session-completeness gate (candle-count based) and the actual proposal-building logic
stay exactly as verified in the previous phase. The only thing added here is swapping
the dispatcher's in-memory dedup for a persistent one: a completed-session event is
recorded in runtime_state before this function returns, so a second call (in this
process, in a new process after restart, or after a crash) sees the persisted record
and never re-evaluates.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional, Sequence

from daytrading.decision.models import MarketBias
from daytrading_workflow.session_workflow import SessionCompletionDispatcher
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle

from .ids import session_event_id


class PersistentSessionRuntime:
    def __init__(self, store: JsonKeyValueStore):
        self.store = store

    def process_symbol(
        self,
        strategy_id: str,
        symbol: str,
        reference_session: str,
        trading_date: date,
        session_candles: Sequence[Candle],
        expected_bar_count: int,
        market_bias: MarketBias,
        post_session_candles: Sequence[Candle] = (),
        supply_demand_context: Optional[Any] = None,
        entry_confirmation_state: Optional[str] = None,
        evaluation_time: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        event_id = session_event_id(strategy_id, symbol, trading_date, reference_session)

        existing = self.store.get(event_id)
        if existing is not None:
            return existing  # already evaluated once -- restart-safe, no duplicate evaluation

        # A fresh, empty-dedup dispatcher per call is safe: the persistent store above
        # is the real dedup layer; this dispatcher instance only supplies the existing,
        # unmodified session-completeness gate (spec section 8's candle-count check).
        dispatcher = SessionCompletionDispatcher()
        proposal = dispatcher.process_one(
            strategy_id, symbol, reference_session, trading_date, session_candles, expected_bar_count,
            market_bias, post_session_candles=post_session_candles,
            supply_demand_context=supply_demand_context, entry_confirmation_state=entry_confirmation_state,
            evaluation_time=evaluation_time,
        )
        if proposal is None:
            return None  # reference session not yet complete -- do not persist, retry next cycle

        now = datetime.now(timezone.utc).isoformat()
        record = {
            "event_id": event_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "trading_date": trading_date.isoformat(),
            "reference_session": reference_session,
            "detected_at": now,
            "evaluated_at": now,
            "proposal": dataclasses.asdict(proposal),
        }
        self.store.put(event_id, record)
        return self.store.get(event_id)  # re-read so first-call and cached-call shapes match exactly
