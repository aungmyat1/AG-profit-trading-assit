"""Tests for execution/crypto_clock.py: ClockOffset measurement, application, refresh, and
threshold rejection. No network call anywhere -- server time is always a plain datetime
constructed in the test."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from execution.crypto_clock import (
    ClockOffsetExceeded,
    DEFAULT_MAX_OFFSET_MS,
    apply_offset,
    measure_offset,
    require_offset_within_threshold,
)


def test_offset_ahead():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local + timedelta(milliseconds=300)
    offset = measure_offset(server, local)
    assert offset.offset_ms == 300


def test_offset_behind():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local - timedelta(milliseconds=450)
    offset = measure_offset(server, local)
    assert offset.offset_ms == -450


def test_apply_offset_corrects_a_timestamp():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local + timedelta(milliseconds=300)
    offset = measure_offset(server, local)
    corrected = apply_offset(local, offset)
    assert corrected == server


def test_refresh_produces_an_updated_offset():
    local1 = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server1 = local1 + timedelta(milliseconds=100)
    offset1 = measure_offset(server1, local1)

    local2 = local1 + timedelta(seconds=30)
    server2 = local2 + timedelta(milliseconds=250)
    offset2 = measure_offset(server2, local2)

    assert offset1.offset_ms == 100
    assert offset2.offset_ms == 250
    assert offset1 != offset2


def test_within_threshold_does_not_raise():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local + timedelta(milliseconds=DEFAULT_MAX_OFFSET_MS - 1)
    offset = measure_offset(server, local)
    require_offset_within_threshold(offset)  # must not raise


def test_exceeding_threshold_ahead_raises():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local + timedelta(milliseconds=DEFAULT_MAX_OFFSET_MS + 500)
    offset = measure_offset(server, local)
    with pytest.raises(ClockOffsetExceeded):
        require_offset_within_threshold(offset)


def test_exceeding_threshold_behind_raises():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local - timedelta(milliseconds=DEFAULT_MAX_OFFSET_MS + 500)
    offset = measure_offset(server, local)
    with pytest.raises(ClockOffsetExceeded):
        require_offset_within_threshold(offset)


def test_custom_threshold_respected():
    local = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
    server = local + timedelta(milliseconds=50)
    offset = measure_offset(server, local)
    require_offset_within_threshold(offset, max_offset_ms=100)  # must not raise
    with pytest.raises(ClockOffsetExceeded):
        require_offset_within_threshold(offset, max_offset_ms=10)
