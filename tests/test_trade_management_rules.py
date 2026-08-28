"""Tests for trade_management.rules: TP1 partial / breakeven / 5R exit decisions, BUY
and SELL, and their HOLD/guard paths (spec sections 10, 12, 13, 30). Pure functions --
no MT5 connection."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mt5.symbol_resolver import SymbolMeta
from trade_management.models import (
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
    NormalizedPosition,
)
from trade_management.rules import (
    REASON_BREAKEVEN_ALREADY_DONE,
    REASON_FINAL_TARGET_NOT_REACHED,
    REASON_PARTIAL_NOT_CONFIRMED,
    REASON_TP1_NOT_REACHED,
    REASON_TP1_UNDEFINED,
    evaluate_breakeven,
    evaluate_exit,
    evaluate_partial_profit,
)
from trade_management.state import StateRecord

SYMBOL_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5,
)


def _claim(direction="BUY", entry=1.17000, sl=1.16800, tp1=1.17600, final_r=5.0, volume=0.40) -> Claim:
    r_distance = (entry - sl) if direction == "BUY" else (sl - entry)
    return Claim(
        ticket=1, symbol="EURUSD", direction=direction, entry_price=entry, initial_sl=sl,
        initial_volume=volume, initial_r_distance=r_distance, tp1=tp1, final_r_multiple=final_r,
        strategy=None, setup=None, claimed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )


def _position(direction="BUY", current_price=1.17010, volume=0.40, sl=1.16800) -> NormalizedPosition:
    return NormalizedPosition(
        ticket=1, symbol="EURUSD", direction=direction, volume_initial=0.40, volume_current=volume,
        entry_price=1.17000, current_bid=current_price, current_ask=current_price, current_price=current_price,
        sl=sl, tp=None, profit=0.0, swap=0.0, commission=None, magic=0, comment="",
        open_time=datetime(2026, 8, 27, tzinfo=timezone.utc), account_login=1, account_server="Test-Demo",
    )


def _state(state: str, **overrides) -> StateRecord:
    return StateRecord(ticket=1, state=state, **overrides)


# --------------------------------------------------------------------------- partial profit

def test_partial_profit_holds_below_tp1_long():
    intent = evaluate_partial_profit(_claim(), _position(current_price=1.17500), _state(STATE_MANAGED_OPEN), SYMBOL_META)
    assert intent.action == ACTION_HOLD
    assert intent.reason_code == REASON_TP1_NOT_REACHED


def test_partial_profit_fires_at_tp1_long():
    intent = evaluate_partial_profit(_claim(), _position(current_price=1.17600), _state(STATE_MANAGED_OPEN), SYMBOL_META)
    assert intent.action == ACTION_PARTIAL_CLOSE
    assert intent.requested_volume == pytest.approx(0.30)  # 75% of 0.40, volume_step=0.01


def test_partial_profit_fires_at_tp1_short():
    claim = _claim(direction="SELL", entry=1.35000, sl=1.35250, tp1=1.34250)
    position = _position(direction="SELL", current_price=1.34000)
    intent = evaluate_partial_profit(claim, position, _state(STATE_MANAGED_OPEN), SYMBOL_META)
    assert intent.action == ACTION_PARTIAL_CLOSE


def test_partial_profit_undefined_tp1_holds():
    claim = _claim(tp1=None)
    intent = evaluate_partial_profit(claim, _position(current_price=1.20000), _state(STATE_MANAGED_OPEN), SYMBOL_META)
    assert intent.action == ACTION_HOLD
    assert intent.reason_code == REASON_TP1_UNDEFINED


def test_partial_profit_does_not_refire_after_confirmed():
    intent = evaluate_partial_profit(_claim(), _position(current_price=1.20000), _state(STATE_TP1_PARTIAL_DONE), SYMBOL_META)
    assert intent.action == ACTION_HOLD


# --------------------------------------------------------------------------- breakeven

def test_breakeven_blocked_until_partial_confirmed():
    intent = evaluate_breakeven(_claim(), _position(), _state(STATE_TP1_PENDING))
    assert intent.action == ACTION_HOLD
    assert intent.reason_code == REASON_PARTIAL_NOT_CONFIRMED


def test_breakeven_fires_after_partial_confirmed():
    intent = evaluate_breakeven(_claim(), _position(volume=0.10), _state(STATE_TP1_PARTIAL_DONE))
    assert intent.action == ACTION_MOVE_SL
    assert intent.new_sl == pytest.approx(1.17000)


def test_breakeven_does_not_refire_once_done():
    intent = evaluate_breakeven(_claim(), _position(volume=0.10), _state(STATE_RUNNER_ACTIVE))
    assert intent.action == ACTION_HOLD
    assert intent.reason_code == REASON_BREAKEVEN_ALREADY_DONE


# --------------------------------------------------------------------------- final exit

def test_exit_not_eligible_before_breakeven():
    intent = evaluate_exit(_claim(), _position(volume=0.10), _state(STATE_TP1_PARTIAL_DONE))
    assert intent.action == ACTION_HOLD


def test_exit_holds_below_5r_long():
    claim = _claim()
    # 1R = 0.00200; below 5R (1.18000) at price 1.17900.
    intent = evaluate_exit(claim, _position(current_price=1.17900, volume=0.10), _state(STATE_RUNNER_ACTIVE))
    assert intent.action == ACTION_HOLD
    assert intent.reason_code == REASON_FINAL_TARGET_NOT_REACHED


def test_exit_fires_at_5r_long():
    claim = _claim()
    intent = evaluate_exit(claim, _position(current_price=1.18000, volume=0.10), _state(STATE_RUNNER_ACTIVE))
    assert intent.action == ACTION_CLOSE
    assert intent.requested_volume == pytest.approx(0.10)


def test_exit_fires_at_5r_short():
    claim = _claim(direction="SELL", entry=1.35000, sl=1.35250, tp1=1.34250)
    # 1R = 0.00250; 5R target = 1.35000 - 0.01250 = 1.33750.
    intent = evaluate_exit(claim, _position(direction="SELL", current_price=1.33750, volume=0.05), _state(STATE_RUNNER_ACTIVE))
    assert intent.action == ACTION_CLOSE
