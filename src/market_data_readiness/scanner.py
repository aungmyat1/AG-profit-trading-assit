"""Read-only, streaming discovery/fingerprint/quality scanner for FX historical CSV
candidates (D:\\ authorized source files, per owner blanket authorization "you can use
market data on D:, when you need" -- 2026-09-10).

Design constraints (see AG_ST_SESSION_SWEEP_CONTINUATION_DATA_READINESS spec):
  - NEVER open a source file in write mode; NEVER load a whole file into memory.
  - Reuse this repo's existing MT5 weekend-reopen-gap UTC offset technique
    (src/mt5/broker_time.py: us_eastern_utc_offset_hours / ny_1700_reopen_instant_utc /
    offset_from_reopen) instead of reinventing timezone detection -- same convention
    src/session_tribranch_research/data_loader.py already uses for the one
    owner-approved EURUSD M5 dataset.
  - Never append "Z" to a naive timestamp without a resolved offset -- UNRESOLVED
    timezone status must be reported honestly, never silently assumed UTC.
  - inventory[symbol][timeframe] = [candidates...] -- always a list, never overwritten.
  - Pipeline order: DISCOVER -> PARSE -> HASH -> VALIDATE_TIMEFRAME -> VALIDATE_TIMEZONE
    -> QUALITY_CHECK -> DETECT_OVERLAP -> SELECT/COMPOSE -> COMMON_COVERAGE -> READINESS.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from mt5.broker_time import BrokerTimeError, offset_from_reopen

MIN_WEEKEND_GAP = timedelta(hours=40)

FILENAME_RE = re.compile(
    r"^(?P<symbol>[A-Z]{6})_(?:(?P<tf>Daily|H1|M15|M5|M1)_)?(?P<start>\d{12,17})_(?P<end>\d{12,17})\.csv$",
    re.IGNORECASE,
)

_SPACING_SECONDS_TO_TIMEFRAME = {60: "M1", 300: "M5", 900: "M15", 3600: "H1"}


@dataclass
class ScanResult:
    path: str
    filename: str
    symbol: str
    declared_timeframe: str
    file_size_bytes: int
    sha256: Optional[str] = None
    row_count: int = 0
    parse_failures: int = 0
    first_ts_raw: Optional[str] = None
    last_ts_raw: Optional[str] = None
    duplicate_timestamps: int = 0
    nonmonotonic_timestamps: int = 0
    ohlc_violations: int = 0
    zero_or_negative_price_rows: int = 0
    largest_gap_hours: float = 0.0
    largest_gap_reopen_ts_raw: Optional[str] = None
    observed_spacing_seconds: Optional[int] = None
    observed_timeframe: Optional[str] = None
    timeframe_status: str = "UNKNOWN"
    is_bidask: bool = False
    broker_utc_offset_hours: Optional[int] = None
    timezone_status: str = "UNRESOLVED"
    first_ts_utc: Optional[str] = None
    last_ts_utc: Optional[str] = None
    quality_status: str = "NOT_EVALUATED"
    errors: List[str] = field(default_factory=list)


def classify_filename(path: str) -> Optional[Dict[str, str]]:
    base = os.path.basename(path)
    m = FILENAME_RE.match(base)
    if not m:
        return None
    return {
        "symbol": m.group("symbol").upper(),
        "declared_tf": (m.group("tf") or "UNKNOWN_TICK").upper(),
        "filename": base,
    }


def sha256_stream(path: str, chunk_size: int = 1024 * 1024) -> str:
    """Streaming SHA-256 -- reads in fixed-size chunks, opened strictly read-only ("rb"),
    never loads the file whole. Safe for multi-GB tick files."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_file(path: str, meta: Dict[str, str]) -> ScanResult:
    """Single streaming pass over the CSV: parses rows, computes quality/timezone/
    timeframe signals with O(1) memory beyond small running counters (no full timestamp
    list retained) so it is safe against multi-GB tick exports."""
    size = os.path.getsize(path)
    result = ScanResult(
        path=path, filename=meta["filename"], symbol=meta["symbol"],
        declared_timeframe=meta["declared_tf"], file_size_bytes=size,
    )
    is_tick = meta["declared_tf"] == "UNKNOWN_TICK"

    prev_t = None
    first_t = None
    last_t = None
    row_count = 0
    parse_failures = 0
    dup_count = 0
    nonmonotonic_count = 0
    ohlc_violations = 0
    zero_neg = 0
    largest_gap = timedelta(0)
    largest_gap_end = None
    spacing_counter: Dict[int, int] = {}
    is_bidask = False

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        reader = csv.reader(fh, delimiter="\t")
        try:
            header = next(reader)
        except StopIteration:
            header = []
        is_bidask = "<BID>" in header or "<ASK>" in header

        for row in reader:
            if not row or len(row) < 2:
                continue
            try:
                if is_bidask:
                    t = datetime.strptime(f"{row[0]} {row[1]}", "%Y.%m.%d %H:%M:%S.%f")
                    bid = float(row[2]) if len(row) > 2 and row[2] not in ("", None) else None
                    ask = float(row[3]) if len(row) > 3 and row[3] not in ("", None) else None
                    if (bid is not None and bid <= 0) or (ask is not None and ask <= 0):
                        zero_neg += 1
                elif meta["declared_tf"] == "DAILY":
                    t = datetime.strptime(row[0], "%Y.%m.%d")
                    o, hi, lo, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
                    if hi < lo or o > hi or o < lo or c > hi or c < lo:
                        ohlc_violations += 1
                    if min(o, hi, lo, c) <= 0:
                        zero_neg += 1
                else:
                    t = datetime.strptime(f"{row[0]} {row[1]}", "%Y.%m.%d %H:%M:%S")
                    o, hi, lo, c = float(row[2]), float(row[3]), float(row[4]), float(row[5])
                    if hi < lo or o > hi or o < lo or c > hi or c < lo:
                        ohlc_violations += 1
                    if min(o, hi, lo, c) <= 0:
                        zero_neg += 1
            except (ValueError, IndexError):
                parse_failures += 1
                continue

            row_count += 1
            if first_t is None:
                first_t = t
            last_t = t

            if prev_t is not None:
                if t == prev_t:
                    dup_count += 1
                elif t < prev_t:
                    nonmonotonic_count += 1
                else:
                    gap = t - prev_t
                    if gap >= largest_gap:  # ties: most-recent wins (matches broker_time._largest_gap)
                        largest_gap = gap
                        largest_gap_end = t
                    if not is_tick:
                        secs = int(gap.total_seconds())
                        spacing_counter[secs] = spacing_counter.get(secs, 0) + 1
            prev_t = t

    observed_seconds = max(spacing_counter.items(), key=lambda kv: kv[1])[0] if spacing_counter else None
    observed_tf = _SPACING_SECONDS_TO_TIMEFRAME.get(observed_seconds)
    if meta["declared_tf"] == "DAILY":
        observed_tf = "DAILY"
    if is_tick:
        observed_tf = "TICK"

    tz_status = "UNRESOLVED"
    offset_hours = None
    if largest_gap >= MIN_WEEKEND_GAP and largest_gap_end is not None:
        try:
            offset_hours = offset_from_reopen(largest_gap_end)
        except BrokerTimeError:
            # The largest gap looked weekend-sized but did not resolve to a whole-hour
            # offset near the true NY 17:00 reopen instant -- fail closed rather than
            # guessing. This can genuinely happen (e.g. the gap found is a data outage,
            # not the weekly reopen, or straddles a source-file splice boundary).
            offset_hours = None
        if offset_hours is not None:
            tz_status = "BROKER_OFFSET_CONFIRMED"

    result.row_count = row_count
    result.parse_failures = parse_failures
    result.first_ts_raw = first_t.isoformat() if first_t else None
    result.last_ts_raw = last_t.isoformat() if last_t else None
    result.duplicate_timestamps = dup_count
    result.nonmonotonic_timestamps = nonmonotonic_count
    result.ohlc_violations = ohlc_violations
    result.zero_or_negative_price_rows = zero_neg
    result.largest_gap_hours = round(largest_gap.total_seconds() / 3600, 2)
    result.largest_gap_reopen_ts_raw = largest_gap_end.isoformat() if largest_gap_end else None
    result.observed_spacing_seconds = observed_seconds
    result.observed_timeframe = observed_tf
    result.timeframe_status = (
        "CONFLICT" if (observed_tf and meta["declared_tf"] not in (observed_tf, "UNKNOWN_TICK")) else "MATCH"
    )
    result.is_bidask = is_bidask
    result.broker_utc_offset_hours = offset_hours
    result.timezone_status = tz_status
    if offset_hours is not None and first_t and last_t:
        result.first_ts_utc = (first_t - timedelta(hours=offset_hours)).isoformat() + "+00:00"
        result.last_ts_utc = (last_t - timedelta(hours=offset_hours)).isoformat() + "+00:00"

    quality_fail = (
        result.ohlc_violations > 0 or result.zero_or_negative_price_rows > 0
        or result.nonmonotonic_timestamps > 0 or result.parse_failures > 0
    )
    if row_count == 0:
        result.quality_status = "FAIL"
    elif quality_fail:
        result.quality_status = "PARTIAL"
    else:
        result.quality_status = "PASS"

    return result


