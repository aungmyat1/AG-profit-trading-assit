"""PANEL_R5C: fail-closed reconciliation of a durable execution decision against
broker-observation evidence. Every test uses a tmp_path-backed DurableExecutionStore
and fake/injected positions_lookup/deals_lookup callables -- no test here imports or
can reach a live MT5 terminal, execution.executor, or any order_send-capable module.
"""
from __future__ import annotations

import pytest

from execution.durable_idempotency import (
    DurableExecutionStore,
    InvalidStateTransition,
    STATE_AUTHORIZED,
    STATE_BROKER_ACCEPTED,
    STATE_PREPARED,
    STATE_RECONCILED,
    STATE_SUBMISSION_PENDING,
    STATE_SUBMISSION_UNKNOWN,
    compute_execution_fingerprint,
    is_retry_safe,
)
from execution.reconciliation import (
    STATE_AMBIGUOUS,
    STATE_BROKER_UNAVAILABLE,
    STATE_CONFLICT,
    STATE_EVIDENCE_INSUFFICIENT,
    STATE_MATCHED,
    STATE_NOT_FOUND,
    comment_tag_for,
    reconcile_decision,
)


class _FakePosition:
    # MT5 semantics: a position's identifier equals its own ticket (the opening order's
    # ticket) -- the identity reconciliation keys on.
    def __init__(self, ticket, comment, symbol="EURUSD", identifier=None):
        self.ticket = ticket
        self.identifier = ticket if identifier is None else identifier
        self.comment = comment
        self.symbol = symbol


class _FakeDeal:
    # MT5 semantics: a deal's ticket is its own deal id; position_id links it to the
    # position it opened (defaults to `ticket` here so single-surface tests keep one id).
    def __init__(self, ticket, comment, entry=0, symbol="EURUSD", position_id=None):
        self.ticket = ticket
        self.position_id = ticket if position_id is None else position_id
        self.comment = comment
        self.entry = entry
        self.symbol = symbol


def _fp(decision_id: str) -> str:
    return compute_execution_fingerprint(
        decision_id=decision_id, proposal_envelope_id="FX:R5C-1", action="APPROVE_DEMO",
        symbol="EURUSD", environment="DEMO", side="BUY", order_type="MARKET",
        volume=0.05, entry=1.1000, sl=1.0950, tp=1.1100, risk_percent=0.5,
    )


def _prepare_pending(store: DurableExecutionStore, decision_id: str, command_id: str = None):
    command_id = command_id or f"OWNER_DECISION:{decision_id}"
    store.create_or_get(
        decision_id=decision_id, proposal_id="FX:R5C-1", fingerprint=_fp(decision_id), command_id=command_id,
    )
    store.transition(decision_id, state=STATE_AUTHORIZED)
    store.transition(decision_id, state=STATE_SUBMISSION_PENDING)
    return store.get(decision_id)


def _lookups(positions=(), deals=()):
    return (lambda symbol=None: list(positions)), (lambda symbol=None: list(deals))


