"""WP5 tests (docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md). No real
Telegram send anywhere -- notifications.telegram_client.TelegramClient is always
constructed with an injected fake `session` object, the same dependency-injection idiom
its own module docstring documents for tests.
"""
from __future__ import annotations

import datetime as dt

import pytest

from notifications.telegram_client import TelegramClient
from ticket_delivery.delivery_store import TicketDeliveryStore
from ticket_delivery.identity import logical_ticket_id
from ticket_delivery.models import (
    STATE_DELIVERED,
    STATE_DELIVERY_AMBIGUOUS,
    STATE_DELIVERY_FAILED_RETRYABLE,
    STATE_DELIVERY_FAILED_TERMINAL,
)
from ticket_delivery.telegram_adapter import (
    REASON_MISSING_BOT_TOKEN,
    REASON_MISSING_CHAT_ID,
    REASON_UNAUTHORIZED_DESTINATION,
    TelegramConfigError,
    TelegramDestinationConfig,
    deliver_informational_ticket,
)

FAKE_TOKEN = "123456:AAFAKE-TEST-TOKEN-NEVER-REAL"
AUTHORIZED_CHAT = 987654321


class _FakeResponse:
    def __init__(self, json_body, status_ok=True):
        self._json_body = json_body
        self._status_ok = status_ok

    def raise_for_status(self):
        if not self._status_ok:
            import requests
            raise requests.HTTPError("simulated HTTP error")

    def json(self):
        return self._json_body


