"""Candle + tick retrieval and UTC normalization. Responsible only for MT5 retrieval,
timestamp normalization, OHLC/tick mapping, and basic completeness/freshness checks --
NOT session/box/regime/sweep calculation (that's strategy_engine's job).

Returns strategy_engine.session.Candle, the canonical shape shared by MT5, CSV, or any
future data source, so the engine never needs to know where a candle came from.
"""
from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import List, Optional

import MetaTrader5 as mt5

from strategy_engine.session import Candle

from .broker_time import BrokerTimeError, detect_broker_utc_offset_hours

_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


class MarketDataError(RuntimeError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class Tick:
    symbol: str
    time_utc: datetime
    bid: float
    ask: float
    spread_points: Optional[int] = None


def _require_connected() -> None:
    if mt5.terminal_info() is None:
        raise MarketDataError("MT5_NOT_CONNECTED", "mt5.connection.connect() has not been called or the terminal dropped")


def _require_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        code, message = mt5.last_error()
        raise MarketDataError("SYMBOL_NOT_FOUND", f"{symbol!r} not found ({code}) {message}")
    if not info.visible:
        # Present in the terminal but not in Market Watch -- MT5_MCP_SETUP.md 'Operating
        # notes': invisible to the API until selected. Select once rather than failing.
        if not mt5.symbol_select(symbol, True):
            raise MarketDataError("SYMBOL_NOT_FOUND", f"{symbol!r} not visible and symbol_select failed")


@lru_cache(maxsize=32)
def _broker_offset_hours(symbol: str) -> int:
    try:
        return detect_broker_utc_offset_hours(symbol)
    except BrokerTimeError as exc:
        raise MarketDataError("TIME_NORMALIZATION_ERROR", str(exc)) from exc


def get_candles(symbol: str, timeframe: str, start_utc: datetime, end_utc: datetime) -> List[Candle]:
    """[start_utc, end_utc) in true UTC. Requires mt5.connection.connect() already called."""
    _require_connected()
    _require_symbol(symbol)
    if timeframe not in _TIMEFRAMES:
        raise MarketDataError("UNSUPPORTED_TIMEFRAME", f"{timeframe!r} not in {list(_TIMEFRAMES)}")
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise MarketDataError("NAIVE_DATETIME_REJECTED", "start_utc/end_utc must be timezone-aware UTC")

    offset = _broker_offset_hours(symbol)
    # Deliberately epoch INTEGERS, not datetime objects: the MetaTrader5 python module
    # converts a naive datetime passed to copy_rates_range via this machine's *system*
    # local timezone (confirmed empirically -- on a UTC+6:30 system it silently shifted
    # every query by 6.5h), not as literal broker-wall-clock digits. Passing an int
    # sidesteps that reinterpretation entirely -- see tests/test_market_data.py.
    start_epoch = _to_broker_epoch(start_utc, offset)
    end_epoch = _to_broker_epoch(end_utc, offset) - 1  # half-open: exclude a bar opening exactly at end_utc

    rates = mt5.copy_rates_range(symbol, _TIMEFRAMES[timeframe], start_epoch, end_epoch)
    if rates is None or len(rates) == 0:
        code, message = mt5.last_error()
        raise MarketDataError("DATA_MISSING", f"copy_rates_range({symbol!r}, {timeframe}) returned no data: ({code}) {message}")

    candles = [
        Candle(
            time=(datetime.utcfromtimestamp(int(r["time"])) - timedelta(hours=offset)).replace(tzinfo=timezone.utc),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["tick_volume"]),
        )
        for r in rates
    ]

    _validate_monotonic(candles, symbol)
    _validate_ohlc(candles, symbol)
    return candles


def get_latest_candles(symbol: str, timeframe: str, count: int) -> List[Candle]:
    """Most recent `count` CLOSED bars, oldest first. Convenience wrapper over
    copy_rates_from_pos (position 1 = last fully closed bar; position 0 is the
    still-forming current bar and is deliberately excluded)."""
    _require_connected()
    _require_symbol(symbol)
    if timeframe not in _TIMEFRAMES:
        raise MarketDataError("UNSUPPORTED_TIMEFRAME", f"{timeframe!r} not in {list(_TIMEFRAMES)}")

    offset = _broker_offset_hours(symbol)
    rates = mt5.copy_rates_from_pos(symbol, _TIMEFRAMES[timeframe], 1, count)
    if rates is None or len(rates) == 0:
        code, message = mt5.last_error()
        raise MarketDataError("DATA_MISSING", f"copy_rates_from_pos({symbol!r}, {timeframe}) returned no data: ({code}) {message}")
    if len(rates) < count:
        raise MarketDataError("INSUFFICIENT_CANDLES", f"{symbol}: requested {count}, got {len(rates)}")

    candles = [
        Candle(
            time=(datetime.utcfromtimestamp(int(r["time"])) - timedelta(hours=offset)).replace(tzinfo=timezone.utc),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r["tick_volume"]),
        )
        for r in rates
    ]
    _validate_monotonic(candles, symbol)
    _validate_ohlc(candles, symbol)
    return candles


def get_tick(symbol: str) -> Tick:
    """Current Bid/Ask. Requires mt5.connection.connect() already called."""
    _require_connected()
    _require_symbol(symbol)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None or tick.time == 0:
        code, message = mt5.last_error()
        raise MarketDataError("DATA_MISSING", f"symbol_info_tick({symbol!r}) returned no data: ({code}) {message}")

    offset = _broker_offset_hours(symbol)
    time_utc = (datetime.utcfromtimestamp(int(tick.time)) - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
    info = mt5.symbol_info(symbol)
    return Tick(symbol=symbol, time_utc=time_utc, bid=float(tick.bid), ask=float(tick.ask),
                spread_points=(info.spread if info is not None else None))


def check_freshness(as_of_utc: datetime, now_utc: datetime, max_age_seconds: float) -> Optional[str]:
    """Pure function: returns 'STALE_DATA' if `as_of_utc` is older than `max_age_seconds`
    relative to `now_utc`, else None. Caller decides the threshold and whether staleness
    is expected (e.g. a closed weekend market) -- this module doesn't guess a market
    calendar."""
    age = (now_utc - as_of_utc).total_seconds()
    if age > max_age_seconds:
        return "STALE_DATA"
    return None


def _to_broker_epoch(true_utc: datetime, offset_hours: int) -> int:
    broker_wall_clock = true_utc.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(hours=offset_hours)
    return calendar.timegm(broker_wall_clock.timetuple())


def _validate_monotonic(candles: List[Candle], symbol: str) -> None:
    for prev, cur in zip(candles, candles[1:]):
        if cur.time == prev.time:
            raise MarketDataError("DUPLICATE_TIMESTAMPS", f"{symbol}: duplicate candle time {cur.time}")
        if cur.time < prev.time:
            raise MarketDataError("NON_MONOTONIC_TIMESTAMPS", f"{symbol}: {cur.time} follows {prev.time}")


def _validate_ohlc(candles: List[Candle], symbol: str) -> None:
    for c in candles:
        if not all(math.isfinite(v) for v in (c.open, c.high, c.low, c.close)):
            raise MarketDataError("NONFINITE_PRICE", f"{symbol} {c.time}: non-finite OHLC value")
        if c.high < c.open or c.high < c.close or c.high < c.low or c.low > c.open or c.low > c.close:
            raise MarketDataError("INVALID_OHLC", f"{symbol} {c.time}: O:{c.open} H:{c.high} L:{c.low} C:{c.close}")
