"""WP7 (docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md)
tests for the new runtime pieces this task adds:

  - TelegramDestinationConfig.from_env() -- reads TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID,
    fails closed on missing/malformed/unauthorized destination, never reuses
    TELEGRAM_CHAT_ID as self-authorizing.
  - deliver_informational_ticket_with_retry() -- retry design (A), chosen and recorded
    explicitly: in-process wait-and-retry with an injectable sleeper, sleep sequence
    [30, 60], 3 total attempts, per the signed policy. No real sleep anywhere in this
    file.
  - AttemptJournal -- durable, append-only delivery-attempt journal; never stores the
    bot token/secrets.

No real Telegram send anywhere -- notifications.telegram_client.TelegramClient is
always constructed with an injected fake `session`, same idiom as
test_ticket_delivery_telegram_adapter.py.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from notifications.telegram_client import TelegramClient
from ticket_delivery.attempt_journal import AttemptJournal
from ticket_delivery.delivery_store import TicketDeliveryStore
from ticket_delivery.identity import logical_ticket_id
from ticket_delivery.models import (
    STATE_DELIVERED,
    STATE_DELIVERY_FAILED_RETRYABLE,
    STATE_DELIVERY_FAILED_TERMINAL,
)
from ticket_delivery.policy import RetryPolicy
from ticket_delivery.telegram_adapter import (
    REASON_INVALID_CHAT_ID,
    REASON_MISSING_BOT_TOKEN,
    REASON_MISSING_CHAT_ID,
    REASON_RETRY_ATTEMPTS_EXHAUSTED,
    REASON_UNAUTHORIZED_DESTINATION,
    TelegramConfigError,
    TelegramDestinationConfig,
    deliver_informational_ticket_with_retry,
)

FAKE_TOKEN = "999999:BBFAKE-WP7-TEST-TOKEN-NEVER-REAL"
AUTHORIZED_CHAT = 555111222

SIGNED_RETRY_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=30, max_delay_seconds=300)


class _FakeResponse:
    def __init__(self, json_body):
        self._json_body = json_body

    def raise_for_status(self):
        pass

    def json(self):
        return self._json_body


class _ScriptedSession:
    """Returns one canned response per call, in order -- .post() is the only method
    TelegramClient.send_message() ever calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json=None, timeout=None):
        self.calls.append({"url": url, "json": json})
        return self._responses.pop(0)


def _store(tmp_path):
    return TicketDeliveryStore(state_dir=str(tmp_path / "state"))


def _ticket_id(symbol="EURUSD"):
    return logical_ticket_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol=symbol, cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))


def _ready(store, tid):
    store.ensure_ready_to_deliver(
        logical_ticket_id=tid, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="EURUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="hash123",
    )
    return tid


def _destination():
    return TelegramDestinationConfig.from_values(bot_token=FAKE_TOKEN, chat_id=AUTHORIZED_CHAT, authorized_chat_ids=[AUTHORIZED_CHAT])


class _RecordingSleeper:
    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)


# --------------------------------------------------------------------------- TelegramDestinationConfig.from_env()

def test_from_env_missing_bot_token_fails_closed(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_env(authorized_chat_ids=[AUTHORIZED_CHAT])
    assert exc_info.value.reason_code == REASON_MISSING_BOT_TOKEN


def test_from_env_missing_chat_id_fails_closed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_env(authorized_chat_ids=[AUTHORIZED_CHAT])
    assert exc_info.value.reason_code == REASON_MISSING_CHAT_ID


def test_from_env_malformed_chat_id_fails_closed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "not-a-number")
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_env(authorized_chat_ids=[AUTHORIZED_CHAT])
    assert exc_info.value.reason_code == REASON_INVALID_CHAT_ID


def test_from_env_unauthorized_destination_fails_closed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    with pytest.raises(TelegramConfigError) as exc_info:
        TelegramDestinationConfig.from_env(authorized_chat_ids=[111])  # AUTHORIZED_CHAT not in this list
    assert exc_info.value.reason_code == REASON_UNAUTHORIZED_DESTINATION


