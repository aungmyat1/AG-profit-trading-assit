"""History normalization, data-quality gate, and bounded head-sync protocol.

Nothing here repairs, fills, or synthesizes bars. A series is VALID, or it is not used.
"""
from __future__ import annotations

import logging
import time as _time
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from typing import Callable, List, Optional, Sequence, Tuple

from host_evidence.symbol_metadata import DstHourError

from .timebase import TimeAuthority, parse_server_wallclock

_log = logging.getLogger(__name__)

VALID = "VALID"
STALE = "STALE"
GAPPED = "GAPPED"
INSUFFICIENT = "INSUFFICIENT"
INVALID = "INVALID"
FRESH = "FRESH"

TF_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60, "D1": 1440}


@dataclass(frozen=True)
class Bar:
    time_utc: datetime  # bar-open time, tz-aware UTC
    open: float
    high: float
    low: float
    close: float
    tick_volume: float = 0.0
    spread_points: Optional[int] = None


@dataclass(frozen=True)
class SeriesQuality:
    timeframe: str
    status: str
    bar_count: int
    closed_count: int
    last_closed_bar_utc: Optional[datetime]
    current_forming_bar_utc: Optional[datetime]
    expected_last_closed_bar_utc: Optional[datetime]
    unexpected_gaps: Tuple[str, ...] = ()
    expected_closure_gaps: int = 0
    issues: Tuple[str, ...] = ()

    def as_dict(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"timeframe": self.timeframe, "status": self.status, "bar_count": self.bar_count,
                "closed_count": self.closed_count, "last_closed_bar_utc": iso(self.last_closed_bar_utc),
                "current_forming_bar_utc": iso(self.current_forming_bar_utc),
                "expected_last_closed_bar_utc": iso(self.expected_last_closed_bar_utc),
                "unexpected_gaps": list(self.unexpected_gaps), "expected_closure_gaps": self.expected_closure_gaps,
                "issues": list(self.issues)}


@dataclass(frozen=True)
class SyncedSeries:
    bars: Tuple[Bar, ...]
    quality: SeriesQuality
    first_read_status: str
    retry_performed: bool
    second_read_status: Optional[str]
    retry_error: Optional[str] = None

    @property
    def closed(self) -> List[Bar]:
        lc = self.quality.last_closed_bar_utc
        return [b for b in self.bars if lc is not None and b.time_utc <= lc]

    def as_dict(self) -> dict:
        d = self.quality.as_dict()
        d.update(first_read_status=self.first_read_status, retry_performed=self.retry_performed,
                 second_read_status=self.second_read_status, retry_error=self.retry_error,
                 data_quality_gate="PASS" if self.quality.status == VALID else "FAIL")
        return d


def normalize_bars(raw: Sequence[dict], ta: TimeAuthority) -> List[Bar]:
    out = []
    for r in raw:
        try:
            time_utc = ta.server_to_utc(parse_server_wallclock(str(r["time"])))
        except DstHourError as exc:  # no single UTC instant: drop + log, never fold
            _log.warning("DROPPED_BAR %s %s", exc.reason_code, exc.server_wall_clock.isoformat())
            continue
        out.append(Bar(time_utc=time_utc,
                       open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]),
                       tick_volume=float(r.get("tick_volume") or 0.0),
                       spread_points=int(r["spread"]) if r.get("spread") is not None else None))
    return out


# ---------------------------------------------------------------------- expected closures

def _in_daily_break(server_start: datetime, server_end: datetime, daily_break: Optional[tuple]) -> bool:
    if not daily_break or server_start.date() != (server_end - timedelta(microseconds=1)).date():
        return False
    b0, b1 = (time.fromisoformat(x) for x in daily_break)
    return b0 <= server_start.time() and (server_end - timedelta(microseconds=1)).time() < b1


def _in_weekend(server_start: datetime, server_end: datetime) -> bool:
    last = server_end - timedelta(microseconds=1)
    return server_start.weekday() >= 5 and last.weekday() >= 5 and (last - server_start) < timedelta(days=2)


def is_expected_closure(bar_open_utc: datetime, timeframe: str, ta: TimeAuthority,
                        daily_break_server: Optional[tuple]) -> bool:
    start = ta.utc_to_server(bar_open_utc)
    end = start + timedelta(minutes=TF_MINUTES[timeframe])
    return _in_weekend(start, end) or (timeframe != "D1" and _in_daily_break(start, end, daily_break_server))


def _floor_server(server_dt: datetime, timeframe: str) -> datetime:
    if timeframe == "D1":
        return server_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    m = TF_MINUTES[timeframe]
    minutes = server_dt.hour * 60 + server_dt.minute
    return server_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minutes - minutes % m)


def expected_last_closed(now_utc: datetime, timeframe: str, ta: TimeAuthority,
                         daily_break_server: Optional[tuple]) -> datetime:
    step = timedelta(minutes=TF_MINUTES[timeframe])
    if TF_MINUTES[timeframe] <= 60:
        # Whole-hour offset: an intraday server-bar boundary is the same boundary in UTC, and
        # flooring in UTC never lands on a repeated/skipped server hour.
        epoch = int(now_utc.timestamp()) // (TF_MINUTES[timeframe] * 60) * TF_MINUTES[timeframe] * 60
        candidate = datetime.fromtimestamp(epoch, timezone.utc) - step
    else:
        candidate = ta.server_to_utc(_floor_server(ta.utc_to_server(now_utc), timeframe)) - step
    for _ in range(4 * 24 * 12):  # bounded walk back over at most a long weekend
        if not is_expected_closure(candidate, timeframe, ta, daily_break_server):
            return candidate
        candidate -= step
    return candidate


# ---------------------------------------------------------------------- assessment

