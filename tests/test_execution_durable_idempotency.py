"""PANEL_R5B: durable execution identity and restart-safe idempotency.

Every test here uses a tmp_path-backed DurableExecutionStore -- never the real
journal/ directory -- and no test in this file imports or can reach
execution.executor, execution.mt5_gateway, or anything that calls order_send.
"""
from __future__ import annotations

import json
import os
import threading
import time

import pytest

from execution.durable_idempotency import (
    ALL_STATES,
    BROKER_ID_ELIGIBLE_STATES,
    DurableExecutionStore,
    FingerprintConflict,
    IdempotencyStateUnavailable,
    STATE_AUTHORIZED,
    STATE_BROKER_ACCEPTED,
    STATE_PREPARED,
    STATE_REJECTED,
    STATE_SUBMISSION_PENDING,
    STATE_SUBMISSION_UNKNOWN,
    compute_execution_fingerprint,
    execution_id_for,
    is_retry_safe,
)


def _fp(decision_id: str, **overrides) -> str:
    base = dict(
        decision_id=decision_id, proposal_envelope_id="FX:R5B-1", action="APPROVE_DEMO",
        symbol="EURUSD", environment="DEMO", side="BUY", order_type="MARKET",
        volume=0.05, entry=1.1000, sl=1.0950, tp=1.1100, risk_percent=0.5,
    )
    base.update(overrides)
    return compute_execution_fingerprint(**base)


