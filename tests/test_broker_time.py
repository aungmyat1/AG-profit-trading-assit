"""Unit tests for mt5.broker_time's offset-from-reopen math. No MT5 connection needed --
pure date/time arithmetic, so this runs in the fast/targeted test tier."""
from __future__ import annotations

import datetime as dt

import pytest

from mt5.broker_time import (
    BrokerTimeError,
    _largest_gap,
    offset_from_reopen,
    us_eastern_utc_offset_hours,
)


def test_us_eastern_offset_is_5_in_january():
    assert us_eastern_utc_offset_hours(dt.date(2026, 1, 15)) == 5


def test_us_eastern_offset_is_4_in_july():
    assert us_eastern_utc_offset_hours(dt.date(2026, 7, 15)) == 4


def test_us_eastern_offset_flips_at_march_dst_start_2026():
    # 2nd Sunday of March 2026 is March 8.
    assert us_eastern_utc_offset_hours(dt.date(2026, 3, 7)) == 5
    assert us_eastern_utc_offset_hours(dt.date(2026, 3, 8)) == 4


def test_us_eastern_offset_flips_at_november_dst_end_2026():
    # 1st Sunday of November 2026 is November 1.
    assert us_eastern_utc_offset_hours(dt.date(2026, 10, 31)) == 4
    assert us_eastern_utc_offset_hours(dt.date(2026, 11, 1)) == 5


def test_offset_from_reopen_winter_broker_plus_2():
    # Winter: NY reopen = Sunday 22:00 UTC. A broker reading of 00:00 (next day) is +2h.
    sunday = dt.date(2026, 1, 4)
    server_reading = dt.datetime.combine(sunday, dt.time(22)) + dt.timedelta(hours=2)
    assert offset_from_reopen(server_reading) == 2


def test_offset_from_reopen_summer_broker_plus_3():
    # Summer: NY reopen = Sunday 21:00 UTC. A broker reading of 00:00 (next day) is +3h.
    sunday = dt.date(2026, 8, 2)
    server_reading = dt.datetime.combine(sunday, dt.time(21)) + dt.timedelta(hours=3)
    assert offset_from_reopen(server_reading) == 3


def test_offset_from_reopen_rejects_non_whole_hour():
    sunday = dt.date(2026, 1, 4)
    server_reading = dt.datetime.combine(sunday, dt.time(22)) + dt.timedelta(minutes=90)
    with pytest.raises(BrokerTimeError):
        offset_from_reopen(server_reading)


# --------------------------------------------------------------------------- gap selection (AG_TIME_NORMALIZATION_V1)

def _m15_series(start: dt.datetime, count: int) -> list[dt.datetime]:
    return [start + dt.timedelta(minutes=15 * i) for i in range(count)]


def test_largest_gap_picks_the_most_recent_tie_not_the_oldest():
    """Two identically-sized weekly-reopen gaps (routine on a feed with no holidays):
    the MOST RECENT one must win, not Python's default max() tie behavior of keeping
    the first (oldest) item -- see _largest_gap's docstring for why the oldest choice
    is a latent correctness risk (a stale offset across an intervening DST change)."""
    week1 = _m15_series(dt.datetime(2026, 7, 20, 0, 0), 5)
    gap_a_end = dt.datetime(2026, 7, 27, 0, 0)
    week2 = _m15_series(gap_a_end, 5)
    gap_b_end = dt.datetime(2026, 8, 3, 0, 0)
    week3 = _m15_series(gap_b_end, 5)
    times = week1 + week2 + week3
    # Both inter-week gaps are exactly 6 days 23:45 -- an intentional tie.
    assert (week2[0] - week1[-1]) == (week3[0] - week2[-1])

    gap, reopen_idx = _largest_gap(times)
    assert times[reopen_idx] == gap_b_end  # the later gap's reopen bar, not gap_a_end


def test_largest_gap_ignores_ordinary_intraday_spacing():
    times = _m15_series(dt.datetime(2026, 8, 3, 0, 0), 10)
    gap, reopen_idx = _largest_gap(times)
    assert gap == dt.timedelta(minutes=15)
