"""Fail-closed guard: verifies the currently connected MT5 account matches the
.env-configured broker identity (mt5.config) before any execution path is allowed to
proceed. Read-only -- makes no order_check/order_send call itself, and does not call
mt5.connection.connect() (callers must already be connected; see mt5.connection).

This is deliberately separate from mt5.account.Account -- that module only reads raw
account state; this module is the one place "does the connected account match what
config claims" is decided (spec: prevent accidental terminal-session leakage, and block
LIVE unless MT5_ENVIRONMENT is explicitly LIVE).
"""
from __future__ import annotations

from typing import Optional

from .account import account as get_account
from .config import MT5ConfigError, load_mt5_config

REASON_CONFIG_ERROR = "CONFIG_ERROR"
REASON_ACCOUNT_UNAVAILABLE = "ACCOUNT_STATE_UNAVAILABLE"
REASON_LOGIN_MISMATCH = "ACCOUNT_LOGIN_MISMATCH"
REASON_SERVER_MISMATCH = "ACCOUNT_SERVER_MISMATCH"
REASON_ENVIRONMENT_MISMATCH = "ACCOUNT_ENVIRONMENT_MISMATCH"


def verify_configured_account() -> Optional[str]:
    """Returns None if the connected MT5 account matches the .env-configured identity
    (login, server, and demo/live environment all agree); otherwise a reason_code.
    Never raises -- an unreachable account or missing config is itself a reason_code, so
    every caller can fail closed on any non-None return."""
    try:
        config = load_mt5_config()
    except MT5ConfigError:
        return REASON_CONFIG_ERROR

    try:
        acct = get_account()
    except Exception:  # noqa: BLE001 -- surfaced as a reason_code, not a crash
        return REASON_ACCOUNT_UNAVAILABLE

    if acct.login != config.login:
        return REASON_LOGIN_MISMATCH
    if acct.server != config.server:
        return REASON_SERVER_MISMATCH

    expected_demo = config.environment == "DEMO"
    if acct.is_demo != expected_demo:
        return REASON_ENVIRONMENT_MISMATCH

    return None
