"""WP6 tests (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md): atomic
deduplication, restart recovery, retry, terminal failure, expiry, ambiguous-outcome
safety. No live Telegram/network call anywhere in this file.
"""
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import pytest

from ticket_delivery.identity import logical_ticket_id
from ticket_delivery.models import (
    STATE_DELIVERED,
    STATE_DELIVERY_AMBIGUOUS,
    STATE_DELIVERY_CLAIMED,
    STATE_DELIVERY_FAILED_RETRYABLE,
    STATE_DELIVERY_FAILED_TERMINAL,
    STATE_NOT_APPLICABLE,
    STATE_READY_TO_DELIVER,
)
from ticket_delivery.delivery_store import TicketDeliveryStore

UTC = dt.timezone.utc


def _ticket_id(**overrides):
    base = dict(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    base.update(overrides)
    return logical_ticket_id(**base)


def _ensure_ready(store: TicketDeliveryStore, ticket_id: str) -> None:
    store.ensure_ready_to_deliver(
        logical_ticket_id=ticket_id, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="deadbeef",
    )


# --------------------------------------------------------------------------- duplicate trigger / repeated run

def test_duplicate_scheduler_trigger_creates_only_one_record(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    first = _ensure_ready(store, ticket_id) or store.get(ticket_id)
    _ensure_ready(store, ticket_id)  # second, duplicate trigger for the same occurrence
    record = store.get(ticket_id)
    assert record.state == STATE_READY_TO_DELIVER
    assert record.attempt_number == 0  # unchanged -- no attempt claimed by mere re-triggering


def test_not_applicable_cycles_are_recorded_but_never_claimable(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id(cycle="LONDON_NEWYORK")
    store.record_not_applicable(
        logical_ticket_id=ticket_id, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="LONDON_NEWYORK",
        trading_date="2026-09-07",
    )
    assert store.get(ticket_id).state == STATE_NOT_APPLICABLE
    result = store.claim_for_delivery(ticket_id)
    assert result.success is False


# --------------------------------------------------------------------------- 10-way concurrency

def test_ten_way_concurrent_claim_exactly_one_winner(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(lambda _: store.claim_for_delivery(ticket_id), range(10)))

    successes = [r for r in results if r.success]
    assert len(successes) == 1
    assert store.get(ticket_id).state == STATE_DELIVERY_CLAIMED
    assert store.get(ticket_id).attempt_number == 1  # only one claim actually incremented it


def test_parallel_workers_different_logical_tickets_each_succeed_independently(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_ids = [_ticket_id(symbol=sym) for sym in ("EURUSD", "GBPUSD")]
    for tid in ticket_ids:
        store.ensure_ready_to_deliver(
            logical_ticket_id=tid, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
            application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
            trading_date="2026-09-07", payload_hash="x",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda tid: store.claim_for_delivery(tid), ticket_ids))

    assert all(r.success for r in results)


# --------------------------------------------------------------------------- restart scenarios

def test_restart_before_claim_reopened_store_still_ready(tmp_path):
    first_store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(first_store, ticket_id)

    reopened_store = TicketDeliveryStore(state_dir=str(tmp_path))  # simulates process restart
    assert reopened_store.get(ticket_id).state == STATE_READY_TO_DELIVER
    result = reopened_store.claim_for_delivery(ticket_id)
    assert result.success is True


def test_restart_after_claim_before_send_second_process_cannot_reclaim(tmp_path):
    first_store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(first_store, ticket_id)
    claim = first_store.claim_for_delivery(ticket_id)
    assert claim.success is True
    # process 1 crashes here, before ever calling mark_delivered/mark_failed_*

    second_store = TicketDeliveryStore(state_dir=str(tmp_path))  # restart
    result = second_store.claim_for_delivery(ticket_id)
    assert result.success is False
    assert second_store.get(ticket_id).state == STATE_DELIVERY_CLAIMED  # exactly as process 1 left it


def test_restart_after_send_before_local_success_recording_state_survives(tmp_path):
    """The claim (and its lock) already persisted to disk before any network attempt --
    a crash between a successful provider send and mark_delivered() leaves the record in
    DELIVERY_CLAIMED, which a caller must treat as ambiguous-on-restart (never silently
    re-claim), not as ready-to-send-again."""
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)
    store.claim_for_delivery(ticket_id)
    # (network send happens here, in the real caller -- not simulated in this unit test)

    reopened = TicketDeliveryStore(state_dir=str(tmp_path))
    assert reopened.get(ticket_id).state == STATE_DELIVERY_CLAIMED
    assert reopened.claim_for_delivery(ticket_id).success is False  # never auto-reclaimed


# --------------------------------------------------------------------------- successful retry / terminal failure / expiry

def test_successful_retry_after_retryable_failure(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)
    store.claim_for_delivery(ticket_id)
    store.mark_failed_retryable(ticket_id, evidence_redacted="HTTP 429 rate limited")
    assert store.get(ticket_id).state == STATE_DELIVERY_FAILED_RETRYABLE

    retry = store.claim_for_delivery(ticket_id)
    assert retry.success is True
    assert retry.record.attempt_number == 2  # a new attempt, same logical ticket
    store.mark_delivered(ticket_id, provider_response_id="msg_123")
    assert store.get(ticket_id).state == STATE_DELIVERED
    assert store.get(ticket_id).logical_ticket_id == ticket_id  # identity never changed across retries


def test_terminal_failure_is_never_retried(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)
    store.claim_for_delivery(ticket_id)
    store.mark_failed_terminal(ticket_id, evidence_redacted="destination unauthorized")

    retry = store.claim_for_delivery(ticket_id)
    assert retry.success is False
    assert store.get(ticket_id).state == STATE_DELIVERY_FAILED_TERMINAL


def test_expired_ticket_cannot_be_claimed(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    past = dt.datetime.now(UTC) - dt.timedelta(minutes=1)
    store.ensure_ready_to_deliver(
        logical_ticket_id=ticket_id, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="x", expires_at=past,
    )
    result = store.claim_for_delivery(ticket_id)
    assert result.success is False


# --------------------------------------------------------------------------- ambiguous outcome

def test_ambiguous_delivery_is_never_automatically_reclaimed(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)
    store.claim_for_delivery(ticket_id)
    store.mark_ambiguous(ticket_id, evidence_redacted="request timeout, no ack received")
    assert store.get(ticket_id).state == STATE_DELIVERY_AMBIGUOUS

    # A scheduler retry / duplicate trigger must never resend from here automatically.
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: store.claim_for_delivery(ticket_id), range(5)))
    assert all(r.success is False for r in results)
    assert store.get(ticket_id).state == STATE_DELIVERY_AMBIGUOUS  # unchanged


def test_ambiguous_outcome_requires_explicit_reconciliation_to_resolve(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)
    store.claim_for_delivery(ticket_id)
    store.mark_ambiguous(ticket_id, evidence_redacted="timeout")

    resolved = store.resolve_ambiguous_outcome(
        ticket_id, resolved_state=STATE_DELIVERED, provider_response_id="msg_999",
        evidence_redacted="manually confirmed present in chat history",
    )
    assert resolved.state == STATE_DELIVERED
    assert resolved.provider_response_id == "msg_999"


# --------------------------------------------------------------------------- correction / no duplicate logical ticket

def test_correction_record_does_not_create_a_second_logical_ticket(tmp_path):
    store = TicketDeliveryStore(state_dir=str(tmp_path))
    ticket_id = _ticket_id()
    _ensure_ready(store, ticket_id)
    _ensure_ready(store, ticket_id)  # simulates a corrected re-evaluation of the same occurrence
    assert store.get(ticket_id).logical_ticket_id == ticket_id
    assert len(store._records.all()) == 1  # exactly one record for this occurrence, ever
