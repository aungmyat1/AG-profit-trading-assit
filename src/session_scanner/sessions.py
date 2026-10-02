"""Deterministic UTC session engine.

Session windows come from config/canonical_sessions.yaml (single source of truth,
half-open [start, end)). Composite trade cycles (ASIAN_LONDON, LONDON_NEWYORK) come from
the strategy contract's own session_pairs -- e.g. ST_ASIAN_SWEEP_5R_V1's London trade
window starts 07:00, not canonical 06:00, and that deviation is the contract's, not ours.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

import yaml

CANONICAL_SESSIONS_PATH = "config/canonical_sessions.yaml"
_DISPLAY = {"asian": "ASIAN", "london_am": "LONDON", "new_york_am": "NEW_YORK"}
OFF_SESSION = "OFF_SESSION"


@dataclass(frozen=True)
class Window:
    name: str
    start: time
    end: time

    def bounds(self, day: date) -> Tuple[datetime, datetime]:
        s = datetime.combine(day, self.start, tzinfo=timezone.utc)
        e = datetime.combine(day, self.end, tzinfo=timezone.utc)
        return s, e


def load_canonical_windows(path: str = CANONICAL_SESSIONS_PATH) -> List[Window]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if cfg.get("timezone") != "UTC" or cfg.get("boundary_policy") != "half_open":
        raise ValueError("canonical_sessions.yaml must be UTC half_open")
    out = [Window(_DISPLAY.get(k, k.upper()), time.fromisoformat(v["start"]), time.fromisoformat(v["end"]))
           for k, v in cfg["sessions"].items()]
    return sorted(out, key=lambda w: w.start)


def _timeline(windows: Sequence[Window], day: date) -> List[Tuple[str, datetime, datetime]]:
    """Contiguous [start, end) segments for `day`, with OFF_SESSION filling the holes."""
    segs, cursor = [], datetime.combine(day, time(0), tzinfo=timezone.utc)
    day_end = cursor + timedelta(days=1)
    for w in windows:
        s, e = w.bounds(day)
        if s > cursor:
            segs.append((OFF_SESSION, cursor, s))
        segs.append((w.name, s, e))
        cursor = e
    if cursor < day_end:
        segs.append((OFF_SESSION, cursor, day_end))
    return segs


@dataclass(frozen=True)
class SessionContext:
    now_utc: datetime
    current_session: str
    previous_session: str
    next_session: str
    session_open_utc: datetime
    session_close_utc: datetime
    minutes_to_close: int
    active_cycle: Optional[str]  # strategy pair whose TRADE window contains now
    active_cycle_window: Optional[Tuple[datetime, datetime]]

    def as_dict(self) -> dict:
        return {"now_utc": self.now_utc.isoformat(), "current_session": self.current_session,
                "previous_session": self.previous_session, "next_session": self.next_session,
                "session_open_utc": self.session_open_utc.isoformat(),
                "session_close_utc": self.session_close_utc.isoformat(),
                "minutes_to_close": self.minutes_to_close, "active_cycle": self.active_cycle,
                "active_cycle_window_utc": [d.isoformat() for d in self.active_cycle_window]
                if self.active_cycle_window else None}


def classify(now_utc: datetime, windows: Sequence[Window],
             cycles: Dict[str, Tuple[time, time]]) -> SessionContext:
    day = now_utc.date()
    segs = _timeline(windows, day - timedelta(days=1)) + _timeline(windows, day) + _timeline(windows, day + timedelta(days=1))
    idx = next(i for i, (_, s, e) in enumerate(segs) if s <= now_utc < e)
    name, s, e = segs[idx]
    prev_name = next(n for n, _, _ in reversed(segs[:idx]) if n != OFF_SESSION)
    next_name = next(n for n, _, _ in segs[idx + 1:] if n != OFF_SESSION)

    active, active_win = None, None
    for cycle_id, (cs, ce) in cycles.items():
        ws = datetime.combine(day, cs, tzinfo=timezone.utc)
        we = datetime.combine(day, ce, tzinfo=timezone.utc)
        if ws <= now_utc < we:
            active, active_win = cycle_id, (ws, we)
    return SessionContext(now_utc, name, prev_name, next_name, s, e,
                          int((e - now_utc).total_seconds() // 60), active, active_win)


def window_levels(bars, start: datetime, end: datetime, expected_bars: int) -> dict:
    """High/low of closed bars in [start, end). `complete` only if every expected bar is present."""
    inside = [b for b in bars if start <= b.time_utc < end]
    if not inside:
        return {"high": None, "low": None, "bars": 0, "expected_bars": expected_bars, "complete": False}
    return {"high": max(b.high for b in inside), "low": min(b.low for b in inside), "bars": len(inside),
            "expected_bars": expected_bars, "complete": len(inside) >= expected_bars}


def previous_day_levels(h1_closed, today: date) -> dict:
    """Previous UTC trading day's high/low from closed H1 bars (walks back over days with no bars)."""
    for back in range(1, 5):
        d = today - timedelta(days=back)
        day_bars = [b for b in h1_closed if b.time_utc.date() == d]
        if day_bars:
            return {"date": d.isoformat(), "high": max(b.high for b in day_bars),
                    "low": min(b.low for b in day_bars), "h1_bars": len(day_bars)}
    return {"date": None, "high": None, "low": None, "h1_bars": 0}
