"""Tests for notifications.trade_management_alerts.notify_confirmed_action -- the
Phase 5 side-effect hook trade_management.manager calls right after a management
action's own {action}_CONFIRMED journal event. All Telegram HTTP is mocked; nothing
here ever makes a real network call.
"""
from __future__ import annotations

import requests

from authorization.config import TelegramGatewayConfig
from notifications import trade_management_alerts
from notifications.telegram_client import TelegramClient as _RealTelegramClient
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
        lambda token: _RealTelegramClient(token, session=fake_session),
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
        lambda token: _RealTelegramClient(token, session=fake_session),
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
        lambda token: _RealTelegramClient(token, session=fake_session),
    )

    # Must not raise -- this is the hard invariant manager.run_cycle_for_ticket depends on.
    trade_management_alerts.notify_confirmed_action(1004, "EURUSD", "MOVE_SL", base_dir=base_dir, config=_cfg())

    events = tm_journal.read_events(1004, base_dir)
    assert events[0]["event"] == "MOVE_SL_TELEGRAM_NOTIFY_FAILED"
    assert events[0]["reason_code"] == "TELEGRAM_SEND_EXCEPTION"


def test_network_exception_log_never_contains_the_bot_token(tmp_path, monkeypatch, caplog):
    """A requests transport exception's str() commonly embeds the full request URL
    (.../bot<TOKEN>/sendMessage) -- this asserts the token is redacted before it ever
    reaches a log line, not merely that the call doesn't raise."""
    base_dir = str(tmp_path / "journal")
    token = "SUPER_SECRET_BOT_TOKEN_123"
    fake_session = _FakeSession(
        raises=requests.ConnectionError(f"failed to reach https://api.telegram.org/bot{token}/sendMessage"),
    )
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda tok: _RealTelegramClient(tok, session=fake_session),
    )

    with caplog.at_level("WARNING"):
        trade_management_alerts.notify_confirmed_action(
            1006, "EURUSD", "MOVE_SL", base_dir=base_dir, config=_cfg(bot_token=token),
        )

    assert token not in caplog.text
    assert "REDACTED" in caplog.text


def test_notification_never_mutates_trading_journal_events(tmp_path, monkeypatch):
    """The notification event is always additive (a new, distinctly-suffixed event) --
    it must never be recorded under the same event name as the trading confirmation
    itself, and must never be the ONLY event when a real CONFIRMED already exists."""
    base_dir = str(tmp_path / "journal")
    tm_journal.record_event(1005, "MOVE_SL_CONFIRMED", base_dir, intent_id="x", volume_after=None)

    fake_session = _FakeSession(response=_FakeResponse({"ok": True, "result": {"message_id": 2}}))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: _RealTelegramClient(token, session=fake_session),
    )
    trade_management_alerts.notify_confirmed_action(1005, "EURUSD", "MOVE_SL", base_dir=base_dir, config=_cfg())

    events = [e["event"] for e in tm_journal.read_events(1005, base_dir)]
    assert events == ["MOVE_SL_CONFIRMED", "MOVE_SL_TELEGRAM_NOTIFY_SENT"]


# --- broker-side close alerts (SL hit) ---------------------------------------------

def test_close_notification_sends_sl_message_and_journals_sent(tmp_path, monkeypatch):
    base_dir = str(tmp_path / "journal")
    fake_session = _FakeSession(response=_FakeResponse({"ok": True, "result": {"message_id": 9}}))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: _RealTelegramClient(token, session=fake_session),
    )

    trade_management_alerts.notify_position_closed(1007, "EURUSD", "SL", base_dir=base_dir, config=_cfg())

    assert len(fake_session.calls) == 1
    sent_text = fake_session.calls[0][1]["text"]
    assert "STOP LOSS" in sent_text
    assert "POSITION_CLOSED_SL" in sent_text
    events = [e["event"] for e in tm_journal.read_events(1007, base_dir)]
    assert events == ["POSITION_CLOSED_SL_TELEGRAM_NOTIFY_SENT"]


def test_close_notification_unknown_reason_is_labelled_unconfirmed(tmp_path, monkeypatch):
    base_dir = str(tmp_path / "journal")
    fake_session = _FakeSession(response=_FakeResponse({"ok": True, "result": {"message_id": 10}}))
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda token: _RealTelegramClient(token, session=fake_session),
    )

    trade_management_alerts.notify_position_closed(1008, "GBPUSD", "UNKNOWN", base_dir=base_dir, config=_cfg())

    sent_text = fake_session.calls[0][1]["text"]
    assert "could not be confirmed" in sent_text
    assert "POSITION_CLOSED_UNKNOWN" in sent_text


def test_close_notification_not_configured_is_a_silent_noop(tmp_path):
    base_dir = str(tmp_path / "journal")
    trade_management_alerts.notify_position_closed(
        1009, "EURUSD", "SL", base_dir=base_dir, config=_cfg(bot_token=""),
    )
    assert tm_journal.read_events(1009, base_dir) == []


def test_close_notification_transport_failure_is_contained_and_journaled(tmp_path, monkeypatch):
    base_dir = str(tmp_path / "journal")
    token = "SUPER_SECRET_BOT_TOKEN_456"
    fake_session = _FakeSession(
        raises=requests.ConnectionError(f"failed to reach https://api.telegram.org/bot{token}/sendMessage"),
    )
    monkeypatch.setattr(
        trade_management_alerts, "TelegramClient",
        lambda tok: _RealTelegramClient(tok, session=fake_session),
    )

    trade_management_alerts.notify_position_closed(
        1010, "EURUSD", "SL", base_dir=base_dir, config=_cfg(bot_token=token),
    )  # must not raise

    events = tm_journal.read_events(1010, base_dir)
    assert events[0]["event"] == "POSITION_CLOSED_SL_TELEGRAM_NOTIFY_FAILED"
    assert events[0]["reason_code"] == "TELEGRAM_SEND_EXCEPTION"
