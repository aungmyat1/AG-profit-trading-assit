"""RAW_PROSPECTIVE_ARCHIVE_V1 -- daily read-only raw market-data collector.

Scope, deliberately narrow (see mission doc for the full boundary this module
must never cross):

  - Reads EURUSD H1/M15/M1 candles plus a single bid/ask/spread tick snapshot
    and broker/symbol identity, once per call, for the calendar day requested.
  - Writes each (symbol, timeframe, date) as its own immutable partition: a
    raw JSONL file of observations plus a QA manifest (hash, row count,
    first/last timestamp, gap/duplicate/monotonicity/OHLC checks).
  - Never overwrites a partition already marked COMPLETE.
  - Never computes a trade outcome, never replays a strategy, never writes to
    state/proposal_ledger or any validation-population artifact.

Every MT5 read goes through the two existing read-only wrappers this repo
already has (`mt5.connection`, `mt5.market_data`) plus two additional calls
to functions already on the mission's explicit allowlist that those wrappers
don't themselves expose a getter for (`terminal_info`, `symbol_info`) --
tests/test_raw_prospective_archive_safety.py statically proves this module
and its two reused wrappers never reach an order-mutating MT5 call.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import MetaTrader5 as mt5

from mt5.connection import connect as _mt5_connect
from mt5.market_data import Tick, get_latest_candles, get_tick
from strategy_engine.session import Candle

SYMBOL = "EURUSD"
TIMEFRAMES: Sequence[str] = ("H1", "M15", "M1")

# Generous enough to cover one UTC calendar day of closed bars per timeframe
# with headroom for the current in-progress bar excluded by get_latest_candles.
_CANDLES_PER_DAY = {"H1": 30, "M15": 110, "M1": 1550}
_BAR_SECONDS = {"H1": 3600, "M15": 900, "M1": 60}

ARCHIVE_NAMESPACE = "RAW_PROSPECTIVE_ARCHIVE_V1"
DEFAULT_ARCHIVE_ROOT = Path("artifacts") / "raw_prospective_archive" / ARCHIVE_NAMESPACE


class ArchiveImmutabilityError(RuntimeError):
    """Raised when a caller attempts to re-collect a partition already COMPLETE."""


class ArchiveDataError(RuntimeError):
    """Raised when MT5 returned no usable data for the requested day."""


@dataclass(frozen=True)
class PartitionManifest:
    archive_namespace: str
    data_role: str
    symbol: str
    timeframe: str
    partition_date: str
    row_count: int
    first_timestamp_utc: Optional[str]
    last_timestamp_utc: Optional[str]
    sha256: str
    timezone_authority: str
    gap_count: int
    gaps: List[dict]
    duplicate_count: int
    monotonic: bool
    ohlc_valid: bool
    broker_server: Optional[str]
    broker_company: Optional[str]
    symbol_metadata: dict
    regime_descriptors: dict
    status: str  # "COMPLETE" once written; this module never writes anything else


@dataclass(frozen=True)
class PartitionResult:
    timeframe: str
    jsonl_path: Path
    manifest_path: Path
    manifest: PartitionManifest


def _partition_paths(archive_root: Path, symbol: str, timeframe: str, day: date) -> tuple[Path, Path]:
    directory = archive_root / symbol / timeframe
    stem = day.isoformat()
    return directory / f"{stem}.jsonl", directory / f"{stem}.manifest.json"


def _canonical_dumps(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _candle_row(symbol: str, timeframe: str, candle: Candle) -> dict:
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "time_utc": candle.time.astimezone(timezone.utc).isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def _filter_to_day(candles: Sequence[Candle], day: date) -> List[Candle]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return [c for c in candles if start <= c.time <= end]


def _detect_gaps(candles: Sequence[Candle], expected_seconds: int) -> List[dict]:
    gaps: List[dict] = []
    for prev, cur in zip(candles, candles[1:]):
        delta = (cur.time - prev.time).total_seconds()
        if delta > expected_seconds:
            gaps.append({
                "after_utc": prev.time.isoformat(),
                "before_utc": cur.time.isoformat(),
                "missing_seconds": delta - expected_seconds,
            })
    return gaps


def _detect_duplicates(candles: Sequence[Candle]) -> int:
    seen = set()
    duplicates = 0
    for c in candles:
        if c.time in seen:
            duplicates += 1
        seen.add(c.time)
    return duplicates


def _is_monotonic(candles: Sequence[Candle]) -> bool:
    return all(a.time < b.time for a, b in zip(candles, candles[1:]))


def _is_ohlc_valid(candles: Sequence[Candle]) -> bool:
    for c in candles:
        if not (c.low <= c.open <= c.high and c.low <= c.close <= c.high and c.low <= c.high):
            return False
    return True


def _server_identity() -> tuple[Optional[str], Optional[str]]:
    """Broker/server identity via the allowlisted, already-read-only
    ``terminal_info`` -- deliberately not ``account_info`` (unneeded balance/
    login exposure) and not a new wrapper module."""
    info = mt5.terminal_info()
    if info is None:
        return None, None
    return getattr(info, "name", None), getattr(info, "company", None)


def _symbol_metadata(symbol: str) -> dict:
    """Broker symbol metadata via the allowlisted, already-read-only
    ``symbol_info``."""
    info = mt5.symbol_info(symbol)
    if info is None:
        return {}
    return {
        "digits": getattr(info, "digits", None),
        "point": getattr(info, "point", None),
        "trade_contract_size": getattr(info, "trade_contract_size", None),
        "currency_base": getattr(info, "currency_base", None),
        "currency_profit": getattr(info, "currency_profit", None),
        "spread_points": getattr(info, "spread", None),
    }


def _regime_descriptors(day: date, h1_candles: Sequence[Candle], tick: Optional[Tick]) -> dict:
    """Outcome-independent descriptors only -- see mission P6. Never used here
    or by any caller to select a favorable window; this module has no
    knowledge of any future DEV_003 and never will."""
    descriptors = {
        "calendar_date": day.isoformat(),
        "weekday": day.strftime("%A"),
    }
    if h1_candles:
        highs = [c.high for c in h1_candles]
        lows = [c.low for c in h1_candles]
        descriptors["day_high"] = max(highs)
        descriptors["day_low"] = min(lows)
        descriptors["day_range"] = max(highs) - min(lows)
    if tick is not None:
        descriptors["spread_points_snapshot"] = tick.spread_points
    return descriptors


def collect_daily_partition(
    day: date,
    symbol: str = SYMBOL,
    timeframes: Sequence[str] = TIMEFRAMES,
    archive_root: Path = DEFAULT_ARCHIVE_ROOT,
    connect_fn: Callable[[], None] = _mt5_connect,
    candles_fn: Callable[[str, str, int], List[Candle]] = get_latest_candles,
    tick_fn: Callable[[str], Tick] = get_tick,
) -> List[PartitionResult]:
    """Collect and immutably persist one calendar day's raw candles for every
    requested timeframe. Raises ArchiveImmutabilityError instead of
    overwriting any partition already COMPLETE -- callers must not catch that
    to force a rewrite; a genuinely corrected partition needs a new,
    explicitly reviewed archive contract, not a silent overwrite here."""
    connect_fn()

    broker_name, broker_company = _server_identity()
    symbol_metadata = _symbol_metadata(symbol)
    try:
        tick = tick_fn(symbol)
    except Exception:
        tick = None

    results: List[PartitionResult] = []
    h1_for_regime: List[Candle] = []
    for timeframe in timeframes:
        jsonl_path, manifest_path = _partition_paths(archive_root, symbol, timeframe, day)
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if existing.get("status") == "COMPLETE":
                raise ArchiveImmutabilityError(
                    f"{symbol} {timeframe} {day.isoformat()} already COMPLETE at {manifest_path}; "
                    "refusing to overwrite a completed raw partition"
                )

        raw_candles = candles_fn(symbol, timeframe, _CANDLES_PER_DAY[timeframe])
        day_candles = _filter_to_day(raw_candles, day)
        if not day_candles:
            raise ArchiveDataError(f"no {timeframe} candles for {symbol} on {day.isoformat()}")
        if timeframe == "H1":
            h1_for_regime = day_candles

        rows = [_candle_row(symbol, timeframe, c) for c in day_candles]
        jsonl_text = "\n".join(_canonical_dumps(r) for r in rows) + "\n"
        digest = hashlib.sha256(jsonl_text.encode("utf-8")).hexdigest()

        manifest = PartitionManifest(
            archive_namespace=ARCHIVE_NAMESPACE,
            data_role="RAW_PROSPECTIVE_OBSERVATION",
            symbol=symbol,
            timeframe=timeframe,
            partition_date=day.isoformat(),
            row_count=len(day_candles),
            first_timestamp_utc=day_candles[0].time.isoformat(),
            last_timestamp_utc=day_candles[-1].time.isoformat(),
            sha256=digest,
            timezone_authority="UTC",
            gap_count=len(_detect_gaps(day_candles, _BAR_SECONDS[timeframe])),
            gaps=_detect_gaps(day_candles, _BAR_SECONDS[timeframe]),
            duplicate_count=_detect_duplicates(day_candles),
            monotonic=_is_monotonic(day_candles),
            ohlc_valid=_is_ohlc_valid(day_candles),
            broker_server=broker_name,
            broker_company=broker_company,
            symbol_metadata=symbol_metadata,
            regime_descriptors=_regime_descriptors(day, h1_for_regime, tick),
            status="COMPLETE",
        )

        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_path.write_text(jsonl_text, encoding="utf-8")
        manifest_path.write_text(_canonical_dumps(asdict(manifest)), encoding="utf-8")

        results.append(PartitionResult(timeframe=timeframe, jsonl_path=jsonl_path, manifest_path=manifest_path, manifest=manifest))

    return results