def discover_candidates(root: str, symbols: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """DISCOVER step: targeted filename glob under `root` for each symbol (never an
    unbounded recursive drive scan). Returns raw path lists keyed by symbol only --
    timeframe classification happens per-file in scan_file (declared_timeframe may be
    UNKNOWN_TICK for a bid/ask tick export with no timeframe token in its filename)."""
    import glob

    found: Dict[str, List[str]] = {s: [] for s in symbols}
    seen_paths = set()
    for symbol in symbols:
        for f in glob.glob(os.path.join(root, f"{symbol}*.csv")):
            resolved = os.path.abspath(f)
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            found[symbol].append(resolved)
    return found


def build_inventory(root: str, symbols: List[str]) -> Dict[str, Dict[str, List[ScanResult]]]:
    """Full DISCOVER->PARSE->HASH->VALIDATE_TIMEFRAME->VALIDATE_TIMEZONE->QUALITY_CHECK
    pipeline. Returns inventory[symbol][declared_timeframe] = [ScanResult, ...] --
    always a list, multiple candidates for the same symbol+timeframe are preserved
    side-by-side, never overwritten."""
    raw = discover_candidates(root, symbols)
    inventory: Dict[str, Dict[str, List[ScanResult]]] = {}
    for symbol, paths in raw.items():
        for path in sorted(paths):
            meta = classify_filename(path)
            if meta is None:
                continue
            rec = scan_file(path, meta)
            rec.sha256 = sha256_stream(path)
            inventory.setdefault(symbol, {}).setdefault(meta["declared_tf"], []).append(rec)
    return inventory


def classify_overlap(a: ScanResult, b: ScanResult) -> str:
    """DETECT_OVERLAP step for two candidates of the same symbol+timeframe. Uses raw
    (pre-UTC) start/end since both share the same declared timeframe/source convention;
    a genuine cross-timezone comparison must first resolve both to UTC (VALIDATE_TIMEZONE
    is expected to have already run before this is called for economic-replay purposes)."""
    if not (a.first_ts_raw and a.last_ts_raw and b.first_ts_raw and b.last_ts_raw):
        return "UNKNOWN"
    a0, a1 = a.first_ts_raw, a.last_ts_raw
    b0, b1 = b.first_ts_raw, b.last_ts_raw
    if a.sha256 and a.sha256 == b.sha256:
        return "DUPLICATE"
    if a1 < b0 or b1 < a0:
        return "DISJOINT_CONTIGUOUS"
    if a0 == b0 and a1 == b1:
        return "OVERLAPPING_IDENTICAL"
    return "OVERLAPPING_CONFLICTING"
