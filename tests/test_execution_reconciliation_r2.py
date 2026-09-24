"""PANEL_R5C-R2: reconciliation keys both broker surfaces on MT5's shared position
identity (position.identifier / deal.position_id), never on each surface's own ticket
-- an MT5 deal's ticket is a deal id that never equals its position's ticket."""
from __future__ import annotations

from types import SimpleNamespace

from execution.durable_idempotency import (
    DurableExecutionStore,
    STATE_AUTHORIZED,
    STATE_BROKER_ACCEPTED,
    STATE_RECONCILED,
    STATE_SUBMISSION_PENDING,
    compute_execution_fingerprint,
)
from execution.reconciliation import (
    STATE_AMBIGUOUS,
    STATE_MATCHED,
    STATE_NOT_FOUND,
    comment_tag_for,
    reconcile_decision,
)


def _store(tmp_path, decision_id):
    command_id = f"OWNER_DECISION:{decision_id}"
    store = DurableExecutionStore(str(tmp_path / "exec"))
    fingerprint = compute_execution_fingerprint(
        decision_id=decision_id, proposal_envelope_id="p", action="APPROVE_DEMO",
        symbol="EURUSD", environment="DEMO",
    )
    store.create_or_get(decision_id=decision_id, proposal_id="p", fingerprint=fingerprint,
                        command_id=command_id)
    store.transition(decision_id, state=STATE_AUTHORIZED)
    store.transition(decision_id, state=STATE_SUBMISSION_PENDING)
    return store, comment_tag_for(command_id)


def _position(tag, ticket):
    return SimpleNamespace(ticket=ticket, identifier=ticket, comment=tag, symbol="EURUSD")


def _opening_deal(tag, deal_ticket, position_id):
    return SimpleNamespace(ticket=deal_ticket, order=position_id, position_id=position_id,
                           entry=0, comment=tag, symbol="EURUSD")


def _reconcile(store, decision_id, positions=(), deals=()):
    return reconcile_decision(
        store, decision_id, symbol="EURUSD",
        positions_lookup=lambda symbol=None: list(positions),
        deals_lookup=lambda symbol=None: list(deals),
    )


def test_open_position_and_its_opening_deal_are_one_broker_record(tmp_path):
    store, tag = _store(tmp_path, "fill")
    result = _reconcile(store, "fill", positions=[_position(tag, 5001)],
                        deals=[_opening_deal(tag, 9001, 5001)])
    assert result.outcome == STATE_MATCHED
    assert result.record.state == STATE_BROKER_ACCEPTED
    assert result.record.broker_order_id == "5001"


def test_position_then_close_only_deal_evidence_reconciles_without_conflict(tmp_path):
    store, tag = _store(tmp_path, "closed")
    first = _reconcile(store, "closed", positions=[_position(tag, 5002)])
    assert first.record.broker_order_id == "5002"

    second = _reconcile(store, "closed", deals=[_opening_deal(tag, 9002, 5002)])
    assert second.outcome == STATE_MATCHED
    assert second.record.state == STATE_RECONCILED
    assert second.record.broker_order_id == "5002"


def test_deal_ticket_is_never_used_as_broker_identity(tmp_path):
    store, tag = _store(tmp_path, "dealonly")
    result = _reconcile(store, "dealonly", deals=[_opening_deal(tag, 9003, 5003)])
    assert result.record.broker_order_id == "5003"


def test_missing_shared_identity_is_not_evidence_even_with_valid_ticket(tmp_path):
    store, tag = _store(tmp_path, "noid")
    position = SimpleNamespace(ticket=5004, comment=tag, symbol="EURUSD")
    deal = SimpleNamespace(ticket=9004, entry=0, comment=tag, symbol="EURUSD")
    result = _reconcile(store, "noid", positions=[position], deals=[deal])
    assert result.outcome == STATE_NOT_FOUND
    assert store.get("noid").state == STATE_SUBMISSION_PENDING
    assert store.get("noid").broker_order_id is None


def test_two_distinct_positions_remain_ambiguous(tmp_path):
    store, tag = _store(tmp_path, "two")
    result = _reconcile(store, "two", positions=[_position(tag, 1), _position(tag, 2)],
                        deals=[_opening_deal(tag, 9, 1)])
    assert result.outcome == STATE_AMBIGUOUS
    assert store.get("two").state == STATE_SUBMISSION_PENDING
