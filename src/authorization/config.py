"""Environment-variable configuration for AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1.

Fail-closed by construction: `execution_enabled` defaults to False, and `is_ready()`
requires a bot token, chat ID, and at least one allowed user before the gateway may
start its callback loop at all (spec section 25/35: "Do not infer enablement from
credentials being present" -- but the inverse also holds, credentials must ALSO be
present, enablement alone is not sufficient either). No `.env` file is read directly
here -- this project has no `python-dotenv` dependency and none is added for this
(spec section 41: "No new dependency unless clearly justified"); an operator-supplied
process environment (a real `.env` loaded by the OS/service manager, or exported
shell variables) is the supported mechanism, consistent with how this repository
already expects MT5/Bybit credentials to reach the process.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Mapping, Optional

DEFAULT_APPROVAL_TTL_SECONDS = 900
DEFAULT_POLL_TIMEOUT_SECONDS = 25
DEFAULT_STATE_DIR = "journal/telegram_execution_gateway"

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _as_bool(value: Optional[str], default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in _TRUE_VALUES


def _as_int_list(value: Optional[str]) -> List[int]:
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class TelegramGatewayConfig:
    execution_enabled: bool
    bot_token: str
    chat_id: Optional[int]
    allowed_user_ids: List[int]
    approval_ttl_seconds: int
    poll_timeout_seconds: int
    state_dir: str

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "TelegramGatewayConfig":
        env = env if env is not None else os.environ
        chat_id_raw = env.get("TELEGRAM_CHAT_ID")
        return cls(
            execution_enabled=_as_bool(env.get("AG_TELEGRAM_EXECUTION_ENABLED"), False),
            bot_token=env.get("TELEGRAM_BOT_TOKEN", ""),
            chat_id=int(chat_id_raw) if chat_id_raw else None,
            allowed_user_ids=_as_int_list(env.get("TELEGRAM_ALLOWED_USER_IDS")),
            approval_ttl_seconds=int(env.get("TELEGRAM_APPROVAL_TTL_SECONDS", DEFAULT_APPROVAL_TTL_SECONDS)),
            poll_timeout_seconds=int(env.get("TELEGRAM_POLL_TIMEOUT_SECONDS", DEFAULT_POLL_TIMEOUT_SECONDS)),
            state_dir=env.get("TELEGRAM_STATE_DIR", DEFAULT_STATE_DIR),
        )

    def is_ready(self) -> bool:
        """True only when the gateway has everything it needs to safely start the
        callback loop -- bot token, exactly one chat, and at least one allowed user.
        Never true merely because `execution_enabled` is set."""
        return bool(self.bot_token) and self.chat_id is not None and bool(self.allowed_user_ids)

    def safe_summary(self) -> dict:
        """Never includes the bot token or any secret -- the only thing this method
        exists to guarantee (spec section 21/42: "Never log bot token... .env
        contents")."""
        return {
            "execution_enabled": self.execution_enabled,
            "chat_configured": self.chat_id is not None,
            "allowed_user_count": len(self.allowed_user_ids),
            "approval_ttl_seconds": self.approval_ttl_seconds,
            "poll_timeout_seconds": self.poll_timeout_seconds,
            "state_dir": self.state_dir,
            "bot_token_configured": bool(self.bot_token),
        }
