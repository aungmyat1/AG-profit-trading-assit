"""Best-effort Telegram side-effects for confirmed trade-management lifecycle actions
(breakeven move, TP1 partial close, final exit) -- Phase 5 of AG_FASTAPI_TELEGRAM_
BACKEND_CONSOLIDATION. Reuses notifications.telegram_client.TelegramClient and
authorization.config.TelegramGatewayConfig exactly as authorization.telegram_gateway /
ticket_delivery.telegram_adapter already do; this module sends a plain informational
message only -- no inline keyboard, no callback, no approval/execution capability.

Hard invariant: this module must NEVER raise into its caller (trade_management.manager's
run_cycle_for_ticket). A Telegram failure is caught here, journaled via the SAME
trade_management.journal already used for the confirmed action itself (a new, distinct
event so a notification failure is recorded separately from -- and never overwrites --
the trading state transition that already completed), and otherwise ignored. The caller
never inspects this function's return value for control flow.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from authorization.config import TelegramGatewayConfig
from trade_management import journal as tm_journal

from .telegram_client import TelegramClient

logger = logging.getLogger("notifications.trade_management_alerts")


def _redact(text: str, bot_token: str) -> str:
    """A transport-level exception's str() can embed the full request URL
    (.../bot<TOKEN>/sendMessage) -- e.g. requests.ConnectionError/Timeout commonly
    include it. Same technique as ticket_delivery.telegram_adapter._redact(); applied
    to every exception string this module logs or journals, not only ones that look
    suspicious."""
    if not text or not bot_token:
        return text
    return re.sub(re.escape(bot_token), "***REDACTED***", text)

_ACTION_LABELS = {
    "PARTIAL_CLOSE": "Partial TP1 close",
    "MOVE_SL": "Breakeven stop move",
    "CLOSE": "Final exit",
}


def notify_confirmed_action(
    ticket: int, symbol: str, action: str, *, reason_code: str = "",
    base_dir: str = "journal", config: Optional[TelegramGatewayConfig] = None,
) -> None:
    """Called only AFTER the action's own `{action}_CONFIRMED` journal event is already
    recorded (see trade_management.manager) -- notification is a side effect of an
    already-committed state transition, never a precondition for one."""
    cfg = config or TelegramGatewayConfig.from_env()
    if not (cfg.bot_token and cfg.chat_id is not None):
        return  # not configured -- silent no-op, this is expected in most environments

    label = _ACTION_LABELS.get(action, action)
    text = (
        f"AG Trade Management\nTicket #{ticket} ({symbol})\n{label} confirmed."
        + (f"\nReason: {reason_code}" if reason_code else "")
    )

    try:
        client = TelegramClient(cfg.bot_token)
        result = client.send_message(cfg.chat_id, text)
    except Exception as exc:  # noqa: BLE001 -- must never propagate into the caller's state machine
        logger.warning(
            "trade management telegram notify failed ticket=%s action=%s: %s",
            ticket, action, _redact(str(exc), cfg.bot_token),
        )
        _record(ticket, action, "TELEGRAM_NOTIFY_FAILED", base_dir, reason_code="TELEGRAM_SEND_EXCEPTION")
        return

    if result.ok:
        _record(ticket, action, "TELEGRAM_NOTIFY_SENT", base_dir)
    else:
        _record(ticket, action, "TELEGRAM_NOTIFY_FAILED", base_dir, reason_code=f"TELEGRAM_ERROR_{result.error_code}")


_CLOSE_REASON_LABELS = {
    "SL": "closed by STOP LOSS",
    "TP": "closed by TAKE PROFIT",
    "STOP_OUT": "closed by broker STOP OUT",
    "MANUAL": "closed manually",
    "EXPERT": "closed by an expert/automated request",
    "UNKNOWN": "closed broker-side (reason could not be confirmed)",
}


def notify_position_closed(
    ticket: int, symbol: str, close_reason: str, *,
    base_dir: str = "journal", config: Optional[TelegramGatewayConfig] = None,
) -> None:
    """Broker-side close alert (stop-loss hit being the case that previously had no
    notification at all -- reconcile() detected STATE_CLOSED and returned silently).

    Same contract as notify_confirmed_action: called only AFTER the close has already
    been reconciled and journaled, never raises into the caller, and is a no-op when
    Telegram is not configured. Caller owns de-duplication (see
    trade_management.manager) so a restart/re-reconcile of an already-notified closed
    position sends nothing.
    """
    cfg = config or TelegramGatewayConfig.from_env()
    if not (cfg.bot_token and cfg.chat_id is not None):
        return  # not configured -- silent no-op

    event = f"POSITION_CLOSED_{close_reason}"
    label = _CLOSE_REASON_LABELS.get(close_reason, _CLOSE_REASON_LABELS["UNKNOWN"])
    text = (
        f"AG Trade Management\nTicket #{ticket} ({symbol})\nPosition {label}.\n"
        f"Reason: {event}"
    )

    try:
        client = TelegramClient(cfg.bot_token)
        result = client.send_message(cfg.chat_id, text)
    except Exception as exc:  # noqa: BLE001 -- must never propagate into reconciliation
        logger.warning(
            "trade management telegram close-notify failed ticket=%s reason=%s: %s",
            ticket, close_reason, _redact(str(exc), cfg.bot_token),
        )
        _record(ticket, event, "TELEGRAM_NOTIFY_FAILED", base_dir, reason_code="TELEGRAM_SEND_EXCEPTION")
        return

    if result.ok:
        _record(ticket, event, "TELEGRAM_NOTIFY_SENT", base_dir)
    else:
        _record(ticket, event, "TELEGRAM_NOTIFY_FAILED", base_dir, reason_code=f"TELEGRAM_ERROR_{result.error_code}")


def _record(ticket: int, action: str, outcome: str, base_dir: str, **payload) -> None:
    try:
        tm_journal.record_event(ticket, f"{action}_{outcome}", base_dir, **payload)
    except OSError:  # noqa: BLE001 -- journaling the notification outcome must also never raise
        logger.warning("trade management telegram notify journal write failed ticket=%s action=%s", ticket, action)
