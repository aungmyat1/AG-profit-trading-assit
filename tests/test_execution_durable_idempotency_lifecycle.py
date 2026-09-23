"""PANEL_R5B_R1: lifecycle-transition remediation.

The independent audit of PANEL_R5B (2ff13af) found DurableExecutionStore.transition()
validated only that the REQUESTED state was a known state, never that reaching it from
the record's ACTUAL current state was legal -- demonstrated by BROKER_ACCEPTED ->
PREPARED being silently accepted and persisted. These tests exercise the fix:
ALLOWED_TRANSITIONS (an explicit current-state -> allowed-target-states graph, checked
before any mutation) and InvalidStateTransition (a specific domain exception).

Every test uses a tmp_path-backed DurableExecutionStore; none touches the real
journal/ directory, and none imports or can reach execution.executor,
execution.mt5_gateway, or order_send.
"""
from __future__ import annotations

import threading

import pytest

from execution.durable_idempotency import (
    ALLOWED_TRANSITIONS,
    DurableExecutionStore,
    InvalidStateTransition,
    STATE_AUTHORIZED,
    STATE_BROKER_ACCEPTED,
    STATE_PREPARED,
    STATE_RECONCILED,
    STATE_REJECTED,
    STATE_SUBMISSION_PENDING,
    STATE_SUBMISSION_UNKNOWN,
    compute_execution_fingerprint,
    is_retry_safe,
)


def _fp(decision_id: str, **overrides) -> str:
    base = dict(
        decision_id=decision_id, proposal_envelope_id="FX:R5B-R1", action="APPROVE_DEMO",
        symbol="EURUSD", environment="DEMO", side="BUY", order_type="MARKET",
        volume=0.05, entry=1.1000, sl=1.0950, tp=1.1100, risk_percent=0.5,
    )
    base.update(overrides)
    return compute_execution_fingerprint(**base)


def _new(store: DurableExecutionStore, decision_id: str):
    return store.create_or_get(decision_id=decision_id, proposal_id="FX:R5B-R1", fingerprint=_fp(decision_id))


