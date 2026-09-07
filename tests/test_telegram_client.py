"""Tests for notifications.telegram_client. All HTTP is mocked -- no real network call
is ever made anywhere in this file."""
from __future__ import annotations

import pytest
import requests

from notifications.telegram_client import (
    ACTION_DETAILS,
    ACTION_EXECUTE,
    ACTION_REJECT,
    CALLBACK_DATA_MAX_BYTES,
    TelegramClient,
    TelegramClientError,
    TelegramRequestError,
    build_callback_data,
    inline_keyboard_markup,
    next_offset,
    parse_callback_data,
    parse_callback_query,
)


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

    def post(self, url, json, timeout):  # noqa: A002 -- matches requests.Session.post signature
        self.calls.append((url, json, timeout))
        return self._responses.pop(0)


# ------------------------------------------------------------------------- send_message

def test_send_message_success():
    session = _FakeSession([_FakeResponse({"ok": True, "result": {"message_id": 42}})])
    client = TelegramClient("TOKEN", session=session)
    result = client.send_message(123, "hello")
    assert result.ok
    assert result.result["message_id"] == 42
    url, payload, _ = session.calls[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload == {"chat_id": 123, "text": "hello"}


def test_send_message_never_logs_token_in_url_param_name():
    # The token appears only in the URL path, never as a JSON field -- guards against
    # an accidental future change that puts it in the request body where a naive log
    # statement might capture params directly.
    session = _FakeSession([_FakeResponse({"ok": True, "result": {}})])
    client = TelegramClient("SECRET_TOKEN", session=session)
    client.send_message(1, "x")
    _, payload, _ = session.calls[0]
    assert "SECRET_TOKEN" not in str(payload)


def test_send_message_chunks_long_text_and_attaches_keyboard_to_last_chunk():
    long_text = "a" * 5000
    session = _FakeSession([
        _FakeResponse({"ok": True, "result": {"message_id": 1}}),
        _FakeResponse({"ok": True, "result": {"message_id": 2}}),
    ])
    client = TelegramClient("TOKEN", session=session)
    keyboard = {"inline_keyboard": [[{"text": "x", "callback_data": "x:1"}]]}
    result = client.send_message(1, long_text, reply_markup=keyboard)
    assert result.result["message_id"] == 2
    assert len(session.calls) == 2
    assert "reply_markup" not in session.calls[0][1]
    assert session.calls[1][1]["reply_markup"] == keyboard


def test_send_message_ok_false_returns_result_not_exception():
    session = _FakeSession([_FakeResponse({"ok": False, "error_code": 400, "description": "bad request"})])
    client = TelegramClient("TOKEN", session=session)
    result = client.send_message(1, "x")
    assert result.ok is False
    assert result.error_code == 400
    assert result.description == "bad request"


def test_transport_failure_raises_telegram_request_error():
    session = _FakeSession([_FakeResponse({}, status=500)])
    client = TelegramClient("TOKEN", session=session)
    with pytest.raises(TelegramRequestError):
        client.send_message(1, "x")


def test_malformed_response_raises():
    session = _FakeSession([_FakeResponse(["not", "a", "dict"])])
    client = TelegramClient("TOKEN", session=session)
    with pytest.raises(TelegramRequestError):
        client.send_message(1, "x")


def test_bot_token_required():
    with pytest.raises(ValueError):
        TelegramClient("")


# --------------------------------------------------------------------------- get_updates

def test_get_updates_passes_offset():
    session = _FakeSession([_FakeResponse({"ok": True, "result": []})])
    client = TelegramClient("TOKEN", session=session)
    client.get_updates(offset=99, timeout=5)
    _, payload, _ = session.calls[0]
    assert payload["offset"] == 99
    assert payload["timeout"] == 5


def test_next_offset_uses_highest_update_id_plus_one():
    updates = [{"update_id": 5}, {"update_id": 7}, {"update_id": 6}]
    assert next_offset(updates, current_offset=None) == 8


def test_next_offset_unchanged_when_no_updates():
    assert next_offset([], current_offset=42) == 42


# ------------------------------------------------------------------ other API methods

def test_answer_callback_query():
    session = _FakeSession([_FakeResponse({"ok": True, "result": True})])
    client = TelegramClient("TOKEN", session=session)
    result = client.answer_callback_query("cbq1", text="done")
    assert result.ok
    _, payload, _ = session.calls[0]
    assert payload == {"callback_query_id": "cbq1", "show_alert": False, "text": "done"}


def test_edit_message_text():
    session = _FakeSession([_FakeResponse({"ok": True, "result": {}})])
    client = TelegramClient("TOKEN", session=session)
    client.edit_message_text(1, 2, "new text", reply_markup=None)
    _, payload, _ = session.calls[0]
    assert payload == {"chat_id": 1, "message_id": 2, "text": "new text"}


def test_edit_message_reply_markup_removes_keyboard():
    session = _FakeSession([_FakeResponse({"ok": True, "result": {}})])
    client = TelegramClient("TOKEN", session=session)
    client.edit_message_reply_markup(1, 2, reply_markup=None)
    _, payload, _ = session.calls[0]
    assert payload == {"chat_id": 1, "message_id": 2}


# -------------------------------------------------------------------- inline keyboard

def test_inline_keyboard_markup_rejects_oversized_callback_data():
    oversized = "x" * (CALLBACK_DATA_MAX_BYTES + 1)
    with pytest.raises(TelegramClientError):
        inline_keyboard_markup([[{"text": "t", "callback_data": oversized}]])


def test_inline_keyboard_markup_shape():
    markup = inline_keyboard_markup([[{"text": "t", "callback_data": "x:abc"}]])
    assert markup == {"inline_keyboard": [[{"text": "t", "callback_data": "x:abc"}]]}


# ------------------------------------------------------------------- callback_data

@pytest.mark.parametrize("action", [ACTION_EXECUTE, ACTION_REJECT, ACTION_DETAILS])
def test_build_and_parse_callback_data_roundtrip(action):
    data = build_callback_data(action, "approval123")
    assert parse_callback_data(data) == (action, "approval123")


def test_build_callback_data_rejects_unsupported_action():
    with pytest.raises(ValueError):
        build_callback_data("z", "approval123")


@pytest.mark.parametrize("raw", [
    "", None, 123, "x", "x:", ":abc", "z:abc", "x" * 100,
])
def test_parse_callback_data_fails_closed(raw):
    assert parse_callback_data(raw) is None


def test_parse_callback_data_splits_only_once_approval_id_is_opaque():
    # maxsplit=1: whatever follows the first ":" is the whole (opaque) approval_id,
    # never re-parsed into further fields -- this is why callback_data can never smuggle
    # execution-critical trade parameters even if it contained extra colons.
    assert parse_callback_data("x:GBPUSD:1.3:1.35") == ("x", "GBPUSD:1.3:1.35")


# ---------------------------------------------------------------- parse_callback_query

def _update(*, callback_query_id="cbq1", user_id=555, chat_id=999, data="x:abc"):
    return {
        "update_id": 1,
        "callback_query": {
            "id": callback_query_id,
            "from": {"id": user_id},
            "data": data,
            "message": {"chat": {"id": chat_id}},
        },
    }


def test_parse_callback_query_happy_path():
    parsed = parse_callback_query(_update())
    assert parsed.callback_query_id == "cbq1"
    assert parsed.user_id == 555
    assert parsed.chat_id == 999
    assert parsed.action == "x"
    assert parsed.approval_id == "abc"


def test_parse_callback_query_missing_message_gives_none_chat_id_not_failure():
    update = _update()
    del update["callback_query"]["message"]
    parsed = parse_callback_query(update)
    assert parsed is not None
    assert parsed.chat_id is None


@pytest.mark.parametrize("mutate", [
    lambda u: u["callback_query"].pop("id"),
    lambda u: u["callback_query"]["from"].__setitem__("id", "not-an-int"),
    lambda u: u["callback_query"].pop("data"),
    lambda u: u["callback_query"].__setitem__("data", "bad-data"),
    lambda u: u.pop("callback_query"),
])
def test_parse_callback_query_fails_closed(mutate):
    update = _update()
    mutate(update)
    assert parse_callback_query(update) is None


def test_parse_callback_query_ignores_non_callback_update():
    assert parse_callback_query({"update_id": 1, "message": {"text": "hi"}}) is None
