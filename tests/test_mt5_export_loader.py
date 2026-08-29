"""Tests for historical_replay.mt5_export_loader (historical-validation continuation
spec sections 7-10, 51). Synthetic CSV fixtures built the same way test_broker_time.py
builds its reopen fixtures -- true UTC reopen instant + a known broker offset -- so the
expected UTC-normalized output is independently computable, not just "whatever the code
produces".
"""
from __future__ import annotations

import datetime as dt

import pytest

from historical_replay.mt5_export_loader import IngestionError, load_mt5_export_csv
from mt5.broker_time import ny_1700_reopen_instant_utc

UTC = dt.timezone.utc
HEADER = "<DATE>\t<TIME>\t<OPEN>\t<HIGH>\t<LOW>\t<CLOSE>\t<TICKVOL>\t<VOL>\t<SPREAD>\n"


def _reopen_utc(sunday: dt.date) -> dt.datetime:
    return ny_1700_reopen_instant_utc(sunday).replace(tzinfo=UTC)


def _row(ts: dt.datetime, o=1.1, h=1.2, l=1.0, c=1.15, tv=10) -> str:
    return f"{ts.strftime('%Y.%m.%d')}\t{ts.strftime('%H:%M:%S')}\t{o}\t{h}\t{l}\t{c}\t{tv}\t0\t10\n"


def _m5_week(start_broker: dt.datetime, bars: int) -> list[dt.datetime]:
    return [start_broker + dt.timedelta(minutes=5 * i) for i in range(bars)]


def _week_ending_friday(monday: dt.datetime, bars: int) -> list[dt.datetime]:
    """A short run of bars anchored at `monday` (broker time), used purely as the
    "previous week" context a weekly-reopen detector needs before the week under test."""
    return _m5_week(monday, bars)


def test_load_normalizes_single_broker_offset_to_utc(tmp_path):
    # A dummy prior week (any offset) gives _offset_segments a weekend gap to find
    # ahead of the week actually under test. Winter reopen: true UTC reopen = Sunday
    # 22:00 UTC; a broker reading of Monday 00:00 is +2h broker offset.
    prior_sunday = dt.date(2025, 12, 28)
    prior_week = _week_ending_friday(
        dt.datetime.combine(prior_sunday + dt.timedelta(days=1), dt.time(0, 0)), 5)

    sunday = dt.date(2026, 1, 4)
    monday_broker_reopen = dt.datetime.combine(sunday + dt.timedelta(days=1), dt.time(0, 0))
    week = _m5_week(monday_broker_reopen, 20)

    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + "".join(_row(t) for t in prior_week + week), encoding="utf-8")

    candles, report = load_mt5_export_csv(str(path), "EURUSD", "M5")

    assert len(candles) == 25
    # broker 00:00 Monday, offset +2 -> true UTC 2026-01-04 22:00 (Sunday)
    assert candles[5].time == _reopen_utc(sunday)
    assert report.rows == 25
    assert report.start_utc == candles[0].time
    assert report.end_utc == candles[-1].time


def test_load_detects_seasonal_offset_change_across_two_reopens(tmp_path):
    """Winter week (+2) followed by a summer week (+3) -- the loader must apply the
    CORRECT offset to each segment, not one constant offset for the whole file."""
    prior_sunday = dt.date(2025, 12, 28)
    prior_week = _week_ending_friday(
        dt.datetime.combine(prior_sunday + dt.timedelta(days=1), dt.time(0, 0)), 5)

    winter_sunday = dt.date(2026, 1, 4)
    winter_monday = dt.datetime.combine(winter_sunday + dt.timedelta(days=1), dt.time(0, 0))
    winter_week = _m5_week(winter_monday, 10)

    summer_sunday = dt.date(2026, 8, 2)
    summer_monday = dt.datetime.combine(summer_sunday + dt.timedelta(days=1), dt.time(0, 0))
    summer_week = _m5_week(summer_monday, 10)

    rows = "".join(_row(t) for t in prior_week + winter_week + summer_week)
    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + rows, encoding="utf-8")

    candles, report = load_mt5_export_csv(str(path), "EURUSD", "M5")

    assert len(candles) == 25
    winter_utc = _reopen_utc(winter_sunday)  # offset +2 applied to winter rows
    summer_utc = _reopen_utc(summer_sunday)  # offset +3 applied to summer rows
    assert candles[5].time == winter_utc
    assert candles[15].time == summer_utc
    assert "UTC+2" in report.source_timezone and "UTC+3" in report.source_timezone