class _FakeSession:
    """Injected in place of `requests` -- .post() is the only method ever called by
    TelegramClient.send_message()."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return self._responder(url, json)


def _store(tmp_path):
    return TicketDeliveryStore(state_dir=str(tmp_path))


def _ticket_id():
    return logical_ticket_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="EURUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))


def _ready(store):
    tid = _ticket_id()
    store.ensure_ready_to_deliver(
        logical_ticket_id=tid, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="hash123",
    )
    return tid


def _destination():
    return TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])


# --------------------------------------------------------------------------- configuration guards

def test_missing_bot_token_fails_closed_before_any_network_call():
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_values(bot_token=None, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])
    assert exc_info.value.reason_code == REASON_MISSING_BOT_TOKEN


def test_missing_destination_fails_closed():
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=None, authorized_chat_ids=[AUTHORIZED_CHAT])
    assert exc_info.value.reason_code == REASON_MISSING_CHAT_ID


def test_unauthorized_destination_rejected():
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=111, authorized_chat_ids=[AUTHORIZED_CHAT])
    assert exc_info.value.reason_code == REASON_UNAUTHORIZED_DESTINATION


def test_bot_token_never_appears_in_dataclass_repr():
    destination = _destination()
    assert FAKE_TOKEN not in repr(destination)
    assert FAKE_TOKEN not in str(destination)


def test_no_default_chat_id_exists_anywhere_in_dataclass():
    import inspect

    import ticket_delivery.telegram_adapter as mod
    source = inspect.getsource(mod)
    assert str(AUTHORIZED_CHAT) not in source  # no hardcoded destination in the module itself


# --------------------------------------------------------------------------- successful delivery

def test_successful_delivery(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: _FakeResponse({"ok": True, "result": {"message_id": 42}}))
    client = TelegramClient(FAKE_TOKEN, session=session)

    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hello", client=client, destination=_destination())

    assert outcome.final_state == "DELIVERED"
    assert outcome.provider_response_id == "42"
    assert store.get(tid).state == STATE_DELIVERED
    assert store.get(tid).provider_response_id == "42"


def test_provider_evidence_is_persisted(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: _FakeResponse({"ok": True, "result": {"message_id": 555}}))
    client = TelegramClient(FAKE_TOKEN, session=session)
    deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert store.get(tid).provider_response_id == "555"


# --------------------------------------------------------------------------- failure classification

def test_rate_limit_is_retryable(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: _FakeResponse({"ok": False, "error_code": 429, "description": "Too Many Requests"}))
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert outcome.final_state == "DELIVERY_FAILED_RETRYABLE"
    assert store.get(tid).state == STATE_DELIVERY_FAILED_RETRYABLE


def test_telegram_ok_false_non_rate_limit_is_terminal(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: _FakeResponse({"ok": False, "error_code": 403, "description": "bot was blocked by the user"}))
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert outcome.final_state == "DELIVERY_FAILED_TERMINAL"
    assert store.get(tid).state == STATE_DELIVERY_FAILED_TERMINAL


def test_malformed_response_is_treated_as_ambiguous_not_terminal(tmp_path):
    class _BadJsonResponse:
        def raise_for_status(self):
            pass

        def json(self):
            raise ValueError("not JSON")

    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: _BadJsonResponse())
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert outcome.final_state == "DELIVERY_AMBIGUOUS"
    assert store.get(tid).state == STATE_DELIVERY_AMBIGUOUS


def test_connection_failure_is_ambiguous_not_assumed_unsent(tmp_path):
    import requests

    def _raise(url, body):
        raise requests.ConnectionError("simulated connection failure")

    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(_raise)
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert outcome.final_state == "DELIVERY_AMBIGUOUS"


def test_timeout_is_ambiguous(tmp_path):
    import requests

    def _raise(url, body):
        raise requests.Timeout("simulated timeout")

    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(_raise)
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert outcome.final_state == "DELIVERY_AMBIGUOUS"


def test_http_error_is_ambiguous_via_request_failed_path(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: _FakeResponse({}, status_ok=False))
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert outcome.final_state == "DELIVERY_AMBIGUOUS"


# --------------------------------------------------------------------------- ambiguity / retry safety

def test_ambiguous_outcome_cannot_be_automatically_reclaimed(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(lambda url, body: (_ for _ in ()).throw(__import__("requests").Timeout("x")))
    client = TelegramClient(FAKE_TOKEN, session=session)
    deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert store.get(tid).state == STATE_DELIVERY_AMBIGUOUS

    # A second delivery attempt against the same store must not be allowed to claim.
    second = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())
    assert second.claimed is False
    assert store.get(tid).state == STATE_DELIVERY_AMBIGUOUS  # unchanged


def test_successful_retry_after_retryable_failure_reuses_logical_ticket(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store)

    failing_session = _FakeSession(lambda url, body: _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}))
    client_fail = TelegramClient(FAKE_TOKEN, session=failing_session)
    deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client_fail, destination=_destination())
    assert store.get(tid).state == STATE_DELIVERY_FAILED_RETRYABLE
    attempt_after_failure = store.get(tid).attempt_number

    ok_session = _FakeSession(lambda url, body: _FakeResponse({"ok": True, "result": {"message_id": 7}}))
    client_ok = TelegramClient(FAKE_TOKEN, session=ok_session)
    outcome = deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client_ok, destination=_destination())

    assert outcome.final_state == "DELIVERED"
    assert store.get(tid).logical_ticket_id == tid  # same logical ticket throughout
    assert store.get(tid).attempt_number == attempt_after_failure + 1  # new attempt number


# --------------------------------------------------------------------------- secret redaction

def test_bot_token_never_appears_in_failure_evidence(tmp_path):
    import requests

    def _raise(url, body):
        raise requests.ConnectionError(f"Failed to connect to https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage")

    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(_raise)
    client = TelegramClient(FAKE_TOKEN, session=session)
    deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())

    record = store.get(tid)
    assert FAKE_TOKEN not in (record.failure_evidence_redacted or "")


def test_bot_token_never_appears_anywhere_in_the_delivery_journal_file(tmp_path):
    import requests

    def _raise(url, body):
        raise requests.ConnectionError(f"connect failed for /bot{FAKE_TOKEN}/sendMessage")

    store = _store(tmp_path)
    tid = _ready(store)
    session = _FakeSession(_raise)
    client = TelegramClient(FAKE_TOKEN, session=session)
    deliver_informational_ticket(store=store, logical_ticket_id=tid, message_text="hi", client=client, destination=_destination())

    import os
    journal_path = os.path.join(str(tmp_path), "delivery_records.json")
    with open(journal_path, encoding="utf-8") as f:
        content = f.read()
    assert FAKE_TOKEN not in content


# --------------------------------------------------------------------------- execution boundary
#
# Covered by the AST-based (not naive-substring) static scan in
# tests/test_ticket_delivery_execution_boundary.py, which already includes this module
# and correctly distinguishes real imports from docstring prose that merely names what
# was deliberately NOT reused.