# --------------------------------------------------------------------------- 1
def test_deterministic_broker_match_advances_to_broker_accepted(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _prepare_pending(store, "dec-1")
    tag = comment_tag_for("OWNER_DECISION:dec-1")
    positions_lookup, deals_lookup = _lookups(positions=[_FakePosition(ticket=555, comment=tag)])

    result = reconcile_decision(
        store, "dec-1", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_MATCHED
    assert result.matched_broker_order_id == "555"
    assert result.record.state == STATE_BROKER_ACCEPTED
    assert result.record.broker_order_id == "555"


# --------------------------------------------------------------------------- 2
def test_missing_broker_evidence_never_mutates_record(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    before = _prepare_pending(store, "dec-2")
    positions_lookup, deals_lookup = _lookups()

    result = reconcile_decision(
        store, "dec-2", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_NOT_FOUND
    assert result.record == before  # completely unchanged -- absence is not proof
    assert store.get("dec-2") == before


# --------------------------------------------------------------------------- 3
def test_ambiguous_multiple_distinct_broker_records(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    before = _prepare_pending(store, "dec-3")
    tag = comment_tag_for("OWNER_DECISION:dec-3")
    positions_lookup, deals_lookup = _lookups(
        positions=[_FakePosition(ticket=1, comment=tag), _FakePosition(ticket=2, comment=tag)],
    )

    result = reconcile_decision(
        store, "dec-3", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_AMBIGUOUS
    assert result.record == before  # never arbitrarily picked one


# --------------------------------------------------------------------------- 4
def test_broker_unavailable_never_treated_as_not_found(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    before = _prepare_pending(store, "dec-4")

    def failing_positions_lookup(symbol=None):
        raise ConnectionError("terminal disconnected")

    _, deals_lookup = _lookups()
    result = reconcile_decision(
        store, "dec-4", symbol="EURUSD", positions_lookup=failing_positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_BROKER_UNAVAILABLE
    assert result.record == before


# --------------------------------------------------------------------------- 5
def test_conflicting_broker_id_fails_closed(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _prepare_pending(store, "dec-5")
    tag = comment_tag_for("OWNER_DECISION:dec-5")
    # First reconciliation establishes broker_order_id = 111.
    positions_lookup, deals_lookup = _lookups(positions=[_FakePosition(ticket=111, comment=tag)])
    first = reconcile_decision(
        store, "dec-5", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert first.record.broker_order_id == "111"

    # A later observation claims a DIFFERENT ticket under the same tag -- must fail
    # closed, never silently overwrite 111 with 222.
    positions_lookup_2, deals_lookup_2 = _lookups(positions=[_FakePosition(ticket=222, comment=tag)])
    conflicting = reconcile_decision(
        store, "dec-5", symbol="EURUSD", positions_lookup=positions_lookup_2, deals_lookup=deals_lookup_2,
    )
    assert conflicting.outcome == STATE_CONFLICT
    assert store.get("dec-5").broker_order_id == "111"  # unchanged


# --------------------------------------------------------------------------- 6
def test_restart_then_successful_reconciliation(tmp_path):
    state_dir = str(tmp_path / "exec")
    instance_one = DurableExecutionStore(state_dir=state_dir)
    _prepare_pending(instance_one, "dec-6")
    del instance_one  # simulate process termination

    instance_two = DurableExecutionStore(state_dir=state_dir)
    tag = comment_tag_for("OWNER_DECISION:dec-6")
    positions_lookup, deals_lookup = _lookups(positions=[_FakePosition(ticket=777, comment=tag)])
    result = reconcile_decision(
        instance_two, "dec-6", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_MATCHED
    assert result.record.state == STATE_BROKER_ACCEPTED
    assert result.record.broker_order_id == "777"
    # No duplicate submission occurred -- reconciliation never calls a submission path
    # at all (see test_execution_reconciliation_no_submit.py).


# --------------------------------------------------------------------------- 7
def test_restart_then_unresolved_reconciliation_preserves_uncertainty(tmp_path):
    state_dir = str(tmp_path / "exec")
    instance_one = DurableExecutionStore(state_dir=state_dir)
    before = _prepare_pending(instance_one, "dec-7")
    del instance_one

    instance_two = DurableExecutionStore(state_dir=state_dir)
    positions_lookup, deals_lookup = _lookups()  # no evidence either way
    result = reconcile_decision(
        instance_two, "dec-7", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_NOT_FOUND
    # Still SUBMISSION_PENDING -- never auto-resubmitted, never returned to AUTHORIZED,
    # never downgraded to REJECTED on absence alone.
    assert instance_two.get("dec-7").state == STATE_SUBMISSION_PENDING
    assert instance_two.get("dec-7") == before
    assert is_retry_safe(instance_two.get("dec-7").state) is False


# --------------------------------------------------------------------------- 8
def test_repeated_reconciliation_is_idempotent(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _prepare_pending(store, "dec-8")
    tag = comment_tag_for("OWNER_DECISION:dec-8")
    positions_lookup, deals_lookup = _lookups(positions=[_FakePosition(ticket=42, comment=tag)])

    first = reconcile_decision(
        store, "dec-8", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    second = reconcile_decision(
        store, "dec-8", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    third = reconcile_decision(
        store, "dec-8", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )

    assert first.record.state == STATE_BROKER_ACCEPTED
    assert second.record.state == STATE_RECONCILED  # BROKER_ACCEPTED -> RECONCILED, legal edge
    assert third.record.state == STATE_RECONCILED  # RECONCILED -> RECONCILED, idempotent no-op
    assert second.record.execution_id == third.record.execution_id
    assert second.record.broker_order_id == third.record.broker_order_id == "42"


# --------------------------------------------------------------------------- 9
def test_illegal_lifecycle_rewind_remains_blocked_after_reconciliation(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _prepare_pending(store, "dec-9")
    tag = comment_tag_for("OWNER_DECISION:dec-9")
    positions_lookup, deals_lookup = _lookups(positions=[_FakePosition(ticket=9, comment=tag)])
    reconcile_decision(store, "dec-9", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup)

    with pytest.raises(InvalidStateTransition):
        store.transition("dec-9", state=STATE_PREPARED)  # BROKER_ACCEPTED -> PREPARED, still illegal


# --------------------------------------------------------------------------- 10
def test_retry_unsafe_states_remain_retry_unsafe(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    record = _prepare_pending(store, "dec-10")
    assert is_retry_safe(record.state) is False  # SUBMISSION_PENDING

    positions_lookup, deals_lookup = _lookups()  # NOT_FOUND -- stays SUBMISSION_PENDING
    reconcile_decision(store, "dec-10", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup)
    assert is_retry_safe(store.get("dec-10").state) is False


# --------------------------------------------------------------------------- extra: SUBMISSION_UNKNOWN path
def test_submission_unknown_resolves_to_broker_accepted_on_match(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _prepare_pending(store, "dec-11")
    store.transition("dec-11", state=STATE_SUBMISSION_UNKNOWN)
    tag = comment_tag_for("OWNER_DECISION:dec-11")
    positions_lookup, deals_lookup = _lookups(positions=[_FakePosition(ticket=11, comment=tag)])

    result = reconcile_decision(
        store, "dec-11", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_MATCHED
    assert result.record.state == STATE_BROKER_ACCEPTED
    assert is_retry_safe(STATE_SUBMISSION_UNKNOWN) is False  # unchanged, still never retry-safe


def test_evidence_insufficient_for_out_of_scope_states(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    store.create_or_get(decision_id="dec-12", proposal_id="FX:R5C-1", fingerprint=_fp("dec-12"))
    positions_lookup, deals_lookup = _lookups()

    result = reconcile_decision(
        store, "dec-12", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_EVIDENCE_INSUFFICIENT  # PREPARED is out of scope
    assert result.record.state == STATE_PREPARED  # unchanged


def test_no_durable_record_is_evidence_insufficient_not_a_crash(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    positions_lookup, deals_lookup = _lookups()
    result = reconcile_decision(
        store, "never-created", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_EVIDENCE_INSUFFICIENT
    assert result.record is None


def test_deal_matching_requires_opening_entry_code(tmp_path):
    """A CLOSING deal (entry != 0) tagged with the same comment must never be mistaken
    for the opening fill -- same convention execution.executor._reconcile_via_broker
    already applies."""
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    before = _prepare_pending(store, "dec-13")
    tag = comment_tag_for("OWNER_DECISION:dec-13")
    positions_lookup, deals_lookup = _lookups(deals=[_FakeDeal(ticket=13, comment=tag, entry=1)])

    result = reconcile_decision(
        store, "dec-13", symbol="EURUSD", positions_lookup=positions_lookup, deals_lookup=deals_lookup,
    )
    assert result.outcome == STATE_NOT_FOUND
    assert result.record == before