def assess_series(bars: Sequence[Bar], timeframe: str, now_utc: datetime, ta: TimeAuthority,
                  daily_break_server: Optional[tuple], min_bars: int) -> SeriesQuality:
    step = timedelta(minutes=TF_MINUTES[timeframe])
    issues: List[str] = []

    for b in bars:
        if min(b.open, b.high, b.low, b.close) <= 0:
            issues.append(f"NONPOSITIVE_PRICE@{b.time_utc.isoformat()}")
        elif b.high < max(b.open, b.close) or b.low > min(b.open, b.close) or b.low > b.high:
            issues.append(f"BAD_OHLC@{b.time_utc.isoformat()}")
    for prev, cur in zip(bars, bars[1:]):
        if cur.time_utc == prev.time_utc:
            issues.append(f"DUPLICATE_BAR@{cur.time_utc.isoformat()}")
        elif cur.time_utc < prev.time_utc:
            issues.append(f"NON_MONOTONIC@{cur.time_utc.isoformat()}")

    # Closed vs forming: a bar is closed only once its full interval has elapsed.
    closed = [b for b in bars if b.time_utc + step <= now_utc]
    forming = [b for b in bars if b.time_utc + step > now_utc]
    last_closed = closed[-1].time_utc if closed else None
    exp_last = expected_last_closed(now_utc, timeframe, ta, daily_break_server)

    def build(status, gaps=(), expected_gaps=0):
        return SeriesQuality(timeframe, status, len(bars), len(closed), last_closed,
                             forming[-1].time_utc if forming else None, exp_last,
                             tuple(gaps), expected_gaps, tuple(issues))

    if issues:
        return build(INVALID)
    if len(closed) < min_bars:
        return build(INSUFFICIENT)

    unexpected, expected_n = [], 0
    for prev, cur in zip(closed, closed[1:]):
        t = prev.time_utc + step
        while t < cur.time_utc:
            if is_expected_closure(t, timeframe, ta, daily_break_server):
                expected_n += 1
            else:
                unexpected.append(f"{prev.time_utc.isoformat()}->{cur.time_utc.isoformat()}")
                break
            t += step
    if unexpected:
        return build(GAPPED, unexpected, expected_n)
    if last_closed < exp_last:
        return build(STALE, (), expected_n)
    return build(VALID, (), expected_n)


def _failed_quality(assess: Callable[[List[Bar]], SeriesQuality], error: Exception) -> SeriesQuality:
    """Represent a source read failure as a failed gate without fabricating bars."""
    q = assess([])
    return replace(q, status=INVALID, issues=q.issues + (f"READ_ERROR:{type(error).__name__}",))


def fetch_with_sync(fetch: Callable[[], List[Bar]], assess: Callable[[List[Bar]], SeriesQuality],
                    retry_delay_s: float = 0.0, sleep: Callable[[float], None] = _time.sleep) -> SyncedSeries:
    """INITIAL_READ + at most ONE SYNC_RETRY.

    A failed first or second read is a failed data-quality gate. The function never
    retries unboundedly and never turns a missing read into synthetic bars.
    """
    first_error = None
    try:
        first = fetch()
        q1 = assess(first)
    except Exception as exc:
        first, first_error = [], exc
        q1 = _failed_quality(assess, exc)
    if q1.status == VALID:
        return SyncedSeries(tuple(first), q1, q1.status, False, None)
    if retry_delay_s > 0:
        sleep(retry_delay_s)
    try:
        second = fetch()
        q2 = assess(second)
        retry_error = None
    except Exception as exc:
        second, retry_error = [], exc
        q2 = _failed_quality(assess, exc)
    return SyncedSeries(tuple(second), q2, q1.status, True, q2.status,
                        type(retry_error or first_error).__name__ if (retry_error or first_error) else None)


# ---------------------------------------------------------------------- quote

@dataclass(frozen=True)
class Quote:
    broker_symbol: str
    bid: float
    ask: float
    tick_time_utc: datetime
    spread_points: int
    spread_price: float
    spread_pips: float
    spread_pct: float
    status: str  # FRESH | STALE | INVALID
    age_seconds: float
    source: str = "TERMINAL_MCP.get_chart_ticks_history"

    def as_dict(self) -> dict:
        return {"broker_symbol": self.broker_symbol, "bid": self.bid, "ask": self.ask,
                "timestamp_utc": self.tick_time_utc.isoformat(), "spread_points": self.spread_points,
                "spread_price": round(self.spread_price, 10), "spread_pips": round(self.spread_pips, 3),
                "spread_pct": round(self.spread_pct, 8),
                "status": self.status, "age_seconds": round(self.age_seconds, 1), "source": self.source}


def assess_quote(broker_symbol: str, tick: Optional[dict], ta: TimeAuthority, now_utc: datetime,
                 point: float, pip_size: float, max_age_s: int,
                 source: str = "TERMINAL_MCP.get_chart_ticks_history") -> Optional[Quote]:
    if not tick:
        return None
    try:
        t = ta.server_to_utc(parse_server_wallclock(str(tick["time_ms"])))
    except DstHourError as exc:  # a quote in the repeated/skipped hour is unusable: no quote
        _log.warning("DROPPED_QUOTE %s %s %s", exc.reason_code, broker_symbol, exc.server_wall_clock.isoformat())
        return None
    bid, ask = float(tick["bid"]), float(tick["ask"])
    age = (now_utc - t).total_seconds()
    spread = ask - bid
    if bid <= 0 or ask <= 0 or bid > ask:
        status = INVALID
    elif age > max_age_s:
        status = STALE
    else:
        status = FRESH
    return Quote(broker_symbol, bid, ask, t, int(round(spread / point)), spread, spread / pip_size,
                 (spread / bid) * 100 if bid else 0.0, status, age, source)
