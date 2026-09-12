"""Controlled-fixture tests for src/market_data_readiness/scanner.py -- the read-only
discovery/fingerprint/quality/timezone scanner built for the
ST_SESSION_SWEEP_CONTINUATION_V1 data-readiness assessment. These use small synthetic
CSVs (never real D:\\ files) so they run deterministically in CI without depending on
owner-authorized local data being present.
"""
from __future__ import annotations

import hashlib
import os

import pytest

from market_data_readiness.scanner import (
    classify_filename,
    classify_overlap,
    discover_candidates,
    scan_file,
    sha256_stream,
)

HEADER = "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"


def _write(tmp_path, name, lines):
    p = tmp_path / name
    p.write_text(HEADER + "".join(lines), encoding="utf-8")
    return str(p)


def _row(date, time_, o, h, l, c):
    return f"{date}\t{time_}\t{o}\t{h}\t{l}\t{c}\t100\t0\t10\n"


# ---- filename classification -------------------------------------------------

def test_classify_filename_declared_timeframe():
    meta = classify_filename(r"D:\EURUSD_M15_202501020000_202606192345.csv")
    assert meta == {"symbol": "EURUSD", "declared_tf": "M15", "filename": "EURUSD_M15_202501020000_202606192345.csv"}


def test_classify_filename_unknown_timeframe_tick_style():
    meta = classify_filename(r"D:\EURUSD_202606182200_202608241902.csv")
    assert meta["declared_tf"] == "UNKNOWN_TICK"


def test_classify_filename_unparseable_returns_none():
    assert classify_filename(r"D:\not_a_match.csv") is None


# ---- discovery / deduplication -------------------------------------------------

def test_discover_candidates_multiple_files_preserved_as_list(tmp_path):
    _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)])
    _write(tmp_path, "EURUSD_M15_202502020000_202502022345.csv", [_row("2025.02.02", "00:00:00", 1, 1, 1, 1)])
    found = discover_candidates(str(tmp_path), ["EURUSD"])
    assert len(found["EURUSD"]) == 2  # never overwritten -- both candidates preserved


def test_discover_candidates_deduplicates_same_resolved_path(tmp_path):
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)])
    found = discover_candidates(str(tmp_path), ["EURUSD"])
    found2 = discover_candidates(str(tmp_path), ["EURUSD"])  # simulate a second glob pass
    combined = set(found["EURUSD"]) | set(found2["EURUSD"])
    assert len(combined) == 1


# ---- timeframe detection / conflict -------------------------------------------------

def test_observed_timeframe_matches_declared_m15(tmp_path):
    rows = [_row("2025.01.02", f"{h:02d}:{m:02d}:00", 1, 1, 1, 1) for h in range(2) for m in (0, 15, 30, 45)]
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.observed_timeframe == "M15"
    assert rec.timeframe_status == "MATCH"


def test_timeframe_conflict_detected_when_filename_disagrees_with_spacing(tmp_path):
    # filename says M15 but actual spacing is 60s (M1)
    rows = [_row("2025.01.02", f"00:{m:02d}:00", 1, 1, 1, 1) for m in range(10)]
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.observed_timeframe == "M1"
    assert rec.timeframe_status == "CONFLICT"


# ---- timezone handling -------------------------------------------------

