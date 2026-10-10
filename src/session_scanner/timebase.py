"""Time authority: UTC is the scanner's only internal clock.

MT5 stamps bars/ticks in broker SERVER wall-clock time. The live offset is derived at runtime
from the Terminal's own get_time_information, corroborated by the freshest broker tick when
available, and rounded to the broker-offset granularity; it is a GATE only. Bars and ticks are
converted PER TIMESTAMP with the VT rule (server wall clock = New York wall clock + 7h,
host_evidence.symbol_metadata.OFFSET_RULE), so a lookback spanning a US DST change is not
shifted by one run-wide offset (CS-DST-AUDIT-01 A1). A live offset that disagrees with the
rule at `utc_now` fails the gate.

mt5ReadOnly labels server wall-clock times with a "Z"/"+00:00" suffix although they are
not UTC; parse_server_wallclock() deliberately discards any such label so a wrong label
can never shift session classification.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from host_evidence.symbol_metadata import server_time_to_utc, server_utc_offset_hours, utc_to_server_time

TIME_GATE_PASS = "PASS"
TIME_GATE_FAIL = "FAIL"

_TZ_SUFFIX = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")


@dataclass(frozen=True)
class TimeAuthority:
    gate: str
    utc_now: Optional[datetime]
    broker_server_now: Optional[datetime]
    broker_utc_offset: Optional[timedelta]
    offset_source: str
    offset_confidence: str  # HIGH | MEDIUM | NONE
    reason: str = ""

    def server_to_utc(self, server_wallclock: datetime) -> datetime:
        """Per-timestamp rule conversion; raises DstHourError inside the repeated/skipped hour."""
        return server_time_to_utc(server_wallclock.replace(tzinfo=None))

    def utc_to_server(self, utc_dt: datetime) -> datetime:
        return utc_to_server_time(utc_dt.astimezone(timezone.utc))

    def as_dict(self) -> dict:
        return {
            "time_gate": self.gate,
            "utc_time": self.utc_now.isoformat() if self.utc_now else None,
            "broker_time": self.broker_server_now.isoformat() if self.broker_server_now else None,
            "broker_utc_offset": _fmt_offset(self.broker_utc_offset),
            "offset_source": self.offset_source,
            "offset_confidence": self.offset_confidence,
            "reason": self.reason,
        }


def _fmt_offset(offset: Optional[timedelta]) -> Optional[str]:
    if offset is None:
        return None
    minutes = int(offset.total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    return f"UTC{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def parse_server_wallclock(value: str) -> datetime:
    """Broker server wall-clock string -> naive datetime. Any timezone label is ignored."""
    text = value.strip().replace(" ", "T")
    text = _TZ_SUFFIX.sub("", text)
    return datetime.fromisoformat(text)


def _round_offset(raw: timedelta, granularity_min: int) -> timedelta:
    step = granularity_min * 60
    return timedelta(seconds=round(raw.total_seconds() / step) * step)


def derive_time_authority(
    time_info: dict,
    latest_tick_server: Optional[datetime] = None,
    local_utc_now: Optional[datetime] = None,
    granularity_min: int = 15,
    max_staleness_s: int = 120,
    max_local_skew_s: int = 60,
) -> TimeAuthority:
    def fail(reason: str) -> TimeAuthority:
        return TimeAuthority(TIME_GATE_FAIL, None, None, None, "NONE", "NONE", reason)

    try:
        utc_now = parse_server_wallclock(time_info["utc_time"]).replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return fail("TERMINAL_UTC_TIME_MISSING")

    if local_utc_now is not None and abs((utc_now - local_utc_now).total_seconds()) > max_local_skew_s:
        return fail("TERMINAL_VS_LOCAL_UTC_SKEW")

    estimates = []
    server_known = time_info.get("trade_server_last_known_time")
    if server_known:
        estimates.append(("terminal.get_time_information.trade_server_last_known_time",
                          parse_server_wallclock(server_known)))
    if latest_tick_server is not None:
        estimates.append(("terminal.latest_broker_tick", latest_tick_server))
    if not estimates:
        return fail("NO_BROKER_CLOCK_SOURCE")

    accepted = []
    for source, server_dt in estimates:
        raw = server_dt - utc_now.replace(tzinfo=None)
        offset = _round_offset(raw, granularity_min)
        residual = abs((raw - offset).total_seconds())
        # A stale server clock (e.g. market closed) lags behind and is only usable while its
        # residual stays inside the staleness bound.
        if residual <= max_staleness_s and timedelta(hours=-12) <= offset <= timedelta(hours=14):
            accepted.append((source, offset))

    if not accepted:
        return fail("BROKER_CLOCK_STALE_OR_IMPLAUSIBLE")
    offsets = {o for _, o in accepted}
    if len(offsets) > 1:
        return fail("BROKER_OFFSET_SOURCES_DISAGREE")

    offset = accepted[0][1]
    if offset != timedelta(hours=server_utc_offset_hours(utc_now)):
        return fail("BROKER_OFFSET_RULE_MISMATCH")
    confidence = "HIGH" if len(accepted) >= 2 else "MEDIUM"
    source = "+".join(s for s, _ in accepted)
    return TimeAuthority(TIME_GATE_PASS, utc_now, (utc_now + offset).replace(tzinfo=None), offset, source, confidence)