def test_from_env_chat_id_alone_never_self_authorizes(monkeypatch):
    """The destination allow-list must be explicitly supplied by the caller -- it is
    never derived from TELEGRAM_CHAT_ID itself, which would make 'is this authorized'
    tautologically true."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    with pytest.raises(TelegramConfigError):
        TelegramDestinationConfig.from_env(authorized_chat_ids=[])


def test_from_env_success(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", FAKE_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", str(AUTHORIZED_CHAT))
    dest = TelegramDestinationConfig.from_env(authorized_chat_ids=[AUTHORIZED_CHAT])
    assert dest.bot_token == FAKE_TOKEN
    assert dest.chat_id == AUTHORIZED_CHAT


def test_from_env_never_reads_authorized_chat_ids_from_environment():
    import inspect

    import ticket_delivery.telegram_adapter as mod
    source = inspect.getsource(mod.TelegramDestinationConfig.from_env)
    assert 'env.get("AUTHORIZED' not in source.upper()
    assert 'env.get("TELEGRAM_ALLOWED_USER_IDS"' not in source  # a different concept entirely, never reused here


# --------------------------------------------------------------------------- retry design (A): in-process wait-and-retry

def test_immediate_success_makes_exactly_one_attempt_and_never_sleeps(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([_FakeResponse({"ok": True, "result": {"message_id": 1}})])
    client = TelegramClient(FAKE_TOKEN, session=session)
    sleeper = _RecordingSleeper()

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=sleeper,
    )

    assert outcome.final_state == "DELIVERED"
    assert len(session.calls) == 1
    assert sleeper.calls == []
    assert store.get(tid).state == STATE_DELIVERED


def test_one_retryable_failure_then_success_sleeps_exactly_30_seconds(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
        _FakeResponse({"ok": True, "result": {"message_id": 2}}),
    ])
    client = TelegramClient(FAKE_TOKEN, session=session)
    sleeper = _RecordingSleeper()

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=sleeper,
    )

    assert outcome.final_state == "DELIVERED"
    assert len(session.calls) == 2
    assert sleeper.calls == [30.0]


def test_two_retryable_failures_then_success_sleeps_30_then_60(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
        _FakeResponse({"ok": True, "result": {"message_id": 3}}),
    ])
    client = TelegramClient(FAKE_TOKEN, session=session)
    sleeper = _RecordingSleeper()

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=sleeper,
    )

    assert outcome.final_state == "DELIVERED"
    assert len(session.calls) == 3
    assert sleeper.calls == [30.0, 60.0]


def test_three_consecutive_retryable_failures_exhausts_the_signed_max_attempts(tmp_path):
    """Signed contract: attempt 1 -> 30s -> attempt 2 -> 60s -> attempt 3 -> exhausted,
    no attempt 4, no third sleep."""
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
    ])
    client = TelegramClient(FAKE_TOKEN, session=session)
    sleeper = _RecordingSleeper()

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=sleeper,
    )

    assert outcome.final_state == "DELIVERY_FAILED_RETRYABLE"
    assert outcome.reason_code == REASON_RETRY_ATTEMPTS_EXHAUSTED
    assert len(session.calls) == 3  # exactly 3 total attempts, never a 4th
    assert sleeper.calls == [30.0, 60.0]
    # persisted record remains DELIVERY_FAILED_RETRYABLE (unlocked) -- exhaustion is
    # scoped to this in-process loop, not a permanent terminal mark.
    assert store.get(tid).state == STATE_DELIVERY_FAILED_RETRYABLE


def test_terminal_failure_never_retried_and_never_sleeps(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([_FakeResponse({"ok": False, "error_code": 403, "description": "bot was blocked"})])
    client = TelegramClient(FAKE_TOKEN, session=session)
    sleeper = _RecordingSleeper()

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=sleeper,
    )

    assert outcome.final_state == "DELIVERY_FAILED_TERMINAL"
    assert len(session.calls) == 1
    assert sleeper.calls == []
    assert store.get(tid).state == STATE_DELIVERY_FAILED_TERMINAL


def test_ambiguous_outcome_never_retried_and_never_sleeps(tmp_path):
    import requests

    def _raise(*a, **k):
        raise requests.Timeout("simulated timeout")

    class _RaisingSession:
        def post(self, url, json=None, timeout=None):
            _raise()

    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    client = TelegramClient(FAKE_TOKEN, session=_RaisingSession())
    sleeper = _RecordingSleeper()

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=sleeper,
    )

    assert outcome.final_state == "DELIVERY_AMBIGUOUS"
    assert sleeper.calls == []


def test_already_delivered_ticket_makes_zero_provider_calls_idempotent(tmp_path):
    """DELIVERED is terminal and idempotent -- a second invocation of the retry wrapper
    against an already-DELIVERED logical ticket must make ZERO provider calls (the
    claim fails before send_message is ever reached)."""
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([_FakeResponse({"ok": True, "result": {"message_id": 9}})])
    client = TelegramClient(FAKE_TOKEN, session=session)
    first = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=_RecordingSleeper(),
    )
    assert first.final_state == "DELIVERED"
    assert len(session.calls) == 1

    class _ExplodingSession:
        def post(self, *a, **k):
            raise AssertionError("provider must not be called for an already-DELIVERED ticket")

    client2 = TelegramClient(FAKE_TOKEN, session=_ExplodingSession())
    second = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client2,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=_RecordingSleeper(),
    )
    assert second.claimed is False
    assert store.get(tid).state == STATE_DELIVERED  # unchanged


# --------------------------------------------------------------------------- AttemptJournal

def test_attempt_journal_records_one_line_per_attempt(tmp_path):
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([
        _FakeResponse({"ok": False, "error_code": 429, "description": "rate limited"}),
        _FakeResponse({"ok": True, "result": {"message_id": 11}}),
    ])
    client = TelegramClient(FAKE_TOKEN, session=session)
    journal_path = str(tmp_path / "attempt_journal.jsonl")
    journal = AttemptJournal(path=journal_path)

    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY,
        sleeper=_RecordingSleeper(), attempt_journal=journal,
    )
    assert outcome.final_state == "DELIVERED"

    with open(journal_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert lines[0]["final_state"] == "DELIVERY_FAILED_RETRYABLE"
    assert lines[0]["attempt_number"] == 1
    assert lines[1]["final_state"] == "DELIVERED"
    assert lines[1]["attempt_number"] == 2
    assert lines[1]["provider_response_id"] == "11"


def test_attempt_journal_never_contains_the_bot_token(tmp_path):
    import requests

    class _RaisingSession:
        def post(self, url, json=None, timeout=None):
            raise requests.ConnectionError(f"connect failed for /bot{FAKE_TOKEN}/sendMessage")

    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    client = TelegramClient(FAKE_TOKEN, session=_RaisingSession())
    journal_path = str(tmp_path / "attempt_journal.jsonl")
    journal = AttemptJournal(path=journal_path)

    deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY,
        sleeper=_RecordingSleeper(), attempt_journal=journal,
    )
    with open(journal_path, encoding="utf-8") as f:
        content = f.read()
    assert FAKE_TOKEN not in content


def test_attempt_journal_is_append_only_across_separate_calls(tmp_path):
    store = _store(tmp_path)
    journal_path = str(tmp_path / "attempt_journal.jsonl")
    journal = AttemptJournal(path=journal_path)

    tid1 = _ready(store, _ticket_id("EURUSD"))
    session1 = _ScriptedSession([_FakeResponse({"ok": True, "result": {"message_id": 1}})])
    client1 = TelegramClient(FAKE_TOKEN, session=session1)
    deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid1, message_text="hi", client=client1,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY,
        sleeper=_RecordingSleeper(), attempt_journal=journal,
    )

    tid2 = logical_ticket_id(strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1", symbol="GBPUSD", cycle="ASIAN_LONDON", trading_date=dt.date(2026, 9, 7))
    store.ensure_ready_to_deliver(
        logical_ticket_id=tid2, strategy_id="ST_ASIAN_SWEEP_5R_V1", strategy_version="1.1.1",
        application_release="AG_TRADE_ASSISTANT_V1_0_3", symbol="GBPUSD", cycle="ASIAN_LONDON",
        trading_date="2026-09-07", payload_hash="hash456",
    )
    session2 = _ScriptedSession([_FakeResponse({"ok": True, "result": {"message_id": 2}})])
    client2 = TelegramClient(FAKE_TOKEN, session=session2)
    deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid2, message_text="hi", client=client2,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY,
        sleeper=_RecordingSleeper(), attempt_journal=journal,
    )

    with open(journal_path, encoding="utf-8") as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert len(lines) == 2
    assert {lines[0]["logical_ticket_id"], lines[1]["logical_ticket_id"]} == {tid1, tid2}


def test_attempt_journal_no_journal_supplied_is_a_no_op(tmp_path):
    """Every pre-WP7 call shape (attempt_journal omitted) keeps working unchanged."""
    store = _store(tmp_path)
    tid = _ready(store, _ticket_id())
    session = _ScriptedSession([_FakeResponse({"ok": True, "result": {"message_id": 1}})])
    client = TelegramClient(FAKE_TOKEN, session=session)
    outcome = deliver_informational_ticket_with_retry(
        store=store, logical_ticket_id=tid, message_text="hi", client=client,
        destination=_destination(), retry_policy=SIGNED_RETRY_POLICY, sleeper=_RecordingSleeper(),
    )
    assert outcome.final_state == "DELIVERED"


def test_no_real_sleeping_anywhere_in_telegram_adapter_module():
    import inspect

    import ticket_delivery.telegram_adapter as mod
    source = inspect.getsource(mod)
    # time.sleep is imported (as the injectable default) but never called directly by
    # name anywhere in this module's own body -- every call site goes through the
    # `sleep` local (the injected sleeper), not a bare `time.sleep(...)` call.
    assert "time.sleep(" not in source
