"""RAW_PROSPECTIVE_ARCHIVE_V1 partition QA -- mission P9 items 7, 8, 9.

Uses injected fake candle/tick/connect functions (no real MT5 terminal
required, no live_mt5 marker needed) to prove: hash-bound partitions, gap and
duplicate detection, and immutability of a COMPLETE partition.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from data_archive.raw_prospective_archive import (
    ArchiveDataError,
    ArchiveImmutabilityError,
    collect_daily_partition,
)
from mt5.market_data import Tick
from strategy_engine.session import Candle

DAY = date(2026, 9, 15)  # a Tuesday: no weekend gap to worry about


def _make_h1_candles(day: date, count: int = 24, skip_hour: int | None = None) -> list[Candle]:
    candles = []
    base = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    for hour in range(count):
        if skip_hour is not None and hour == skip_hour:
            continue
        t = base + timedelta(hours=hour)
        price = 1.1000 + hour * 0.0001
        candles.append(Candle(time=t, open=price, high=price + 0.0002, low=price - 0.0002, close=price + 0.0001, volume=100.0))
    return candles


def _fake_connect() -> None:
    return None


def _fake_tick(symbol: str) -> Tick:
    return Tick(symbol=symbol, time_utc=datetime.now(timezone.utc), bid=1.1000, ask=1.1002, spread_points=2)


def test_partition_is_hash_bound_and_row_accurate(tmp_path: Path) -> None:
    h1 = _make_h1_candles(DAY)

    def fake_candles(symbol: str, timeframe: str, count: int) -> list[Candle]:
        return h1 if timeframe == "H1" else _make_h1_candles(DAY, count=24)

    results = collect_daily_partition(
        DAY, timeframes=("H1",), archive_root=tmp_path,
        connect_fn=_fake_connect, candles_fn=fake_candles, tick_fn=_fake_tick,
    )
    result = results[0]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))

    assert manifest["row_count"] == 24
    assert manifest["status"] == "COMPLETE"
    assert manifest["gap_count"] == 0
    assert manifest["duplicate_count"] == 0
    assert manifest["monotonic"] is True
    assert manifest["ohlc_valid"] is True

    raw_text = result.jsonl_path.read_text(encoding="utf-8")
    import hashlib
    assert manifest["sha256"] == hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    assert len([line for line in raw_text.splitlines() if line.strip()]) == 24


def test_partition_detects_gap(tmp_path: Path) -> None:
    h1_with_gap = _make_h1_candles(DAY, skip_hour=12)

    def fake_candles(symbol: str, timeframe: str, count: int) -> list[Candle]:
        return h1_with_gap

    results = collect_daily_partition(
        DAY, timeframes=("H1",), archive_root=tmp_path,
        connect_fn=_fake_connect, candles_fn=fake_candles, tick_fn=_fake_tick,
    )
    manifest = json.loads(results[0].manifest_path.read_text(encoding="utf-8"))
    assert manifest["row_count"] == 23
    assert manifest["gap_count"] == 1
    assert manifest["gaps"][0]["missing_seconds"] == 3600.0


def test_partition_detects_duplicate_timestamp(tmp_path: Path) -> None:
    h1 = _make_h1_candles(DAY, count=5)
    duplicated = h1 + [h1[-1]]  # append a duplicate final bar (still non-decreasing, so it slips past monotonic-strict check)

    def fake_candles(symbol: str, timeframe: str, count: int) -> list[Candle]:
        return duplicated

    results = collect_daily_partition(
        DAY, timeframes=("H1",), archive_root=tmp_path,
        connect_fn=_fake_connect, candles_fn=fake_candles, tick_fn=_fake_tick,
    )
    manifest = json.loads(results[0].manifest_path.read_text(encoding="utf-8"))
    assert manifest["duplicate_count"] == 1
    assert manifest["monotonic"] is False


def test_completed_partition_is_immutable(tmp_path: Path) -> None:
    h1 = _make_h1_candles(DAY)

    def fake_candles(symbol: str, timeframe: str, count: int) -> list[Candle]:
        return h1

    collect_daily_partition(
        DAY, timeframes=("H1",), archive_root=tmp_path,
        connect_fn=_fake_connect, candles_fn=fake_candles, tick_fn=_fake_tick,
    )
    with pytest.raises(ArchiveImmutabilityError):
        collect_daily_partition(
            DAY, timeframes=("H1",), archive_root=tmp_path,
            connect_fn=_fake_connect, candles_fn=fake_candles, tick_fn=_fake_tick,
        )


def test_no_data_for_day_raises_instead_of_fabricating(tmp_path: Path) -> None:
    def empty_candles(symbol: str, timeframe: str, count: int) -> list[Candle]:
        return []

    with pytest.raises(ArchiveDataError):
        collect_daily_partition(
            DAY, timeframes=("H1",), archive_root=tmp_path,
            connect_fn=_fake_connect, candles_fn=empty_candles, tick_fn=_fake_tick,
        )
