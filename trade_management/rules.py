"""The three deterministic management rules (spec sections 10, 12, 13), each a pure
function: (claim, position, state) -> at most one ManagementIntent. No MT5 calls here --
see mt5.management_gateway for the only place that happens (spec section 1's frozen
architectural principle).

`position-monitor` (state.py + position_monitor-shaped NormalizedPosition) and
`risk-manager` (risk.py) feed these; `partial-profit-manager`, `breakeven-manager`, and
`exit-manager` are exactly evaluate_partial_profit / evaluate_breakeven / evaluate_exit
below -- the .claude/skills/trade_management/* SKILL.md files delegate to these
functions rather than reimplementing the rule.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from mt5.symbol_resolver import SymbolMeta

from .models import (
    ACTION_CLOSE,
    ACTION_HOLD,
    ACTION_MOVE_SL,
    ACTION_PARTIAL_CLOSE,
    STATE_BREAKEVEN_DONE,
    STATE_MANAGED_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_TP1_PARTIAL_DONE,
    STATE_TP1_PENDING,
    Claim,
    ManagementIntent,
    NormalizedPosition,
    make_intent_id,
)
from .risk import current_r, normalize_partial_close_volume, target_price
from .state import StateRecord

PARTIAL_CLOSE_FRACTION = 0.75  # Rule 3, spec section 27 -- not user-configurable in V1.

REASON_TP1_UNDEFINED = "TP1_UNDEFINED"
REASON_TP1_NOT_REACHED = "TP1_NOT_REACHED"
REASON_TP1_ALREADY_HANDLED = "TP1_ALREADY_HANDLED"
REASON_PARTIAL_NOT_CONFIRMED = "PARTIAL_NOT_CONFIRMED"
REASON_BREAKEVEN_ALREADY_DONE = "BREAKEVEN_ALREADY_DONE"
REASON_TP1_PARTIAL_CONFIRMED = "TP1_PARTIAL_CONFIRMED"
REASON_RUNNER_NOT_ELIGIBLE = "RUNNER_NOT_ELIGIBLE"
REASON_FINAL_TARGET_NOT_REACHED = "FINAL_TARGET_REACHED_PENDING"
REASON_FINAL_TARGET_REACHED = "FINAL_TARGET_REACHED"
REASON_ALREADY_CLOSED = "ALREADY_CLOSED"


def _hold(ticket: int, symbol: str, milestone: str, reason_code: str) -> ManagementIntent:
    return ManagementIntent(
        intent_id=make_intent_id(ticket, ACTION_HOLD, milestone),
        position_ticket=ticket,
        symbol=symbol,
        action=ACTION_HOLD,
        reason_code=reason_code,
        created_at=datetime.now(timezone.utc),
    )


def evaluate_partial_profit(
    claim: Claim,
    position: NormalizedPosition,
    state: StateRecord,
    symbol_meta: SymbolMeta,
) -> ManagementIntent:
    if state.state not in (STATE_MANAGED_OPEN, STATE_TP1_PENDING):
        return _hold(claim.ticket, claim.symbol, "TP1_PARTIAL", REASON_TP1_ALREADY_HANDLED)

    if claim.tp1 is None:
        return _hold(claim.ticket, claim.symbol, "TP1_PARTIAL", REASON_TP1_UNDEFINED)

    reached = (
        position.current_price >= claim.tp1 if claim.direction == "BUY" else position.current_price <= claim.tp1
    )
    if not reached:
        return _hold(claim.ticket, claim.symbol, "TP1_PARTIAL", REASON_TP1_NOT_REACHED)

    close_volume, _remaining, reason_code = normalize_partial_close_volume(
        position.volume_current, PARTIAL_CLOSE_FRACTION, symbol_meta
    )
    if reason_code is not None:
        return _hold(claim.ticket, claim.symbol, "TP1_PARTIAL", reason_code)

    return ManagementIntent(
        intent_id=make_intent_id(claim.ticket, ACTION_PARTIAL_CLOSE, "TP1_PARTIAL"),
        position_ticket=claim.ticket,
        symbol=claim.symbol,
        action=ACTION_PARTIAL_CLOSE,
        reason_code="TP1_REACHED",
        requested_volume=close_volume,
        created_at=datetime.now(timezone.utc),
    )


def evaluate_breakeven(claim: Claim, position: NormalizedPosition, state: StateRecord) -> ManagementIntent:
    if state.state in (STATE_BREAKEVEN_DONE, STATE_RUNNER_ACTIVE):
        return _hold(claim.ticket, claim.symbol, "BREAKEVEN", REASON_BREAKEVEN_ALREADY_DONE)

    if state.state != STATE_TP1_PARTIAL_DONE:
        return _hold(claim.ticket, claim.symbol, "BREAKEVEN", REASON_PARTIAL_NOT_CONFIRMED)

    return ManagementIntent(
        intent_id=make_intent_id(claim.ticket, ACTION_MOVE_SL, "BREAKEVEN"),
        position_ticket=claim.ticket,
        symbol=claim.symbol,
        action=ACTION_MOVE_SL,
        reason_code=REASON_TP1_PARTIAL_CONFIRMED,
        new_sl=claim.entry_price,
        created_at=datetime.now(timezone.utc),
    )


def evaluate_exit(claim: Claim, position: NormalizedPosition, state: StateRecord) -> ManagementIntent:
    if state.state not in (STATE_BREAKEVEN_DONE, STATE_RUNNER_ACTIVE):
        return _hold(claim.ticket, claim.symbol, "FINAL_EXIT", REASON_RUNNER_NOT_ELIGIBLE)

    r_now = current_r(claim.direction, claim.entry_price, position.current_price, claim.initial_r_distance)
    if r_now is None or r_now < claim.final_r_multiple:
        return _hold(claim.ticket, claim.symbol, "FINAL_EXIT", REASON_FINAL_TARGET_NOT_REACHED)

    return ManagementIntent(
        intent_id=make_intent_id(claim.ticket, ACTION_CLOSE, "FINAL_EXIT"),
        position_ticket=claim.ticket,
        symbol=claim.symbol,
        action=ACTION_CLOSE,
        reason_code=REASON_FINAL_TARGET_REACHED,
        requested_volume=position.volume_current,
        created_at=datetime.now(timezone.utc),
    )


def final_target_price(claim: Claim) -> Optional[float]:
    return target_price(claim.direction, claim.entry_price, claim.initial_r_distance, claim.final_r_multiple)
