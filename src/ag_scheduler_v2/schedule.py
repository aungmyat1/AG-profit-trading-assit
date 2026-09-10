"""Canonical daily schedule (spec section 3/4): deterministic UTC state resolution and
transition logging. All boundaries are half-open [start, end) UTC, sourced from
config/ag_scheduler_v2.yaml -- never hardcoded here, matching session_clock.py's
"read the contract, don't redefine it" convention.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from ag_scheduler_v2.config_loader import SchedulerConfigConflict, load_config

# Explicit state vocabulary (spec section 4).
PRE_FLIGHT = "PRE_FLIGHT"
BTC_OBSERVE = "BTC_OBSERVE"
BTC_FINALIZE = "BTC_FINALIZE"
PRE_LONDON_REFERENCE = "PRE_LONDON_REFERENCE"
PRE_LONDON_READINESS = "PRE_LONDON_READINESS"
WINDOW_ASIAN_LONDON = "WINDOW_ASIAN_LONDON"
POST_LONDON = "POST_LONDON"
STANDBY = "STANDBY"
PRE_NEW_YORK = "PRE_NEW_YORK"
WINDOW_LONDON_NEWYORK = "WINDOW_LONDON_NEWYORK"
POST_NEW_YORK = "POST_NEW_YORK"
P1_RESEARCH = "P1_RESEARCH"
RECOVERY = "RECOVERY"
DEGRADED = "DEGRADED"
STOPPED = "STOPPED"

_ORDERED_SCHEDULE_STATES = (
    PRE_FLIGHT, BTC_OBSERVE, BTC_FINALIZE, PRE_LONDON_REFERENCE, PRE_LONDON_READINESS,
    WINDOW_ASIAN_LONDON, POST_LONDON, STANDBY, PRE_NEW_YORK, WINDOW_LONDON_NEWYORK,
    POST_NEW_YORK, P1_RESEARCH,
)

P0_STATES = frozenset({
    PRE_FLIGHT, BTC_OBSERVE, BTC_FINALIZE, PRE_LONDON_REFERENCE, PRE_LONDON_READINESS,
    WINDOW_ASIAN_LONDON, POST_LONDON, PRE_NEW_YORK, WINDOW_LONDON_NEWYORK, POST_NEW_YORK,
})
P1_STATES = frozenset({P1_RESEARCH})
# STANDBY is neither pure P0 nor pure P1 -- its P1 eligibility is config-gated
# (spec section 6); see resource_classes.py.


@dataclass(frozen=True)
class ScheduleEntry:
    state: str
    start: dt.time
    end: Optional[dt.time]  # None => open-ended (P1_RESEARCH runs until next PRE_FLIGHT)


def _parse_hhmm(value: str) -> dt.time:
    hour, minute = value.split(":")
    return dt.time(int(hour), int(minute))


@lru_cache(maxsize=1)
def load_schedule(path: Optional[str] = None) -> tuple:
    raw = load_config(path)
    entries_raw = raw.get("schedule")
    if not entries_raw:
        raise SchedulerConfigConflict("SCHEDULER_CONFIG_CONFLICT: schedule is missing/empty")

    entries = []
    for item in entries_raw:
        state = item.get("state")
        if state not in _ORDERED_SCHEDULE_STATES:
            raise SchedulerConfigConflict(f"SCHEDULER_CONFIG_CONFLICT: unknown schedule state {state!r}")
        start = _parse_hhmm(item["start"])
        end = _parse_hhmm(item["end"]) if item.get("end") is not None else None
        entries.append(ScheduleEntry(state=state, start=start, end=end))

    seen_states = [e.state for e in entries]
    if seen_states != list(_ORDERED_SCHEDULE_STATES):
        raise SchedulerConfigConflict(
            "SCHEDULER_CONFIG_CONFLICT: schedule states must appear exactly once, in canonical order: "
            f"expected {list(_ORDERED_SCHEDULE_STATES)}, got {seen_states}"
        )

    for prev, cur in zip(entries, entries[1:]):
        if prev.end is None:
            raise SchedulerConfigConflict(
                f"SCHEDULER_CONFIG_CONFLICT: only the final schedule entry may be open-ended, "
                f"but {prev.state!r} (not last) has end=null"
            )
        if prev.end != cur.start:
            raise SchedulerConfigConflict(
                f"SCHEDULER_CONFIG_CONFLICT: schedule gap/overlap between {prev.state!r} (ends {prev.end}) "
                f"and {cur.state!r} (starts {cur.start})"
            )
    if entries[-1].end is not None:
        raise SchedulerConfigConflict(
            f"SCHEDULER_CONFIG_CONFLICT: final schedule entry {entries[-1].state!r} must be open-ended (end=null)"
        )
    if entries[0].state != PRE_FLIGHT:
        raise SchedulerConfigConflict("SCHEDULER_CONFIG_CONFLICT: schedule must start at PRE_FLIGHT")

    return tuple(entries)


def resolve_state(now_utc: dt.datetime, path: Optional[str] = None) -> str:
    """Deterministic state resolution for a UTC instant. The schedule covers the whole
    day except [00:00, PRE_FLIGHT.start) and [P1_RESEARCH.start, 24:00), both of which
    fall inside the open-ended P1_RESEARCH window carried over from the previous day --
    i.e. any time strictly before the first entry's start also resolves to P1_RESEARCH
    (yesterday's research window, not yet rolled into today's PRE_FLIGHT)."""
    if now_utc.tzinfo is None:
        raise ValueError("TIMEZONE_NAIVE_TIMESTAMP: resolve_state requires a tz-aware UTC datetime")
    entries = load_schedule(path)
    t = now_utc.astimezone(dt.timezone.utc).time()

    if t < entries[0].start:
        return P1_RESEARCH
    for entry in entries:
        if entry.end is None or (entry.start <= t < entry.end):
            if entry.end is None and t < entry.start:
                continue
            return entry.state
    # Unreachable given load_schedule's own contiguity validation.
    raise SchedulerConfigConflict(f"SCHEDULER_CONFIG_CONFLICT: no schedule entry covers {t}")


def next_boundary_utc(now_utc: dt.datetime, path: Optional[str] = None) -> dt.datetime:
    """The next UTC instant at which the resolved state changes."""
    entries = load_schedule(path)
    today = now_utc.astimezone(dt.timezone.utc).date()
    t = now_utc.astimezone(dt.timezone.utc).time()

    for entry in entries:
        if entry.end is not None and t < entry.end:
            return dt.datetime.combine(today, entry.end, tzinfo=dt.timezone.utc)
    # Currently in (or before) the open-ended P1_RESEARCH window -- next boundary is
    # tomorrow's PRE_FLIGHT start.
    tomorrow = today + dt.timedelta(days=1)
    return dt.datetime.combine(tomorrow, entries[0].start, tzinfo=dt.timezone.utc)


@dataclass(frozen=True)
class StateTransition:
    from_state: Optional[str]
    to_state: str
    at_utc: dt.datetime


def transitions_between(start_utc: dt.datetime, end_utc: dt.datetime, path: Optional[str] = None) -> tuple:
    """Deterministic, logged list of every state transition in [start_utc, end_utc).
    Used both for real-time transition logging and for recovery reconstruction of
    what states were missed across a restart gap."""
    if end_utc <= start_utc:
        return tuple()
    transitions = []
    cursor = start_utc
    prev_state = resolve_state(cursor, path)
    transitions.append(StateTransition(from_state=None, to_state=prev_state, at_utc=cursor))
    while True:
        boundary = next_boundary_utc(cursor, path)
        if boundary >= end_utc:
            break
        new_state = resolve_state(boundary, path)
        transitions.append(StateTransition(from_state=prev_state, to_state=new_state, at_utc=boundary))
        prev_state = new_state
        cursor = boundary
    return tuple(transitions)
