from datetime import datetime, timedelta, timezone
import pytest

from svos.virtual_account import AccountError
from svos.virtual_exchange import ExchangeRecord, OrderState
from svos.virtual_ledger import LedgerError, VirtualLedger

UTC = timezone.utc
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def rec(kind, event, at, price, obs=None):
    return ExchangeRecord(kind, kind + event, "O1", at, OrderState.FILLED, kind, "DS1", event, "D1", "P1", 1.1, price, obs, event)


def ledger_with_close(ambiguous=False):
    l = VirtualLedger()
    root = l.append(event_type="TradeProposal", at=T0, dataset_id="DS1", source_event_id="D1", payload={"symbol": "EURUSD"})
    fill = l.append_exchange_record(rec("FILL", "F1", T0 + timedelta(minutes=16), 1.1005), strategy_id="S", strategy_version="1", side="LONG", stop_price=1.099, target_price=1.101, parent_event_ids=[root.event_id])
    outcome = l.append_exchange_record(rec("EXIT", "X1", T0 + timedelta(minutes=17), None if ambiguous else 1.101, "AMBIGUOUS_SEQUENCE" if ambiguous else "FAVORABLE"), strategy_id="S", strategy_version="1", side="LONG", parent_event_ids=[fill.event_id])
    return l, root, fill, outcome


def test_hash_chain_append_and_duplicate_idempotency():
    l, root, fill, _ = ledger_with_close()
    duplicate = l.append(event_type="TradeProposal", at=T0, dataset_id="DS1", source_event_id="D1", payload={"symbol": "EURUSD"})
    assert duplicate.event_id == root.event_id and len(l.events) == 3
    l.verify()
    assert l.terminal_hash


def test_replay_matches_original_account_for_close_and_ambiguity():
    l, _, _, _ = ledger_with_close()
    replayed = l.replay_account()
    assert len(replayed.open_positions) == 0 and len(replayed.closed_positions) == 1
    assert replayed.latest_snapshot.economic_pnl_status == "NOT_MODELED"
    ambiguous, _, _, _ = ledger_with_close(True)
    unresolved = ambiguous.replay_account()
    assert len(unresolved.open_positions) == 1 and not unresolved.closed_positions


def test_repeated_equivalent_sequences_have_same_terminal_hash():
    a, _, _, _ = ledger_with_close(); b, _, _, _ = ledger_with_close()
    assert a.terminal_hash == b.terminal_hash
    assert [e.event_id for e in a.events] == [e.event_id for e in b.events]


def test_failure_safety_for_parent_chain_and_conflicts():
    l = VirtualLedger()
    with pytest.raises(LedgerError):
        l.append(event_type="VirtualFill", at=T0, dataset_id="DS1", source_event_id="F", payload={}, parent_event_ids=["missing"])
    l.append(event_type="TradeProposal", at=T0, dataset_id="DS1", source_event_id="D", payload={})
    with pytest.raises(LedgerError):
        l.append(event_type="TradeProposal", at=T0 + timedelta(minutes=1), dataset_id="DS1", source_event_id="D", payload={"changed": True})
