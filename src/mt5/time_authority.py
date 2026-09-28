"""Broker server-time authority: effective-period UTC offsets shared by every symbol on
one broker server (AG_FX_OPPORTUNITY_PLATFORM_V2 P6-R1).

Why not "largest gap" (broker_time.detect_broker_utc_offset_hours): a single missing
reopen bar on ONE symbol (observed live: VTMarkets-Demo USDJPY lacked Monday
2026-09-14 00:00, first bar 00:15) makes that weekend the largest gap and the whole
clock is derived from an incomplete bar. Here:

* every weekly reopen in the evidence is an observation; a reading that does not
  resolve to a whole-hour offset (broker_time.offset_from_reopen) is REJECTED as
  evidence -- missing bars never redefine the clock, and history is never filled in;
* observations are grouped per week (true-UTC NY-17:00 reopen instant) into one
  TimeAuthorityPeriod per (broker, server, [reopen_k, reopen_k+1)) -- the offset may
  differ per period, so DST changes are data-derived, never a hardcoded +3;
* evidence is pooled across symbols of the SAME server connection; valid observations
  that disagree within a period raise TimeAuthorityConflict (no majority vote);
* no valid observation for the needed period raises TimeAuthorityUnavailable.

Pure: no MT5 import. mt5.market_data supplies server identity and broker-clock bar times.
Naive datetimes are broker wall-clock readings; aware datetimes are true UTC.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .broker_time import MIN_WEEKEND_GAP, BrokerTimeError, offset_from_reopen

# The latest known period stays authoritative until just before the earliest possible
# next weekly reopen (a US DST start moves the reopen one hour earlier in UTC).
_LATEST_PERIOD_SPAN = timedelta(days=7) - timedelta(hours=1)
# Adjacent weekly reopens are 7d apart, +-1h across a US DST change.
_MAX_WEEK_SPAN = timedelta(days=7) + timedelta(hours=1)

SOURCE_SERVER_CONSENSUS = "SERVER_CONSENSUS"  # >= 2 same-server symbols agree
SOURCE_SERVER_SHARED = "SERVER_SHARED"        # one same-server symbol, not the requester
SOURCE_SYMBOL_LOCAL = "SYMBOL_LOCAL"          # only the requesting symbol (bounded fallback)


class TimeAuthorityUnavailable(BrokerTimeError):
    """No valid server-time evidence covers the requested instant -- fail closed."""


class TimeAuthorityConflict(BrokerTimeError):
    """Valid same-server evidence disagrees about one period's offset -- fail closed."""


@dataclass(frozen=True)
class ReopenObservation:
    symbol: str
    broker_reading: datetime            # naive broker wall clock of the first bar after the gap
    gap: timedelta
    reopen_utc: Optional[datetime]      # aware; None when rejected
    utc_offset_hours: Optional[int]
    status: str                         # VALID | REJECTED_NOT_WHOLE_HOUR
    detail: str = ""


