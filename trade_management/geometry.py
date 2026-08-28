"""Trade geometry validation + R/reward distance -- pure functions, no MT5 calls.

Mirrors execution/validator.py::validate_geometry()'s LONG/SHORT SL/TP sign checks
(same underlying rule: SL must be on the losing side of entry, TP on the winning side)
but is generic over a plain (direction, entry, stop_loss, take_profit) request rather
than a strategy_engine.TradeSignal, so it works for both a registered strategy's
candidate and a manually-entered trade -- see TRADE_MANAGEMENT_V1_SPEC.md.

Does not repair invalid geometry (no "better SL/TP") -- only reports which reason_code
made it invalid.
"""
from __future__ import annotations

import math
from typing import Optional

from .models import (
    GEOMETRY_INVALID_DIRECTION,
    GEOMETRY_INVALID_LONG_STOP,
    GEOMETRY_INVALID_LONG_TARGET,
    GEOMETRY_INVALID_PRICE,
    GEOMETRY_INVALID_SHORT_STOP,
    GEOMETRY_INVALID_SHORT_TARGET,
    GEOMETRY_VALID,
    GEOMETRY_ZERO_STOP_DISTANCE,
    SymbolMeta,
    TradeGeometry,
)


def evaluate_geometry(
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: Optional[float] = None,
    symbol_meta: Optional[SymbolMeta] = None,
) -> TradeGeometry:
    if direction not in ("LONG", "SHORT"):
        return TradeGeometry(status=GEOMETRY_INVALID_DIRECTION, direction=direction, entry=entry,
                              stop_loss=stop_loss, take_profit=take_profit,
                              reason=f"direction must be LONG or SHORT, got {direction!r}.")

    prices = [entry, stop_loss] + ([take_profit] if take_profit is not None else [])
    if not all(isinstance(p, (int, float)) and math.isfinite(p) for p in prices):
        return TradeGeometry(status=GEOMETRY_INVALID_PRICE, direction=direction, entry=entry,
                              stop_loss=stop_loss, take_profit=take_profit,
                              reason="entry/stop_loss/take_profit must be finite numbers.")

    stop_distance = abs(entry - stop_loss)
    if stop_distance <= 0:
        return TradeGeometry(status=GEOMETRY_ZERO_STOP_DISTANCE, direction=direction, entry=entry,
                              stop_loss=stop_loss, take_profit=take_profit,
                              reason="stop_loss equals entry -- zero risk distance.")

    if direction == "LONG" and not (stop_loss < entry):
        return TradeGeometry(status=GEOMETRY_INVALID_LONG_STOP, direction=direction, entry=entry,
                              stop_loss=stop_loss, take_profit=take_profit,
                              reason="LONG requires stop_loss < entry.")
    if direction == "SHORT" and not (stop_loss > entry):
        return TradeGeometry(status=GEOMETRY_INVALID_SHORT_STOP, direction=direction, entry=entry,
                              stop_loss=stop_loss, take_profit=take_profit,
                              reason="SHORT requires stop_loss > entry.")

    reward_distance = None
    rr_multiple = None
    if take_profit is not None:
        if direction == "LONG" and not (take_profit > entry):
            return TradeGeometry(status=GEOMETRY_INVALID_LONG_TARGET, direction=direction, entry=entry,
                                  stop_loss=stop_loss, take_profit=take_profit,
                                  reason="LONG requires take_profit > entry.")
        if direction == "SHORT" and not (take_profit < entry):
            return TradeGeometry(status=GEOMETRY_INVALID_SHORT_TARGET, direction=direction, entry=entry,
                                  stop_loss=stop_loss, take_profit=take_profit,
                                  reason="SHORT requires take_profit < entry.")
        reward_distance = abs(take_profit - entry)
        rr_multiple = reward_distance / stop_distance

    stop_distance_points = None
    if symbol_meta is not None and symbol_meta.point and symbol_meta.point > 0:
        stop_distance_points = stop_distance / symbol_meta.point

    return TradeGeometry(
        status=GEOMETRY_VALID, direction=direction, entry=entry, stop_loss=stop_loss,
        take_profit=take_profit, stop_distance_price=stop_distance,
        stop_distance_points=stop_distance_points, reward_distance_price=reward_distance,
        rr_multiple=rr_multiple,
    )
