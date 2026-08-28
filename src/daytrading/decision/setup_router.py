"""DAYTRADING_BASIC_SKILLS_ROUTER_V1 setup router (spec sections 11-14): gates
strategy_engine.session.route_completed_session()'s regime/setup/direction output
against a MarketBias for alignment, fail-closed on conflict. Never reimplements ER
classification or sweep detection -- route_completed_session (0.40 ER threshold,
strict-penetration sweep) is called exactly once and its SetupDecision is embedded
verbatim.

Session-pair names (asian/london_am/new_york_am/...) are metadata only -- nothing here
branches on session_name (spec section 28: the same classifier/router path must work
for any currently-supported reference/trade pair).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional, Sequence

from strategy_engine.session import (
    Candle,
    DecisionStatus,
    Direction,
    Regime,
    SetupType,
    build_reference_box,
    route_completed_session,
)

from .models import DaytradingSetupDecision, DirectionAlignment, MarketBias, MarketBiasDirection

_SWEEP_SIDE_BY_REASON = {
    "UPPER_SWEEP_STRICT_PENETRATION": "BUY_SIDE",
    "LOWER_SWEEP_STRICT_PENETRATION": "SELL_SIDE",
}

_BIAS_REASON = {
    MarketBiasDirection.BULLISH.value: "MARKET_BIAS_BULLISH",
    MarketBiasDirection.BEARISH.value: "MARKET_BIAS_BEARISH",
    MarketBiasDirection.NEUTRAL.value: "MARKET_BIAS_NEUTRAL",
    MarketBiasDirection.INDETERMINATE.value: "MARKET_BIAS_INDETERMINATE",
}

_CONFLICT_REASON = {
    SetupType.TREND: "BIAS_TREND_CONFLICT",
    SetupType.SWEEP: "BIAS_SWEEP_CONFLICT",
    SetupType.RANGE: "BIAS_RANGE_CONFLICT",
}
_ALIGNED_REASON = {
    SetupType.TREND: "BIAS_TREND_ALIGNED",
    SetupType.SWEEP: "BIAS_SWEEP_ALIGNED",
    SetupType.RANGE: "BIAS_RANGE_ALIGNED",
}


def _direction_alignment(bias: MarketBias, direction: Optional[Direction]) -> DirectionAlignment:
    if direction is None:
        return DirectionAlignment.NOT_APPLICABLE
    if bias.direction not in (MarketBiasDirection.BULLISH.value, MarketBiasDirection.BEARISH.value):
        return DirectionAlignment.BIAS_NEUTRAL
    aligned = (bias.direction == MarketBiasDirection.BULLISH.value and direction == Direction.LONG) or \
        (bias.direction == MarketBiasDirection.BEARISH.value and direction == Direction.SHORT)
    return DirectionAlignment.ALIGNED if aligned else DirectionAlignment.CONFLICT


def route_daytrading_setup(
    strategy_id: str,
    symbol: str,
    session_name: str,
    session_date: date,
    session_candles: Sequence[Candle],
    expected_bar_count: int,
    market_bias: MarketBias,
    post_session_candles: Sequence[Candle] = (),
    supply_demand_context: Optional[Any] = None,
    entry_confirmation_state: Optional[str] = None,
    evaluation_time: Optional[datetime] = None,
) -> DaytradingSetupDecision:
    box = build_reference_box(session_name, session_candles, expected_bar_count)
    if not box.session_complete:
        return DaytradingSetupDecision(
            symbol=symbol, strategy_id=strategy_id, evaluation_time=evaluation_time,
            market_bias=market_bias, decision_status="WAITING_REFERENCE",
            supply_demand_context=supply_demand_context, entry_confirmation_state=entry_confirmation_state,
            reason_codes=("REFERENCE_SESSION_INCOMPLETE",),
        )

    _, regime, session_decision = route_completed_session(
        strategy_id, symbol, session_name, session_date, session_candles, expected_bar_count,
        post_session_candles,
    )

    session_trend_direction = session_decision.direction if regime is Regime.TREND else None
    sweep_side = _SWEEP_SIDE_BY_REASON.get(session_decision.reason_code)
    sweep_detected = session_decision.setup_type is SetupType.SWEEP and session_decision.decision_status is DecisionStatus.VALID

    reason_codes = [_BIAS_REASON[market_bias.direction]]
    reason_codes.append("ER_TREND_LONG" if regime is Regime.TREND and session_trend_direction == Direction.LONG else
                         "ER_TREND_SHORT" if regime is Regime.TREND and session_trend_direction == Direction.SHORT else
                         "ER_RANGE" if regime is Regime.RANGE else "ER_INDETERMINATE")
    if regime is Regime.RANGE:
        reason_codes.append("SELL_SIDE_SWEEP" if sweep_side == "SELL_SIDE" else
                             "BUY_SIDE_SWEEP" if sweep_side == "BUY_SIDE" else "NO_REFERENCE_SWEEP")

    if session_decision.decision_status is not DecisionStatus.VALID:
        decision_status = session_decision.decision_status.value
        alignment = DirectionAlignment.NOT_APPLICABLE
        execution_eligible = False
        if decision_status == "NO_SETUP":
            reason_codes.append("NO_SETUP")
    else:
        alignment = _direction_alignment(market_bias, session_decision.direction)
        if alignment is DirectionAlignment.CONFLICT:
            decision_status = "CONFLICT"
            execution_eligible = False
            reason_codes.append(_CONFLICT_REASON[session_decision.setup_type])
        elif alignment is DirectionAlignment.BIAS_NEUTRAL:
            decision_status = "NO_SETUP"
            execution_eligible = False
            reason_codes.append("NO_DIRECTION")
        else:  # ALIGNED (NOT_APPLICABLE cannot occur here -- VALID always carries a direction)
            decision_status = "VALID"
            execution_eligible = entry_confirmation_state == "CONFIRMED"
            reason_codes.append(_ALIGNED_REASON[session_decision.setup_type])
            reason_codes.append("SELECT_" + session_decision.setup_type.value + "_SETUP")
            reason_codes.append("CONFIRMED_FOR_EXECUTION" if execution_eligible else "WAITING_CONFIRMATION")

    return DaytradingSetupDecision(
        symbol=symbol, strategy_id=strategy_id, evaluation_time=evaluation_time,
        market_bias=market_bias, regime=regime, session_trend_direction=session_trend_direction,
        efficiency_ratio=box.efficiency_ratio,
        sweep_detected=sweep_detected, sweep_side=sweep_side,
        setup_type=session_decision.setup_type, direction=session_decision.direction,
        direction_alignment=alignment, decision_status=decision_status, execution_eligible=execution_eligible,
        supply_demand_context=supply_demand_context, entry_confirmation_state=entry_confirmation_state,
        reason_codes=tuple(reason_codes), session_decision=session_decision,
    )
