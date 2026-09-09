"""Tests for notifications.trade_management_alerts.notify_confirmed_action -- the
Phase 5 side-effect hook trade_management.manager calls right after a management
action's own {action}_CONFIRMED journal event. All Telegram HTTP is mocked; nothing
here ever makes a real network call.
"""
from __future__ import annotations

import requests

from authorization.config import TelegramGatewayConfig
from notifications import trade_management_alerts
from trade_management import journal as tm_journal


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    def post(self, url, json, timeout):  # noqa: A002
        self.calls.append((url, json, timeout))
        if self._raises is not None:
            raise self._raises
        return self._response


def _cfg(*, bot_token="TOKEN", chat_id=555):
    return TelegramGatewayConfig(
        execution_enabled=False, bot_token=bot_token, chat_id=chat_id, allowed_user_ids=[],
        approval_ttl_seconds=900, poll_timeout_seconds=25, state_dir="journal/telegram_execution_gateway",
    )


def test_not_configured_is_a_silent_noop(tmp_path):
    base_dir = str(tmp_path / "journal")
    trade_management_alerts.notify_confirmed_action(
        1001, "EURUSD", "MOVE_SL", reason_code="TP1_PARTIAL_CONFIRMED", base_dir=base_dir,
        config=_cfg(bot_token=""),
    )
    assert tm_journal.read_events(1001, base_dir) == []


def test_success_journals_notify_sent(tmp_path, monkeypatch):
    base_dir = str(tmp_path / "journal")
    fake_session = _FakeSession(response=_FakeResponse({"ok": True, "result": {"message_id": 1}}))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: trade_management_alerts.TelegramClient(token, session=fake_session),
    )

    trade_management_alerts.notify_confirmed_action(
        1002, "GBPUSD", "PARTIAL_CLOSE", reason_code="TP1_REACHED", base_dir=base_dir, config=_cfg(),
    )

    events = [e["event"] for e in tm_journal.read_events(1002, base_dir)]
    assert events == ["PARTIAL_CLOSE_TELEGRAM_NOTIFY_SENT"]
    assert len(fake_session.calls) == 1


def test_gateway_rejection_journals_notify_failed_separately(tmp_path, monkeypatch):
    base_dir = str(tmp_path / "journal")
    fake_session = _FakeSession(response=_FakeResponse({"ok": False, "error_code": 401, "description": "Unauthorized"}))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: trade_management_alerts.TelegramClient(token, session=fake_session),
    )

    trade_management_alerts.notify_confirmed_action(1003, "XAUUSD", "CLOSE", base_dir=base_dir, config=_cfg())

    events = tm_journal.read_events(1003, base_dir)
    assert events[0]["event"] == "CLOSE_TELEGRAM_NOTIFY_FAILED"
    assert events[0]["reason_code"] == "TELEGRAM_ERROR_401"


def test_network_exception_never_raises_and_is_journaled(tmp_path, monkeypatch):
    base_dir = str(tmp_path / "journal")
    fake_session = _FakeSession(raises=requests.ConnectionError("no route to host"))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: trade_management_alerts.TelegramClient(token, session=fake_session),
    )

    # Must not raise -- this is the hard invariant manager.run_cycle_for_ticket depends on.
    trade_management_alerts.notify_confirmed_action(1004, "EURUSD", "MOVE_SL", base_dir=base_dir, config=_cfg())

    events = tm_journal.read_events(1004, base_dir)
    assert events[0]["event"] == "MOVE_SL_TELEGRAM_NOTIFY_FAILED"
    assert events[0]["reason_code"] == "TELEGRAM_SEND_EXCEPTION"


def test_notification_never_mutates_trading_journal_events(tmp_path, monkeypatch):
    """The notification event is always additive (a new, distinctly-suffixed event) --
    it must never be recorded under the same event name as the trading confirmation
    itself, and must never be the ONLY event when a real CONFIRMED already exists."""
    base_dir = str(tmp_path / "journal")
    tm_journal.record_event(1005, "MOVE_SL_CONFIRMED", base_dir, intent_id="x", volume_after=None)

    fake_session = _FakeSession(response=_FakeResponse({"ok": True, "result": {"message_id": 2}}))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: trade_management_alerts.TelegramClient(token, session=fake_session),
    )
    trade_management_alerts.notify_confirmed_action(1005, "EURUSD", "MOVE_SL", base_dir=base_dir, config=_cfg())

    events = [e["event"] for e in tm_journal.read_events(1005, base_dir)]
    assert events == ["MOVE_SL_CONFIRMED", "MOVE_SL_TELEGRAM_NOTIFY_SENT"]