def test_timezone_unresolved_when_no_weekend_gap_present(tmp_path):
    rows = [_row("2025.01.02", f"{h:02d}:00:00", 1, 1, 1, 1) for h in range(5)]
    path = _write(tmp_path, "EURUSD_H1_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.timezone_status == "UNRESOLVED"
    assert rec.first_ts_utc is None  # never silently appends Z / assumes UTC


def test_timezone_resolved_via_weekend_reopen_gap(tmp_path):
    # Friday close then a genuine weekend gap (>40h) into the Sunday 17:00 NY reopen.
    # 2025-01-03 is a Friday; NY 17:00 EST (winter, offset 5h) = 2025-01-03T22:00 broker
    # wall clock at a hypothetical 0-offset broker, but here we simulate a broker whose
    # wall clock reads 2025-01-05 22:00:00 as the reopen bar (i.e. broker_offset = 0 for
    # this synthetic scenario -- server_time == true_utc).
    rows = [
        _row("2025.01.03", "20:00:00", 1, 1, 1, 1),
        _row("2025.01.03", "21:00:00", 1, 1, 1, 1),
        _row("2025.01.05", "22:00:00", 1, 1, 1, 1),  # true UTC reopen instant, offset 0
        _row("2025.01.05", "23:00:00", 1, 1, 1, 1),
    ]
    path = _write(tmp_path, "EURUSD_H1_202501030000_202501052345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.timezone_status == "BROKER_OFFSET_CONFIRMED"
    assert rec.broker_utc_offset_hours == 0
    assert rec.first_ts_utc is not None


def test_timezone_unresolved_when_weekend_sized_gap_not_a_true_reopen(tmp_path):
    # A >40h gap exists but its endpoint does not fall on a whole-hour offset from the
    # true NY 17:00 UTC reopen instant (e.g. a data-outage gap, not the weekly reopen).
    # Must fail closed to UNRESOLVED, never raise or silently guess an offset -- this is
    # a REAL behavior found scanning D:\EURUSD_M1_202605180946_202607312356.csv (its
    # largest gap's reopen reading, 2026-07-06 00:02:00, is not a whole-hour offset from
    # the 2026-07-06 21:00:00 UTC true reopen instant).
    rows = [
        _row("2025.01.03", "20:00:00", 1, 1, 1, 1),
        _row("2025.01.05", "20:31:00", 1, 1, 1, 1),  # 48.5h gap, off-hour minute residue
    ]
    path = _write(tmp_path, "EURUSD_H1_202501030000_202501052345.csv", rows)
    rec = scan_file(path, classify_filename(path))
    assert rec.largest_gap_hours >= 40
    assert rec.timezone_status == "UNRESOLVED"
    assert rec.broker_utc_offset_hours is None
    assert rec.first_ts_utc is None


# ---- SHA-256 streaming -------------------------------------------------

def test_sha256_stream_matches_hashlib_direct(tmp_path):
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)])
    expected = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert sha256_stream(path, chunk_size=16) == expected  # tiny chunk size forces multi-chunk path


def test_sha256_stream_does_not_modify_source_file(tmp_path):
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)])
    before_mtime = os.path.getmtime(path)
    before_size = os.path.getsize(path)
    sha256_stream(path)
    assert os.path.getmtime(path) == before_mtime
    assert os.path.getsize(path) == before_size


# ---- OHLC / duplicate / non-monotonic quality checks -------------------------------------------------

def test_ohlc_violation_detected_high_less_than_low(tmp_path):
    rows = [_row("2025.01.02", "00:00:00", 1.0, 0.9, 1.1, 1.0)]  # high < low
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.ohlc_violations == 1
    assert rec.quality_status in ("PARTIAL", "FAIL")


def test_duplicate_timestamps_detected(tmp_path):
    rows = [_row("2025.01.02", "00:00:00", 1, 1, 1, 1), _row("2025.01.02", "00:00:00", 1, 1, 1, 1)]
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.duplicate_timestamps == 1


def test_nonmonotonic_timestamps_detected(tmp_path):
    rows = [_row("2025.01.02", "00:15:00", 1, 1, 1, 1), _row("2025.01.02", "00:00:00", 1, 1, 1, 1)]
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.nonmonotonic_timestamps == 1
    assert rec.quality_status == "PARTIAL"


def test_short_dataset_quality_and_row_count(tmp_path):
    rows = [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)]
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.row_count == 1
    assert rec.quality_status == "PASS"  # a single clean row is not itself a quality failure


def test_empty_file_quality_fail(tmp_path):
    path = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", [])
    meta = classify_filename(path)
    rec = scan_file(path, meta)
    assert rec.row_count == 0
    assert rec.quality_status == "FAIL"


