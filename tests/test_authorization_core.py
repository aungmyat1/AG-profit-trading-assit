"""Focused tests for AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1 Phase A+B: the authorization
core only. No Telegram network call, no MT5 call, no Bybit call -- ExecutionCoordinator
is never imported/invoked here. Uses tmp_path-backed stores throughout, never the real
journal/ directory.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest

from authorization.integrity import compute_proposal_hash, verify_proposal_integrity
from authorization.models import (
    ENVIRONMENT_DEMO,
    REASON_APPROVAL_ALREADY_PROCESSED,
    REASON_APPROVAL_EXPIRED,
    REASON_APPROVAL_NOT_FOUND,
    REASON_UNAUTHORIZED_TELEGRAM_CHAT,
    REASON_UNAUTHORIZED_TELEGRAM_USER,
    STATE_CLAIMED,
    STATE_CREATED,
    STATE_EXECUTED,
    STATE_EXECUTING,
    STATE_EXPIRED,
    STATE_PENDING,
    STATE_REJECTED,
    VENUE_MT5,
)
from authorization.store import ExecutionApprovalStore, check_chat_authorized, check_user_authorized
from execution.adapter import TradeProposal

UTC = dt.timezone.utc


def _proposal(**overrides) -> TradeProposal:
    base = dict(
        setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-07",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="GBPUSD", profile_id="FOREX",
        direction="SHORT", entry=1.34942, stop_loss=1.35026, tp1=1.34798, tp2=1.34522,
        volume=0.05, risk_amount=4.2, risk_percent=0.5,
    )
    base.update(overrides)
    return TradeProposal(**base)


# --------------------------------------------------------------------------- integrity

def test_proposal_hash_deterministic():
    p = _proposal()
    assert compute_proposal_hash(p) == compute_proposal_hash(_proposal())


def test_proposal_hash_changes_on_entry_mutation():
    p = _proposal()
    h = compute_proposal_hash(p)
    mutated = dataclasses.replace(p, entry=1.35000)
    assert compute_proposal_hash(mutated) != h


@pytest.mark.parametrize("field_name,new_value", [
    ("entry", 1.35000), ("stop_loss", 1.36000), ("tp1", 1.30000), ("tp2", 1.20000),
    ("volume", 0.99), ("direction", "LONG"), ("risk_amount", 999.0), ("risk_percent", 5.0),
])
def test_proposal_hash_changes_on_any_execution_critical_field(field_name, new_value):
    p = _proposal()
    h = compute_proposal_hash(p)
    mutated = dataclasses.replace(p, **{field_name: new_value})
    assert compute_proposal_hash(mutated) != h


def test_verify_integrity_true_for_unchanged_proposal():
    p = _proposal()
    assert verify_proposal_integrity(p, compute_proposal_hash(p)) is True


def test_verify_integrity_false_for_changed_proposal():
    p = _proposal()
    h = compute_proposal_hash(p)
    mutated = dataclasses.replace(p, stop_loss=1.40000)
    assert verify_proposal_integrity(mutated, h) is False


# --------------------------------------------------------------------------- creation

def test_create_persists_in_created_state(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    assert approval.state == STATE_CREATED
    assert approval.proposal_hash == compute_proposal_hash(_proposal())
    fetched = store.get(approval.approval_id)
    assert fetched == approval


def test_approval_id_is_opaque_and_not_derived_from_proposal(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    a1 = store.create(_proposal(), venue=VENUE_MT5)
    a2 = store.create(_proposal(setup_id="different-setup"), venue=VENUE_MT5)
    assert a1.approval_id != a2.approval_id
    for approval_id in (a1.approval_id, a2.approval_id):
        assert "GBPUSD" not in approval_id
        assert "1.34" not in approval_id


def test_only_demo_environment_supported(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    with pytest.raises(ValueError):
        store.create(_proposal(), venue=VENUE_MT5, environment="LIVE")


def test_mark_sent_to_telegram_transitions_created_to_pending(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    updated = store.mark_sent_to_telegram(approval.approval_id, chat_id=111, message_id=222)
    assert updated.state == STATE_PENDING
    assert updated.telegram_chat_id == 111
    assert updated.telegram_message_id == 222


# --------------------------------------------------------------------------- expiry

def test_expired_approval_cannot_be_claimed(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    now = dt.datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
    approval = store.create(_proposal(), venue=VENUE_MT5, ttl_seconds=60, now=now)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    later = now + dt.timedelta(seconds=61)
    result = store.claim(approval.approval_id, now=later)
    assert result.success is False
    assert result.reason_code == REASON_APPROVAL_EXPIRED
    assert result.approval.state == STATE_EXPIRED
    assert store.get(approval.approval_id).state == STATE_EXPIRED


def test_expired_approval_cannot_be_rejected(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    now = dt.datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
    approval = store.create(_proposal(), venue=VENUE_MT5, ttl_seconds=60, now=now)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    later = now + dt.timedelta(minutes=30)
    result = store.reject(approval.approval_id, now=later)
    assert result.success is False
    assert result.reason_code == REASON_APPROVAL_EXPIRED


# --------------------------------------------------------------------------- claim

def test_unknown_approval_cannot_be_claimed(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    result = store.claim("does-not-exist")
    assert result.success is False
    assert result.reason_code == REASON_APPROVAL_NOT_FOUND


def test_claim_succeeds_exactly_once(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    first = store.claim(approval.approval_id)
    assert first.success is True
    assert first.approval.state == STATE_CLAIMED

    second = store.claim(approval.approval_id)
    assert second.success is False
    assert second.reason_code == REASON_APPROVAL_ALREADY_PROCESSED


def test_double_click_concurrent_claim_has_exactly_one_winner(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: store.claim(approval.approval_id), range(8)))

    successes = [r for r in results if r.success]
    assert len(successes) == 1
    assert store.get(approval.approval_id).state == STATE_CLAIMED


def test_claim_and_reject_race_has_exactly_one_winner(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(store.claim, approval.approval_id)
        f2 = pool.submit(store.reject, approval.approval_id)
        r1, r2 = f1.result(), f2.result()

    successes = [r for r in (r1, r2) if r.success]
    assert len(successes) == 1
    assert store.get(approval.approval_id).state in (STATE_CLAIMED, STATE_REJECTED)


def test_rejected_approval_cannot_later_be_claimed(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    rejection = store.reject(approval.approval_id)
    assert rejection.success is True
    assert rejection.approval.state == STATE_REJECTED

    claim_after_reject = store.claim(approval.approval_id)
    assert claim_after_reject.success is False
    assert claim_after_reject.reason_code == REASON_APPROVAL_ALREADY_PROCESSED


def test_executed_approval_cannot_be_claimed_again(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    store.claim(approval.approval_id)
    store.mark_executing(approval.approval_id)
    store.mark_executed(approval.approval_id, approved_by_user_id=42, result_reference="TICKET-1")

    result = store.claim(approval.approval_id)
    assert result.success is False
    assert result.reason_code == REASON_APPROVAL_ALREADY_PROCESSED
    assert store.get(approval.approval_id).state == STATE_EXECUTED


# ------------------------------------------------------------------------- lifecycle

def test_full_lifecycle_to_executed(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    claimed = store.claim(approval.approval_id).approval
    assert claimed.state == STATE_CLAIMED

    executing = store.mark_executing(approval.approval_id)
    assert executing.state == STATE_EXECUTING

    executed = store.mark_executed(approval.approval_id, approved_by_user_id=42, result_reference="TICKET-1")
    assert executed.state == STATE_EXECUTED
    assert executed.approved_by_user_id == 42
    assert executed.result_reference == "TICKET-1"


def test_mark_executing_requires_claimed_state(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    # never claimed -- still PENDING
    assert store.mark_executing(approval.approval_id) is None


def test_mark_failed_from_executing(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    store.claim(approval.approval_id)
    store.mark_executing(approval.approval_id)
    failed = store.mark_failed(approval.approval_id, failure_reason="BROKER_REJECTED")
    assert failed.state == "FAILED"
    assert failed.failure_reason == "BROKER_REJECTED"


# ----------------------------------------------------------------- restart persistence

def test_restart_persistence_consumed_approval_stays_consumed(tmp_path):
    store1 = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store1.create(_proposal(), venue=VENUE_MT5)
    store1.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)
    store1.claim(approval.approval_id)
    store1.mark_executing(approval.approval_id)
    store1.mark_executed(approval.approval_id, approved_by_user_id=42, result_reference="TICKET-1")

    # Simulate a process restart: brand-new store instance, same on-disk state_dir.
    store2 = ExecutionApprovalStore(state_dir=str(tmp_path))
    reloaded = store2.get(approval.approval_id)
    assert reloaded.state == STATE_EXECUTED

    result = store2.claim(approval.approval_id)
    assert result.success is False
    assert result.reason_code == REASON_APPROVAL_ALREADY_PROCESSED


# ------------------------------------------------------------------ details (read-only)

def test_get_is_read_only_and_never_mutates_state(tmp_path):
    store = ExecutionApprovalStore(state_dir=str(tmp_path))
    approval = store.create(_proposal(), venue=VENUE_MT5)
    store.mark_sent_to_telegram(approval.approval_id, chat_id=1, message_id=1)

    for _ in range(5):
        fetched = store.get(approval.approval_id)
        assert fetched.state == STATE_PENDING
    # A "Details" view calling get() repeatedly must never itself change state or
    # consume the approval.
    assert store.claim(approval.approval_id).success is True


# ---------------------------------------------------------------- Telegram user/chat

def test_authorized_user_accepted():
    assert check_user_authorized(555, [555, 777]).authorized is True


def test_unauthorized_user_blocked():
    result = check_user_authorized(999, [555, 777])
    assert result.authorized is False
    assert result.reason_code == REASON_UNAUTHORIZED_TELEGRAM_USER


def test_authorized_chat_accepted():
    assert check_chat_authorized(-1001234567890, -1001234567890).authorized is True


def test_unauthorized_chat_blocked():
    result = check_chat_authorized(123, -1001234567890)
    assert result.authorized is False
    assert result.reason_code == REASON_UNAUTHORIZED_TELEGRAM_CHAT


def test_user_id_used_as_principal_not_username():
    """check_user_authorized only ever accepts an int -- there is no username
    parameter at all, so a caller cannot accidentally authorize by the mutable,
    not-guaranteed-unique Telegram username."""
    import inspect
    params = inspect.signature(check_user_authorized).parameters
    assert "username" not in params
    assert "user_id" in params


# -------------------------------------------------------------------- execution firewall

def test_authorization_module_never_imports_execution_send_path():
    import authorization.models as models_mod
    import authorization.integrity as integrity_mod
    import authorization.store as store_mod

    for module in (models_mod, integrity_mod, store_mod):
        assert not hasattr(module, "order_send")
        assert "coordinator" not in vars(module)
        assert "executor" not in vars(module)
