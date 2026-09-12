"""Real, closed-bar MT5 retrieval for research use only. Reuses
`mt5.connection.connect()` verbatim (src/mt5/connection.py) -- no new connection
logic. Raw epoch -> UTC uses direct `datetime.fromtimestamp(epoch, tz=timezone.utc)`
only, per the timestamp-authority finding already established in this session
(broker offset is a SEPARATE, later concern -- never applied to an already-absolute
Unix epoch here).

CONTAINMENT: this module imports MetaTrader5 for read-only market-data retrieval
only. It never imports or calls `order_send`, `order_check`, or any function from
`execution.*` / `mt5.management_gateway` -- verified by
tests/test_research_external_containment.py's static AST scan, same technique as
`tests/test_external_candidate_governance_invariance.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

import MetaTrader5 as mt5

from mt5.connection import MT5ConnectionError, connect  # noqa: F401 (re-exported for callers)


@dataclass(frozen=True)
class RawBar:
    raw_epoch: int
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int


def capture_closed_bars(symbol: str, timeframe_name: str, count: int) -> List[RawBar]:
    """Connects (idempotent) and retrieves the last `count` bars via
    `mt5.copy_rates_from_pos(symbol, timeframe, 0, count)` -- position 0 is always the
    most recently CLOSED bar in the MetaTrader5 API's own convention (the still-forming
    bar is never included by copy_rates_from_pos at position 0 the way tick data would
    be), so no separate forming-bar exclusion is needed here."""
    connect()
    timeframe_map = {
        "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
    }
    if timeframe_name not in timeframe_map:
        raise ValueError(f"unsupported timeframe {timeframe_name!r}")

    rates = mt5.copy_rates_from_pos(symbol, timeframe_map[timeframe_name], 0, count)
    if rates is None:
        code, message = mt5.last_error()
        raise RuntimeError(f"copy_rates_from_pos failed: ({code}) {message}")

    bars: List[RawBar] = []
    for row in rates:
        raw_epoch = int(row["time"])
        bars.append(RawBar(
            raw_epoch=raw_epoch,
            timestamp_utc=datetime.fromtimestamp(raw_epoch, tz=timezone.utc).isoformat(),
            open=float(row["open"]), high=float(row["high"]), low=float(row["low"]), close=float(row["close"]),
            tick_volume=int(row["tick_volume"]), spread=int(row["spread"]), real_volume=int(row["real_volume"]),
        ))
    return bars


def broker_server_name() -> str:
    account_info = mt5.account_info()
    return account_info.server if account_info is not None else "UNKNOWN"
