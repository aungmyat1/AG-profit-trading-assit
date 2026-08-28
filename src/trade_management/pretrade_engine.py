"""TRADE_MANAGEMENT_V1 engine -- the single public entry point for pre-trade geometry,
sizing, and (optional) position-state advisory.

Proposed Trade (strategy candidate or manual entry) -> TradeManagementRequest ->
evaluate_trade_management() -> TradeManagementResult -- consumed by either a human via
the assistant, or a signed strategy building its own TradeIntent. Never calls
execution/order_check/order_send -- see tests/test_trade_management_pretrade.py's
import-safety test.

`overall_status` aggregation (the one judgment call this module makes beyond
pass-through -- see docs/specs/TRADE_MANAGEMENT_V1_SPEC.md):

    geometry invalid                                    -> BLOCKED
    geometry valid, sizing not requested                -> READY
    geometry valid, sizing READY                         -> READY
    geometry valid, sizing failed (any other status)     -> BLOCKED

`READY` means "Trade Management's calculations are valid," never "execute this trade" --
execution authority is a separate concern (execution/, gated independently, project-wide
paused; see docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md).
"""
from __future__ import annotations

from .geometry import evaluate_geometry
from .models import (
    GEOMETRY_VALID,
    OVERALL_BLOCKED,
    OVERALL_READY,
    PositionSizing,
    SIZING_NOT_REQUESTED,
    SIZING_READY,
    TradeManagementRequest,
    TradeManagementResult,
)
from .position_state import evaluate_position_state
from .sizing import evaluate_sizing


def evaluate_trade_management(request: TradeManagementRequest) -> TradeManagementResult:
    geometry = evaluate_geometry(
        request.direction, request.entry_price, request.stop_loss,
        request.take_profit, request.symbol_meta,
    )

    reasons = []
    if geometry.reason:
        reasons.append(geometry.reason)

    if geometry.status != GEOMETRY_VALID:
        sizing = PositionSizing(status=SIZING_NOT_REQUESTED,
                                 reason="Sizing not evaluated -- geometry is invalid.")
    elif request.equity is None and request.risk_percent is None and request.risk_amount is None \
            and request.symbol_meta is None:
        sizing = PositionSizing(status=SIZING_NOT_REQUESTED,
                                 reason="No risk/equity/symbol_meta supplied -- caller did not request sizing.")
    else:
        max_risk_percent = (
            request.management_policy.max_risk_percent if request.management_policy else None
        )
        sizing = evaluate_sizing(
            request.entry_price, request.stop_loss, request.equity,
            request.risk_percent, request.risk_amount, request.symbol_meta, max_risk_percent,
        )
        if sizing.reason:
            reasons.append(sizing.reason)

    position_state = evaluate_position_state(
        request.direction, request.entry_price, request.stop_loss, request.take_profit,
        request.current_price, request.management_policy,
    )

    if geometry.status != GEOMETRY_VALID or sizing.status not in (SIZING_READY, SIZING_NOT_REQUESTED):
        overall_status = OVERALL_BLOCKED
    else:
        overall_status = OVERALL_READY

    return TradeManagementResult(
        symbol=request.symbol,
        direction=request.direction,
        overall_status=overall_status,
        geometry=geometry,
        sizing=sizing,
        position_state=position_state,
        reasons=tuple(reasons),
    )
