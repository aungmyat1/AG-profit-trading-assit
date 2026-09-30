"""Minimal crypto symbol tick/price-precision config.

Audited before adding: no existing crypto tick-size or symbol-metadata utility exists
anywhere in this repo (mt5.symbol_resolver.SymbolMeta requires a live MT5 terminal and is
Forex/CFD-shaped; targets.py's pip_size() is an explicit Forex-only convention -- spec:
"do NOT apply Forex pip math to crypto"). This is deliberately just the minimum: a
per-symbol tick size constant, plus a synthetic SymbolMeta-shaped record so
execution.risk.size_position -- which only ever reads tick_size/tick_value/
contract_size/volume_min/max/step, pure arithmetic, no MT5 call -- can be REUSED
unchanged for crypto position sizing too, exactly as the revised scope asks for.

tick_value == tick_size (i.e. value_per_price_unit == 1) is the correct USDT-perp
convention when volume is quoted in whole coins and contract_size == 1 (a 1-unit price
move on a 1-coin position changes USDT PnL by 1) -- a documented assumption for V1, not a
live exchange-fetched fact (no exchange integration in this task, per spec).
"""
from __future__ import annotations

from mt5.symbol_resolver import METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta

CRYPTO_TICK_SIZE = {
    "BTCUSDT": 0.1,
    "ETHUSDT": 0.01,
}

DEFAULT_SL_BUFFER_TICKS = 10.0


def crypto_symbol_meta(
    symbol: str, volume_min: float = 0.001, volume_max: float = 1000.0, volume_step: float = 0.001
) -> SymbolMeta:
    if symbol not in CRYPTO_TICK_SIZE:
        raise ValueError(f"no tick size configured for crypto symbol {symbol!r} -- see CRYPTO_TICK_SIZE")
    tick = CRYPTO_TICK_SIZE[symbol]
    digits = len(str(tick).split(".")[-1]) if "." in str(tick) else 0
    return SymbolMeta(
        symbol=symbol, tick_size=tick, tick_value=tick, contract_size=1.0,
        volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
        digits=digits, point=tick,
        # RESEARCH ONLY (module docstring) -- explicitly tagged, never EXCHANGE_VERIFIED,
        # so a real-execution code path cannot mistake this for broker-fetched metadata.
        # See execution.adapter.require_exchange_verified_metadata().
        metadata_source=METADATA_SOURCE_SYNTHETIC_RESEARCH,
    )


def crypto_sl_buffer_price(symbol: str, buffer_ticks: float = DEFAULT_SL_BUFFER_TICKS) -> float:
    if symbol not in CRYPTO_TICK_SIZE:
        raise ValueError(f"no tick size configured for crypto symbol {symbol!r} -- see CRYPTO_TICK_SIZE")
    return CRYPTO_TICK_SIZE[symbol] * buffer_ticks
