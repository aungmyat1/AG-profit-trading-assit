"""Read-only quote-state metadata recorded beside each spread observation (P6-R3).

Purpose: give an independent analyst observable API facts that may help explain
zero-spread quotes (fresh two-sided quote vs repeated tick vs non-tradable symbol state
vs demo-feed representation). This module INTERPRETS NOTHING: it copies fields the
MetaTrader5 API actually returned and decodes codes only through the local API's own
constant tables (passed in as `constants`). A code with no local constant table is
recorded raw with decode "UNAVAILABLE_IN_LOCAL_API". No field here is evidence of
executability, and none changes the validated bid/ask spread semantics.

Pure: no MT5 import; deterministic for identical inputs; no account data.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Mapping, Optional

TICK_FIELDS = ("time", "time_msc", "flags", "last", "volume", "volume_real")
SYMBOL_FIELDS = (
    "trade_mode", "trade_exemode", "filling_mode", "order_mode", "trade_calc_mode", "chart_mode",
    "spread", "spread_float", "trade_stops_level", "trade_freeze_level", "ticks_bookdepth",
    "visible", "select", "time", "bid", "ask", "bidhigh", "bidlow", "askhigh", "asklow",
    "session_deals", "session_buy_orders", "session_sell_orders",
)
UNAVAILABLE = "UNAVAILABLE_IN_LOCAL_API"


def local_constant_tables(module: Any) -> Dict[str, Dict[str, int]]:
    """{prefix: {NAME: value}} for the constant families the local API actually defines."""
    tables = {}
    for prefix in ("TICK_FLAG_", "SYMBOL_TRADE_MODE_", "SYMBOL_TRADE_EXECUTION_", "SYMBOL_FILLING_"):
        tables[prefix] = {k[len(prefix):]: int(getattr(module, k)) for k in dir(module) if k.startswith(prefix)}
    return tables


def _copy(obj: Any, fields) -> Dict[str, Any]:
    out = {}
    for f in fields:
        if obj is not None and hasattr(obj, f):
            v = getattr(obj, f)
            if isinstance(v, float) and not math.isfinite(v):
                v = str(v)  # canonical evidence JSON forbids NaN/inf; keep the raw token
            out[f] = v if isinstance(v, (bool, int, float, str)) or v is None else str(v)
    return out


def _decode_enum(value: Optional[int], table: Mapping[str, int]):
    if value is None:
        return None
    if not table:
        return UNAVAILABLE
    names = [n for n, v in sorted(table.items()) if v == value]
    return names[0] if len(names) == 1 else (names or "UNKNOWN_CODE")


def _decode_bits(value: Optional[int], table: Mapping[str, int]):
    if value is None:
        return None
    if not table:
        return UNAVAILABLE
    return sorted(n for n, bit in table.items() if bit and int(value) & bit)


def quote_metadata(
    raw_tick: Any,
    symbol_info: Any,
    constants: Mapping[str, Mapping[str, int]],
    previous_time_msc: Optional[int],
) -> Dict[str, Any]:
    tick = _copy(raw_tick, TICK_FIELDS)
    sym = _copy(symbol_info, SYMBOL_FIELDS)
    time_msc = tick.get("time_msc")
    return {
        "tick": tick,
        "tick_fields_present": sorted(tick),
        "tick_flags_decoded": _decode_bits(tick.get("flags"), constants.get("TICK_FLAG_", {})),
        "same_tick_as_previous_sample": (time_msc == previous_time_msc) if (time_msc is not None and previous_time_msc is not None) else None,
        "symbol": sym,
        "symbol_fields_present": sorted(sym),
        "trade_mode_decoded": _decode_enum(sym.get("trade_mode"), constants.get("SYMBOL_TRADE_MODE_", {})),
        "execution_mode_decoded": _decode_enum(sym.get("trade_exemode"), constants.get("SYMBOL_TRADE_EXECUTION_", {})),
        "filling_mode_decoded": _decode_bits(sym.get("filling_mode"), constants.get("SYMBOL_FILLING_", {})),
        "interpretation": "NONE (raw API facts; not executability evidence)",
    }