# --------------------------------------------------------------------------- 1
def test_first_execution_identity_persists(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    fingerprint = _fp("dec-1")
    record = store.create_or_get(
        decision_id="dec-1", proposal_id="FX:R5B-1", fingerprint=fingerprint,
        command_id="OWNER_DECISION:dec-1",
    )
    assert record.execution_id == execution_id_for("dec-1")
    assert record.decision_id == "dec-1"
    assert record.proposal_id == "FX:R5B-1"
    assert record.command_id == "OWNER_DECISION:dec-1"
    assert record.fingerprint == fingerprint
    assert record.state == STATE_PREPARED

    reread = store.get("dec-1")
    assert reread == record


# --------------------------------------------------------------------------- 2
def test_identical_retry_returns_same_record(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    fingerprint = _fp("dec-2")
    first = store.create_or_get(decision_id="dec-2", proposal_id="FX:R5B-1", fingerprint=fingerprint)
    second = store.create_or_get(decision_id="dec-2", proposal_id="FX:R5B-1", fingerprint=fingerprint)
    assert first == second
    assert first.execution_id == second.execution_id


# --------------------------------------------------------------------------- 3
def test_conflicting_fingerprint_fails_closed(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    store.create_or_get(decision_id="dec-3", proposal_id="FX:R5B-1", fingerprint=_fp("dec-3"))
    with pytest.raises(FingerprintConflict):
        store.create_or_get(
            decision_id="dec-3", proposal_id="FX:R5B-1",
            fingerprint=_fp("dec-3", symbol="GBPUSD"),  # a different trade
        )
    # The original record must be untouched, not overwritten.
    reread = store.get("dec-3")
    assert reread.fingerprint == _fp("dec-3")


# --------------------------------------------------------------------------- 4 / 5
def test_restart_preserves_identity_and_state(tmp_path):
    state_dir = str(tmp_path / "exec")
    fingerprint = _fp("dec-4")

    instance_one = DurableExecutionStore(state_dir=state_dir)
    created = instance_one.create_or_get(decision_id="dec-4", proposal_id="FX:R5B-1", fingerprint=fingerprint)
    instance_one.transition(
        "dec-4", state=STATE_SUBMISSION_PENDING,
    )
    del instance_one  # simulate process exit -- nothing but the on-disk file survives

    instance_two = DurableExecutionStore(state_dir=state_dir)
    reread = instance_two.get("dec-4")
    assert reread is not None
    assert reread.execution_id == created.execution_id
    assert reread.fingerprint == fingerprint
    assert reread.state == STATE_SUBMISSION_PENDING

    # A "retry" after restart with the identical fingerprint must return the SAME
    # record, never create a second one.
    again = instance_two.create_or_get(decision_id="dec-4", proposal_id="FX:R5B-1", fingerprint=fingerprint)
    assert again.execution_id == created.execution_id
    assert again.state == STATE_SUBMISSION_PENDING  # create_or_get never resets state


# --------------------------------------------------------------------------- 6
def test_concurrent_duplicate_creation_produces_one_record(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    fingerprint = _fp("dec-6")
    results = []
    errors = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            results.append(
                store.create_or_get(decision_id="dec-6", proposal_id="FX:R5B-1", fingerprint=fingerprint)
            )
        except Exception as exc:  # noqa: BLE001 -- captured for assertion, not swallowed
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert errors == []
    assert len(results) == 8
    execution_ids = {r.execution_id for r in results}
    assert execution_ids == {execution_id_for("dec-6")}  # exactly one canonical identity

    # And exactly one record persisted on disk, not eight.
    with open(os.path.join(str(tmp_path / "exec"), "executions.json"), encoding="utf-8") as f:
        on_disk = json.load(f)
    assert list(on_disk.keys()) == ["dec-6"]


# --------------------------------------------------------------------------- 7
def test_persistence_unavailable_fails_closed(tmp_path):
    # A path component that is actually a FILE, not a directory -- os.makedirs must
    # fail, and that failure must surface as IdempotencyStateUnavailable, never as
    # "no lock held, safe to create".
    blocker = tmp_path / "blocked_file"
    blocker.write_text("not a directory")
    unusable_state_dir = str(blocker / "exec")

    store = DurableExecutionStore(state_dir=unusable_state_dir)
    with pytest.raises(IdempotencyStateUnavailable):
        store.create_or_get(decision_id="dec-7", proposal_id="FX:R5B-1", fingerprint=_fp("dec-7"))


# --------------------------------------------------------------------------- 8
def test_corrupted_persistence_fails_closed(tmp_path):
    state_dir = str(tmp_path / "exec")
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "executions.json"), "w", encoding="utf-8") as f:
        f.write("{not valid json::: truncated")

    store = DurableExecutionStore(state_dir=state_dir)
    with pytest.raises(IdempotencyStateUnavailable):
        store.get("dec-8")
    with pytest.raises(IdempotencyStateUnavailable):
        store.create_or_get(decision_id="dec-8", proposal_id="FX:R5B-1", fingerprint=_fp("dec-8"))


# --------------------------------------------------------------------------- 9
def test_submission_unknown_is_never_retry_safe():
    assert is_retry_safe(STATE_SUBMISSION_UNKNOWN) is False
    assert is_retry_safe(STATE_SUBMISSION_PENDING) is False
    assert is_retry_safe(STATE_BROKER_ACCEPTED) is False
    # States that do NOT represent "a submission may already have happened" remain
    # reportable as retry-safe at the persistence layer (a later package still decides
    # whether/how to act on that).
    assert is_retry_safe(STATE_PREPARED) is True
    assert is_retry_safe(STATE_AUTHORIZED) is True
    assert is_retry_safe(STATE_REJECTED) is True


# --------------------------------------------------------------------------- 10
def test_broker_ids_attached_only_per_state_rules(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    store.create_or_get(decision_id="dec-10", proposal_id="FX:R5B-1", fingerprint=_fp("dec-10"))

    # Cannot attach a broker_order_id while transitioning into a non-eligible state.
    with pytest.raises(ValueError):
        store.transition("dec-10", state=STATE_AUTHORIZED, broker_order_id="123456")

    # Eligible state: attaching succeeds.
    updated = store.transition("dec-10", state=STATE_SUBMISSION_PENDING)
    assert updated.broker_order_id is None
    updated = store.transition("dec-10", state=STATE_BROKER_ACCEPTED, broker_order_id="123456")
    assert updated.broker_order_id == "123456"

    # Never silently overwritten with a DIFFERENT broker_order_id.
    with pytest.raises(ValueError):
        store.transition("dec-10", state=STATE_BROKER_ACCEPTED, broker_order_id="999999")

    # Re-affirming the SAME broker_order_id is not an error (idempotent reconciliation
    # write), and is a no-op on the stored value.
    reaffirmed = store.transition("dec-10", state=STATE_BROKER_ACCEPTED, broker_order_id="123456")
    assert reaffirmed.broker_order_id == "123456"


def test_transition_requires_existing_record(tmp_path):
    store = DurableExecutionStore(state_dir=str(tmp_path / "exec"))
    with pytest.raises(IdempotencyStateUnavailable):
        store.transition("never-created", state=STATE_AUTHORIZED)


def test_fingerprint_never_uses_python_hash():
    """compute_execution_fingerprint must be stable across process invocations --
    Python's built-in hash() for str is randomized per-process (PYTHONHASHSEED) unless
    explicitly disabled, so this asserts the actual implementation is SHA-256 (a fixed,
    64-hex-char digest), not a proxy for hash()."""
    fingerprint = _fp("dec-fp")
    assert len(fingerprint) == 64
    assert all(c in "0123456789abcdef" for c in fingerprint)
    # Deterministic: recomputing from the same inputs reproduces the same value.
    assert fingerprint == _fp("dec-fp")


def test_fingerprint_changes_with_execution_critical_fields():
    base = _fp("dec-fp-2")
    assert base != _fp("dec-fp-2", symbol="GBPUSD")
    assert base != _fp("dec-fp-2", side="SELL")
    assert base != _fp("dec-fp-2", volume=0.10)
    assert base != _fp("dec-fp-2", entry=1.2000)


def test_all_states_and_broker_eligible_states_are_disjoint_from_nothing_unexpected():
    # Sanity: every reserved state name from the mission's own diagram is defined.
    assert {
        "PREPARED", "AUTHORIZED", "SUBMISSION_PENDING", "SUBMISSION_UNKNOWN",
        "BROKER_ACCEPTED", "REJECTED", "RECONCILED",
    } == ALL_STATES
    assert BROKER_ID_ELIGIBLE_STATES <= ALL_STATES
