"""Canonical session clock -- the single source of truth consumer for
CANONICAL_SESSION_WINDOWS_V1 (config/canonical_sessions.yaml).

Any active code that needs to know where the Asian / London AM / New York AM market-session
boundaries are should import from this module rather than defining its own hours. See
CANONICAL_SESSION_MIGRATION_REPORT.md for the force-migration this module was introduced under.

Fails closed: a corrupted or reinterpreted contract (wrong timezone, wrong boundary policy,
non-monotonic hours, overlapping sessions) raises SessionContractConflict rather than silently
computing something plausible-looking.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional
import yaml

CONTRACT_VERSION = "CANONICAL_SESSION_WINDOWS_V1"
_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "canonical_sessions.yaml"
_REQUIRED_NAMES = ("asian", "london_am", "new_york_am")


class SessionContractConflict(ValueError):
    """Raised when config/canonical_sessions.yaml is missing, malformed, or reinterpreted."""


@dataclass(frozen=True)
class SessionDefinition:
    name: str
    start_hour: int
    end_hour: int
    expected_m15_bars: int

    @property
    def duration_hours(self) -> int:
        return self.end_hour - self.start_hour


@lru_cache(maxsize=1)
def _raw_contract() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except OSError as exc:
        raise SessionContractConflict(f"SESSION_CONTRACT_CONFLICT: cannot read {_CONFIG_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: canonical_sessions.yaml did not parse to a mapping")
    return raw


@lru_cache(maxsize=1)
def load_canonical_sessions() -> dict[str, SessionDefinition]:
    raw = _raw_contract()

    if raw.get("version") != CONTRACT_VERSION:
        raise SessionContractConflict(
            f"SESSION_CONTRACT_CONFLICT: expected version {CONTRACT_VERSION!r}, got {raw.get('version')!r}"
        )
    if raw.get("timezone") != "UTC":
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: timezone reinterpretation is forbidden (must be UTC)")
    if raw.get("boundary_policy") != "half_open":
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: boundary_policy must be half_open")
    if raw.get("dst_policy") != "fixed_utc":
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: dst_policy must be fixed_utc (no DST/local-time shift)")

    sessions_raw = raw.get("sessions") or {}
    missing = [name for name in _REQUIRED_NAMES if name not in sessions_raw]
    if missing:
        raise SessionContractConflict(f"SESSION_CONTRACT_CONFLICT: missing required session(s) {missing}")

    definitions: dict[str, SessionDefinition] = {}
    for name, spec in sessions_raw.items():
        try:
            start_hour = int(str(spec["start"]).split(":")[0])
            end_hour = int(str(spec["end"]).split(":")[0])
            expected = int(spec["expected_m15_bars"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SessionContractConflict(f"SESSION_CONTRACT_CONFLICT: malformed session {name!r}: {exc}") from exc
        if not (0 <= start_hour < end_hour <= 24):
            raise SessionContractConflict(f"SESSION_CONTRACT_CONFLICT: session {name!r} hours not increasing/in-range")
        if expected != (end_hour - start_hour) * 4:
            raise SessionContractConflict(
                f"SESSION_CONTRACT_CONFLICT: session {name!r} expected_m15_bars={expected} "
                f"does not match duration ({(end_hour - start_hour) * 4} expected for M15)"
            )
        definitions[name] = SessionDefinition(name, start_hour, end_hour, expected)

    _assert_no_overlap(definitions)
    return definitions


def _assert_no_overlap(definitions: dict[str, SessionDefinition]) -> None:
    ordered = sorted(definitions.values(), key=lambda d: d.start_hour)
    for a, b in zip(ordered, ordered[1:]):
        if a.end_hour > b.start_hour:
            raise SessionContractConflict(
                f"SESSION_CONTRACT_CONFLICT: session overlap between {a.name!r} and {b.name!r}"
            )


def validate_session_contract() -> dict[str, SessionDefinition]:
    """Run full integrity checks and return the validated definitions, or raise SessionContractConflict."""
    definitions = load_canonical_sessions()
    asian, london, new_york = definitions["asian"], definitions["london_am"], definitions["new_york_am"]

    assert asian.start_hour < asian.end_hour, "asian hours must be increasing"
    assert london.start_hour < london.end_hour, "london_am hours must be increasing"
    assert new_york.start_hour < new_york.end_hour, "new_york_am hours must be increasing"

    if asian.duration_hours != 6 or asian.expected_m15_bars != 24:
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: asian session must be 6h / 24 M15 bars")
    if london.duration_hours != 5 or london.expected_m15_bars != 20:
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: london_am session must be 5h / 20 M15 bars")
    if new_york.duration_hours != 3 or new_york.expected_m15_bars != 12:
        raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: new_york_am session must be 3h / 12 M15 bars")

    # The 11:00-12:00 UTC gap belongs to neither AM session.
    for hour in (11,):
        if london.start_hour <= hour < london.end_hour:
            raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: 11:00 UTC must not be inside london_am")
        if new_york.start_hour <= hour < new_york.end_hour:
            raise SessionContractConflict("SESSION_CONTRACT_CONFLICT: 11:00 UTC must not be inside new_york_am")

    return definitions


def get_session_definition(name: str) -> SessionDefinition:
    definitions = load_canonical_sessions()
    if name not in definitions:
        raise SessionContractConflict(f"SESSION_CONTRACT_CONFLICT: unknown session name {name!r}")
    return definitions[name]


def get_session_bounds(on_date: date, name: str) -> tuple[datetime, datetime]:
    """Half-open [start, end) UTC bounds for `name` on the given calendar date."""
    d = get_session_definition(name)
    start = datetime.combine(on_date, time(d.start_hour), tzinfo=timezone.utc)
    end = datetime.combine(on_date, time(d.end_hour), tzinfo=timezone.utc) if d.end_hour < 24 \
        else start + timedelta(hours=d.duration_hours)
    return start, end


def is_in_session(ts: datetime, name: str) -> bool:
    d = get_session_definition(name)
    return d.start_hour <= ts.hour < d.end_hour


def session_complete(ts: datetime, on_date: date, name: str) -> bool:
    """True once `ts` is at or past the session's end boundary for `on_date`."""
    _, end = get_session_bounds(on_date, name)
    return ts >= end


def expected_bar_count(name: str, timeframe: str = "M15") -> int:
    d = get_session_definition(name)
    if timeframe == "M15":
        return d.expected_m15_bars
    if timeframe == "M5":
        return d.expected_m15_bars * 3
    if timeframe == "M1":
        return d.expected_m15_bars * 15
    raise SessionContractConflict(f"SESSION_CONTRACT_CONFLICT: unsupported timeframe {timeframe!r}")
