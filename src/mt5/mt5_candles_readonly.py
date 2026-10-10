"""MT5_CANDLES_READONLY_R1 -- read-only, fixture-compatible MT5 candle adapter for the four
FX-objective instruments (EURUSD, GBPUSD, USDJPY, XAUUSD).

Read-only by construction: the only MT5 calls are ``symbol_info`` (symbol existence),
``copy_rates_from_pos`` / ``copy_rates_range`` (candles) and ``last_error`` (diagnostics).
Nothing here calls order_send, order_check, symbol_select, positions_*, orders_*, history_*
or any account function (tests/test_mt5_candles_readonly.py enforces this).

Symbol identity: canonical -> broker symbols come only from the versioned
CANONICAL_TO_BROKER_MAP (mt5.canonical_broker_map, default_symbol_map()). No suffix is
ever guessed; a missing/mismatched mapping or a broker symbol the terminal does not know is
SYMBOL_MAPPING_MISSING, never a substitute symbol.

Time authority: MT5 bar times are broker-server wall clock. They are converted to aware UTC
here, once, with host_evidence.symbol_metadata.server_time_to_utc (the owner-stated rule:
server midnight = New York 17:00) -- the same single conversion point scripts/host uses.
Callers never see server time.

Integrity: duplicate, non-monotonic or off-grid timestamps raise. Gaps are reported (never
forward-filled, never manufactured) and classified as WEEKEND_CLOSE, DAILY_BREAK (around the
17:00 New York rollover) or INTRADAY_GAP.

Not wired into any evaluator; this module performs no strategy evaluation.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List

from host_evidence.symbol_metadata import NY, DstHourError, server_time_to_utc
from mt5 import canonical_broker_map
from strategy_engine.session import Candle

_log = logging.getLogger(__name__)
UTC = dt.timezone.utc

SUPPORTED_SYMBOLS = ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD")
TIMEFRAME_MINUTES = {"M15": 15, "H1": 60}
CANONICAL_FIELDS = ("symbol", "time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume")
# The complete set of MT5 attributes this adapter may touch (constants excluded).
ALLOWED_MT5_CALLS = frozenset({"symbol_info", "copy_rates_from_pos", "copy_rates_range", "last_error"})

SYMBOL_MAPPING_MISSING = "SYMBOL_MAPPING_MISSING"
UNSUPPORTED_TIMEFRAME = "UNSUPPORTED_TIMEFRAME"
DATA_MISSING = "DATA_MISSING"
CONVERSION_ERROR = "CONVERSION_ERROR"
DUPLICATE_TIMESTAMP = "DUPLICATE_TIMESTAMP"
NON_MONOTONIC = "NON_MONOTONIC"
OFF_GRID_TIMESTAMP = "OFF_GRID_TIMESTAMP"
# Terminal status for a symbol whose acquisition failed; the other symbols are unaffected.
DATA_ERROR = "DATA_ERROR"

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_METADATA_DIR = os.path.join(_REPO_ROOT, "config", "symbol_metadata", "host_captured")


class CandleAdapterError(RuntimeError):
    terminal_status = DATA_ERROR

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CanonicalCandle:
    symbol: str          # canonical symbol (never the broker symbol)
    time: dt.datetime    # bar-open time, aware UTC
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int          # MT5 bar spread, in points
    real_volume: int

    def to_engine_candle(self) -> Candle:
        """The strategy_engine / evaluator-fixture Candle (volume = tick volume)."""
        return Candle(time=self.time, open=self.open, high=self.high, low=self.low,
                      close=self.close, volume=float(self.tick_volume))


def load_symbol_map(metadata_dir: str = DEFAULT_METADATA_DIR) -> Dict[str, str]:
    """canonical -> broker symbol, from committed host-captured metadata only.  Symbols
    without a valid record are absent; resolve_broker_symbol() then fails loudly."""
    out: Dict[str, str] = {}
    for canonical in SUPPORTED_SYMBOLS:
        path = os.path.join(metadata_dir, f"{canonical}.json")
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, ValueError):
            continue
        broker = rec.get("broker_symbol")
        if rec.get("canonical_symbol") == canonical and isinstance(broker, str) and broker:
            out[canonical] = broker
    return out


def resolve_broker_symbol(canonical: str, symbol_map: Dict[str, str]) -> str:
    if canonical not in SUPPORTED_SYMBOLS:
        raise CandleAdapterError(SYMBOL_MAPPING_MISSING, f"{canonical!r} is not a supported canonical symbol")
    broker = symbol_map.get(canonical)
    if not broker:
        raise CandleAdapterError(SYMBOL_MAPPING_MISSING, f"no broker symbol mapped for {canonical!r}")
    return broker


def _server_wall(raw_time: int) -> dt.datetime:
    # copy_rates 'time' is server wall clock encoded as epoch seconds; strip the false UTC label.
    return dt.datetime.fromtimestamp(raw_time, UTC).replace(tzinfo=None)


def _to_canonical(canonical: str, rates: Any) -> List[CanonicalCandle]:
    try:
        out = []
        for r in rates:
            try:
                t = server_time_to_utc(_server_wall(int(r["time"])))
            except DstHourError as exc:  # repeated/skipped server hour: drop + log, never fold
                _log.warning("DROPPED_BAR %s %s %s", exc.reason_code, canonical, exc.server_wall_clock.isoformat())
                continue
            out.append(CanonicalCandle(
                symbol=canonical, time=t,
                open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]),
                tick_volume=int(r["tick_volume"]), spread=int(r["spread"]), real_volume=int(r["real_volume"]),
            ))
        return out
    except (KeyError, IndexError, TypeError, ValueError, OverflowError, OSError) as exc:
        raise CandleAdapterError(CONVERSION_ERROR, f"{canonical}: {type(exc).__name__} {exc}") from exc


def _check_integrity(candles: List[CanonicalCandle], timeframe: str) -> None:
    step = TIMEFRAME_MINUTES[timeframe]
    for i, c in enumerate(candles):
        if c.time.tzinfo is None or c.time.utcoffset() != dt.timedelta(0):
            raise CandleAdapterError(CONVERSION_ERROR, f"{c.symbol} bar {i} is not aware UTC: {c.time!r}")
        if (c.time.minute % step if step < 60 else c.time.minute) or c.time.second or c.time.microsecond:
            raise CandleAdapterError(OFF_GRID_TIMESTAMP, f"{c.symbol}/{timeframe} {c.time.isoformat()}")
        if i:
            prev = candles[i - 1].time
            if c.time == prev:
                raise CandleAdapterError(DUPLICATE_TIMESTAMP, f"{c.symbol}/{timeframe} {c.time.isoformat()}")
            if c.time < prev:
                raise CandleAdapterError(NON_MONOTONIC, f"{c.symbol}/{timeframe} {prev.isoformat()} -> {c.time.isoformat()}")


def fetch_closed_candles(mt5: Any, canonical: str, timeframe: str, count: int,
                         symbol_map: Dict[str, str]) -> List[CanonicalCandle]:
    """The last `count` CLOSED bars (position 1 onward), oldest first, aware UTC."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise CandleAdapterError(UNSUPPORTED_TIMEFRAME, repr(timeframe))
    broker = resolve_broker_symbol(canonical, symbol_map)
    if mt5.symbol_info(broker) is None:
        raise CandleAdapterError(SYMBOL_MAPPING_MISSING, f"{canonical} -> {broker!r} unknown to terminal: {mt5.last_error()}")
    rates = mt5.copy_rates_from_pos(broker, getattr(mt5, f"TIMEFRAME_{timeframe}"), 1, count)
    if rates is None or len(rates) == 0:
        raise CandleAdapterError(DATA_MISSING, f"{canonical}/{timeframe} ({broker}): {mt5.last_error()}")
    candles = _to_canonical(canonical, rates)
    _check_integrity(candles, timeframe)
    return candles


