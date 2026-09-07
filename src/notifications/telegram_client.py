"""Minimal Telegram Bot API client -- exactly the methods
AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1 needs, not a general-purpose framework.

Validated against the current official Telegram Bot API documentation
(https://core.telegram.org/bots/api, checked 2026-09-05) for this milestone:
  - sendMessage: POST, chat_id + text required; parse_mode/reply_markup optional;
    reply_markup carries an InlineKeyboardMarkup: {"inline_keyboard": [[{"text":...,
    "callback_data":...}, ...], ...]}.
  - getUpdates: offset/limit/timeout/allowed_updates, all optional. "An update is
    considered confirmed as soon as getUpdates is called with an offset higher than
    its update_id" -- offset must be recalculated after every call to (highest
    update_id seen) + 1, or old updates are redelivered forever.
  - A callback_query Update carries: update_id, callback_query.id,
    callback_query.from.id (the numeric Telegram user ID -- the principal, never a
    username), callback_query.message.chat.id, callback_query.data.
  - answerCallbackQuery: callback_query_id required; text/show_alert optional.
  - editMessageText: chat_id + message_id + text required; reply_markup optional.
  - editMessageReplyMarkup: chat_id + message_id required; reply_markup optional.

Transport conventions mirrored BY REFERENCE ONLY from
D:\\ddev\\Integrated_Claude_Forex_PQTA_System_upgraded\\integrated_system\\ops\\telegram_relay.py
(a local, one-way, stdlib-only relay with no callback/execution capability of its
own -- nothing from it is imported or copied verbatim): message chunking at Telegram's
4096-char text limit, and treating a non-2xx/non-"ok" response as a reportable failure
rather than an exception the caller must guess about.

Uses this repository's existing `requests` dependency (already used by
execution_runtime.binance_usdtm_feed / bybit_linear_perp_feed) with an injectable
`session`, the same dependency-injection idiom those adapters already use, so tests
never make a real network call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_TEXT_MAX_CHARS = 4096
CALLBACK_DATA_MAX_BYTES = 64  # Telegram Bot API hard limit on InlineKeyboardButton.callback_data


class TelegramClientError(RuntimeError):
    """Base for every fail-closed rejection this client raises. reason_code mirrors
    the repository's existing MarketDataError/BinanceFeedError/BybitFeedError
    convention."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class TelegramRequestError(TelegramClientError):
    """Transport-level failure (HTTP error, timeout, malformed JSON) or a Telegram
    `"ok": false` response."""


@dataclass(frozen=True)
class TelegramApiResult:
    """Deterministic outer shape for every Telegram API call -- always returned,
    never an exception for an expected transport failure (same convention as
    execution.models.ExecutionReport)."""

    ok: bool
    result: Any = None
    error_code: Optional[int] = None
    description: Optional[str] = None


