"""Public entry point for the strategy engine.

External code (assistant/, scripts/) should call `evaluate()` here rather than reaching
into strategy_engine.session directly (route_completed_session, classify, etc.) -- that
keeps the session-box internals free to change without breaking callers, and keeps a
single place that stamps every result with the strategy's own id/config instead of a
caller-supplied one.

Does not import MT5 and does not send orders. See ../execution/ for what happens to a
TradeSignal after this.
"""
from __future__ import annotations

from datetime import date
from typing import Optional, Sequence

from .models import StrategyConfig, TradeSignal
from .session import Candle, DecisionStatus, Regime, route_completed_session


def evaluate(
    strategy: StrategyConfig,
    pair_id: str,
    symbol: str,
    session_date: date,
    session_candles: Sequence[Candle],
    expected_bar_count: int,
    post_session_candles: Sequence[Candle] = (),
    regime_override: Optional[Regime] = None,
) -> TradeSignal:
    """regime_override: AG_PROJECT_ARCHITECTURE_READINESS_COMPLETION_V1 -- passed
    through unchanged to route_completed_session (see its own docstring). Omitting it
    (None, the default) preserves exact prior behavior for every existing caller."""
    if symbol not in strategy.instruments:
        raise ValueError(f"{symbol!r} is not in {strategy.strategy_id}'s instruments: {strategy.instruments}")

    pair = next((p for p in strategy.session_pairs if p.pair_id == pair_id), None)
    if pair is None:
        known = [p.pair_id for p in strategy.session_pairs]
        raise ValueError(f"unknown pair_id {pair_id!r} for {strategy.strategy_id}; known pairs: {known}")

    box, regime, decision = route_completed_session(
        strategy.strategy_id,
        symbol,
        pair.reference_session.name,
        session_date,
        session_candles,
        expected_bar_count,
        post_session_candles,
        regime_override=regime_override,
    )

    status = "SIGNAL" if decision.decision_status is DecisionStatus.VALID else "NO_TRADE"

    return TradeSignal(
        signal_id=f"{strategy.strategy_id}:{pair.pair_id}:{symbol}:{session_date.isoformat()}",
        strategy_id=strategy.strategy_id,
        strategy_version=strategy.version,
        symbol=symbol,
        pair_id=pair.pair_id,
        reference_session=pair.reference_session.name,
        session_date=session_date,
        box_high=box.session_high,
        box_low=box.session_low,
        box_mid=box.session_mid,
        regime=regime.value,
        setup=decision.setup_type.value,
        status=status,
        reason_code=decision.reason_code,
        direction=decision.direction.value if decision.direction else None,
        entry=decision.entry_reference,
        stop_loss=decision.stop_reference,
        risk_distance=decision.risk_distance,
        signal_timestamp=decision.signal_timestamp,
    )
