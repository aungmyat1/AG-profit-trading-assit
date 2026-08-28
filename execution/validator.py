"""Pre-sizing checks: entry/stop/target geometry, entry-order-type definedness, and
account/symbol/config sanity. Pure functions returning a reason_code (or None on pass)
-- no MT5 calls, no state -- so intent_builder.py can sequence them deterministically.

Spread/slippage/freshness checks (the broker-side pre-send validation) are a later,
separate concern once order_check is implemented -- not duplicated here.
"""
from __future__ import annotations

import math
from typing import Optional

from mt5.symbol_resolver import SymbolMeta
from strategy_engine.models import StrategyConfig, TradeSignal

_ALLOWED_ORDER_TYPES = {"MARKET", "LIMIT"}


def validate_geometry(signal: TradeSignal, strategy: StrategyConfig) -> Optional[str]:
    """Returns a reason_code on failure, None on pass."""
    if signal.status != "SIGNAL":
        return "NOT_A_SIGNAL"

    if signal.direction not in ("LONG", "SHORT") or signal.entry is None or signal.stop_loss is None:
        return "INVALID_ENTRY_GEOMETRY"
    if not (math.isfinite(signal.entry) and math.isfinite(signal.stop_loss)):
        return "INVALID_ENTRY_GEOMETRY"

    stop_distance = abs(signal.entry - signal.stop_loss)
    if not math.isfinite(stop_distance) or stop_distance <= 0:
        return "INVALID_STOP_DISTANCE"

    if signal.direction == "LONG" and not (signal.stop_loss < signal.entry):
        return "INVALID_ENTRY_GEOMETRY"
    if signal.direction == "SHORT" and not (signal.stop_loss > signal.entry):
        return "INVALID_ENTRY_GEOMETRY"

    take_profit = _leg1_target(signal, strategy)
    if take_profit is not None:
        if signal.direction == "LONG" and not (take_profit > signal.entry):
            return "INVALID_ENTRY_GEOMETRY"
        if signal.direction == "SHORT" and not (take_profit < signal.entry):
            return "INVALID_ENTRY_GEOMETRY"

    if strategy.entry_order_type not in _ALLOWED_ORDER_TYPES:
        # e.g. this strategy's "MARKET_OR_LIMIT" -- a real gap, not a bug; see
        # strategies/STRATEGY_LEDGER.md 'Open gaps found building execution/'.
        return "ENTRY_EXECUTION_UNDEFINED"

    return None


def validate_account_and_config(
    equity: Optional[float],
    risk_per_trade_pct: Optional[float],
    symbol_meta: Optional[SymbolMeta],
) -> Optional[str]:
    if equity is None or not math.isfinite(equity) or equity <= 0:
        return "ACCOUNT_DATA_MISSING"
    if risk_per_trade_pct is None or not math.isfinite(risk_per_trade_pct) or not (0 < risk_per_trade_pct <= 100):
        return "INVALID_RISK_CONFIG"
    if symbol_meta is None:
        return "SYMBOL_METADATA_MISSING"
    if (
        symbol_meta.tick_size <= 0
        or symbol_meta.tick_value <= 0
        or symbol_meta.contract_size <= 0
        or symbol_meta.volume_step <= 0
        or symbol_meta.volume_min <= 0
        or symbol_meta.volume_max < symbol_meta.volume_min
    ):
        return "SYMBOL_METADATA_MISSING"
    return None


def leg1_take_profit(signal: TradeSignal, strategy: StrategyConfig) -> Optional[float]:
    return _leg1_target(signal, strategy)


def _leg1_target(signal: TradeSignal, strategy: StrategyConfig) -> Optional[float]:
    if not strategy.legs:
        return None
    leg1 = strategy.legs[0]
    if leg1.target_type != "OPPOSITE_SESSION_BOUNDARY":
        return None
    if signal.direction == "LONG":
        return signal.box_high
    if signal.direction == "SHORT":
        return signal.box_low
    return None
