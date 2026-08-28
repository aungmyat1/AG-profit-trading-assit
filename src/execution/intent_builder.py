"""Builds a TradeIntent from a strategy_engine.TradeSignal.

SIGNAL TradeSignal -> geometry/config validation -> live-equity risk sizing ->
volume/risk re-validation -> READY_FOR_ORDER_CHECK.

Stops here. Does not call order_check or order_send -- see execution/mt5_gateway.py
(still NotImplementedError) for that boundary. No breakeven/trailing/partial-close
logic; this module produces one intent for one signal, nothing more.
"""
from __future__ import annotations

from mt5.symbol_resolver import SymbolMeta
from strategy_engine.models import StrategyConfig, TradeSignal

from .models import STATUS_READY, IntentResult, TradeIntent
from .risk import size_position
from .validator import leg1_take_profit, validate_account_and_config, validate_geometry


def build_intent(
    signal: TradeSignal,
    strategy: StrategyConfig,
    equity: float,
    symbol_meta: SymbolMeta,
    risk_per_trade_pct: float,
) -> IntentResult:
    geometry_error = validate_geometry(signal, strategy)
    if geometry_error is not None:
        return IntentResult(status=geometry_error, reason_code=geometry_error)

    config_error = validate_account_and_config(equity, risk_per_trade_pct, symbol_meta)
    if config_error is not None:
        return IntentResult(status=config_error, reason_code=config_error)

    volume, risk_amount, sizing_error = size_position(
        signal.entry, signal.stop_loss, equity, risk_per_trade_pct, symbol_meta
    )
    if sizing_error is not None:
        return IntentResult(status=sizing_error, reason_code=sizing_error)

    intent = TradeIntent(
        signal_id=signal.signal_id,
        strategy_id=signal.strategy_id,
        strategy_version=signal.strategy_version,
        pair_id=signal.pair_id,
        symbol=signal.symbol,
        direction=signal.direction,
        entry=signal.entry,
        stop_loss=signal.stop_loss,
        take_profit=leg1_take_profit(signal, strategy),
        volume=volume,
        risk_amount=risk_amount,
        risk_percent=risk_per_trade_pct,
        equity_at_sizing=equity,
        magic_number=strategy.magic_number,
    )
    return IntentResult(status=STATUS_READY, reason_code=STATUS_READY, intent=intent)
