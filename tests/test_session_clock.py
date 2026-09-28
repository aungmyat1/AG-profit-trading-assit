"""Tests for the shared canonical session service (session_clock.py).

Covers CANONICAL_SESSION_MIGRATION section 6 (runtime integrity checks) and section 22
(canonical clock / boundary tests), independent of any one strategy's consumption of it.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

import session_clock as sc

UTC = dt.timezone.utc
DAY = dt.date(2026, 1, 5)


def test_validate_session_contract_passes_on_the_real_config():
    definitions = sc.validate_session_contract()
    assert definitions["asian"] == sc.SessionDefinition("asian", 0, 6, 24)
    assert definitions["london_am"] == sc.SessionDefinition("london_am", 6, 11, 20)
    assert definitions["new_york_am"] == sc.SessionDefinition("new_york_am", 12, 15, 12)


@pytest.mark.parametrize(
    "name,duration_hours,bars",
    [("asian", 6, 24), ("london_am", 5, 20), ("new_york_am", 3, 12)],
)
def test_durations_and_bar_counts(name, duration_hours, bars):
    d = sc.get_session_definition(name)
    assert d.duration_hours == duration_hours
    assert d.expected_m15_bars == bars


def test_hour_ordering():
    asian = sc.get_session_definition("asian")
    london = sc.get_session_definition("london_am")
    ny = sc.get_session_definition("new_york_am")
    assert asian.start_hour < asian.end_hour == 6
    assert london.start_hour == 6 < london.end_hour == 11
    assert ny.start_hour == 12 < ny.end_hour == 15


def test_sessions_do_not_overlap():
    asian = sc.get_session_definition("asian")
    london = sc.get_session_definition("london_am")
    ny = sc.get_session_definition("new_york_am")
    assert asian.end_hour <= london.start_hour
    assert london.end_hour <= ny.start_hour


@pytest.mark.parametrize(
    "hour,minute,expected",
    [(5, 45, True), (0, 0, True), (6, 0, False), (23, 59, False)],
)
def test_asian_boundary(hour, minute, expected):
    ts = dt.datetime.combine(DAY, dt.time(hour, minute), tzinfo=UTC)
    assert sc.is_in_session(ts, "asian") is expected


@pytest.mark.parametrize(
    "hour,minute,expected",
    [(6, 0, True), (10, 45, True), (11, 0, False), (5, 59, False)],
)
def test_london_am_boundary(hour, minute, expected):
    ts = dt.datetime.combine(DAY, dt.time(hour, minute), tzinfo=UTC)
    assert sc.is_in_session(ts, "london_am") is expected


@pytest.mark.parametrize(
    "hour,minute,expected",
    [(12, 0, True), (14, 45, True), (15, 0, False), (11, 59, False)],
)
def test_new_york_am_boundary(hour, minute, expected):
    ts = dt.datetime.combine(DAY, dt.time(hour, minute), tzinfo=UTC)
    assert sc.is_in_session(ts, "new_york_am") is expected


def test_the_11_to_12_gap_belongs_to_no_am_session():
    ts = dt.datetime.combine(DAY, dt.time(11, 30), tzinfo=UTC)
    assert sc.is_in_session(ts, "london_am") is False
    assert sc.is_in_session(ts, "new_york_am") is False
    assert sc.is_in_session(ts, "asian") is False


def test_get_session_bounds_half_open():
    start, end = sc.get_session_bounds(DAY, "london_am")
    assert start == dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)
    assert end == dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC)


def test_session_complete():
    start, end = sc.get_session_bounds(DAY, "asian")
    assert sc.session_complete(end, DAY, "asian") is True
    assert sc.session_complete(end - dt.timedelta(minutes=1), DAY, "asian") is False


def test_expected_bar_count_by_timeframe():
    assert sc.expected_bar_count("asian", "M15") == 24
    assert sc.expected_bar_count("asian", "M5") == 72
    assert sc.expected_bar_count("asian", "M1") == 360
    with pytest.raises(sc.SessionContractConflict):
        sc.expected_bar_count("asian", "H1")


def test_unknown_session_name_rejected():
    with pytest.raises(sc.SessionContractConflict):
        sc.get_session_definition("tokyo_pm")


# --------------------------------------------------------- contract corruption (fail closed)

def _write_and_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raw: dict):
    path = tmp_path / "canonical_sessions.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    monkeypatch.setattr(sc, "_CONFIG_PATH", path)
    sc._raw_contract.cache_clear()
    sc.load_canonical_sessions.cache_clear()


VALID_SESSIONS = {
    "asian": {"start": "00:00", "end": "06:00", "expected_m15_bars": 24},
    "london_am": {"start": "06:00", "end": "11:00", "expected_m15_bars": 20},
    "new_york_am": {"start": "12:00", "end": "15:00", "expected_m15_bars": 12},
}


def test_wrong_timezone_is_rejected(tmp_path, monkeypatch):
    _write_and_load(tmp_path, monkeypatch, {
        "version": "CANONICAL_SESSION_WINDOWS_V1", "timezone": "Europe/London",
        "boundary_policy": "half_open", "dst_policy": "fixed_utc", "sessions": VALID_SESSIONS,
    })
    with pytest.raises(sc.SessionContractConflict):
        sc.load_canonical_sessions()


def test_dst_policy_not_fixed_utc_is_rejected(tmp_path, monkeypatch):
    _write_and_load(tmp_path, monkeypatch, {
        "version": "CANONICAL_SESSION_WINDOWS_V1", "timezone": "UTC",
        "boundary_policy": "half_open", "dst_policy": "europe_london_local", "sessions": VALID_SESSIONS,
    })
    with pytest.raises(sc.SessionContractConflict):
        sc.load_canonical_sessions()


def test_overlapping_sessions_rejected(tmp_path, monkeypatch):
    overlapping = dict(VALID_SESSIONS)
    overlapping["london_am"] = {"start": "05:00", "end": "11:00", "expected_m15_bars": 24}
    _write_and_load(tmp_path, monkeypatch, {
        "version": "CANONICAL_SESSION_WINDOWS_V1", "timezone": "UTC",
        "boundary_policy": "half_open", "dst_policy": "fixed_utc", "sessions": overlapping,
    })
    with pytest.raises(sc.SessionContractConflict):
        sc.load_canonical_sessions()


def test_bar_count_mismatch_rejected(tmp_path, monkeypatch):
    bad = dict(VALID_SESSIONS)
    bad["asian"] = {"start": "00:00", "end": "06:00", "expected_m15_bars": 99}
    _write_and_load(tmp_path, monkeypatch, {
        "version": "CANONICAL_SESSION_WINDOWS_V1", "timezone": "UTC",
        "boundary_policy": "half_open", "dst_policy": "fixed_utc", "sessions": bad,
    })
    with pytest.raises(sc.SessionContractConflict):
        sc.load_canonical_sessions()


def test_wrong_version_rejected(tmp_path, monkeypatch):
    _write_and_load(tmp_path, monkeypatch, {
        "version": "SOME_OTHER_VERSION", "timezone": "UTC",
        "boundary_policy": "half_open", "dst_policy": "fixed_utc", "sessions": VALID_SESSIONS,
    })
    with pytest.raises(sc.SessionContractConflict):
        sc.load_canonical_sessions()


@pytest.fixture(autouse=True)
def _reset_cache_after_each_test():
    yield
    sc._raw_contract.cache_clear()
    sc.load_canonical_sessions.cache_clear()
