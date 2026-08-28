"""Tests for trade_management.validator: the gate every ManagementIntent must pass
before mt5.management_gateway is ever called (spec section 16). Pure functions -- no
MT5 connection."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mt5.symbol_resolver import SymbolMeta
from trade_management.models import (
    ACTION_CLOSE,
    ACTION_MOVE_SL,
    ACTION_PARTIAL_CLOSE,
    Claim,
    ManagementIntent,
    NormalizedPosition,
    make_intent_id,
)
from trade_management.validator import (
    REASON_ALREADY_COMPLETED,
    REASON_DIRECTION_MISMATCH,
    REASON_ILLEGAL_REMAINDER,
    REASON_NOT_CLAIMED,
    REASON_POSITION_NOT_FOUND,
    REASON_SL_INCREASES_RISK,
    REASON_SL_WRONG_SIDE,
    REASON_TICKET_MISMATCH,
    REASON_VOLUME_EXCEEDS_POSITION,
    validate,
)

SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)


def _claim(**overrides) -> Claim:
    defaults = dict(
        ticket=1, symbol="EURUSD", direction="BUY", entry_price=1.17000, initial_sl=1.16800,
        initial_volume=0.40, initial_r_distance=0.00200, tp1=1.17600, final_r_multiple=5.0,
        strategy=None, setup=None, claimed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return Claim(**defaults)


def _position(**overrides) -> NormalizedPosition:
    defaults = dict(
        ticket=1, symbol="EURUSD", direction="BUY", volume_initial=0.40, volume_current=0.40,
        entry_price=1.17000, current_bid=1.17600, current_ask=1.17602, current_price=1.17600,
        sl=1.16800, tp=None, profit=0.0, swap=0.0, commission=None, magic=0, comment="",
        open_time=datetime(2026, 8, 27, tzinfo=timezone.utc), account_login=1, account_server="Test-Demo",
    )
    defaults.update(overrides)
    return NormalizedPosition(**defaults)


def _partial_intent(volume=0.30) -> ManagementIntent:
    return ManagementIntent(
        intent_id=make_intent_id(1, ACTION_PARTIAL_CLOSE, "TP1_PARTIAL"), position_ticket=1, symbol="EURUSD",
        action=ACTION_PARTIAL_CLOSE, reason_code="TP1_REACHED", requested_volume=volume,
    )


def test_valid_partial_close_passes():
    result = validate(_partial_intent(), _claim(), _position(), frozenset(), SYMBOL_META)
    assert result.ok


def test_missing_claim_blocks():
    result = validate(_partial_intent(), None, _position(), frozenset())
    assert not result.ok and result.reason_code == REASON_NOT_CLAIMED


def test_missing_position_blocks():
    result = validate(_partial_intent(), _claim(), None, frozenset())
    assert not result.ok and result.reason_code == REASON_POSITION_NOT_FOUND


def test_ticket_mismatch_blocks():
    result = validate(_partial_intent(), _claim(ticket=2), _position(), frozenset())
    assert not result.ok and result.reason_code == REASON_TICKET_MISMATCH


def test_direction_mismatch_blocks():
    result = validate(_partial_intent(), _claim(direction="SELL"), _position(direction="BUY"), frozenset())
    assert not result.ok and result.reason_code == REASON_DIRECTION_MISMATCH


def test_duplicate_action_blocked():
    intent = _partial_intent()
    result = validate(intent, _claim(), _position(), frozenset({intent.intent_id}), SYMBOL_META)
    assert not result.ok and result.reason_code == REASON_ALREADY_COMPLETED


def test_partial_close_volume_exceeds_position_blocks():
    result = validate(_partial_intent(volume=1.0), _claim(), _position(volume_current=0.40), frozenset(), SYMBOL_META)
    assert not result.ok and result.reason_code == REASON_VOLUME_EXCEEDS_POSITION


def test_partial_close_illegal_remainder_blocks():
    # remaining = 0.40 - 0.395 = 0.005, below volume_min (0.01).
    result = validate(_partial_intent(volume=0.395), _claim(), _position(volume_current=0.40), frozenset(), SYMBOL_META)
    assert not result.ok and result.reason_code == REASON_ILLEGAL_REMAINDER


def test_move_sl_widening_risk_blocks_long():
    intent = ManagementIntent(
        intent_id=make_intent_id(1, ACTION_MOVE_SL, "BREAKEVEN"), position_ticket=1, symbol="EURUSD",
        action=ACTION_MOVE_SL, reason_code="TP1_PARTIAL_CONFIRMED", new_sl=1.16700,  # below initial_sl 1.16800
    )
    result = validate(intent, _claim(), _position(volume_current=0.10), frozenset())
    assert not result.ok and result.reason_code == REASON_SL_INCREASES_RISK


def test_move_sl_to_breakeven_passes_long():
    intent = ManagementIntent(
        intent_id=make_intent_id(1, ACTION_MOVE_SL, "BREAKEVEN"), position_ticket=1, symbol="EURUSD",
        action=ACTION_MOVE_SL, reason_code="TP1_PARTIAL_CONFIRMED", new_sl=1.17000,  # == entry
    )
    result = validate(intent, _claim(), _position(volume_current=0.10, current_price=1.17600), frozenset())
    assert result.ok


def test_move_sl_wrong_side_of_market_blocks():
    intent = ManagementIntent(
        intent_id=make_intent_id(1, ACTION_MOVE_SL, "BREAKEVEN"), position_ticket=1, symbol="EURUSD",
        action=ACTION_MOVE_SL, reason_code="TP1_PARTIAL_CONFIRMED", new_sl=1.17700,  # above current price
    )
    result = validate(intent, _claim(), _position(volume_current=0.10, current_price=1.17600), frozenset())
    assert not result.ok and result.reason_code == REASON_SL_WRONG_SIDE


def test_move_sl_within_stops_level_blocks():
    meta = SymbolMeta(**{**SYMBOL_META.__dict__, "point": 0.00001, "trade_stops_level": 100})
    # min distance = 100 * 0.00001 = 0.00100; current_price=1.17600, new_sl=1.17000 ->
    # distance = 0.00600, which is fine -- use a much closer SL to trigger the block.
    intent = ManagementIntent(
        intent_id=make_intent_id(1, ACTION_MOVE_SL, "BREAKEVEN"), position_ticket=1, symbol="EURUSD",
        action=ACTION_MOVE_SL, reason_code="TP1_PARTIAL_CONFIRMED", new_sl=1.17590,  # only 10 points away
    )
    result = validate(intent, _claim(), _position(volume_current=0.10, current_price=1.17600), frozenset(), meta)
    assert not result.ok and result.reason_code == "SL_TOO_CLOSE_TO_MARKET"


def test_move_sl_respects_stops_level_when_far_enough():
    meta = SymbolMeta(**{**SYMBOL_META.__dict__, "point": 0.00001, "trade_stops_level": 100})
    intent = ManagementIntent(
        intent_id=make_intent_id(1, ACTION_MOVE_SL, "BREAKEVEN"), position_ticket=1, symbol="EURUSD",
        action=ACTION_MOVE_SL, reason_code="TP1_PARTIAL_CONFIRMED", new_sl=1.17000,
    )
    result = validate(intent, _claim(), _position(volume_current=0.10, current_price=1.17600), frozenset(), meta)
    assert result.ok


def test_close_intent_valid():
    intent = ManagementIntent(
        intent_id=make_intent_id(1, ACTION_CLOSE, "FINAL_EXIT"), position_ticket=1, symbol="EURUSD",
        action=ACTION_CLOSE, reason_code="FINAL_TARGET_REACHED", requested_volume=0.10,
    )
    result = validate(intent, _claim(), _position(volume_current=0.10), frozenset())
    assert result.ok
