"""Lightweight, non-broker-coupled position-state advisory for a proposed/tracked
trade -- current R-multiple and breakeven-eligibility only, driven strictly by a
caller-supplied ManagementPolicy.breakeven_trigger_r. Never modifies anything.

This is deliberately NOT a replacement for Phase 6's manual-entry management system
(claims.py/state.py/rules.py/position_monitor.py), which remains the authoritative,
broker-reconciled advisory for a claimed, already-open MT5 position with its own signed
75%/25% partial+breakeven policy. This module exists for the case Phase 6 does not
cover: a proposed or informally-tracked candidate that has no broker ticket/claim yet
(e.g. a strategy's candidate before a human decides to open it). Reuses
trade_management.risk.current_r() directly -- the R-multiple formula is not
reimplemented a second time.
"""
from __future__ import annotations

from typing import Optional

from .models import (
    ADVISORY_BREAKEVEN_ELIGIBLE,
    ADVISORY_HOLD,
    ADVISORY_INSUFFICIENT_DATA,
    ADVISORY_NOT_REQUESTED,
    ADVISORY_TARGET_REACHED,
    ManagementPolicy,
    PositionStateAdvisory,
)
from .risk import current_r

_DIRECTION_TO_BROKER_SIDE = {"LONG": "BUY", "SHORT": "SELL"}


def evaluate_position_state(
    direction: str,
    entry_price: float,
    stop_loss: float,
    take_profit: Optional[float],
    current_price: Optional[float],
    management_policy: Optional[ManagementPolicy],
) -> PositionStateAdvisory:
    if current_price is None:
        return PositionStateAdvisory(status=ADVISORY_NOT_REQUESTED,
                                      reason="No current_price supplied.")

    initial_r_distance = abs(entry_price - stop_loss)
    broker_side = _DIRECTION_TO_BROKER_SIDE.get(direction)
    r = current_r(broker_side, entry_price, current_price, initial_r_distance) if broker_side else None
    if r is None:
        return PositionStateAdvisory(status=ADVISORY_INSUFFICIENT_DATA,
                                      reason="Could not compute current R (invalid direction or stop distance).")

    if take_profit is not None:
        target_reached = (
            (direction == "LONG" and current_price >= take_profit)
            or (direction == "SHORT" and current_price <= take_profit)
        )
        if target_reached:
            return PositionStateAdvisory(status=ADVISORY_TARGET_REACHED, current_r=r)

    if management_policy is not None and management_policy.breakeven_trigger_r is not None:
        if r >= management_policy.breakeven_trigger_r:
            return PositionStateAdvisory(status=ADVISORY_BREAKEVEN_ELIGIBLE, current_r=r)

    return PositionStateAdvisory(status=ADVISORY_HOLD, current_r=r)