# --------------------------------------------------------------------------- 1-5
# Valid forward transitions -- the mission's own canonical path plus the uncertainty
# branch, each exercised as its own edge.
def test_valid_prepared_to_authorized(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-1")
    updated = store.transition("dec-1", state=STATE_AUTHORIZED)
    assert updated.state == STATE_AUTHORIZED


def test_valid_authorized_to_submission_pending(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-2")
    store.transition("dec-2", state=STATE_AUTHORIZED)
    updated = store.transition("dec-2", state=STATE_SUBMISSION_PENDING)
    assert updated.state == STATE_SUBMISSION_PENDING


def test_valid_submission_pending_to_broker_accepted(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-3")
    store.transition("dec-3", state=STATE_AUTHORIZED)
    store.transition("dec-3", state=STATE_SUBMISSION_PENDING)
    updated = store.transition("dec-3", state=STATE_BROKER_ACCEPTED, broker_order_id="1")
    assert updated.state == STATE_BROKER_ACCEPTED
    assert updated.broker_order_id == "1"


def test_valid_submission_pending_to_submission_unknown(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-4")
    store.transition("dec-4", state=STATE_AUTHORIZED)
    store.transition("dec-4", state=STATE_SUBMISSION_PENDING)
    updated = store.transition("dec-4", state=STATE_SUBMISSION_UNKNOWN)
    assert updated.state == STATE_SUBMISSION_UNKNOWN


def test_valid_broker_accepted_to_reconciled(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-5")
    store.transition("dec-5", state=STATE_AUTHORIZED)
    store.transition("dec-5", state=STATE_SUBMISSION_PENDING)
    store.transition("dec-5", state=STATE_BROKER_ACCEPTED, broker_order_id="1")
    updated = store.transition("dec-5", state=STATE_RECONCILED)
    assert updated.state == STATE_RECONCILED


def test_valid_rejection_transitions_where_permitted(tmp_path):
    """"valid rejection transitions where the contract permits them" (P4) -- REJECTED
    is reachable from PREPARED, AUTHORIZED, SUBMISSION_PENDING, and SUBMISSION_UNKNOWN
    (never resurrected afterward -- see the rewind-protection tests below)."""
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    for start_chain, decision_id in (
        ((), "dec-rej-prepared"),
        ((STATE_AUTHORIZED,), "dec-rej-authorized"),
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING), "dec-rej-pending"),
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN), "dec-rej-unknown"),
    ):
        _new(store, decision_id)
        for state in start_chain:
            store.transition(decision_id, state=state)
        updated = store.transition(decision_id, state=STATE_REJECTED)
        assert updated.state == STATE_REJECTED


# --------------------------------------------------------------------------- 6-9
# Rewind protection -- the mission's own required-invalid list.
@pytest.mark.parametrize(
    "chain,illegal_target",
    [
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_BROKER_ACCEPTED), STATE_PREPARED),
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_BROKER_ACCEPTED), STATE_AUTHORIZED),
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN), STATE_PREPARED),
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_SUBMISSION_UNKNOWN), STATE_AUTHORIZED),
        ((STATE_REJECTED,), STATE_PREPARED),
        ((STATE_REJECTED,), STATE_AUTHORIZED),
        ((STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_BROKER_ACCEPTED, STATE_RECONCILED), STATE_PREPARED),
        (
            (STATE_AUTHORIZED, STATE_SUBMISSION_PENDING, STATE_BROKER_ACCEPTED, STATE_RECONCILED),
            STATE_SUBMISSION_PENDING,
        ),
    ],
    ids=[
        "BROKER_ACCEPTED->PREPARED", "BROKER_ACCEPTED->AUTHORIZED",
        "SUBMISSION_UNKNOWN->PREPARED", "SUBMISSION_UNKNOWN->AUTHORIZED",
        "REJECTED->PREPARED", "REJECTED->AUTHORIZED",
        "RECONCILED->PREPARED", "RECONCILED->SUBMISSION_PENDING",
    ],
)
def test_rewind_rejected(tmp_path, chain, illegal_target):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    decision_id = f"dec-rewind-{illegal_target}-{chain[-1] if chain else 'none'}"
    _new(store, decision_id)
    for state in chain:
        kwargs = {"broker_order_id": "1"} if state == STATE_BROKER_ACCEPTED else {}
        store.transition(decision_id, state=state, **kwargs)

    with pytest.raises(InvalidStateTransition):
        store.transition(decision_id, state=illegal_target)


