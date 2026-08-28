"""Risk supervisor: deterministic position sizing from risk budget + broker symbol
metadata. Independent of AI/strategy discretion -- this is the only place volume is
computed, and it works from tick_size/tick_value/contract_size rather than assuming FX
pip-value math, so the same function sizes FX, metals, or anything else MT5 exposes
that metadata for.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

from mt5.symbol_resolver import SymbolMeta

_FLOAT_TOL = 1e-9


def size_position(
    entry: float,
    stop_loss: float,
    equity: float,
    risk_per_trade_pct: float,
    symbol_meta: SymbolMeta,
) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    """Returns (volume, risk_amount, reason_code). reason_code is None on success; on
    failure volume and risk_amount are both None and reason_code is one of
    VOLUME_BELOW_MIN / VOLUME_ABOVE_MAX / RISK_EXCEEDS_BUDGET / INVALID_STOP_DISTANCE.

    Money-per-lot is derived from tick_size/tick_value (broker-supplied, symbol-agnostic)
    rather than a hardcoded pip-value formula -- see this module's docstring.
    """
    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return None, None, "INVALID_STOP_DISTANCE"

    risk_budget = equity * (risk_per_trade_pct / 100.0)
    value_per_price_unit = symbol_meta.tick_value / symbol_meta.tick_size
    loss_per_lot = stop_distance * value_per_price_unit

    raw_volume = risk_budget / loss_per_lot
    steps = math.floor(raw_volume / symbol_meta.volume_step + _FLOAT_TOL)
    volume = round(steps * symbol_meta.volume_step, 8)  # round off float accumulation noise

    if volume < symbol_meta.volume_min - _FLOAT_TOL:
        return None, None, "VOLUME_BELOW_MIN"
    if volume > symbol_meta.volume_max + _FLOAT_TOL:
        return None, None, "VOLUME_ABOVE_MAX"

    risk_amount = volume * loss_per_lot
    tolerance = max(risk_budget * 1e-6, 1e-6)
    if risk_amount > risk_budget + tolerance:
        return None, None, "RISK_EXCEEDS_BUDGET"

    return volume, risk_amount, None
