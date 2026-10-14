"""VT server trading day, shared by the C14 risk snapshot and its tests.

The committed host metadata states the rule SERVER_MIDNIGHT_EQUALS_NEW_YORK_1700: the server clock
runs at America/New_York + 7h, so a server day starts at 17:00 New York on the previous calendar day
(21:00 UTC in US summer time, 22:00 UTC in winter). The captured numeric offset (3) is summer-only
and is never used. Any other rule, server or schema returns None: callers block, never guess.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

OFFSET_RULE = ("SERVER_MIDNIGHT_EQUALS_NEW_YORK_1700: server_utc_offset_hours = "
               "America/New_York UTC offset + 7")
METADATA_SCHEMA = "AG_HOST_SYMBOL_METADATA_V2"
SERVER = "VTMarkets-Demo"
_NY = ZoneInfo("America/New_York")
_SHIFT = timedelta(hours=7)


def rule_ok(metadata: Optional[Mapping[str, Any]]) -> bool:
    return (isinstance(metadata, Mapping) and metadata.get("schema") == METADATA_SCHEMA
            and metadata.get("server") == SERVER and metadata.get("server_utc_offset_rule") == OFFSET_RULE)


def _utc(at: Any) -> Optional[datetime]:
    if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
        return None
    return at.astimezone(timezone.utc)


def server_offset(at_utc: datetime, metadata: Optional[Mapping[str, Any]]) -> Optional[timedelta]:
    """Server-clock minus UTC at an instant (+3h in US summer time, +2h in winter)."""
    at = _utc(at_utc)
    if at is None or not rule_ok(metadata):
        return None
    return at.astimezone(_NY).utcoffset() + _SHIFT


def server_clock(at_utc: datetime, metadata: Optional[Mapping[str, Any]]) -> Optional[datetime]:
    """Server wall-clock time at an instant, as a naive datetime (MT5 times use this clock)."""
    offset = server_offset(at_utc, metadata)
    return None if offset is None else (_utc(at_utc) + offset).replace(tzinfo=None)


def server_day(at_utc: datetime, metadata: Optional[Mapping[str, Any]]) -> Optional[date]:
    clock = server_clock(at_utc, metadata)
    return None if clock is None else clock.date()


def server_day_start_utc(day: date, metadata: Optional[Mapping[str, Any]]) -> Optional[datetime]:
    """UTC instant the server day starts: 17:00 New York on the previous calendar day."""
    if type(day) is not date or not rule_ok(metadata):
        return None
    return datetime.combine(day - timedelta(days=1), time(17), tzinfo=_NY).astimezone(timezone.utc)
