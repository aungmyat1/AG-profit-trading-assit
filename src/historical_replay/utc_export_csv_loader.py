"""Ingestion adapter: already-UTC MetaTrader5-Python-direct CSV export (comma-delimited,
`timestamp_utc` column) -> Candle list + IngestionReport.

Distinct from `mt5_export_loader.load_mt5_export_csv` (tab-delimited, broker-local-time
"Export" menu format requiring weekend-gap offset detection) -- this is a genuinely
different file produced by a different pull mechanism: `MetaTrader5.copy_rates_range`
(the Python package), which returns UTC epoch seconds directly, already persisted as UTC
with no transformation (see artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/
FRESH_DATA_ADMISSION/*_ADMISSION.json `timezone_note`). No offset detection is needed or
performed here. Reuses IngestionReport/GapReport from mt5_export_loader (import, not a
new type) so downstream code (symbol_metadata_manifest, h1_bias) sees an identical shape.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from strategy_engine.session.candles import Candle

from .candle_store import TIMEFRAME_MINUTES
from .mt5_export_loader import MIN_WEEKEND_GAP, GapReport, IngestionError, IngestionReport


def load_utc_export_csv(path: str, symbol: str, timeframe: str) -> Tuple[List[Candle], IngestionReport]:
    """Parses, validates (strictly-increasing timestamps, valid OHLC), and returns UTC
    candles from a `timestamp_utc,open,high,low,close,...` CSV. Never repairs data --
    raises IngestionError on any quality violation, matching mt5_export_loader's own
    fail-closed contract."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise IngestionError("UNSUPPORTED_TIMEFRAME", f"{timeframe!r} not in {list(TIMEFRAME_MINUTES)}")
    native_interval = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])

    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "timestamp_utc" not in reader.fieldnames:
            raise IngestionError("UNSUPPORTED_FORMAT", f"{path}: expected timestamp_utc header, got {reader.fieldnames}")
        rows = []
        for r in reader:
            ts = datetime.strptime(r["timestamp_utc"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
            tv = float(r["tick_volume"]) if r.get("tick_volume") not in (None, "") else None
            rows.append((ts, o, h, l, c, tv))

    if len(rows) < 2:
        raise IngestionError("INSUFFICIENT_ROWS", f"{path}: only {len(rows)} rows")

    times = [r[0] for r in rows]
    for a, b in zip(times, times[1:]):
        if b <= a:
            raise IngestionError("DUPLICATE_OR_UNORDERED_TIMESTAMP", f"{path}: {a} -> {b} not strictly increasing")
    for ts, o, h, l, c, _tv in rows:
        if not (h >= max(o, c) and l <= min(o, c) and h >= l):
            raise IngestionError("INVALID_OHLC", f"{path}: {ts} open={o} high={h} low={l} close={c}")

    candles = [Candle(time=ts, open=o, high=h, low=l, close=c, volume=tv) for ts, o, h, l, c, tv in rows]

    gap_reports = []
    for i in range(1, len(times)):
        gap = times[i] - times[i - 1]
        if gap != native_interval:
            classification = "EXPECTED_MARKET_CLOSURE" if gap >= MIN_WEEKEND_GAP else "UNEXPECTED_DATA_GAP"
            gap_reports.append(GapReport(before=times[i - 1], after=times[i], duration=gap, classification=classification))

    report = IngestionReport(
        symbol=symbol, timeframe=timeframe, rows=len(candles),
        start_utc=candles[0].time, end_utc=candles[-1].time,
        source_timezone="UTC (MetaTrader5 Python copy_rates_* native, no transformation)",
        gaps=tuple(gap_reports), broker_times=tuple(times),
    )
    return candles, report
