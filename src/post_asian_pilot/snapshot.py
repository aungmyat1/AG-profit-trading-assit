"""AsianSessionSnapshot: an immutable, identity/provenance-carrying wrapper around
strategy_engine.session.build_reference_box(), plus the candle-array integrity check
(exact count, no gaps/duplicates, monotonic, no forming candle) that neither
build_reference_box nor session_clock validates on their own -- build_reference_box only
checks bar_count >= expected_bar_count (session_complete), trusting the caller for
everything else (see its own docstring). This module is the one place that trust is
actually verified, so a bad candle array fails closed as DATA_ERROR instead of silently
producing a box.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional, Sequence, Tuple

from strategy_engine.session import Candle, ReferenceBox, build_reference_box

from .fingerprint import fingerprint

DATA_QUALITY_OK = "OK"
DATA_QUALITY_INVALID = "INVALID"


@dataclass(frozen=True)
class AsianSessionSnapshot:
    snapshot_id: str
    strategy_id: str
    symbol: str
    trading_date: date
    session_name: str
    start_utc: datetime
    end_utc: datetime

    open: float
    high: float
    low: float
    close: float
    midpoint: float
    range: float

    high_time: datetime
    low_time: datetime

    bar_count: int
    expected_bar_count: int

    source_fingerprint: str
    data_quality: str
    created_at_utc: datetime

    box: ReferenceBox


@dataclass(frozen=True)
class SnapshotResult:
    status: str  # "VALID" or "DATA_ERROR"
    snapshot: Optional[AsianSessionSnapshot]
    reason_codes: Tuple[str, ...]


def validate_candle_array(
    candles: Sequence[Candle], expected_bar_count: int, timeframe_minutes: int = 15,
    as_of: Optional[datetime] = None,
) -> Tuple[str, ...]:
    """Returns an empty tuple if the array is a clean, complete, closed-bar series;
    otherwise a tuple of reason codes for every distinct problem found."""
    reasons = []

    if len(candles) != expected_bar_count:
        reasons.append(f"BAR_COUNT_MISMATCH_EXPECTED_{expected_bar_count}_GOT_{len(candles)}")

    times = [c.time for c in candles]
    if len(set(times)) != len(times):
        reasons.append("DUPLICATE_BAR_TIME")

    if times == sorted(times) and len(set(times)) == len(times):
        for prev, cur in zip(times, times[1:]):
            if (cur - prev) != timedelta(minutes=timeframe_minutes):
                reasons.append("BAR_GAP_OR_OVERLAP")
                break
    else:
        reasons.append("OUT_OF_ORDER_BARS")

    if as_of is not None and times:
        last_bar_close = times[-1] + timedelta(minutes=timeframe_minutes)
        if last_bar_close > as_of:
            reasons.append("FORMING_CANDLE_INCLUDED")

    return tuple(reasons)


def _snapshot_id(strategy_id: str, symbol: str, trading_date: date, session_name: str) -> str:
    import hashlib
    digest = hashlib.blake2b(
        f"{strategy_id}|{symbol}|{trading_date.isoformat()}|{session_name}".encode("utf-8"), digest_size=8,
    ).hexdigest()
    return f"SNAPSHOT-{symbol}-{trading_date.isoformat()}-{digest}"


def build_asian_session_snapshot(
    strategy_id: str, symbol: str, trading_date: date, session_name: str,
    start_utc: datetime, end_utc: datetime,
    candles: Sequence[Candle], expected_bar_count: int,
    as_of: datetime, created_at_utc: Optional[datetime] = None,
) -> SnapshotResult:
    reasons = validate_candle_array(candles, expected_bar_count, as_of=as_of)
    if reasons:
        return SnapshotResult(status="DATA_ERROR", snapshot=None, reason_codes=reasons)

    box = build_reference_box(session_name, candles, expected_bar_count)

    high_time = next(c.time for c in candles if c.high == box.session_high)
    low_time = next(c.time for c in candles if c.low == box.session_low)

    source_fingerprint = fingerprint([[c.time.isoformat(), c.open, c.high, c.low, c.close] for c in candles])

    snapshot = AsianSessionSnapshot(
        snapshot_id=_snapshot_id(strategy_id, symbol, trading_date, session_name),
        strategy_id=strategy_id, symbol=symbol, trading_date=trading_date, session_name=session_name,
        start_utc=start_utc, end_utc=end_utc,
        open=box.session_open, high=box.session_high, low=box.session_low, close=box.session_close,
        midpoint=box.session_mid, range=box.session_range,
        high_time=high_time, low_time=low_time,
        bar_count=box.bar_count, expected_bar_count=expected_bar_count,
        source_fingerprint=source_fingerprint, data_quality=DATA_QUALITY_OK,
        created_at_utc=created_at_utc or datetime.now(timezone.utc),
        box=box,
    )
    return SnapshotResult(status="VALID", snapshot=snapshot, reason_codes=())
