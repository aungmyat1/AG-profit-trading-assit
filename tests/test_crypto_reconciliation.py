"""Tests for execution/crypto_reconciliation.py: restart reconciliation from mocked local
journal state + mocked exchange open orders/positions. All inputs are plain dict fixtures
-- no network call anywhere in the module under test."""
from __future__ import annotations

from execution.crypto_reconciliation import (
    REASON_LOCAL_EXECUTED_NOT_FOUND,
    REASON_MULTIPLE_EXCHANGE_MATCHES,
    REASON_NO_EXCHANGE_EVIDENCE_FOR_CLAIM,
    STATE_AMBIGUOUS,
    STATE_CONFIRMED_ABSENT,
    STATE_CONFIRMED_OPEN,
    reconcile,
)


def test_confirmed_open_via_exchange_position_match():
    local = [{"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": "CLAIMED"}]
    positions = [{"clientOrderId": "AGX-1", "orderId": 555}]
    results = reconcile(local, [], positions)
    assert results[0].state == STATE_CONFIRMED_OPEN
    assert results[0].exchange_order_id == "555"


def test_confirmed_open_via_exchange_order_match():
    local = [{"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": "CLAIMED"}]
    orders = [{"clientOrderId": "AGX-1", "orderId": 777}]
    results = reconcile(local, orders, [])
    assert results[0].state == STATE_CONFIRMED_OPEN
    assert results[0].exchange_order_id == "777"


def test_claimed_locally_but_no_exchange_evidence_is_ambiguous():
    local = [{"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": "CLAIMED"}]
    results = reconcile(local, [], [])
    assert results[0].state == STATE_AMBIGUOUS
    assert results[0].reason_code == REASON_NO_EXCHANGE_EVIDENCE_FOR_CLAIM


def test_locally_executed_but_no_exchange_evidence_is_ambiguous():
    local = [{"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": "EXECUTED"}]
    results = reconcile(local, [], [])
    assert results[0].state == STATE_AMBIGUOUS
    assert results[0].reason_code == REASON_LOCAL_EXECUTED_NOT_FOUND


def test_no_local_claim_and_no_exchange_evidence_is_confirmed_absent():
    local = [{"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": None}]
    results = reconcile(local, [], [])
    assert results[0].state == STATE_CONFIRMED_ABSENT


def test_multiple_exchange_matches_is_ambiguous_never_a_guess():
    local = [{"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": "CLAIMED"}]
    orders = [{"clientOrderId": "AGX-1", "orderId": 1}, {"clientOrderId": "AGX-1", "orderId": 2}]
    results = reconcile(local, orders, [])
    assert results[0].state == STATE_AMBIGUOUS
    assert results[0].reason_code == REASON_MULTIPLE_EXCHANGE_MATCHES


def test_multiple_local_entries_reconciled_independently():
    local = [
        {"command_id": "cmd-1", "client_order_id": "AGX-1", "validation_state": "CLAIMED"},
        {"command_id": "cmd-2", "client_order_id": "AGX-2", "validation_state": "CLAIMED"},
    ]
    positions = [{"clientOrderId": "AGX-1", "orderId": 1}]
    results = reconcile(local, [], positions)
    by_id = {r.command_id: r for r in results}
    assert by_id["cmd-1"].state == STATE_CONFIRMED_OPEN
    assert by_id["cmd-2"].state == STATE_AMBIGUOUS
