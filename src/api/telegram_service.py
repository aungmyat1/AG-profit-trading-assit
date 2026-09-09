"""Backend-owned Telegram status/test/notify operations for GET /api/telegram/status,
POST /api/telegram/test, POST /api/telegram/trades/{id}/notify, POST /api/telegram/
positions/{id}/notify. Reuses notifications.telegram_client.TelegramClient and
authorization.config.TelegramGatewayConfig exactly as authorization.telegram_gateway
already does -- this is not a second Telegram gateway, just a thin HTTP-facing wrapper
around the same client/config. No inline keyboard, no callback handling, no execution
capability of any kind lives here.

Secret ownership: TelegramGatewayConfig.from_env() is the only place a bot token is
read, and it is never returned by any function in this module -- see TelegramStatus /
TelegramActionResult, neither of which carries a token field.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from authorization.config import TelegramGatewayConfig
from notifications.telegram_client import TelegramClient, TelegramClientError

TEST_NOTIFICATION_COOLDOWN_SECONDS = 30.0


def _outbound_ready(cfg: TelegramGatewayConfig) -> bool:
    """Outbound send capability (status/test/notify -- no inline keyboard, no callback
    handling) needs only a bot token and a destination chat -- unlike
    TelegramGatewayConfig.is_ready(), which additionally requires a non-empty
    `allowed_user_ids` because THAT flag gates the separate inbound-callback
    authorization path (authorization.telegram_gateway's Execute/Reject buttons).
    Reusing is_ready() here would report NOT_CONFIGURED for an environment that has a
    bot token and chat configured for outbound alerts but has deliberately not enabled
    inbound Telegram-button execution -- a real, supported configuration this module
    must not treat as unconfigured."""
    return bool(cfg.bot_token) and cfg.chat_id is not None


# Process-local last-send timestamp -- a minimal abuse guard for the test-notification
# endpoint. Deliberately simple (no new rate-limiting infrastructure invented for this
# milestone): one shared cooldown is enough to stop a client from hammering the bot
# token with rapid repeated test sends.
_last_test_sent_monotonic: dict = {}


@dataclass(frozen=True)
class TelegramStatus:
    configured: bool
    bot_configured: bool
    chat_configured: bool
    reachable: bool
    reason_code: Optional[str] = None


@dataclass(frozen=True)
class TelegramActionResult:
    success: bool
    reason_code: Optional[str] = None
    message_id: Optional[str] = None


def get_status(config: Optional[TelegramGatewayConfig] = None) -> TelegramStatus:
    """`reachable` is only ever attempted when both a bot token and chat are actually
    configured -- never fabricated true merely because the environment variables
    exist. A live getMe() call is read-only and sends no message."""
    cfg = config or TelegramGatewayConfig.from_env()
    bot_configured = bool(cfg.bot_token)
    chat_configured = cfg.chat_id is not None
    configured = _outbound_ready(cfg)

    if not configured:
        return TelegramStatus(
            configured=False, bot_configured=bot_configured, chat_configured=chat_configured,
            reachable=False, reason_code="NOT_CONFIGURED",
        )

    try:
        client = TelegramClient(cfg.bot_token)
        result = client.get_me()
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        return TelegramStatus(
            configured=True, bot_configured=bot_configured, chat_configured=chat_configured,
            reachable=False, reason_code=f"TELEGRAM_UNREACHABLE:{type(exc).__name__}",
        )

    if not result.ok:
        return TelegramStatus(
            configured=True, bot_configured=bot_configured, chat_configured=chat_configured,
            reachable=False, reason_code=f"TELEGRAM_ERROR_{result.error_code}",
        )
    return TelegramStatus(configured=True, bot_configured=bot_configured, chat_configured=chat_configured, reachable=True)


def send_test_notification(config: Optional[TelegramGatewayConfig] = None) -> TelegramActionResult:
    cfg = config or TelegramGatewayConfig.from_env()
    if not _outbound_ready(cfg):
        return TelegramActionResult(success=False, reason_code="NOT_CONFIGURED")

    now = time.monotonic()
    last = _last_test_sent_monotonic.get("last")
    if last is not None and (now - last) < TEST_NOTIFICATION_COOLDOWN_SECONDS:
        return TelegramActionResult(success=False, reason_code="RATE_LIMITED")
    _last_test_sent_monotonic["last"] = now

    text = "AG Profit Trading Assistant: backend diagnostic test message. No trading action was taken."
    return _send(cfg, text)


def notify_trade(approval, config: Optional[TelegramGatewayConfig] = None) -> TelegramActionResult:
    """`approval` is the canonical ExecutionApproval the caller already loaded from
    authorization.store.ExecutionApprovalStore -- this function never accepts or trusts
    a client-supplied symbol/price/volume/P&L for the message body."""
    cfg = config or TelegramGatewayConfig.from_env()
    if not _outbound_ready(cfg):
        return TelegramActionResult(success=False, reason_code="NOT_CONFIGURED")
    text = (
        "AG Trade Ticket\n"
        f"approval_id={approval.approval_id}\n"
        f"setup_id={approval.setup_id}\n"
        f"environment={approval.environment}\n"
        f"state={approval.state}"
    )
    return _send(cfg, text)


def notify_position(position, config: Optional[TelegramGatewayConfig] = None) -> TelegramActionResult:
    """`position` is a trade_management.position_monitor.NormalizedPosition the caller
    already loaded from the real MT5 position -- never a client-supplied payload."""
    cfg = config or TelegramGatewayConfig.from_env()
    if not _outbound_ready(cfg):
        return TelegramActionResult(success=False, reason_code="NOT_CONFIGURED")
    text = (
        "AG Position Update\n"
        f"ticket={position.ticket}\n"
        f"symbol={position.symbol}\n"
        f"direction={position.direction}\n"
        f"volume={position.volume_current}\n"
        f"current_price={position.current_price}\n"
        f"profit={position.profit}"
    )
    return _send(cfg, text)


def _send(cfg: TelegramGatewayConfig, text: str) -> TelegramActionResult:
    try:
        client = TelegramClient(cfg.bot_token)
        result = client.send_message(cfg.chat_id, text)
    except TelegramClientError as exc:
        return TelegramActionResult(success=False, reason_code=f"TELEGRAM_CLIENT_ERROR:{exc.reason_code}")
    except Exception as exc:  # noqa: BLE001 -- never leak a raw traceback to the client
        return TelegramActionResult(success=False, reason_code=f"TELEGRAM_SEND_ERROR:{type(exc).__name__}")

    if not result.ok:
        return TelegramActionResult(success=False, reason_code=f"TELEGRAM_ERROR_{result.error_code}")
    message_id = result.result.get("message_id") if isinstance(result.result, dict) else None
    return TelegramActionResult(success=True, message_id=str(message_id) if message_id is not None else None)