def test_unexpected_gap_reported_not_silently_filled(tmp_path):
    prior_sunday = dt.date(2025, 12, 28)
    prior_week = _week_ending_friday(
        dt.datetime.combine(prior_sunday + dt.timedelta(days=1), dt.time(0, 0)), 5)

    winter_sunday = dt.date(2026, 1, 4)
    monday = dt.datetime.combine(winter_sunday + dt.timedelta(days=1), dt.time(0, 0))
    week = _m5_week(monday, 10)
    # Remove the 5th bar of the target week to create a single-bar (10 min) gap.
    week_with_gap = week[:5] + week[6:]

    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + "".join(_row(t) for t in prior_week + week_with_gap), encoding="utf-8")

    _candles, report = load_mt5_export_csv(str(path), "EURUSD", "M5")

    assert len(report.unexpected_gaps) == 1
    assert report.unexpected_gaps[0].duration == dt.timedelta(minutes=10)


def test_weekend_gap_classified_expected_not_unexpected(tmp_path):
    winter_sunday = dt.date(2026, 1, 4)
    week1 = _m5_week(dt.datetime.combine(winter_sunday + dt.timedelta(days=1), dt.time(0, 0)), 5)
    week2 = _m5_week(dt.datetime.combine(winter_sunday + dt.timedelta(days=8), dt.time(0, 0)), 5)

    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + "".join(_row(t) for t in week1 + week2), encoding="utf-8")

    _candles, report = load_mt5_export_csv(str(path), "EURUSD", "M5")

    assert len(report.unexpected_gaps) == 0
    assert any(g.classification == "EXPECTED_MARKET_CLOSURE" for g in report.gaps)


def test_rejects_duplicate_timestamp(tmp_path):
    winter_sunday = dt.date(2026, 1, 4)
    monday = dt.datetime.combine(winter_sunday + dt.timedelta(days=1), dt.time(0, 0))
    week = _m5_week(monday, 10)
    week_with_dup = week[:5] + [week[4]] + week[5:]  # duplicate the 5th timestamp

    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + "".join(_row(t) for t in week_with_dup), encoding="utf-8")

    with pytest.raises(IngestionError):
        load_mt5_export_csv(str(path), "EURUSD", "M5")


def test_rejects_invalid_ohlc(tmp_path):
    winter_sunday = dt.date(2026, 1, 4)
    monday = dt.datetime.combine(winter_sunday + dt.timedelta(days=1), dt.time(0, 0))
    week = _m5_week(monday, 5)
    rows = "".join(_row(t) for t in week[:-1])
    rows += _row(week[-1], o=1.1, h=0.9, l=1.0, c=1.15)  # high < open: invalid

    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + rows, encoding="utf-8")

    with pytest.raises(IngestionError):
        load_mt5_export_csv(str(path), "EURUSD", "M5")


def test_rejects_unsupported_timeframe(tmp_path):
    winter_sunday = dt.date(2026, 1, 4)
    monday = dt.datetime.combine(winter_sunday + dt.timedelta(days=1), dt.time(0, 0))
    week = _m5_week(monday, 5)
    path = tmp_path / "EURUSD_M5.csv"
    path.write_text(HEADER + "".join(_row(t) for t in week), encoding="utf-8")

    with pytest.raises(IngestionError):
        load_mt5_export_csv(str(path), "EURUSD", "M3")

