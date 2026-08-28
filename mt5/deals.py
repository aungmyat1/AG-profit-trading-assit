"""Deal history reads (history_deals_get). Read-only -- used by trade_management to
confirm a partial/full close actually filled (broker state is authoritative, spec
section 19/22), never to place or modify anything.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

import MetaTrader5 as mt5


class DealsError(RuntimeError):
    pass


def deals_for_position(ticket: int, lookback: timedelta = timedelta(days=7)) -> Sequence:
    """Raw MT5 deal rows (history_deals_get() namedtuples) for a given position ticket,
    most recent lookback window. Used to confirm a requested partial/full close was
    actually executed by the broker, not just accepted by the Python call."""
    now = datetime.now(timezone.utc)
    raw = mt5.history_deals_get(now - lookback, now, position=ticket)
    if raw is None:
        code, message = mt5.last_error()
        raise DealsError(f"HISTORY_DEALS_GET_FAILED: ({code}) {message}")
    return list(raw)


def deals_for_symbol(symbol: str, lookback: timedelta = timedelta(hours=24)) -> Sequence:
    """Raw MT5 deal rows for a symbol over a lookback window, no ticket required --
    used by execution/executor.py's crash/restart reconciliation (AG_DEMO_EXECUTION_SAFETY_V1,
    2026-08-28) to detect a broker-side fill that happened before local journal persistence,
    by scanning for a matching command_id tag in the deal's own comment. Reuses this
    module's existing history_deals_get wrapper rather than adding a second one."""
    now = datetime.now(timezone.utc)
    raw = mt5.history_deals_get(now - lookback, now)
    if raw is None:
        code, message = mt5.last_error()
        raise DealsError(f"HISTORY_DEALS_GET_FAILED: ({code}) {message}")
    # group= filters by a broker-side symbol-group mask, not always an exact match --
    # filter client-side on the deal's own symbol field for correctness instead.
    return [d for d in raw if d.symbol == symbol]