def observe_reopens(symbol: str, broker_times: Sequence[datetime]) -> Tuple[ReopenObservation, ...]:
    """One observation per weekend-sized gap in an ordered naive broker-time series."""
    out: List[ReopenObservation] = []
    for prev, cur in zip(broker_times, broker_times[1:]):
        gap = cur - prev
        if gap < MIN_WEEKEND_GAP:
            continue
        try:
            offset = offset_from_reopen(cur)
        except BrokerTimeError as exc:
            out.append(ReopenObservation(symbol, cur, gap, None, None, "REJECTED_NOT_WHOLE_HOUR", str(exc)))
            continue
        reopen = (cur - timedelta(hours=offset)).replace(minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
        out.append(ReopenObservation(symbol, cur, gap, reopen, offset, "VALID"))
    return tuple(out)


@dataclass(frozen=True)
class TimeAuthorityPeriod:
    broker: str
    server: str
    effective_from_utc: datetime            # the week's true-UTC reopen instant
    effective_until_utc: Optional[datetime]  # next known reopen; None == latest known period
    utc_offset_hours: int                    # server_time = true_utc + offset
    source: str
    evidence_symbols: Tuple[str, ...]

    def coverage_end(self) -> Tuple[datetime, str]:
        """(exclusive end, basis). A period never reaches past its own week: a missing or
        unobserved next week stays uncovered (fail closed), not inheriting this offset."""
        until = self.effective_until_utc
        if until is None or until > self.effective_from_utc + _MAX_WEEK_SPAN:
            return self.effective_from_utc + _LATEST_PERIOD_SPAN, "WEEK_BOUND"
        return until, "NEXT_REOPEN"

    def covers_utc(self, t: datetime) -> bool:
        return self.effective_from_utc <= t < self.coverage_end()[0]

    def provenance(self, symbol: str) -> Dict[str, object]:
        return {
            "broker": self.broker,
            "server": self.server,
            "effective_from_utc": self.effective_from_utc.isoformat(),
            "effective_until_utc": self.coverage_end()[0].isoformat(),
            "effective_until_basis": self.coverage_end()[1],
            "utc_offset_hours": self.utc_offset_hours,
            "source": self.source,
            "evidence_symbols": list(self.evidence_symbols),
            "scope": "SYMBOL_LOCAL" if self.evidence_symbols == (symbol,) else "SERVER_SHARED",
        }


def resolve_periods(
    broker: str, server: str, requesting_symbol: str, observations: Iterable[ReopenObservation],
) -> Tuple[TimeAuthorityPeriod, ...]:
    """Group VALID observations by week; one agreed offset per week or TimeAuthorityConflict."""
    weeks: Dict[datetime, Dict[str, int]] = {}
    for ob in observations:
        if ob.status != "VALID":
            continue
        weeks.setdefault(ob.reopen_utc, {})[ob.symbol] = ob.utc_offset_hours
    starts = sorted(weeks)
    periods = []
    for i, start in enumerate(starts):
        by_symbol = weeks[start]
        offsets = set(by_symbol.values())
        if len(offsets) != 1:
            raise TimeAuthorityConflict(
                f"{broker}/{server}: week {start.isoformat()} offsets disagree {dict(sorted(by_symbol.items()))}")
        symbols = tuple(sorted(by_symbol))
        if len(symbols) >= 2:
            source = SOURCE_SERVER_CONSENSUS
        elif symbols == (requesting_symbol,):
            source = SOURCE_SYMBOL_LOCAL
        else:
            source = SOURCE_SERVER_SHARED
        periods.append(TimeAuthorityPeriod(
            broker=broker, server=server, effective_from_utc=start,
            effective_until_utc=starts[i + 1] if i + 1 < len(starts) else None,
            utc_offset_hours=offsets.pop(), source=source, evidence_symbols=symbols))
    return tuple(periods)


class TimeAuthorityTimeline:
    """Ordered, non-overlapping effective periods for one (broker, server)."""

    def __init__(self, periods: Sequence[TimeAuthorityPeriod]):
        self.periods = tuple(sorted(periods, key=lambda p: p.effective_from_utc))

    def at_utc(self, t: datetime) -> TimeAuthorityPeriod:
        for p in self.periods:
            if p.covers_utc(t):
                return p
        raise TimeAuthorityUnavailable(f"no server-time authority covers {t.isoformat()}")

    def at_broker(self, reading: datetime) -> TimeAuthorityPeriod:
        """Period for a naive broker wall-clock reading.

        A period's broker-clock window starts at its own reopen reading, so across a DST
        change (where the old and new offsets both map e.g. Monday 00:00 into some UTC
        instant) the reading belongs to the LATEST period that has already reopened."""
        started = [p for p in self.periods
                   if p.effective_from_utc.replace(tzinfo=None) + timedelta(hours=p.utc_offset_hours) <= reading]
        if started:
            p = started[-1]
            if p.covers_utc((reading - timedelta(hours=p.utc_offset_hours)).replace(tzinfo=timezone.utc)):
                return p
        raise TimeAuthorityUnavailable(f"no server-time authority covers broker reading {reading.isoformat()}")

    def covering(self, start: datetime, end: datetime) -> Tuple[TimeAuthorityPeriod, ...]:
        """Every period touched by [start, end]; raises unless the whole span is covered."""
        first, last = self.at_utc(start), self.at_utc(end)
        return tuple(p for p in self.periods if first.effective_from_utc <= p.effective_from_utc <= last.effective_from_utc)


def merge_periods(
    known: Mapping[datetime, TimeAuthorityPeriod], new: Iterable[TimeAuthorityPeriod],
) -> Dict[datetime, TimeAuthorityPeriod]:
    """Merge newly resolved periods into previously validated ones (same server).

    A previously validated period is kept unless the new evidence is stronger (more
    symbols); any offset disagreement for the same week raises TimeAuthorityConflict.
    Until-bounds are recomputed from the merged set of reopen instants.
    """
    merged = dict(known)
    for p in new:
        old = merged.get(p.effective_from_utc)
        if old is not None and old.utc_offset_hours != p.utc_offset_hours:
            raise TimeAuthorityConflict(
                f"{p.broker}/{p.server}: week {p.effective_from_utc.isoformat()} previously "
                f"{old.utc_offset_hours}h, now {p.utc_offset_hours}h")
        if old is None or len(p.evidence_symbols) > len(old.evidence_symbols):
            merged[p.effective_from_utc] = p
    starts = sorted(merged)
    return {s: _with_until(merged[s], starts[i + 1] if i + 1 < len(starts) else None) for i, s in enumerate(starts)}


def _with_until(p: TimeAuthorityPeriod, until: Optional[datetime]) -> TimeAuthorityPeriod:
    return TimeAuthorityPeriod(p.broker, p.server, p.effective_from_utc, until, p.utc_offset_hours,
                               p.source, p.evidence_symbols)
