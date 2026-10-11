"""Clock-offset support (spec item 6) for a future Binance USDT-M order path, which would
need to keep local request timestamps within Binance's recvWindow tolerance of the
exchange's serverTime. No network call anywhere here -- "server time" is always a
caller-supplied datetime (a test double in every call in this phase; a future live phase
would populate it from GET /fapi/v1/time, which this module does not call).

Threshold: Binance's Futures API "Timing Security" documentation caps recvWindow at
5000ms and rejects a request once (serverTime - timestamp) exceeds it. This module
documents a CONSERVATIVE default of 1000ms (1s) -- well under that 5000ms ceiling -- as a
judgment call pending live-verified round-trip latency in a future authorized phase; it is
not itself measured or fetched from anywhere live.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# Conservative default; see module docstring for the reasoning and its relationship to
# Binance's documented <=5000ms recvWindow ceiling.
DEFAULT_MAX_OFFSET_MS = 1000


class ClockOffsetExceeded(RuntimeError):
    """Raised by require_offset_within_threshold() when |offset_ms| > max_offset_ms."""

    def __init__(self, offset_ms: int, threshold_ms: int):
        super().__init__(
            f"clock offset {offset_ms}ms exceeds threshold {threshold_ms}ms -- refusing to "
            "treat local time as trustworthy for this cycle."
        )
        self.offset_ms = offset_ms
        self.threshold_ms = threshold_ms


@dataclass(frozen=True)
class ClockOffset:
    """offset_ms = server_time - local_time, in milliseconds, at the moment `local_time`
    was captured. Positive means the exchange clock is AHEAD of local; negative means the
    exchange clock is BEHIND local."""

    offset_ms: int
    measured_at: datetime  # the local_time this offset was measured against


def measure_offset(server_time: datetime, local_time: datetime) -> ClockOffset:
    """Pure computation -- both timestamps are caller-supplied (test doubles in this
    phase). No network call."""
    delta = server_time - local_time
    offset_ms = int(round(delta.total_seconds() * 1000))
    return ClockOffset(offset_ms=offset_ms, measured_at=local_time)


def apply_offset(local_time: datetime, offset: ClockOffset) -> datetime:
    """Produces a corrected timestamp: local_time shifted by the previously-measured
    offset. Does not re-measure -- callers needing a fresh correction must call
    measure_offset() again (see "refresh" test case)."""
    return local_time + timedelta(milliseconds=offset.offset_ms)


def require_offset_within_threshold(offset: ClockOffset, *, max_offset_ms: int = DEFAULT_MAX_OFFSET_MS) -> None:
    """Fail closed: raises ClockOffsetExceeded if the measured offset's magnitude exceeds
    max_offset_ms. Callers should call this immediately after measure_offset() and before
    trusting any offset-corrected timestamp for a future exchange request."""
    if abs(offset.offset_ms) > max_offset_ms:
        raise ClockOffsetExceeded(offset.offset_ms, max_offset_ms)
