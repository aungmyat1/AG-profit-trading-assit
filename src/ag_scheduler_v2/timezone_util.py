"""UTC scheduler authority + MMT (UTC+06:30) display conversion.

Spec section 2: canonical timezone authority is UTC. Myanmar time (MMT) is
display/operator time only, and must never be modeled as a bare integer hour offset
(e.g. `MMT_OFFSET_HOURS = 6`). MMT is represented here as a proper fixed-offset
`datetime.timezone` of +06:30, so every conversion goes through Python's own
timezone-aware arithmetic rather than ad hoc integer hour math.
"""
from __future__ import annotations

import datetime as dt

MMT = dt.timezone(dt.timedelta(hours=6, minutes=30), name="MMT")


def ensure_utc(ts: dt.datetime) -> dt.datetime:
    """Raise if `ts` is naive; normalize to UTC if it carries another tzinfo."""
    if ts.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: scheduler authority requires tz-aware UTC datetimes")
    return ts.astimezone(dt.timezone.utc)


def utc_to_mmt(ts_utc: dt.datetime) -> dt.datetime:
    """Convert a tz-aware UTC timestamp to MMT for display only. Never used for
    scheduling decisions -- those always operate on the UTC value."""
    return ensure_utc(ts_utc).astimezone(MMT)


def mmt_to_utc(ts_mmt: dt.datetime) -> dt.datetime:
    if ts_mmt.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: MMT timestamp must be tz-aware")
    return ts_mmt.astimezone(dt.timezone.utc)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
