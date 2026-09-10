"""MT5 terminal connection lifecycle. Read-only concern: this module never places or
modifies an order -- see execution/mt5_gateway.py for that boundary.
"""
from __future__ import annotations

import MetaTrader5 as mt5

from mt5.config import load_mt5_config


class MT5ConnectionError(RuntimeError):
    pass


def connect() -> None:
    """Idempotent: safe to call when already connected. Requires the MT5 terminal to
    already be running and logged in (docs/setup/MT5_MCP_SETUP.md 'Operating notes') -- this
    function cannot launch it."""
    if not mt5.initialize():
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"MT5_INITIALIZE_FAILED: ({code}) {message}")


def connect_configured() -> None:
    """Connect to the exact configured Vantage Demo terminal/account.

    This is used by execution-facing subprocesses so MT5 auto-discovery cannot attach
    to another installed terminal. Broker identity is still rechecked by the gateway
    before any order submission.
    """
    config = load_mt5_config()
    kwargs = {
        "login": config.login,
        "password": config.password,
        "server": config.server,
    }
    if config.terminal_path:
        kwargs["path"] = config.terminal_path
    if not mt5.initialize(timeout=10_000, **kwargs):
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"MT5_CONFIGURED_INITIALIZE_FAILED: ({code}) {message}")


def shutdown() -> None:
    mt5.shutdown()


def is_connected() -> bool:
    return mt5.terminal_info() is not None
