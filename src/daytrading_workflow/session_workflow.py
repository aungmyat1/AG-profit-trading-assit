"""SESSION_TRADE completion workflow (spec sections 5, 8-11): once per completed
reference session, project daytrading.decision.route_daytrading_setup's already-computed
decision into a SessionTradeProposal. No new regime/setup/bias logic -- only field
mapping plus the once-only dedup bookkeeping that does not exist anywhere else in this
repo (strategy_engine.session.route_completed_session is documented stateless/one-shot
with no dedup of its own; something has to own "don't re-evaluate the same completed
session twice," and nothing currently does).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Optional, Sequence, Set, Tuple

from daytrading.decision.models import DaytradingSetupDecision, MarketBias
from daytrading.decision.setup_router import route_daytrading_setup
from strategy_engine.session import Candle, build_reference_box

from .models import (
    PROPOSAL_CONFLICT,
    PROPOSAL_INDETERMINATE,
    PROPOSAL_NO_SETUP,
    PROPOSAL_VALID,
    PROPOSAL_WAITING_CONFIRMATION,
    SessionTradeProposal,
)

_DECISION_STATUS_TO_PROPOSAL_STATUS = {
    "NO_SETUP": PROPOSAL_NO_SETUP,
    "CONFLICT": PROPOSAL_CONFLICT,
}


def _proposal_status(decision: DaytradingSetupDecision) -> str:
    if decision.decision_status == "VALID":
        # route_daytrading_setup already distinguishes these via its own reason codes
        # (spec section 9's VALID_PROPOSAL vs WAITING_CONFIRMATION) -- not re-derived here.
        return PROPOSAL_VALID if "CONFIRMED_FOR_EXECUTION" in decision.reason_codes else PROPOSAL_WAITING_CONFIRMATION
    return _DECISION_STATUS_TO_PROPOSAL_STATUS.get(decision.decision_status, PROPOSAL_INDETERMINATE)


def evaluate_session_completion(
    strategy_id: str,
    symbol: str,
    reference_session: str,
    trading_date: date,
    session_candles: Sequence[Candle],
    expected_bar_count: int,
    market_bias: MarketBias,
    post_session_candles: Sequence[Candle] = (),
    supply_demand_context=None,
    entry_confirmation_state: Optional[str] = None,
    evaluation_time: Optional[datetime] = None,
) -> SessionTradeProposal:
    box = build_reference_box(reference_session, session_candles, expected_bar_count)
    decision = route_daytrading_setup(
        strategy_id, symbol, reference_session, trading_date, session_candles, expected_bar_count,
        market_bias, post_session_candles=post_session_candles,
        supply_demand_context=supply_demand_context, entry_confirmation_state=entry_confirmation_state,
        evaluation_time=evaluation_time,
    )
    session_decision = decision.session_decision

    return SessionTradeProposal(
        strategy_id=strategy_id,
        symbol=symbol,
        trading_date=trading_date,
        reference_session=reference_session,
        reference_start=session_candles[0].time if session_candles else None,
        reference_end=session_candles[-1].time if session_candles else None,
        market_bias=decision.market_bias.direction,
        reference_high=box.session_high if box.session_complete else None,
        reference_low=box.session_low if box.session_complete else None,
        reference_mid=box.session_mid if box.session_complete else None,
        reference_open=box.session_open if box.session_complete else None,
        reference_close=box.session_close if box.session_complete else None,
        efficiency_ratio=decision.efficiency_ratio,
        regime=decision.regime.value if decision.regime is not None else None,
        sweep_detected=decision.sweep_detected,
        sweep_side=decision.sweep_side,
        setup_type=decision.setup_type.value,
        direction=decision.direction.value if decision.direction is not None else None,
        entry_reference=session_decision.entry_reference if session_decision is not None else None,
        stop_reference=session_decision.stop_reference if session_decision is not None else None,
        target_reference=session_decision.target_reference if session_decision is not None else None,
        entry_confirmation_state=entry_confirmation_state,
        proposal_status=_proposal_status(decision),
        reason_codes=decision.reason_codes,
        created_at=evaluation_time,
    )


class SessionCompletionDispatcher:
    """Fires evaluate_session_completion at most once per
    (strategy_id, symbol, reference_session, trading_date) -- spec section 10's
    once-only processing. `seen_keys` is injectable so a caller can back it with
    persistent storage across process restarts; defaults to an in-memory set scoped to
    this dispatcher instance."""

    def __init__(self, seen_keys: Optional[Set[Tuple[str, str, str, date]]] = None):
        self._seen: Set[Tuple[str, str, str, date]] = seen_keys if seen_keys is not None else set()

    def process_one(
        self,
        strategy_id: str,
        symbol: str,
        reference_session: str,
        trading_date: date,
        session_candles: Sequence[Candle],
        expected_bar_count: int,
        market_bias: MarketBias,
        post_session_candles: Sequence[Candle] = (),
        supply_demand_context=None,
        entry_confirmation_state: Optional[str] = None,
        evaluation_time: Optional[datetime] = None,
    ) -> Optional[SessionTradeProposal]:
        if not session_candles:
            return None
        box = build_reference_box(reference_session, session_candles, expected_bar_count)
        if not box.session_complete:
            return None  # no SESSION_COMPLETED event yet -- do not evaluate or mark seen

        key = (strategy_id, symbol, reference_session, trading_date)
        if key in self._seen:
            return None  # already evaluated once for this symbol+session+date

        self._seen.add(key)
        return evaluate_session_completion(
            strategy_id, symbol, reference_session, trading_date, session_candles, expected_bar_count,
            market_bias, post_session_candles=post_session_candles,
            supply_demand_context=supply_demand_context, entry_confirmation_state=entry_confirmation_state,
            evaluation_time=evaluation_time,
        )

    def process_universe(
        self,
        symbols: Sequence[str],
        reference_session: str,
        trading_date: date,
        sessions_by_symbol: Dict[str, dict],
    ) -> Dict[str, Optional[SessionTradeProposal]]:
        """Evaluate the configured universe once for a completed reference session
        (spec section 8/11) -- a symbol missing from `sessions_by_symbol` or not yet
        session-complete is simply absent/None from the result, never forced to a
        fabricated proposal. `sessions_by_symbol[symbol]` supplies that symbol's own
        process_one kwargs (strategy_id, session_candles, expected_bar_count,
        market_bias, and optionally post_session_candles/supply_demand_context/
        entry_confirmation_state/evaluation_time)."""
        results: Dict[str, Optional[SessionTradeProposal]] = {}
        for symbol in symbols:
            params = sessions_by_symbol.get(symbol)
            if params is None:
                continue
            results[symbol] = self.process_one(
                symbol=symbol, reference_session=reference_session, trading_date=trading_date, **params,
            )
        return results
