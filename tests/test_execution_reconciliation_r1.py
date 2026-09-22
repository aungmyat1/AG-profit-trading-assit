from __future__ import annotations

from execution.durable_idempotency import (
    DurableExecutionStore,
    STATE_AUTHORIZED,
    STATE_SUBMISSION_PENDING,
    STATE_SUBMISSION_UNKNOWN,
    compute_execution_fingerprint,
)
from execution.reconciliation import (
    STATE_MATCHED,
    STATE_NOT_FOUND,
    comment_tag_for,
    reconcile_decision,
)


class Evidence:
    def __init__(self, comment, ticket):
        self.comment = comment
        self.ticket = ticket
        self.entry = 0


def _store(tmp_path, decision_id="r1", command_id=None):
    command_id = command_id or f"OWNER_DECISION:{decision_id}"
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


def _reconcile(store, decision_id, positions=(), deals=()):
    return reconcile_decision(
        store, decision_id, symbol="EURUSD",
        positions_lookup=lambda symbol=None: list(positions),
        deals_lookup=lambda symbol=None: list(deals),
    )


def test_invalid_ticket_values_never_match_or_persist(tmp_path):
    for index, ticket in enumerate((None, "", " ", "None", "null", 0, "0", -1, "-1", True, 1.5)):
        store, tag = _store(tmp_path / str(index), f"invalid-{index}")
        result = _reconcile(store, f"invalid-{index}", positions=[Evidence(tag, ticket)])
        assert result.outcome == STATE_NOT_FOUND
        record = store.get(f"invalid-{index}")
        assert record.state == STATE_SUBMISSION_PENDING
        assert record.broker_order_id is None


def test_valid_positive_integer_ticket_matches(tmp_path):
    store, tag = _store(tmp_path, "valid")
    result = _reconcile(store, "valid", positions=[Evidence(tag, 12345)])
    assert result.outcome == STATE_MATCHED
    assert result.record.broker_order_id == "12345"


def test_wrong_tag_does_not_match_valid_ticket(tmp_path):
    store, tag = _store(tmp_path, "wrong")
    result = _reconcile(store, "wrong", positions=[Evidence(tag + "X", 12345)])
    assert result.outcome == STATE_NOT_FOUND
    assert store.get("wrong").broker_order_id is None


def test_invalid_plus_valid_uses_only_valid_identity(tmp_path):
    store, tag = _store(tmp_path, "mixed")
    result = _reconcile(
        store, "mixed", positions=[Evidence(tag, None)], deals=[Evidence(tag, 54321)],
    )
    assert result.outcome == STATE_MATCHED
    assert result.record.broker_order_id == "54321"


def test_unknown_restart_with_invalid_evidence_stays_unknown_then_recovers(tmp_path):
    store, tag = _store(tmp_path, "restart")
    store.transition("restart", state=STATE_SUBMISSION_UNKNOWN)
    del store

    restarted = DurableExecutionStore(str(tmp_path / "exec"))
    invalid = _reconcile(restarted, "restart", positions=[Evidence(tag, None)])
    assert invalid.outcome == STATE_NOT_FOUND
    assert restarted.get("restart").state == STATE_SUBMISSION_UNKNOWN
    assert restarted.get("restart").broker_order_id is None

    valid = _reconcile(restarted, "restart", positions=[Evidence(tag, 67890)])
    assert valid.outcome == STATE_MATCHED
    assert valid.record.broker_order_id == "67890"
