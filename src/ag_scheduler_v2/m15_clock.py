"""M15 bar-close wake architecture (spec section 8). During active FX windows the
scheduler wakes near :00/:15/:30/:45 rather than continuously polling, but never
assumes a bar is complete merely because wall-clock time crossed the boundary -- it
requires confirmation that the data provider actually delivered the closed bar, within
a bounded settlement tolerance.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from ag_scheduler_v2.config_loader import load_config

_MINUTE_MARKS = (0, 15, 30, 45)

DATA_STALE = "DATA_STALE"


def next_m15_close_utc(now_utc: dt.datetime) -> dt.datetime:
    if now_utc.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: next_m15_close_utc requires tz-aware UTC")
    now_utc = now_utc.astimezone(dt.timezone.utc)
    floor_minute = (now_utc.minute // 15) * 15
    candidate = now_utc.replace(minute=floor_minute, second=0, microsecond=0)
    if candidate <= now_utc:
        candidate += dt.timedelta(minutes=15)
    return candidate


def previous_m15_close_utc(now_utc: dt.datetime) -> dt.datetime:
    if now_utc.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: previous_m15_close_utc requires tz-aware UTC")
    now_utc = now_utc.astimezone(dt.timezone.utc)
    floor_minute = (now_utc.minute // 15) * 15
    candidate = now_utc.replace(minute=floor_minute, second=0, microsecond=0)
    if candidate == now_utc:
        return candidate - dt.timedelta(minutes=15)
    return candidate


@dataclass(frozen=True)
class BarSettlementPolicy:
    """Mechanism only -- Phase-1 owner hypotheses read from config, never optimized here
    (spec section 41). `close_settlement_seconds` is how long past the wall-clock close
    the scheduler waits before even checking for the bar; `maximum_wait_seconds` bounds
    total wait before declaring DATA_STALE."""

    close_settlement_seconds: float
    maximum_wait_seconds: float

    @classmethod
    def from_config(cls, path: Optional[str] = None) -> "BarSettlementPolicy":
        raw = (load_config(path).get("m15_event") or {})
        if "close_settlement_seconds" not in raw or "maximum_wait_seconds" not in raw:
            raise ValueError("SCHEDULER_CONFIG_CONFLICT: m15_event.close_settlement_seconds/maximum_wait_seconds required")
        return cls(
            close_settlement_seconds=float(raw["close_settlement_seconds"]),
            maximum_wait_seconds=float(raw["maximum_wait_seconds"]),
        )

    def earliest_check_utc(self, bar_close_utc: dt.datetime) -> dt.datetime:
        return bar_close_utc + dt.timedelta(seconds=self.close_settlement_seconds)

    def deadline_utc(self, bar_close_utc: dt.datetime) -> dt.datetime:
        return bar_close_utc + dt.timedelta(seconds=self.maximum_wait_seconds)


@dataclass(frozen=True)
class BarAvailabilityResult:
    available: bool
    reason_code: Optional[str] = None


def confirm_bar_available(
    *,
    bar_close_utc: dt.datetime,
    provider_latest_closed_bar_utc: Optional[dt.datetime],
    now_utc: dt.datetime,
    policy: BarSettlementPolicy,
) -> BarAvailabilityResult:
    """`provider_latest_closed_bar_utc` is whatever the market-data adapter reports as
    the most recent bar it has actually delivered (the close timestamp of that bar), or
    None if the provider has nothing yet. A bar is available only once the provider's
    own delivered close timestamp is at or past the bar we're waiting for -- wall-clock
    time crossing the boundary is never sufficient by itself."""
    if provider_latest_closed_bar_utc is not None and provider_latest_closed_bar_utc >= bar_close_utc:
        return BarAvailabilityResult(available=True)
    if now_utc >= policy.deadline_utc(bar_close_utc):
        return BarAvailabilityResult(available=False, reason_code=DATA_STALE)
    return BarAvailabilityResult(available=False, reason_code="AWAITING_SETTLEMENT")
