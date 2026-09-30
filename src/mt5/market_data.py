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

from shared_cache.bounded_cache import BoundedCache
from strategy_engine.session import Candle

from .broker_time import BrokerTimeError, NoWeekendGapError, detect_broker_utc_offset_hours

# A 24/7 instrument (crypto CFDs: BTCUSD/ETHUSD on Vantage) has no weekly reopen gap for
# detect_broker_utc_offset_hours() to derive an offset from -- see AG_VANTAGE_MT5_CRYPTO_VENUE_V1
# follow-up, 2026-09-13. The broker's UTC offset is a property of the connected MT5
# SERVER, not of any one traded instrument: every symbol on a single terminal connection
# shares one server wall clock, so a 24/7 instrument's offset is re-derived from a
# reference FX symbol on that same connection instead of being assumed or hardcoded as a
# number. EURUSD/GBPUSD are the two FX symbols this repository's Vantage config
# (config/mt5.yaml) already knows to be tradable on this account; tried in order, first
# success wins.
_REFERENCE_SYMBOLS_FOR_24_7_OFFSET = ("EURUSD", "GBPUSD")

_TIMEFRAMES = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
    # TD-2 (AG_TD_TOPDOWN_CONTEXT, TopDownContext V1): additive only -- W1 is the one
    # timeframe TD-0's audit found nowhere in this repo. Native MT5 weekly candles via
    # mt5.TIMEFRAME_W1; no synthesis from any lower timeframe.
    "W1": mt5.TIMEFRAME_W1,
}

# TD-6 Layer A: raw closed-candle cache, wired directly into get_latest_candles()
# below (see that function's own docstring for why this placement -- not an external
# wrapper -- is what keeps historical_replay/data_source_patch.py's existing replay
# substitution mechanism fully intact). Local to this cache only, independent of
# _TIMEFRAMES above (same "kept independent, no shared private symbol" convention
# strategy_contract/market_snapshot.py already uses for its own timeframe-minutes copy).
_RAW_CACHE_PERIOD_MINUTES = {
    "M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440, "W1": 10080,
}


class _RawCacheEntry:
    __slots__ = ("candles", "valid_until")

    def __init__(self, candles, valid_until: datetime) -> None:
        self.candles = candles
        self.valid_until = valid_until


_RAW_CANDLE_CACHE: BoundedCache = BoundedCache()


def _is_raw_cache_entry_valid(entry: "_RawCacheEntry") -> bool:
    """A new bar of that timeframe cannot exist before `valid_until` (computed from
    the ACTUAL last fetched candle's own close, not a guess) -- see get_latest_candles's
    docstring. Never wall-clock TTL as the sole correctness authority: this check is
    conservative and provably correct, not merely probably fresh."""
    return datetime.now(timezone.utc) < entry.valid_until


def clear_raw_candle_cache() -> None:
    """Test-isolation / explicit reset only -- never called as part of normal request
    handling."""
    _RAW_CANDLE_CACHE.clear()


def raw_candle_cache_diagnostics() -> dict:
    return _RAW_CANDLE_CACHE.diagnostics()


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
        # Present in the terminal but not in Market Watch -- docs/setup/MT5_MCP_SETUP.md 'Operating
        # notes': invisible to the API until selected. Select once rather than failing.
        if not mt5.symbol_select(symbol, True):
            raise MarketDataError("SYMBOL_NOT_FOUND", f"{symbol!r} not visible and symbol_select failed")


@lru_cache(maxsize=32)
def _broker_offset_hours(symbol: str) -> int:
    try:
        return detect_broker_utc_offset_hours(symbol)
    except NoWeekendGapError as exc:
        for reference_symbol in _REFERENCE_SYMBOLS_FOR_24_7_OFFSET:
            if reference_symbol == symbol:
                continue
            try:
                return detect_broker_utc_offset_hours(reference_symbol)
            except BrokerTimeError:
                continue
        raise MarketDataError(
            "TIME_NORMALIZATION_ERROR",
            f"{symbol}: no weekly reopen gap (24/7 instrument) and no reference FX symbol "
            f"in {_REFERENCE_SYMBOLS_FOR_24_7_OFFSET} could establish the broker's UTC offset "
            f"on this connection",
        ) from exc
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
    still-forming current bar and is deliberately excluded).

    TD-6 Layer A: an identical (symbol, timeframe, count) request within the same
    closed bar is served from an in-process cache instead of a second MT5 round trip
    -- see _is_raw_cache_entry_valid below for the exact, data-identity-driven (never
    wall-clock-TTL) invalidation rule. Deliberately implemented INSIDE this function's
    own body, not as an external wrapper: historical_replay/data_source_patch.py
    substitutes replay data by monkeypatching each consumer module's own bound name of
    get_latest_candles (including this module's own name, for callers that import it
    fresh per-call) -- when patched, the ENTIRE function object named here is replaced,
    so this cache is automatically and completely bypassed during replay without any
    replay-specific code in this module. A cache miss's behavior is byte-identical to
    this function's behavior before TD-6."""
    cache_key = (symbol, timeframe, count)
    cached_entry = _RAW_CANDLE_CACHE.get(cache_key, is_valid=_is_raw_cache_entry_valid)
    if cached_entry is not None:
        return list(cached_entry.candles)

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

    if timeframe in _RAW_CACHE_PERIOD_MINUTES:
        valid_until = candles[-1].time + timedelta(minutes=_RAW_CACHE_PERIOD_MINUTES[timeframe])
        _RAW_CANDLE_CACHE.put(cache_key, _RawCacheEntry(candles=tuple(candles), valid_until=valid_until))
    return candles


def get_tick(symbol: str) -> Tick:
    """Current Bid/Ask. Requires mt5.connection.connect() already called."""
    _require_connected()
    _require_symbol(symbol)

    tick = mt5.symbol_info_tick(symbol)
    if tick is None or tick.time == 0:
        code, message = mt5.last_error()
        raise MarketDataError("DATA_MISSING", f"symbol_info_tick({symbol!r}) returned no data: ({code}) {message}")

    # Non-positive Bid/Ask is "no quote yet", not a price. Observed live on this account
    # (AG_VANTAGE_MT5_CRYPTO_VENUE_V1, 2026-09-13): immediately after _require_symbol()
    # selects a symbol that was NOT already in Market Watch, symbol_info_tick() can
    # return bid=0.0/ask=0.0 for a moment before the first quote streams in. FX never hit
    # this because EURUSD/GBPUSD are always already in Market Watch; BTCUSD/ETHUSD are
    # not, so crypto reaches it on the very first call after a terminal restart. Without
    # this guard a 0.0 would flow into execution.executor._resolve_entry_price() as a
    # real entry price and be rejected later by geometry with a misleading reason code
    # (INVALID_LONG_STOP) instead of the accurate "there is no market data". Fails closed
    # with the same DATA_MISSING code the branch above already uses -- an added
    # rejection, never a new acceptance, so no previously-valid tick becomes invalid.
    if not (float(tick.bid) > 0 and float(tick.ask) > 0):
        raise MarketDataError(
            "DATA_MISSING",
            f"symbol_info_tick({symbol!r}) returned a non-positive quote "
            f"(bid={tick.bid}, ask={tick.ask}) -- symbol likely just selected into "
            f"Market Watch and not yet quoting",
        )

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
