"""Broker symbol facts: Market Watch visibility/suffix resolution, and the contract
metadata risk sizing needs (tick size/value, contract size, volume min/max/step,
digits). Deliberately just data lookup -- no pip-value assumption baked in here; FX,
metals, and anything else all go through the same tick_size/tick_value/contract_size
fields (execution/risk.py's job to use them, not this module's job to interpret them).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import MetaTrader5 as mt5


class SymbolMetaError(RuntimeError):
    pass


@dataclass(frozen=True)
class SymbolMeta:
    symbol: str
    tick_size: float
    tick_value: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    digits: int
    point: float = 0.0
    trade_stops_level: int = 0  # points; broker's minimum SL/TP distance from market
    trade_freeze_level: int = 0  # points; broker's minimum distance to modify/close near market


def resolve(symbol: str) -> str:
    raise NotImplementedError(
        "mt5.symbol_resolver.resolve (broker-suffix resolution, e.g. XAUUSD -> XAUUSD.crp) "
        "is not implemented yet -- not needed while the connected account's Market Watch "
        "uses unsuffixed names. See PROJECT_STATUS.md."
    )


def available_symbols(group: Optional[str] = None) -> List[str]:
    """Symbol discovery: names MT5's Market Watch/terminal currently exposes.
    `group` is MT5's own glob-style filter, e.g. "*USD*". Requires
    mt5.connection.connect() already called."""
    symbols = mt5.symbols_get(group) if group else mt5.symbols_get()
    if symbols is None:
        code, message = mt5.last_error()
        raise SymbolMetaError(f"SYMBOL_METADATA_MISSING: symbols_get() failed: ({code}) {message}")
    return sorted(s.name for s in symbols)


def get_symbol_meta(symbol: str) -> SymbolMeta:
    """Requires mt5.connection.connect() already called."""
    info = mt5.symbol_info(symbol)
    if info is None:
        code, message = mt5.last_error()
        raise SymbolMetaError(f"SYMBOL_METADATA_MISSING: symbol_info({symbol!r}) failed: ({code}) {message}")

    if not info.visible:
        # Not in Market Watch -- docs/setup/MT5_MCP_SETUP.md 'Operating notes': invisible to the API
        # even on the right terminal. Try to select it once rather than failing outright.
        if not mt5.symbol_select(symbol, True):
            raise SymbolMetaError(f"SYMBOL_METADATA_MISSING: {symbol!r} not visible and symbol_select failed")
        info = mt5.symbol_info(symbol)
        if info is None:
            raise SymbolMetaError(f"SYMBOL_METADATA_MISSING: symbol_info({symbol!r}) failed after symbol_select")

    if info.trade_tick_size <= 0 or info.trade_tick_value <= 0 or info.trade_contract_size <= 0 or info.volume_step <= 0:
        raise SymbolMetaError(f"SYMBOL_METADATA_MISSING: {symbol!r} has non-positive tick/contract/step metadata")

    return SymbolMeta(
        symbol=symbol,
        tick_size=float(info.trade_tick_size),
        tick_value=float(info.trade_tick_value),
        contract_size=float(info.trade_contract_size),
        volume_min=float(info.volume_min),
        volume_max=float(info.volume_max),
        volume_step=float(info.volume_step),
        digits=int(info.digits),
        point=float(info.point),
        trade_stops_level=int(info.trade_stops_level),
        trade_freeze_level=int(info.trade_freeze_level),
    )
