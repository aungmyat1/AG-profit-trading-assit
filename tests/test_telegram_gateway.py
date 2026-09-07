"""Integration tests for authorization.telegram_gateway.TelegramExecutionGateway.

No real network call anywhere: a hand-written fake TelegramClient records calls and
returns canned TelegramApiResult objects. No MT5/Bybit import anywhere in this file or
in the module under test -- `fake_execution_handler` is the only execution handler ever
injected here, matching Phase C scope (no broker wiring).
"""
from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor

import pytest

from authorization.models import (
    REASON_APPROVAL_ALREADY_PROCESSED,
    REASON_APPROVAL_EXPIRED,
    REASON_APPROVAL_NOT_FOUND,
    REASON_PROPOSAL_INTEGRITY_MISMATCH,
    REASON_PROPOSAL_NOT_FOUND,
    REASON_UNAUTHORIZED_TELEGRAM_CHAT,
    REASON_UNAUTHORIZED_TELEGRAM_USER,
    STATE_EXECUTED,
    STATE_FAILED,
    STATE_REJECTED,
    VENUE_MT5,
    AuthorizationCheckResult,
)
from authorization.store import ExecutionApprovalStore
from authorization.telegram_gateway import ExecutionHandlerResult, TelegramExecutionGateway, fake_execution_handler
from execution.adapter import TradeProposal
from notifications.telegram_client import ParsedCallbackQuery, build_callback_data

ALLOWED_USER = 111
ALLOWED_CHAT = 999


class _FakeApiResult:
    def __init__(self, ok=True, result=None):
        self.ok = ok
        self.result = result


