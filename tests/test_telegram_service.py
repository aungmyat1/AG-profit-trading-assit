"""Tests for api.telegram_service -- GET /api/telegram/status and POST /api/telegram/
test's underlying logic, plus notify_trade/notify_position. All Telegram HTTP is
mocked via TelegramClient's injectable session (same idiom as test_telegram_client.py);
no real network call is ever made in this file.
"""
from __future__ import annotations

import time

import pytest
import requests

from authorization.config import TelegramGatewayConfig
from api import telegram_service
from notifications.telegram_client import TelegramClient


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):  # noqa: A002
        self.calls.append((url, json, timeout))
        return self._responses.pop(0)


def _cfg(*, bot_token="TOKEN", chat_id=123, allowed_user_ids=()):
    return TelegramGatewayConfig(
        execution_enabled=False, bot_token=bot_token, chat_id=chat_id,
        allowed_user_ids=list(allowed_user_ids), approval_ttl_seconds=900,
        poll_timeout_seconds=25, state_dir="journal/telegram_execution_gateway",
    )


@pytest.fixture(autouse=True)
def _reset_cooldown():
    telegram_service._last_test_sent_monotonic.clear()
    yield
    telegram_service._last_test_sent_monotonic.clear()


# ------------------------------------------------------------------------ get_status

def test_status_not_configured_missing_token():
    status = telegram_service.get_status(_cfg(bot_token=""))
    assert status.configured is False
    assert status.bot_configured is False
    assert status.reachable is False
    assert status.reason_code == "NOT_CONFIGURED"


def test_status_not_configured_missing_chat():
    status = telegram_service.get_status(_cfg(chat_id=None))
    assert status.configured is False
    assert status.chat_configured is False
    assert status.reachable is False


def test_status_configured_without_allowed_user_ids_is_still_configured(monkeypatch):
    """Reproduces this repo's actual default local .env shape: bot token + chat id
    set, but TELEGRAM_ALLOWED_USER_IDS unset (inbound-callback authorization not
    enabled). Outbound status/test/notify must still report configured=True -- see
    telegram_service._outbound_ready's docstring."""
    cfg = _cfg(allowed_user_ids=())
    assert cfg.is_ready() is False  # sanity: the underlying gateway config is NOT "ready" for callbacks

    fake_session = _FakeSession([_FakeResponse({"ok": True, "result": {"id": 1, "is_bot": True}})])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))

    status = telegram_service.get_status(cfg)
    assert status.configured is True
    assert status.reachable is True


def test_status_configured_but_unreachable_on_telegram_error(monkeypatch):
    fake_session = _FakeSession([_FakeResponse({"ok": False, "error_code": 401, "description": "Unauthorized"})])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))

    status = telegram_service.get_status(_cfg())
    assert status.configured is True
    assert status.reachable is False
    assert status.reason_code == "TELEGRAM_ERROR_401"


def test_status_configured_but_unreachable_on_network_failure(monkeypatch):
    class _RaisingSession:
        def post(self, url, json, timeout):
            raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=_RaisingSession()))

    status = telegram_service.get_status(_cfg())
    assert status.configured is True
    assert status.reachable is False
    assert "TELEGRAM_UNREACHABLE" in status.reason_code


def test_status_never_carries_a_token_field():
    status = telegram_service.get_status(_cfg(bot_token=""))
    assert not hasattr(status, "bot_token")
    assert "TOKEN" not in repr(status)


# ------------------------------------------------------------------- send_test_notification

def test_test_notification_not_configured():
    result = telegram_service.send_test_notification(_cfg(bot_token=""))
    assert result.success is False
    assert result.reason_code == "NOT_CONFIGURED"


def test_test_notification_success(monkeypatch):
    fake_session = _FakeSession([_FakeResponse({"ok": True, "result": {"message_id": 7}})])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))

    result = telegram_service.send_test_notification(_cfg())
    assert result.success is True
    assert result.message_id == "7"


def test_test_notification_rate_limited(monkeypatch):
    fake_session = _FakeSession([
        _FakeResponse({"ok": True, "result": {"message_id": 1}}),
        _FakeResponse({"ok": True, "result": {"message_id": 2}}),
    ])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)

    first = telegram_service.send_test_notification(_cfg())
    second = telegram_service.send_test_notification(_cfg())

    assert first.success is True
    assert second.success is False
    assert second.reason_code == "RATE_LIMITED"
    assert len(fake_session.calls) == 1  # the second call never reached Telegram at all


def test_test_notification_gateway_failure(monkeypatch):
    fake_session = _FakeSession([_FakeResponse({"ok": False, "error_code": 429, "description": "Too Many Requests"})])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))

    result = telegram_service.send_test_notification(_cfg())
    assert result.success is False
    assert result.reason_code == "TELEGRAM_ERROR_429"


# ------------------------------------------------------------------------- notify_trade

class _FakeApproval:
    approval_id = "AP-1"
    setup_id = "ST_ASIAN_SWEEP_5R_V1:ASIAN_LONDON:GBPUSD:2026-09-08"
    environment = "DEMO"
    state = "SENT_TO_TELEGRAM"


def test_notify_trade_not_configured():
    result = telegram_service.notify_trade(_FakeApproval(), _cfg(bot_token=""))
    assert result.success is False
    assert result.reason_code == "NOT_CONFIGURED"


def test_notify_trade_success_uses_only_canonical_fields(monkeypatch):
    fake_session = _FakeSession([_FakeResponse({"ok": True, "result": {"message_id": 9}})])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))

    result = telegram_service.notify_trade(_FakeApproval(), _cfg())
    assert result.success is True
    sent_text = fake_session.calls[0][1]["text"]
    assert "AP-1" in sent_text and "DEMO" in sent_text


# ---------------------------------------------------------------------- notify_position

class _FakePosition:
    ticket = 42
    symbol = "EURUSD"
    direction = "BUY"
    volume_current = 0.30
    current_price = 1.1750
    profit = 12.5


def test_notify_position_not_configured():
    result = telegram_service.notify_position(_FakePosition(), _cfg(chat_id=None))
    assert result.success is False
    assert result.reason_code == "NOT_CONFIGURED"


def test_notify_position_success(monkeypatch):
    fake_session = _FakeSession([_FakeResponse({"ok": True, "result": {"message_id": 10}})])
    monkeypatch.setattr(telegram_service, "TelegramClient", lambda token: TelegramClient(token, session=fake_session))

    result = telegram_service.notify_position(_FakePosition(), _cfg())
    assert result.success is True
    sent_text = fake_session.calls[0][1]["text"]
    assert "42" in sent_text and "EURUSD" in sent_text
