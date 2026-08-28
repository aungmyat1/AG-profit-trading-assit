"""Tests for trade_management.state: restart-safe reconciliation against live broker
state (spec sections 22, 23, 30 'Restart/reconciliation'). Pure function -- no MT5
connection, positions are hand-built."""
from __future__ import annotations

from datetime import datetime, timezone

from trade_management.models import (
    STATE_BREAKEVEN_DONE,
    STATE_CLOSED,
    STATE_MANAGED_OPEN,
    STATE_RUNNER_ACTIVE,
    STATE_TP1_PARTIAL_DONE,
    Claim,
    NormalizedPosition,
)
from trade_management.state import (
    REASON_OK,
    REASON_POSITION_CLOSED_EXTERNALLY,
    REASON_UNEXPECTED_SL_CHANGE,
    REASON_UNEXPECTED_VOLUME_REDUCTION,
    StateRecord,
    reconcile,
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


def test_restart_before_tp1_is_consistent():
    record = StateRecord(ticket=1, state=STATE_MANAGED_OPEN)
    new_record, reason = reconcile(_claim(), record, _position())
    assert reason == REASON_OK
    assert new_record.state == STATE_MANAGED_OPEN


def test_restart_after_confirmed_partial_is_consistent():
    record = StateRecord(ticket=1, state=STATE_TP1_PARTIAL_DONE, confirmed_partial_volume=0.10)
    new_record, reason = reconcile(_claim(), record, _position(volume_current=0.10))
    assert reason == REASON_OK


def test_restart_after_broker_side_close_marks_closed():
    record = StateRecord(ticket=1, state=STATE_RUNNER_ACTIVE, breakeven_confirmed=True)
    new_record, reason = reconcile(_claim(), record, None)
    assert reason == REASON_POSITION_CLOSED_EXTERNALLY
    assert new_record.state == STATE_CLOSED


def test_already_closed_position_missing_is_still_ok():
    record = StateRecord(ticket=1, state=STATE_CLOSED)
    new_record, reason = reconcile(_claim(), record, None)
    assert reason == REASON_OK
    assert new_record.state == STATE_CLOSED


def test_unexpected_volume_reduction_before_our_partial_blocks():
    # Journal says MANAGED_OPEN (we never requested a partial) but the broker already
    # shows reduced volume -- a manual partial close, per spec section 23.
    record = StateRecord(ticket=1, state=STATE_MANAGED_OPEN)
    new_record, reason = reconcile(_claim(), record, _position(volume_current=0.20))
    assert reason == REASON_UNEXPECTED_VOLUME_REDUCTION


def test_volume_mismatch_after_confirmed_partial_blocks():
    record = StateRecord(ticket=1, state=STATE_TP1_PARTIAL_DONE, confirmed_partial_volume=0.10)
    new_record, reason = reconcile(_claim(), record, _position(volume_current=0.05))
    assert reason == REASON_UNEXPECTED_VOLUME_REDUCTION


def test_unexpected_sl_change_after_breakeven_blocks():
    record = StateRecord(ticket=1, state=STATE_BREAKEVEN_DONE, breakeven_confirmed=True)
    # Claim.entry_price is 1.17000; SL manually moved off that.
    new_record, reason = reconcile(_claim(), record, _position(volume_current=0.10, sl=1.16900))
    assert reason == REASON_UNEXPECTED_SL_CHANGE
