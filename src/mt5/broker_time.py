"""Broker-server UTC offset detection via the weekly reopen gap, per
docs/setup/MT5_MCP_SETUP.md's 'Worth keeping from the guide':

FX reopens at a fixed UTC instant (Sunday 17:00 New York local, regardless of the
broker's own clock), so the offset between the broker's wall-clock reading of that
instant and the true UTC instant IS the broker's UTC offset -- derived from data, not
asserted from a DST table for the broker itself. This is the one place a DST table is
still used deliberately: US Eastern time, to compute the *reference* instant, not the
broker's own zone.

MT5 quirk this works around: candle timestamps returned by the MetaTrader5 python API
are epoch seconds that read correctly as the *broker's own wall clock* when interpreted
naively (datetime.utcfromtimestamp) -- they are NOT true UTC unless the broker happens
to run its server on UTC. Naive (tz-less) datetimes are used throughout this module on
purpose: attaching tzinfo and letting Python/MT5 attempt further conversion would
silently reintroduce the very bug this module exists to avoid.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List, Tuple

import MetaTrader5 as mt5

MIN_WEEKEND_GAP = timedelta(hours=40)  # a weekday data gap is never this long; the weekly reopen gap is ~44-49h


class BrokerTimeError(RuntimeError):
    pass


def us_eastern_utc_offset_hours(d: date) -> int:
    """Hours to ADD to US Eastern local time to get UTC: 4 during EDT, 5 during EST.
    US rule since 2007: DST from the 2nd Sunday of March to the 1st Sunday of November."""
    march1 = date(d.year, 3, 1)
    first_sunday_march = march1 + timedelta(days=(6 - march1.weekday()) % 7)
    dst_start = first_sunday_march + timedelta(days=7)
    nov1 = date(d.year, 11, 1)
    dst_end = nov1 + timedelta(days=(6 - nov1.weekday()) % 7)
    return 4 if dst_start <= d < dst_end else 5


def ny_1700_reopen_instant_utc(sunday_date: date) -> datetime:
    """True UTC instant of the weekly FX reopen (Sunday 17:00 New York local), as a
    naive datetime whose fields ARE the UTC wall clock."""
    offset = us_eastern_utc_offset_hours(sunday_date)
    return datetime.combine(sunday_date, time(17)) + timedelta(hours=offset)


def offset_from_reopen(server_reopen_reading: datetime) -> int:
    """server_reopen_reading: the broker-server-time reading (naive) of the first bar
    after the weekly reopen gap. Returns the broker's UTC offset in whole hours
    (server_time = true_utc + offset)."""
    true_utc = ny_1700_reopen_instant_utc(server_reopen_reading.date())
    # The reopen bar can land up to ~15 minutes after the true instant (bar granularity);
    # searching the same or adjacent calendar day covers any date-boundary edge case.
    for day_shift in (0, -1, 1):
        candidate = ny_1700_reopen_instant_utc(server_reopen_reading.date() + timedelta(days=day_shift))
        delta = (server_reopen_reading - candidate).total_seconds() / 3600
        if abs(delta - round(delta)) < 0.01 and abs(round(delta)) <= 14:
            return round(delta)
    raise BrokerTimeError(
        f"OFFSET_FROM_REOPEN_AMBIGUOUS: {server_reopen_reading} did not resolve to a whole-hour "
        f"offset near {true_utc} UTC reopen"
    )


def _largest_gap(times: List[datetime]) -> Tuple[timedelta, int]:
    """Returns (gap, index-of-first-bar-after-the-gap) for the largest gap between
    consecutive timestamps. When multiple gaps tie for largest (common: every ordinary
    weekend closure produces an identically-sized gap on this kind of feed), the MOST
    RECENT one wins -- not Python's default `max()` behavior of keeping the first
    (oldest) tied item. Anchoring on the oldest tied reopen would derive the broker's
    offset from a week that could predate a DST transition inside the lookback window,
    silently producing a stale-but-plausible-looking offset instead of failing loudly.
    This is a general correctness fix, not specific to any one symbol."""
    gaps = [(times[i + 1] - times[i], i + 1) for i in range(len(times) - 1)]
    return max(gaps, key=lambda g: (g[0], g[1]))


def detect_broker_utc_offset_hours(symbol: str, lookback_bars: int = 3000) -> int:
    """Fetch M15 candles, find the largest (most recent, on ties) time gap (the
    weekend), and derive the broker's UTC offset from the first bar after it. Requires
    mt5.connection.connect() to have already been called."""
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, lookback_bars)
    if rates is None or len(rates) < 2:
        code, message = mt5.last_error()
        raise BrokerTimeError(f"DATA_MISSING: copy_rates_from_pos({symbol!r}) returned no data: ({code}) {message}")

    times = [datetime.utcfromtimestamp(int(r["time"])) for r in rates]  # naive: reads as broker wall clock
    gap, reopen_idx = _largest_gap(times)
    if gap < MIN_WEEKEND_GAP:
        raise BrokerTimeError(
            f"NO_WEEKEND_GAP_FOUND: largest gap in last {lookback_bars} M15 bars for {symbol!r} "
            f"was {gap}, need >= {MIN_WEEKEND_GAP} to identify the weekly reopen"
        )

    return offset_from_reopen(times[reopen_idx])