def fetch_candles_range(mt5: Any, canonical: str, timeframe: str, start_utc: dt.datetime,
                        end_utc: dt.datetime, symbol_map: Dict[str, str]) -> List[CanonicalCandle]:
    """Bars whose UTC open time lies in [start_utc, end_utc].  The server-side query window is
    widened by a day each side (offset-agnostic) and the result is filtered in UTC here."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise CandleAdapterError(UNSUPPORTED_TIMEFRAME, repr(timeframe))
    if start_utc.tzinfo is None or end_utc.tzinfo is None:
        raise ValueError("start_utc/end_utc must be timezone-aware")
    broker = resolve_broker_symbol(canonical, symbol_map)
    if mt5.symbol_info(broker) is None:
        raise CandleAdapterError(SYMBOL_MAPPING_MISSING, f"{canonical} -> {broker!r} unknown to terminal: {mt5.last_error()}")
    pad = dt.timedelta(days=1)
    rates = mt5.copy_rates_range(broker, getattr(mt5, f"TIMEFRAME_{timeframe}"),
                                 (start_utc - pad).astimezone(UTC), (end_utc + pad).astimezone(UTC))
    if rates is None:
        raise CandleAdapterError(DATA_MISSING, f"{canonical}/{timeframe} ({broker}): {mt5.last_error()}")
    candles = [c for c in _to_canonical(canonical, rates) if start_utc <= c.time <= end_utc]
    _check_integrity(candles, timeframe)
    return candles


def _classify_gap(prev_open: dt.datetime, next_open: dt.datetime, step: dt.timedelta) -> str:
    missing_from = (prev_open + step).astimezone(NY)
    missing_to = next_open.astimezone(NY)
    if next_open - prev_open >= dt.timedelta(hours=24) and missing_from.weekday() in (4, 5, 6):
        return "WEEKEND_CLOSE"
    # A short gap whose missing bars include the 17:00 New York rollover hour
    # (FX dealing break; XAUUSD 17:00-18:00 NY).
    if missing_to - missing_from <= dt.timedelta(hours=2):
        t = missing_from
        while t < missing_to:
            if t.hour == 17:
                return "DAILY_BREAK"
            t += step
    return "INTRADAY_GAP"


def series_report(candles: List[CanonicalCandle], timeframe: str) -> Dict[str, Any]:
    """Integrity summary; reports gaps, never fills them."""
    step = dt.timedelta(minutes=TIMEFRAME_MINUTES[timeframe])
    gaps = []
    duplicates = 0
    non_monotonic = 0
    for a, b in zip(candles, candles[1:]):
        delta = b.time - a.time
        if delta == dt.timedelta(0):
            duplicates += 1
        elif delta < dt.timedelta(0):
            non_monotonic += 1
        elif delta > step:
            gaps.append({"after": a.time.isoformat(), "next": b.time.isoformat(),
                         "missing_bars": int(delta / step) - 1, "kind": _classify_gap(a.time, b.time, step)})
    return {
        "rows": len(candles),
        "first": candles[0].time.isoformat() if candles else None,
        "last": candles[-1].time.isoformat() if candles else None,
        "duplicates": duplicates,
        "non_monotonic": non_monotonic,
        "gaps": gaps,
        "unexpected_gaps": sum(1 for g in gaps if g["kind"] == "INTRADAY_GAP"),
        "utc_aware": all(c.time.tzinfo is not None and c.time.utcoffset() == dt.timedelta(0) for c in candles),
    }


def to_engine_candles(candles: List[CanonicalCandle]) -> List[Candle]:
    return [c.to_engine_candle() for c in candles]


def as_rows(candles: List[CanonicalCandle]) -> List[Dict[str, Any]]:
    """JSON-safe canonical rows (time as ISO-8601 UTC)."""
    return [{f: (getattr(c, f).isoformat() if f == "time" else getattr(c, f)) for f in CANONICAL_FIELDS}
            for c in candles]


def symbol_map_status(symbols=SUPPORTED_SYMBOLS):
    """(mapped, blocked): canonical -> broker for every resolvable entry of the versioned
    CANONICAL_TO_BROKER_MAP, and canonical -> reason for each UNMAPPED / DATA_ERROR entry.
    One bad entry blocks only its own symbol."""
    symbol_map = canonical_broker_map.load_map()
    mapped: Dict[str, str] = {}
    blocked: Dict[str, str] = {}
    for canonical in symbols:
        try:
            mapped[canonical] = symbol_map.resolve(canonical)
        except (canonical_broker_map.SymbolUnmapped, canonical_broker_map.SymbolDataError) as exc:
            blocked[canonical] = str(exc)
    return mapped, blocked


def default_symbol_map() -> Dict[str, str]:
    """Resolvable entries of the versioned CANONICAL_TO_BROKER_MAP for SUPPORTED_SYMBOLS. An
    UNMAPPED or DATA_ERROR canonical is absent, so resolve_broker_symbol() raises
    SYMBOL_MAPPING_MISSING for that symbol only."""
    return symbol_map_status()[0]


def fetch_closed_candles_per_symbol(mt5: Any, symbols, timeframe: str, count: int,
                                    symbol_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """fetch_closed_candles for each symbol independently. A failing symbol gets
    {"status": DATA_ERROR, "code", "detail"}; the others still return {"status": "OK", "candles"}."""
    out: Dict[str, Dict[str, Any]] = {}
    for canonical in symbols:
        try:
            out[canonical] = {"status": "OK",
                              "candles": fetch_closed_candles(mt5, canonical, timeframe, count, symbol_map)}
        except CandleAdapterError as exc:
            out[canonical] = {"status": DATA_ERROR, "code": exc.code, "detail": exc.detail}
    return out


__all__ = [
    "ALLOWED_MT5_CALLS", "CANONICAL_FIELDS", "CandleAdapterError", "CanonicalCandle", "DATA_ERROR", "SUPPORTED_SYMBOLS",
    "SYMBOL_MAPPING_MISSING", "TIMEFRAME_MINUTES", "as_rows", "default_symbol_map", "fetch_candles_range",
    "fetch_closed_candles", "fetch_closed_candles_per_symbol", "load_symbol_map", "resolve_broker_symbol", "series_report", "symbol_map_status", "to_engine_candles",
]
