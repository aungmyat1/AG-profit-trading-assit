"""Ingestion adapter: MetaTrader "Export" CSV -> HistoricalCandleStore (historical-
validation spec sections 7-10 of the continuation task). The smallest adapter needed --
no second candle-store abstraction; this module's only job is parse -> validate ->
normalize -> hand rows to HistoricalCandleStore.load_series.

TIMEZONE (spec section 9: never assume from filename): MT5's own "Export" CSV, like the
live `copy_rates_*` API, reports timestamps in the broker's OWN wall clock, not UTC --
confirmed empirically here, not assumed, by reusing the project's existing weekly-
reopen-gap technique (mt5.broker_time.offset_from_reopen, already relied on for live
data). A single fixed offset is NOT safe: real broker feeds observe seasonal DST
(verified on the actual EURUSD M5 export this phase loaded: offset alternates +2/+3
across the 15-month range), so this loader detects the offset independently for every
weekly segment rather than assuming one constant for the whole file.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

from mt5.broker_time import BrokerTimeError, offset_from_reopen
from strategy_engine.session import Candle

from .candle_store import TIMEFRAME_MINUTES, HistoricalDataError

MIN_WEEKEND_GAP = timedelta(hours=40)  # same threshold as mt5.broker_time._largest_gap


class IngestionError(HistoricalDataError):
    pass


@dataclass(frozen=True)
class GapReport:
    before: datetime  # broker-time timestamp of the last bar before the gap
    after: datetime  # broker-time timestamp of the first bar after the gap
    duration: timedelta
    classification: str  # EXPECTED_MARKET_CLOSURE / UNEXPECTED_DATA_GAP


@dataclass(frozen=True)
class IngestionReport:
    symbol: str
    timeframe: str
    rows: int
    start_utc: datetime
    end_utc: datetime
    source_timezone: str
    normalized_timezone: str = "UTC"
    gaps: Tuple[GapReport, ...] = field(default_factory=tuple)
    # Broker wall-clock timestamp for each returned candle, same order/length as the
    # candles list `load_mt5_export_csv` returns. MT5's own D1/H4 candles are anchored
    # to the BROKER's calendar day/4h window, not UTC (confirmed empirically: cross-
    # checking a UTC-midnight-bucketed derived D1 against a native MT5 D1 export showed
    # every single bar mismatched, because the broker's UTC offset -- +2/+3 seasonal --
    # does not divide evenly into a day). `resampler.resample_broker_aligned` needs
    # these to bucket D1/H4 correctly; ordinary UTC-boundary `resample` remains correct
    # for M15/H1 (whole-hour offsets preserve hour boundaries).
    broker_times: Tuple[datetime, ...] = field(default_factory=tuple)

    @property
    def unexpected_gaps(self) -> Tuple[GapReport, ...]:
        return tuple(g for g in self.gaps if g.classification == "UNEXPECTED_DATA_GAP")


def _parse_rows(path: str) -> List[Tuple[datetime, float, float, float, float, float]]:
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader)
        if not any(h.strip("<>").upper() == "OPEN" for h in header):
            raise IngestionError("UNSUPPORTED_FORMAT", f"{path}: expected MT5 OHLC export header, got {header}")
        rows = []
        for r in reader:
            if len(r) < 6:
                continue
            date_s, time_s, o, h, l, c = r[0], r[1], r[2], r[3], r[4], r[5]
            tv = float(r[6]) if len(r) > 6 and r[6] else None
            ts = datetime.strptime(f"{date_s} {time_s}", "%Y.%m.%d %H:%M:%S")
            rows.append((ts, float(o), float(h), float(l), float(c), tv))
    return rows


def _find_all_gaps(times: List[datetime]) -> List[Tuple[timedelta, int]]:
    """Every consecutive-pair delta, unfiltered -- used only to locate the weekly
    reopen (the single largest recurring gap), not for anomaly reporting."""
    return [(times[i + 1] - times[i], i + 1) for i in range(len(times) - 1)]


def _find_anomalous_gaps(times: List[datetime], native_interval: timedelta) -> List[Tuple[timedelta, int]]:
    """Only deltas that differ from the timeframe's own native bar spacing -- i.e.
    actual gaps, not every ordinary consecutive bar."""
    return [(times[i + 1] - times[i], i + 1) for i in range(len(times) - 1)
            if (times[i + 1] - times[i]) != native_interval]


def _offset_segments(times: List[datetime]) -> List[Tuple[datetime, int]]:
    """Returns [(segment_start_broker_time, utc_offset_hours), ...] ascending by start.
    Each segment runs from its start up to (not including) the next segment's start.
    One segment per weekly-reopen boundary found via the weekend gap; the leading
    partial segment (before the first reopen in the file) inherits the first detected
    offset (no DST change is assumed within an unobserved leading partial week)."""
    weekend_gaps = [(g, idx) for g, idx in _find_all_gaps(times) if g >= MIN_WEEKEND_GAP]
    if not weekend_gaps:
        raise IngestionError("NO_WEEKEND_GAP_FOUND",
                              "cannot determine broker UTC offset: no weekly reopen gap found in this file")

    segments: List[Tuple[datetime, int]] = []
    for _, idx in weekend_gaps:
        reopen_time = times[idx]
        try:
            offset = offset_from_reopen(reopen_time)
        except BrokerTimeError as exc:
            raise IngestionError("OFFSET_FROM_REOPEN_AMBIGUOUS", str(exc)) from exc
        segments.append((reopen_time, offset))

    segments.sort(key=lambda s: s[0])
    # Leading partial segment: same offset as the first reopen found.
    return [(times[0], segments[0][1])] + segments


def _offset_for(ts: datetime, segments: List[Tuple[datetime, int]]) -> int:
    offset = segments[0][1]
    for seg_start, seg_offset in segments:
        if ts >= seg_start:
            offset = seg_offset
        else:
            break
    return offset


def load_mt5_export_csv(path: str, symbol: str, timeframe: str) -> Tuple[List[Candle], IngestionReport]:
    """Parses, validates, and UTC-normalizes an MT5-export OHLC CSV. Raises
    IngestionError on any data-quality violation that would silently corrupt replay
    (non-monotonic/duplicate timestamps, invalid OHLC) -- never repairs data (spec
    section 8: 'do not automatically fill missing candles')."""
    if timeframe not in TIMEFRAME_MINUTES:
        raise IngestionError("UNSUPPORTED_TIMEFRAME", f"{timeframe!r} not in {list(TIMEFRAME_MINUTES)}")
    native_interval = timedelta(minutes=TIMEFRAME_MINUTES[timeframe])

    rows = _parse_rows(path)
    if len(rows) < 2:
        raise IngestionError("INSUFFICIENT_ROWS", f"{path}: only {len(rows)} rows")

    broker_times = [r[0] for r in rows]
    for a, b in zip(broker_times, broker_times[1:]):
        if b <= a:
            raise IngestionError("DUPLICATE_OR_UNORDERED_TIMESTAMP", f"{path}: {a} -> {b} not strictly increasing")
    for ts, o, h, l, c, _tv in rows:
        if not (h >= max(o, c) and l <= min(o, c) and h >= l):
            raise IngestionError("INVALID_OHLC", f"{path}: {ts} open={o} high={h} low={l} close={c}")

    segments = _offset_segments(broker_times)
    distinct_offsets = sorted({offset for _, offset in segments})
    source_tz_label = "BROKER_SERVER_TIME(" + "/".join(f"UTC+{off}" for off in distinct_offsets) + " seasonal DST)"

    candles = []
    for ts, o, h, l, c, tv in rows:
        offset = _offset_for(ts, segments)
        utc_time = (ts - timedelta(hours=offset)).replace(tzinfo=timezone.utc)
        candles.append(Candle(time=utc_time, open=o, high=h, low=l, close=c, volume=tv))

    gap_reports = []
    for gap, idx in _find_anomalous_gaps(broker_times, native_interval):
        classification = "EXPECTED_MARKET_CLOSURE" if gap >= MIN_WEEKEND_GAP else "UNEXPECTED_DATA_GAP"
        gap_reports.append(GapReport(before=broker_times[idx - 1], after=broker_times[idx],
                                      duration=gap, classification=classification))

    report = IngestionReport(
        symbol=symbol, timeframe=timeframe, rows=len(candles),
        start_utc=candles[0].time, end_utc=candles[-1].time,
        source_timezone=source_tz_label, gaps=tuple(gap_reports),
        broker_times=tuple(broker_times),
    )
    return candles, report
