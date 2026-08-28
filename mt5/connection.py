"""MT5 terminal connection lifecycle. Read-only concern: this module never places or
modifies an order -- see execution/mt5_gateway.py for that boundary.
"""
from __future__ import annotations

import MetaTrader5 as mt5


class MT5ConnectionError(RuntimeError):
    pass


def connect() -> None:
    """Idempotent: safe to call when already connected. Requires the MT5 terminal to
    already be running and logged in (MT5_MCP_SETUP.md 'Operating notes') -- this
    function cannot launch it."""
    if not mt5.initialize():
        code, message = mt5.last_error()
        raise MT5ConnectionError(f"MT5_INITIALIZE_FAILED: ({code}) {message}")


def shutdown() -> None:
    mt5.shutdown()


def is_connected() -> bool:
    return mt5.terminal_info() is not None