def inline_keyboard_markup(rows: List[List[Dict[str, str]]]) -> Dict[str, Any]:
    """Builds the exact InlineKeyboardMarkup JSON shape the API expects. `rows` is a
    list of button rows, each button a {"text": ..., "callback_data": ...} dict. Every
    callback_data is validated against Telegram's 64-byte limit here, fail-closed,
    rather than silently truncated or sent to Telegram to reject."""
    for row in rows:
        for button in row:
            data = button.get("callback_data", "")
            if len(data.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
                raise TelegramClientError(
                    "CALLBACK_DATA_TOO_LONG",
                    f"callback_data {data!r} exceeds {CALLBACK_DATA_MAX_BYTES} bytes",
                )
    return {"inline_keyboard": rows}


class TelegramClient:
    """`session`/`base_url` are injected purely so tests can mock the HTTP boundary
    without any network call -- same idiom as
    execution_runtime.bybit_linear_perp_feed.BybitLinearPerpFeed."""

    def __init__(self, bot_token: str, session: Optional[Any] = None,
                base_url: str = TELEGRAM_API_BASE, timeout: float = 30.0):
        if not bot_token:
            raise ValueError("bot_token is required")
        self._bot_token = bot_token
        self._http = session or requests
        self._base_url = base_url
        self._timeout = timeout

    def _call(self, method: str, params: Dict[str, Any]) -> TelegramApiResult:
        url = f"{self._base_url}/bot{self._bot_token}/{method}"
        try:
            resp = self._http.post(url, json=params, timeout=self._timeout)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            raise TelegramRequestError(f"{method.upper()}_REQUEST_FAILED", str(exc)) from exc
        if not isinstance(payload, dict):
            raise TelegramRequestError(f"{method.upper()}_MALFORMED_RESPONSE",
                                       f"expected a JSON object, got {type(payload)}")
        if not payload.get("ok"):
            return TelegramApiResult(ok=False, error_code=payload.get("error_code"),
                                     description=payload.get("description"))
        return TelegramApiResult(ok=True, result=payload.get("result"))

    def send_message(self, chat_id: int, text: str, *, parse_mode: Optional[str] = None,
                     reply_markup: Optional[Dict[str, Any]] = None) -> TelegramApiResult:
        """Splits over Telegram's 4096-char text limit, same convention as the locally
        referenced telegram_relay.py. Returns the LAST chunk's result (the caller only
        needs the final message_id, e.g. for a ticket that fits in one chunk -- the
        common case for this feature's short, fixed-format tickets)."""
        chunks = [text[i:i + TELEGRAM_TEXT_MAX_CHARS] for i in range(0, len(text), TELEGRAM_TEXT_MAX_CHARS)] or [""]
        result = TelegramApiResult(ok=True)
        for i, chunk in enumerate(chunks):
            params: Dict[str, Any] = {"chat_id": chat_id, "text": chunk}
            if parse_mode:
                params["parse_mode"] = parse_mode
            # reply_markup only on the final chunk -- buttons belong on the message the
            # ticket actually ends on.
            if reply_markup is not None and i == len(chunks) - 1:
                params["reply_markup"] = reply_markup
            result = self._call("sendMessage", params)
            if not result.ok:
                return result
        return result

    def get_updates(self, *, offset: Optional[int] = None, limit: int = 20,
                    timeout: int = 0, allowed_updates: Optional[List[str]] = None) -> TelegramApiResult:
        params: Dict[str, Any] = {"limit": limit, "timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        if allowed_updates is not None:
            params["allowed_updates"] = allowed_updates
        return self._call("getUpdates", params)

    def answer_callback_query(self, callback_query_id: str, *, text: Optional[str] = None,
                              show_alert: bool = False) -> TelegramApiResult:
        params: Dict[str, Any] = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text is not None:
            params["text"] = text
        return self._call("answerCallbackQuery", params)

    def edit_message_text(self, chat_id: int, message_id: int, text: str, *,
                          reply_markup: Optional[Dict[str, Any]] = None) -> TelegramApiResult:
        params: Dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self._call("editMessageText", params)

    def edit_message_reply_markup(self, chat_id: int, message_id: int, *,
                                  reply_markup: Optional[Dict[str, Any]] = None) -> TelegramApiResult:
        params: Dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            params["reply_markup"] = reply_markup
        return self._call("editMessageReplyMarkup", params)


@dataclass(frozen=True)
class ParsedCallbackQuery:
    """The only fields the gateway is ever allowed to trust from a callback -- no
    execution-critical trade parameter is ever read from Telegram input (spec section
    9/12/13)."""

    callback_query_id: str
    user_id: int
    chat_id: Optional[int]
    action: str  # "x" (execute) / "r" (reject) / "d" (details)
    approval_id: str


def next_offset(updates: List[Dict[str, Any]], current_offset: Optional[int]) -> Optional[int]:
    """Per the official getUpdates contract: offset must become (highest update_id
    seen) + 1, never merely incremented by len(updates) -- Telegram does not guarantee
    exactly-once delivery ordering assumptions beyond update_id being monotonic."""
    if not updates:
        return current_offset
    highest = max(u["update_id"] for u in updates)
    return highest + 1


ACTION_EXECUTE = "x"
ACTION_REJECT = "r"
ACTION_DETAILS = "d"
_SUPPORTED_ACTIONS = frozenset({ACTION_EXECUTE, ACTION_REJECT, ACTION_DETAILS})
_CALLBACK_DATA_SEPARATOR = ":"


def build_callback_data(action: str, approval_id: str) -> str:
    """The ONLY shape callback_data may ever take -- action + opaque approval_id,
    never any execution-critical trade parameter (spec section 9/12: "Never encode
    execution-critical trade parameters in Telegram callback data")."""
    if action not in _SUPPORTED_ACTIONS:
        raise ValueError(f"unsupported action {action!r}")
    return f"{action}{_CALLBACK_DATA_SEPARATOR}{approval_id}"


def parse_callback_data(raw: str) -> Optional[tuple]:
    """Strict parse: returns (action, approval_id) or None for anything malformed.
    Never raises -- a malformed/unknown/oversized payload is an expected, reportable
    outcome (BLOCK, no state change), not a crash. Deliberately conservative: any
    ambiguity fails closed to None rather than guessing at intent."""
    if not isinstance(raw, str) or not raw:
        return None
    if len(raw.encode("utf-8")) > CALLBACK_DATA_MAX_BYTES:
        return None
    parts = raw.split(_CALLBACK_DATA_SEPARATOR, 1)
    if len(parts) != 2:
        return None
    action, approval_id = parts
    if action not in _SUPPORTED_ACTIONS:
        return None
    if not approval_id:
        return None
    return action, approval_id


def parse_callback_query(update: Dict[str, Any]) -> Optional[ParsedCallbackQuery]:
    """Extracts ONLY the fields the gateway is ever allowed to trust from a raw
    Telegram Update dict. Returns None for anything malformed/incomplete -- fail
    closed, never partially trust a callback. `chat_id` is None (not a parse failure)
    when the callback's original message is unavailable (Telegram: "message ... may
    be unavailable if it is too old"); callers must treat a missing chat_id as
    unauthorized, never as an implicit skip of chat validation."""
    callback_query = update.get("callback_query")
    if not isinstance(callback_query, dict):
        return None
    callback_query_id = callback_query.get("id")
    from_user = callback_query.get("from") or {}
    user_id = from_user.get("id")
    data = callback_query.get("data")
    if not callback_query_id or not isinstance(user_id, int) or not data:
        return None
    parsed = parse_callback_data(data)
    if parsed is None:
        return None
    action, approval_id = parsed
    message = callback_query.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    return ParsedCallbackQuery(
        callback_query_id=callback_query_id, user_id=user_id,
        chat_id=chat_id if isinstance(chat_id, int) else None,
        action=action, approval_id=approval_id,
    )
