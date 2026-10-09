"""Deterministic, non-repairing quality gates for offline M5 research artifacts.

The gate classifies source quality only.  It never fills a missing price bar, sorts a
non-monotonic source, deduplicates rows, or otherwise changes the raw evidence.  UTC
normalization and timeframe construction happen only in separately lineaged derived
artifacts after this gate passes.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

from .ingestion import DerivedDataset, OhlcBar, RawDataset, build_derived_dataset, parse_utc_timestamp

M5_DELTA = timedelta(minutes=5)
BARS_PER_UTC_DAY = 288
QUALITY_GATE_ID = "OFFLINE_M5_QUALITY_GATE_V1"
UTC_NORMALIZATION_TRANSFORM_ID = "UTC_NORMALIZATION_V1"
RESAMPLE_TRANSFORM_IDS = {
    "M15": "UTC_RESAMPLE_M15_V1",
    "H1": "UTC_RESAMPLE_H1_V1",
    "D1": "UTC_RESAMPLE_D1_V1",
}
TIMEFRAME_MINUTES = {"M15": 15, "H1": 60, "D1": 1440}


@dataclass(frozen=True)
class QualityGateReport:
    dataset_id: str
    status: str                         # PASS | FAIL | INCONCLUSIVE
    checks: Mapping[str, str]
    reason_codes: Tuple[str, ...]
    coverage: Mapping[str, Any]
    complete_utc_days: Tuple[str, ...]
    usable_m5_rows: int
    derived_counts: Mapping[str, int]


def utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _complete_days(bars: Sequence[OhlcBar]) -> Tuple[date, ...]:
    by_day: Dict[date, list[OhlcBar]] = {}
    for bar in bars:
        by_day.setdefault(bar.time.date(), []).append(bar)
    complete = []
    for day, group in sorted(by_day.items()):
        ordered = sorted(group, key=lambda b: b.time)
        expected_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        expected = tuple(expected_start + i * M5_DELTA for i in range(BARS_PER_UTC_DAY))
        if len(ordered) == BARS_PER_UTC_DAY and tuple(b.time for b in ordered) == expected:
            complete.append(day)
    return tuple(complete)


def complete_utc_days(bars: Sequence[OhlcBar]) -> Tuple[str, ...]:
    """Public report helper: exact 288-bar UTC calendar days only."""
    return tuple(day.isoformat() for day in _complete_days(bars))


def _is_declared_gap(previous: datetime, current: datetime,
                     expected_gap_intervals: Sequence[Mapping[str, Any]]) -> bool:
    """A discontinuity is allowed only when *every* missing expected M5 timestamp lies
    inside one explicit exporter-declared interval.  No loose weekend/maintenance
    heuristic is used for the 24-hour Crypto-CFD contract.
    """
    missing = []
    point = previous + M5_DELTA
    while point < current:
        missing.append(point)
        point += M5_DELTA
    if not missing:
        return False
    parsed = []
    for interval in expected_gap_intervals:
        try:
            start = parse_utc_timestamp(interval["start_utc"])
            end = parse_utc_timestamp(interval["end_utc"])
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        parsed.append((start, end))
    return bool(parsed) and all(any(start <= point < end for start, end in parsed) for point in missing)


def _resample_complete(bars: Sequence[OhlcBar], minutes: int) -> Tuple[OhlcBar, ...]:
    """UTC-aligned OHLC resample.  An incomplete bucket is omitted—not filled or
    synthesized.  Callers use its omission as deterministic completeness evidence."""
    step = timedelta(minutes=minutes)
    expected_count = minutes // 5
    buckets: Dict[datetime, list[OhlcBar]] = {}
    for bar in bars:
        epoch_seconds = int(bar.time.timestamp())
        bucket_seconds = (epoch_seconds // int(step.total_seconds())) * int(step.total_seconds())
        bucket = datetime.fromtimestamp(bucket_seconds, tz=timezone.utc)
        buckets.setdefault(bucket, []).append(bar)
    output = []
    for start, group in sorted(buckets.items()):
        ordered = sorted(group, key=lambda item: item.time)
        expected = tuple(start + i * M5_DELTA for i in range(expected_count))
        if len(ordered) != expected_count or tuple(item.time for item in ordered) != expected:
            continue
        output.append(OhlcBar(
            time=start, open=ordered[0].open, high=max(item.high for item in ordered),
            low=min(item.low for item in ordered), close=ordered[-1].close,
            volume=(sum(item.volume for item in ordered if item.volume is not None)
                    if any(item.volume is not None for item in ordered) else None),
        ))
    return tuple(output)


def _expected_full_bucket_count(bars: Sequence[OhlcBar], minutes: int) -> int:
    """Count buckets whose source timestamps fully occupy their UTC bucket.  This is
    deliberately calculated without OHLC values, so completeness is independent of
    strategy outcomes."""
    step = timedelta(minutes=minutes)
    expected_count = minutes // 5
    groups: Dict[datetime, set[datetime]] = {}
    for bar in bars:
        second = int(bar.time.timestamp())
        start = datetime.fromtimestamp((second // int(step.total_seconds())) * int(step.total_seconds()),
                                        tz=timezone.utc)
        groups.setdefault(start, set()).add(bar.time)
    count = 0
    for start, timestamps in groups.items():
        expected = {start + i * M5_DELTA for i in range(expected_count)}
        if timestamps == expected:
            count += 1
    return count


def quality_gate(dataset: RawDataset) -> QualityGateReport:
    """Evaluate mandatory quality invariants.  Any failure is a fail-closed ``FAIL``;
    no price transformation is applied as a side effect."""
    bars = dataset.bars
    checks: Dict[str, str] = {}
    codes: list[str] = []

    def check(name: str, passes: bool, code: str) -> None:
        checks[name] = "PASS" if passes else "FAIL"
        if not passes:
            codes.append(code)

    timestamps = tuple(bar.time for bar in bars)
    check("nonempty", bool(bars), "NO_USABLE_M5_ROWS")
    duplicate = len(timestamps) != len(set(timestamps))
    check("duplicate_timestamps", not duplicate, "DUPLICATE_TIMESTAMPS")
    monotonic = all(before < after for before, after in zip(timestamps, timestamps[1:]))
    check("monotonic_timestamps", monotonic, "NON_MONOTONIC_TIMESTAMPS")

    valid_ohlc = all(
        bar.high >= bar.low and bar.low <= bar.open <= bar.high and bar.low <= bar.close <= bar.high
        for bar in bars
    )
    check("valid_ohlc", valid_ohlc, "INVALID_OHLC")

    expected_gap_intervals = dataset.expected_gap_intervals
    unexpected_gaps = []
    if monotonic and not duplicate:
        for before, after in zip(timestamps, timestamps[1:]):
            if after - before != M5_DELTA and not _is_declared_gap(before, after, expected_gap_intervals):
                unexpected_gaps.append((before, after))
    check("unexpected_m5_gaps", not unexpected_gaps, "UNEXPECTED_M5_GAP")

    meta = dataset.timestamp_normalization
    normal_complete = (meta.get("normalized_timezone") == "UTC"
                       and bool(meta.get("normalization_complete"))
                       and meta.get("timestamp_convention") == "OPEN_TIME")
    all_utc = all(bar.time.tzinfo is not None and bar.time.utcoffset() == timedelta(0) for bar in bars)
    check("normalization_completeness", normal_complete and all_utc,
          "TIMESTAMP_NORMALIZATION_INCOMPLETE")

    utc_grid = all(
        bar.time.second == 0 and bar.time.microsecond == 0 and bar.time.minute % 5 == 0
        for bar in bars
    )
    check("utc_day_integrity", utc_grid, "UTC_DAY_INTEGRITY_FAILURE")

    derived_counts: Dict[str, int] = {}
    derived_ok = True
    if monotonic and not duplicate and not unexpected_gaps and utc_grid:
        for timeframe, minutes in TIMEFRAME_MINUTES.items():
            actual = _resample_complete(bars, minutes)
            expected = _expected_full_bucket_count(bars, minutes)
            derived_counts[timeframe] = len(actual)
            if len(actual) != expected:
                derived_ok = False
    else:
        derived_ok = False
        derived_counts = {timeframe: 0 for timeframe in TIMEFRAME_MINUTES}
    check("derived_timeframe_completeness", derived_ok, "DERIVED_TIMEFRAME_INCOMPLETE")

    complete = complete_utc_days(bars)
    coverage = {
        "start_utc": utc_iso(bars[0].time) if bars else None,
        "end_utc": utc_iso(bars[-1].time) if bars else None,
        "row_count": len(bars),
        "unexpected_gap_count": len(unexpected_gaps),
        "complete_utc_day_count": len(complete),
    }
    return QualityGateReport(
        dataset_id=dataset.dataset_id, status="PASS" if not codes else "FAIL",
        checks=checks, reason_codes=tuple(dict.fromkeys(codes)), coverage=coverage,
        complete_utc_days=complete, usable_m5_rows=len(bars) if not codes else 0,
        derived_counts=derived_counts,
    )


def normalize_and_derive(
    raw: RawDataset,
    artifact_root: str | None = None,
) -> Mapping[str, DerivedDataset]:
    """Create independently-hashed ``NORMALIZED_M5 → M15/H1/D1`` artifacts.  This
    function assumes the mandatory quality gate has already passed; callers must not use
    it to repair a failing source.
    """
    root = None if artifact_root is None else __import__("pathlib").Path(artifact_root)
    normalized = build_derived_dataset(raw, UTC_NORMALIZATION_TRANSFORM_ID, "M5", raw.bars, root)
    output: Dict[str, DerivedDataset] = {"NORMALIZED_M5": normalized}
    for timeframe, minutes in TIMEFRAME_MINUTES.items():
        output[timeframe] = build_derived_dataset(
            normalized, RESAMPLE_TRANSFORM_IDS[timeframe], timeframe,
            _resample_complete(normalized.bars, minutes), root,
        )
    return output


def derived_payload_hash(dataset: DerivedDataset) -> str:
    """Small helper used by partition manifests/tests to bind lineage without reading
    prices a second time."""
    return hashlib.sha256(_canonical({
        "dataset_id": dataset.dataset_id, "parent_dataset_id": dataset.parent_dataset_id,
        "transform_id": dataset.transform_id, "sha256": dataset.sha256,
    })).hexdigest()


__all__ = [
    "BARS_PER_UTC_DAY", "M5_DELTA", "QUALITY_GATE_ID", "QualityGateReport",
    "complete_utc_days", "derived_payload_hash", "normalize_and_derive", "quality_gate", "utc_iso",
]