class _FakeTelegramClient:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.markup_edits = []
        self.answers = []
        self._next_message_id = 1

    def send_message(self, chat_id, text, *, reply_markup=None, parse_mode=None):
        message_id = self._next_message_id
        self._next_message_id += 1
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return _FakeApiResult(ok=True, result={"message_id": message_id})

    def answer_callback_query(self, callback_query_id, *, text=None, show_alert=False):
        self.answers.append({"callback_query_id": callback_query_id, "text": text})
        return _FakeApiResult(ok=True)

    def edit_message_text(self, chat_id, message_id, text, *, reply_markup=None):
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup})
        return _FakeApiResult(ok=True)

    def edit_message_reply_markup(self, chat_id, message_id, *, reply_markup=None):
        self.markup_edits.append({"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup})
        return _FakeApiResult(ok=True)


def _proposal(**overrides) -> TradeProposal:
    base = dict(
        setup_id="ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-07",
        strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="GBPUSD", profile_id="FOREX",
        direction="SHORT", entry=1.34942, stop_loss=1.35026, tp1=1.34798, tp2=1.34522,
        volume=0.05, risk_amount=4.2, risk_percent=0.5,
    )
    base.update(overrides)
    return TradeProposal(**base)


def _always_authorized(strategy_id):
    """This Phase C/gateway-mechanics suite tests claim/reject/execute/restart plumbing,
    not the Phase D1 strategy-authorization feature (covered separately in
    tests/test_phase_d1_strategy_authorization.py and
    tests/test_telegram_gateway_d1_execute_flow.py) -- so it injects an always-True
    strategy check rather than depending on strategies/registry.yaml's real, and
    intentionally False, ST_ASIAN_SWEEP_5R_V1 entry."""
    return AuthorizationCheckResult(True)


def _make_gateway(tmp_path, *, proposal=None, execution_handler=fake_execution_handler,
                  allowed_user_ids=(ALLOWED_USER,), allowed_chat_id=ALLOWED_CHAT,
                  strategy_authorization_check=_always_authorized):
    store = ExecutionApprovalStore(str(tmp_path / "state"))
    client = _FakeTelegramClient()
    proposals = {}
    if proposal is not None:
        proposals[proposal.setup_id] = proposal

    def lookup(setup_id):
        return proposals.get(setup_id)

    gateway = TelegramExecutionGateway(
        client=client, store=store, proposal_lookup=lookup, execution_handler=execution_handler,
        allowed_user_ids=list(allowed_user_ids), allowed_chat_id=allowed_chat_id,
        strategy_authorization_check=strategy_authorization_check,
    )
    return gateway, store, client, proposals


def _callback(action, approval_id, *, user_id=ALLOWED_USER, chat_id=ALLOWED_CHAT, cbq_id="cbq1"):
    return ParsedCallbackQuery(callback_query_id=cbq_id, user_id=user_id, chat_id=chat_id,
                               action=action, approval_id=approval_id)


def _create_sent_approval(gateway, store, proposal):
    approval = store.create(proposal, venue=VENUE_MT5)
    sent = gateway.send_ticket(proposal, approval)
    assert sent is not None
    return sent


# --------------------------------------------------------------------------- send_ticket

def test_send_ticket_transitions_to_pending_and_records_message_id(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = store.create(proposal, venue=VENUE_MT5)
    sent = gateway.send_ticket(proposal, approval)
    assert sent.state == "PENDING"
    assert sent.telegram_chat_id == ALLOWED_CHAT
    assert sent.telegram_message_id == 1
    assert client.sent[0]["reply_markup"] is not None


# ---------------------------------------------------------------------- authorization

def test_unauthorized_user_blocked_before_touching_approval(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("x", approval.approval_id, user_id=666))
    assert result == REASON_UNAUTHORIZED_TELEGRAM_USER
    assert store.get(approval.approval_id).state == "PENDING"


def test_unauthorized_chat_blocked(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("x", approval.approval_id, chat_id=1))
    assert result == REASON_UNAUTHORIZED_TELEGRAM_CHAT
    assert store.get(approval.approval_id).state == "PENDING"


def test_none_chat_id_treated_as_unauthorized(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("x", approval.approval_id, chat_id=None))
    assert result == REASON_UNAUTHORIZED_TELEGRAM_CHAT


def test_unknown_approval_id_blocked(tmp_path):
    gateway, _store, _client, _ = _make_gateway(tmp_path)
    result = gateway.handle_callback(_callback("x", "does-not-exist"))
    assert result == REASON_APPROVAL_NOT_FOUND


# --------------------------------------------------------------------------- details

def test_details_is_read_only(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("d", approval.approval_id))
    assert result == "DETAILS_SHOWN"
    assert store.get(approval.approval_id).state == "PENDING"
    assert "Proposal ID" in client.edits[-1]["text"]


# --------------------------------------------------------------------------- reject

def test_reject_transitions_and_removes_keyboard(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("r", approval.approval_id))
    assert result == STATE_REJECTED
    assert store.get(approval.approval_id).state == STATE_REJECTED
    assert client.edits[-1]["reply_markup"] is None
    assert "REJECTED" in client.edits[-1]["text"]


def test_double_reject_second_call_reports_already_processed(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    first = gateway.handle_callback(_callback("r", approval.approval_id))
    second = gateway.handle_callback(_callback("r", approval.approval_id))
    assert first == STATE_REJECTED
    assert second == REASON_APPROVAL_ALREADY_PROCESSED


# --------------------------------------------------------------------------- execute

def test_execute_success_calls_fake_handler_and_marks_executed(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("x", approval.approval_id))
    assert result == STATE_EXECUTED
    final = store.get(approval.approval_id)
    assert final.state == STATE_EXECUTED
    assert final.result_reference == f"FAKE-{approval.approval_id}"
    assert "EXECUTED" in client.edits[-1]["text"]
    assert client.edits[-1]["reply_markup"] is None


def test_execute_double_click_exactly_one_wins(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(gateway.handle_callback, _callback("x", approval.approval_id, cbq_id="a")),
            pool.submit(gateway.handle_callback, _callback("x", approval.approval_id, cbq_id="b")),
        ]
        results = [f.result() for f in futures]

    assert results.count(STATE_EXECUTED) == 1
    assert results.count(REASON_APPROVAL_ALREADY_PROCESSED) == 1
    assert store.get(approval.approval_id).state == STATE_EXECUTED


def test_execute_vs_reject_race_exactly_one_wins(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(gateway.handle_callback, _callback("x", approval.approval_id, cbq_id="a")),
            pool.submit(gateway.handle_callback, _callback("r", approval.approval_id, cbq_id="b")),
        ]
        results = [f.result() for f in futures]

    final_state = store.get(approval.approval_id).state
    assert final_state in (STATE_EXECUTED, STATE_REJECTED)
    assert results.count(REASON_APPROVAL_ALREADY_PROCESSED) == 1


def test_execute_after_already_executed_is_replay_blocked(tmp_path):
    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal)
    approval = _create_sent_approval(gateway, store, proposal)
    gateway.handle_callback(_callback("x", approval.approval_id, cbq_id="first"))
    replay = gateway.handle_callback(_callback("x", approval.approval_id, cbq_id="replay"))
    assert replay == REASON_APPROVAL_ALREADY_PROCESSED
    # the fake handler's result_reference must not have been overwritten by the replay
    assert store.get(approval.approval_id).result_reference == f"FAKE-{approval.approval_id}"


def test_execute_on_expired_approval_never_calls_execution_handler(tmp_path):
    calls = []

    def handler(proposal, approval):
        calls.append(1)
        return ExecutionHandlerResult(success=True, result_reference="x", detail="x")

    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal, execution_handler=handler)
    approval = store.create(proposal, venue=VENUE_MT5, ttl_seconds=-10)
    gateway.send_ticket(proposal, approval)
    result = gateway.handle_callback(_callback("x", approval.approval_id))
    assert result == REASON_APPROVAL_EXPIRED
    assert calls == []
    assert store.get(approval.approval_id).state == "EXPIRED"


def test_execute_proposal_not_found_never_calls_execution_handler_and_marks_failed(tmp_path):
    calls = []

    def handler(proposal, approval):
        calls.append(1)
        return ExecutionHandlerResult(success=True, result_reference="x", detail="x")

    proposal = _proposal()
    gateway, store, client, proposals = _make_gateway(tmp_path, proposal=proposal, execution_handler=handler)
    approval = _create_sent_approval(gateway, store, proposal)
    proposals.clear()  # simulate the proposal having disappeared before Execute was pressed

    result = gateway.handle_callback(_callback("x", approval.approval_id))
    assert result == REASON_PROPOSAL_NOT_FOUND
    assert calls == []
    final = store.get(approval.approval_id)
    assert final.state == STATE_FAILED
    assert final.failure_reason == REASON_PROPOSAL_NOT_FOUND


def test_execute_integrity_mismatch_never_calls_execution_handler_and_marks_failed(tmp_path):
    calls = []

    def handler(proposal, approval):
        calls.append(1)
        return ExecutionHandlerResult(success=True, result_reference="x", detail="x")

    proposal = _proposal()
    gateway, store, client, proposals = _make_gateway(tmp_path, proposal=proposal, execution_handler=handler)
    approval = _create_sent_approval(gateway, store, proposal)
    # Mutate the looked-up proposal after ticket creation -- the persisted approval's
    # proposal_hash was computed from the ORIGINAL proposal, so this must be detected.
    proposals[proposal.setup_id] = dataclasses.replace(proposal, entry=1.99999)

    result = gateway.handle_callback(_callback("x", approval.approval_id))
    assert result == REASON_PROPOSAL_INTEGRITY_MISMATCH
    assert calls == []
    final = store.get(approval.approval_id)
    assert final.state == STATE_FAILED
    assert final.failure_reason == REASON_PROPOSAL_INTEGRITY_MISMATCH
    assert "MISMATCH" in client.edits[-1]["text"] or "NOT EXECUTED" in client.edits[-1]["text"]


def test_execute_handler_failure_marks_failed_not_executed(tmp_path):
    def failing_handler(proposal, approval):
        return ExecutionHandlerResult(success=False, result_reference="", detail="DEMO_ORDER_REJECTED")

    proposal = _proposal()
    gateway, store, client, _ = _make_gateway(tmp_path, proposal=proposal, execution_handler=failing_handler)
    approval = _create_sent_approval(gateway, store, proposal)
    result = gateway.handle_callback(_callback("x", approval.approval_id))
    assert result == STATE_FAILED
    final = store.get(approval.approval_id)
    assert final.state == STATE_FAILED
    assert final.failure_reason == "DEMO_ORDER_REJECTED"
    assert "NOT EXECUTED" in client.edits[-1]["text"]
    assert "No retry has been performed automatically." in client.edits[-1]["text"]


# --------------------------------------------------------------------------- restart

def test_restart_new_gateway_instance_same_state_dir_stays_consistent(tmp_path):
    proposal = _proposal()
    state_dir = str(tmp_path / "state")
    store1 = ExecutionApprovalStore(state_dir)
    client1 = _FakeTelegramClient()
    proposals = {proposal.setup_id: proposal}
    gateway1 = TelegramExecutionGateway(
        client=client1, store=store1, proposal_lookup=proposals.get, execution_handler=fake_execution_handler,
        allowed_user_ids=[ALLOWED_USER], allowed_chat_id=ALLOWED_CHAT,
        strategy_authorization_check=_always_authorized,
    )
    approval = store1.create(proposal, venue=VENUE_MT5)
    gateway1.send_ticket(proposal, approval)
    gateway1.handle_callback(_callback("x", approval.approval_id))

    # Simulate a process restart: brand-new store + gateway instance, same state_dir.
    store2 = ExecutionApprovalStore(state_dir)
    client2 = _FakeTelegramClient()
    gateway2 = TelegramExecutionGateway(
        client=client2, store=store2, proposal_lookup=proposals.get, execution_handler=fake_execution_handler,
        allowed_user_ids=[ALLOWED_USER], allowed_chat_id=ALLOWED_CHAT,
        strategy_authorization_check=_always_authorized,
    )
    replay = gateway2.handle_callback(_callback("x", approval.approval_id, cbq_id="after-restart"))
    assert replay == REASON_APPROVAL_ALREADY_PROCESSED
    assert store2.get(approval.approval_id).state == STATE_EXECUTED


# ------------------------------------------------------------------------- firewall

def test_gateway_module_never_imports_broker_execution_symbols():
    """Checks actual import statements only -- prose in comments/docstrings is allowed
    to name ExecutionCoordinator when explaining what this module deliberately does
    NOT do yet (see the module docstring); what must never appear is an import of it,
    or of any MT5/Bybit order-construction module."""
    import ast

    import authorization.telegram_gateway as module

    source = open(module.__file__, "r", encoding="utf-8").read()
    tree = ast.parse(source)
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_names.add(node.module)

    forbidden_modules = ("mt5", "execution.coordinator", "execution.executor",
                        "execution_runtime.bybit_linear_perp_feed", "execution_runtime.binance_usdtm_feed", "ccxt")
    for forbidden in forbidden_modules:
        assert not any(name == forbidden or name.startswith(forbidden + ".") for name in imported_names), (
            f"unexpected broker-shaped import: {forbidden}"
        )
    assert "order_send" not in source