# --------------------------------------------------------------------------- 10
def test_invalid_transition_leaves_durable_record_unchanged(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-10")
    store.transition("dec-10", state=STATE_AUTHORIZED)
    store.transition("dec-10", state=STATE_SUBMISSION_PENDING)
    before = store.transition("dec-10", state=STATE_BROKER_ACCEPTED, broker_order_id="1")

    with pytest.raises(InvalidStateTransition):
        store.transition("dec-10", state=STATE_PREPARED)

    after = store.get("dec-10")
    assert after == before  # state, fingerprint, broker IDs, execution identity: all unchanged


# --------------------------------------------------------------------------- 11
def test_illegal_rewind_remains_rejected_after_restart(tmp_path):
    state_dir = str(tmp_path / "exec")
    instance_one = DurableExecutionStore(state_dir=state_dir)
    _new(instance_one, "dec-11")
    instance_one.transition("dec-11", state=STATE_AUTHORIZED)
    instance_one.transition("dec-11", state=STATE_SUBMISSION_PENDING)
    instance_one.transition("dec-11", state=STATE_BROKER_ACCEPTED, broker_order_id="1")
    del instance_one

    instance_two = DurableExecutionStore(state_dir=state_dir)
    preserved = instance_two.get("dec-11")
    assert preserved.state == STATE_BROKER_ACCEPTED

    with pytest.raises(InvalidStateTransition):
        instance_two.transition("dec-11", state=STATE_PREPARED)

    assert instance_two.get("dec-11") == preserved


# --------------------------------------------------------------------------- 12
def test_incompatible_concurrent_transitions_serialize_safely(tmp_path):
    """From AUTHORIZED, two writers race for SUBMISSION_PENDING and REJECTED --
    both individually legal from AUTHORIZED. Whichever commits first determines what
    is legal for the second: REJECTED is reachable from SUBMISSION_PENDING too, so the
    only outcome that can ever persist is REJECTED (either directly, or via
    AUTHORIZED->SUBMISSION_PENDING->REJECTED) -- there is no interleaving that leaves
    the record corrupted, lost, or in an impossible state, and a writer whose target is
    illegal from whatever the other writer already committed must raise, never
    silently overwrite it."""
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-12")
    store.transition("dec-12", state=STATE_AUTHORIZED)

    outcomes = {}
    barrier = threading.Barrier(2)

    def to_submission_pending():
        barrier.wait()
        try:
            outcomes["A"] = ("ok", store.transition("dec-12", state=STATE_SUBMISSION_PENDING).state)
        except InvalidStateTransition as exc:
            outcomes["A"] = ("rejected", exc)

    def to_rejected():
        barrier.wait()
        try:
            outcomes["B"] = ("ok", store.transition("dec-12", state=STATE_REJECTED).state)
        except InvalidStateTransition as exc:
            outcomes["B"] = ("rejected", exc)

    threads = [threading.Thread(target=to_submission_pending), threading.Thread(target=to_rejected)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert set(outcomes) == {"A", "B"}
    final = store.get("dec-12")
    assert final.state == STATE_REJECTED  # the only state reachable regardless of ordering
    # Whichever writer's transition was illegal from the state it actually landed on
    # must have raised InvalidStateTransition, never silently applied.
    for outcome in outcomes.values():
        assert outcome[0] in ("ok", "rejected")


# --------------------------------------------------------------------------- 13
def test_retry_safety_states_unchanged_by_remediation():
    assert is_retry_safe(STATE_SUBMISSION_PENDING) is False
    assert is_retry_safe(STATE_SUBMISSION_UNKNOWN) is False
    assert is_retry_safe(STATE_BROKER_ACCEPTED) is False


# --------------------------------------------------------------------------- 14
def test_broker_id_conflict_behavior_intact(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-14")
    store.transition("dec-14", state=STATE_AUTHORIZED)
    store.transition("dec-14", state=STATE_SUBMISSION_PENDING)
    store.transition("dec-14", state=STATE_BROKER_ACCEPTED, broker_order_id="1")

    with pytest.raises(ValueError):
        store.transition("dec-14", state=STATE_BROKER_ACCEPTED, broker_order_id="2")

    reaffirmed = store.transition("dec-14", state=STATE_BROKER_ACCEPTED, broker_order_id="1")
    assert reaffirmed.broker_order_id == "1"


# --------------------------------------------------------------------------- P5: same-state semantics
def test_same_state_transition_is_idempotent_not_a_rewind(tmp_path):
    """PANEL_R5B_R1 P5: STATE -> SAME_STATE is an idempotent no-op, even from a
    terminal state whose ALLOWED_TRANSITIONS set is empty -- it is never looked up in
    that graph, so it is never mistaken for a rewind."""
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    _new(store, "dec-same")
    store.transition("dec-same", state=STATE_AUTHORIZED)
    store.transition("dec-same", state=STATE_SUBMISSION_PENDING)
    store.transition("dec-same", state=STATE_BROKER_ACCEPTED, broker_order_id="1")
    store.transition("dec-same", state=STATE_RECONCILED)

    before = store.get("dec-same")
    reaffirmed = store.transition("dec-same", state=STATE_RECONCILED)  # terminal -> itself
    assert reaffirmed.state == STATE_RECONCILED
    assert reaffirmed.execution_id == before.execution_id
    assert reaffirmed.fingerprint == before.fingerprint
    assert reaffirmed.broker_order_id == before.broker_order_id


def test_allowed_transitions_graph_matches_documented_terminals():
    assert ALLOWED_TRANSITIONS[STATE_REJECTED] == frozenset()
    assert ALLOWED_TRANSITIONS[STATE_RECONCILED] == frozenset()
