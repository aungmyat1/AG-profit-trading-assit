from datetime import datetime, timedelta, timezone
import pytest

from svos.virtual_account import AccountError, PositionState, VirtualAccount
from svos.virtual_exchange import ExchangeRecord, OrderState

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def rec(kind, at, price=None, obs=None, event="E"):
    return ExchangeRecord(kind, kind + event, "O1", at, OrderState.FILLED, kind,
                          "DS1", event, "D1", "P1", 1.1000, price, obs, event)


def fill():
    return rec("FILL", T0 + timedelta(minutes=16), 1.1005, event="FILL-E")


def test_no_fill_no_position_and_valid_fill_one_position():
    account = VirtualAccount()
    assert not account.open_positions
    p = account.apply_fill(fill(), strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version="1.0.1", symbol="EURUSD", side="LONG", stop_price=1.099, target_price=1.101)
    assert len(account.open_positions) == 1 and p.state is PositionState.OPEN
    assert p.reference_price == 1.1 and p.executable_entry_price == 1.1005
    assert not p.broker_volume_authority


def test_duplicate_fill_is_idempotent_and_conflict_fails():
    a = VirtualAccount(); p1 = a.apply_fill(fill(), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")
    p2 = a.apply_fill(fill(), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")
    assert p1.position_id == p2.position_id and len(a.open_positions) == 1
    with pytest.raises(AccountError):
        a.apply_fill(rec("FILL", T0 + timedelta(minutes=16), 1.2, event="FILL-E"), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")


def test_exit_closes_once_and_mechanical_pnl_is_not_economic_pnl():
    a = VirtualAccount(); a.apply_fill(fill(), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")
    closed = a.apply_exit(rec("EXIT", T0 + timedelta(minutes=17), 1.1010, "FAVORABLE", "EXIT-E"))
    assert closed.state is PositionState.CLOSED and closed.normalized_pnl == pytest.approx(.0005)
    assert len(a.closed_positions) == 1 and len(a.open_positions) == 0
    assert a.apply_exit(rec("EXIT", T0 + timedelta(minutes=17), 1.1010, "FAVORABLE", "EXIT-E")) is closed
    assert a.latest_snapshot.economic_pnl_status == "NOT_MODELED"


def test_ambiguous_does_not_close_and_temporal_or_lineage_fail_closed():
    a = VirtualAccount(); a.apply_fill(fill(), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")
    assert a.apply_exit(rec("EXIT", T0 + timedelta(minutes=17), None, "AMBIGUOUS_SEQUENCE", "AMB-E")) is None
    assert len(a.open_positions) == 1
    with pytest.raises(AccountError):
        a.apply_exit(rec("EXIT", T0 + timedelta(minutes=15), 1.099, "ADVERSE", "EARLY"))
    with pytest.raises(AccountError):
        a.apply_fill(ExchangeRecord("FILL", "NO-D", "O1", T0 + timedelta(minutes=16), OrderState.FILLED, "FILL", "", "NO-D", "D1", "P1", 1.1, 1.1), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")


def test_repeated_account_run_has_identical_snapshots_and_unsupported_quantity_is_explicit():
    def run():
        a = VirtualAccount(starting_engineering_balance=10)
        a.apply_fill(fill(), strategy_id="S", strategy_version="1", symbol="EURUSD", side="LONG")
        a.apply_exit(rec("EXIT", T0 + timedelta(minutes=17), 1.099, "ADVERSE", "EXIT-E"))
        return [s.snapshot_id for s in a.snapshots], list(a.closed_positions)
    assert run() == run()
    assert VirtualAccount().max_open_positions == 1
