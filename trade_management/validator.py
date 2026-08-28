"""Pre-execution checks for a ManagementIntent (spec section 16). Pure functions, no MT5
calls -- mirrors execution/validator.py's style so trade_management can be tested the
same way (mocked positions/claims, no live connection).

validate() is the single gate every intent must pass before mt5.management_gateway is
ever called. Fail closed: any ambiguity returns ok=False with a specific reason_code,
never a guess.
"""
from __future__ import annotations

import math
from typing import Optional

from mt5.symbol_resolver import SymbolMeta

from .models import (
    ACTION_CLOSE,
    ACTION_HOLD,
    ACTION_MOVE_SL,
    ACTION_PARTIAL_CLOSE,
    Claim,
    ManagementIntent,
    NormalizedPosition,
    ValidationResult,
)

REASON_NO_ACTION = "NO_ACTION_REQUIRED"
REASON_TICKET_MISMATCH = "TICKET_MISMATCH"
REASON_SYMBOL_MISMATCH = "SYMBOL_MISMATCH"
REASON_DIRECTION_MISMATCH = "DIRECTION_MISMATCH"
REASON_POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
REASON_NOT_CLAIMED = "POSITION_NOT_CLAIMED"
REASON_ALREADY_COMPLETED = "ACTION_ALREADY_COMPLETED"
REASON_INVALID_VOLUME = "INVALID_REQUESTED_VOLUME"
REASON_VOLUME_EXCEEDS_POSITION = "VOLUME_EXCEEDS_POSITION"
REASON_ILLEGAL_REMAINDER = "ILLEGAL_REMAINDER_VOLUME"
REASON_SL_MISSING = "NEW_SL_MISSING"
REASON_SL_INCREASES_RISK = "SL_INCREASES_RISK"
REASON_SL_WRONG_SIDE = "SL_WRONG_SIDE_OF_MARKET"
REASON_SL_TOO_CLOSE_TO_MARKET = "SL_TOO_CLOSE_TO_MARKET"
REASON_MARKET_DATA_MISSING = "MARKET_DATA_MISSING"
REASON_STALE_DATA = "STALE_BROKER_DATA"
_FLOAT_TOL = 1e-9


def validate(
    intent: ManagementIntent,
    claim: Optional[Claim],
    position: Optional[NormalizedPosition],
    already_completed_intent_ids: frozenset,
    symbol_meta: Optional[SymbolMeta] = None,
    data_is_fresh: bool = True,
) -> ValidationResult:
    if intent.action == ACTION_HOLD:
        return ValidationResult(ok=False, reason_code=REASON_NO_ACTION)

    if claim is None:
        return ValidationResult(ok=False, reason_code=REASON_NOT_CLAIMED)

    if position is None:
        return ValidationResult(ok=False, reason_code=REASON_POSITION_NOT_FOUND)

    if intent.position_ticket != claim.ticket or intent.position_ticket != position.ticket:
        return ValidationResult(ok=False, reason_code=REASON_TICKET_MISMATCH)

    if intent.symbol != claim.symbol or intent.symbol != position.symbol:
        return ValidationResult(ok=False, reason_code=REASON_SYMBOL_MISMATCH)

    if claim.direction != position.direction:
        return ValidationResult(ok=False, reason_code=REASON_DIRECTION_MISMATCH)

    if not data_is_fresh:
        return ValidationResult(ok=False, reason_code=REASON_STALE_DATA)

    if not math.isfinite(position.current_price):
        return ValidationResult(ok=False, reason_code=REASON_MARKET_DATA_MISSING)

    if intent.intent_id in already_completed_intent_ids:
        return ValidationResult(ok=False, reason_code=REASON_ALREADY_COMPLETED)

    if intent.action == ACTION_PARTIAL_CLOSE:
        return _validate_partial_close(intent, position, symbol_meta)

    if intent.action == ACTION_MOVE_SL:
        return _validate_move_sl(intent, claim, position, symbol_meta)

    if intent.action == ACTION_CLOSE:
        return _validate_close(intent, position)

    return ValidationResult(ok=False, reason_code="UNKNOWN_ACTION")


def _validate_partial_close(
    intent: ManagementIntent, position: NormalizedPosition, symbol_meta: Optional[SymbolMeta]
) -> ValidationResult:
    volume = intent.requested_volume
    if volume is None or not math.isfinite(volume) or volume <= 0:
        return ValidationResult(ok=False, reason_code=REASON_INVALID_VOLUME)
    if volume > position.volume_current + _FLOAT_TOL:
        return ValidationResult(ok=False, reason_code=REASON_VOLUME_EXCEEDS_POSITION)

    remaining = position.volume_current - volume
    if symbol_meta is not None:
        if remaining > _FLOAT_TOL and remaining < symbol_meta.volume_min - _FLOAT_TOL:
            return ValidationResult(ok=False, reason_code=REASON_ILLEGAL_REMAINDER)

    return ValidationResult(ok=True, reason_code="VALID")


def _validate_move_sl(
    intent: ManagementIntent, claim: Claim, position: NormalizedPosition, symbol_meta: Optional[SymbolMeta]
) -> ValidationResult:
    new_sl = intent.new_sl
    if new_sl is None or not math.isfinite(new_sl):
        return ValidationResult(ok=False, reason_code=REASON_SL_MISSING)

    # Never widen risk beyond the originally accepted risk (spec section 9/18).
    if claim.direction == "BUY" and new_sl < claim.initial_sl - _FLOAT_TOL:
        return ValidationResult(ok=False, reason_code=REASON_SL_INCREASES_RISK)
    if claim.direction == "SELL" and new_sl > claim.initial_sl + _FLOAT_TOL:
        return ValidationResult(ok=False, reason_code=REASON_SL_INCREASES_RISK)

    # SL must stay on the correct side of current market price.
    if claim.direction == "BUY" and new_sl >= position.current_price:
        return ValidationResult(ok=False, reason_code=REASON_SL_WRONG_SIDE)
    if claim.direction == "SELL" and new_sl <= position.current_price:
        return ValidationResult(ok=False, reason_code=REASON_SL_WRONG_SIDE)

    # Broker's minimum SL/TP distance from current market price (spec Phase 0 item 17
    # / Phase 6 "respects stops level" / "respects freeze level") -- an order that
    # violates this is rejected by the broker anyway, but checking here lets us fail
    # closed with a specific reason_code instead of an unhandled broker rejection.
    if symbol_meta is not None and symbol_meta.point > 0:
        min_points = max(symbol_meta.trade_stops_level, symbol_meta.trade_freeze_level)
        min_distance = min_points * symbol_meta.point
        if min_distance > 0 and abs(position.current_price - new_sl) < min_distance - _FLOAT_TOL:
            return ValidationResult(ok=False, reason_code=REASON_SL_TOO_CLOSE_TO_MARKET)

    return ValidationResult(ok=True, reason_code="VALID")


def _validate_close(intent: ManagementIntent, position: NormalizedPosition) -> ValidationResult:
    volume = intent.requested_volume
    if volume is None or not math.isfinite(volume) or volume <= 0:
        return ValidationResult(ok=False, reason_code=REASON_INVALID_VOLUME)
    if volume > position.volume_current + _FLOAT_TOL:
        return ValidationResult(ok=False, reason_code=REASON_VOLUME_EXCEEDS_POSITION)
    return ValidationResult(ok=True, reason_code="VALID")