# ---- bid/ask tick precision -------------------------------------------------

def test_bidask_tick_file_detected_and_never_labeled_ohlc(tmp_path):
    p = tmp_path / "EURUSD_202601010000_202601020000.csv"
    p.write_text(
        "<DATE>\t<TIME>\t<BID>\t<ASK>\t<LAST>\t<VOLUME>\t<FLAGS>\n"
        "2026.01.01\t00:00:00.100\t1.10000\t1.10010\t\t\t6\n"
        "2026.01.01\t00:00:00.200\t1.10001\t1.10011\t\t\t6\n",
        encoding="utf-8",
    )
    meta = classify_filename(str(p))
    assert meta["declared_tf"] == "UNKNOWN_TICK"
    rec = scan_file(str(p), meta)
    assert rec.is_bidask is True
    assert rec.observed_timeframe == "TICK"


# ---- overlap classification -------------------------------------------------

def test_overlap_disjoint_contiguous(tmp_path):
    p1 = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)])
    p2 = _write(tmp_path, "EURUSD_M15_202502020000_202502022345.csv", [_row("2025.02.02", "00:00:00", 1, 1, 1, 1)])
    a = scan_file(p1, classify_filename(p1))
    b = scan_file(p2, classify_filename(p2))
    assert classify_overlap(a, b) == "DISJOINT_CONTIGUOUS"


def test_overlap_conflicting_when_ranges_intersect_but_differ(tmp_path):
    rows_a = [_row("2025.01.02", "00:00:00", 1, 1, 1, 1), _row("2025.01.02", "00:15:00", 1, 1, 1, 1)]
    rows_b = [_row("2025.01.02", "00:15:00", 2, 2, 2, 2), _row("2025.01.02", "00:30:00", 2, 2, 2, 2)]
    p1 = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows_a)
    p2 = _write(tmp_path, "EURUSD_M15_202502020000_202502022345.csv", rows_b)
    a = scan_file(p1, classify_filename(p1))
    b = scan_file(p2, classify_filename(p2))
    assert classify_overlap(a, b) == "OVERLAPPING_CONFLICTING"


def test_overlap_duplicate_when_identical_hash(tmp_path):
    rows = [_row("2025.01.02", "00:00:00", 1, 1, 1, 1)]
    p1 = _write(tmp_path, "EURUSD_M15_202501020000_202501022345.csv", rows)
    p2 = _write(tmp_path, "EURUSD_M15_202502020000_202502022345.csv", rows)
    a = scan_file(p1, classify_filename(p1))
    a.sha256 = sha256_stream(p1)
    b = scan_file(p2, classify_filename(p2))
    b.sha256 = sha256_stream(p2)
    assert classify_overlap(a, b) == "DUPLICATE"


# ---- gap detection (weekend + material) -------------------------------------------------

def test_weekend_gap_recorded_as_largest_gap(tmp_path):
    rows = [
        _row("2025.01.03", "20:00:00", 1, 1, 1, 1),
        _row("2025.01.05", "22:00:00", 1, 1, 1, 1),  # ~50h weekend gap
    ]
    path = _write(tmp_path, "EURUSD_H1_202501030000_202501052345.csv", rows)
    rec = scan_file(path, classify_filename(path))
    assert rec.largest_gap_hours >= 40


def test_material_intraweek_gap_recorded_not_confused_with_weekend(tmp_path):
    rows = [
        _row("2025.01.02", "00:00:00", 1, 1, 1, 1),
        _row("2025.01.02", "05:00:00", 1, 1, 1, 1),  # 5h gap, well under weekend threshold
    ]
    path = _write(tmp_path, "EURUSD_H1_202501020000_202501022345.csv", rows)
    rec = scan_file(path, classify_filename(path))
    assert rec.largest_gap_hours == pytest.approx(5.0)
    assert rec.timezone_status == "UNRESOLVED"  # too small to be the weekly reopen gap
