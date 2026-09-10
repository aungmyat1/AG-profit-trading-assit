"""Top-level AG_DAILY_OPPORTUNITY_SCHEDULER_V2 state machine + checkpoint persistence
(spec sections 4, 36, 38, 39). `tick(now_utc)` is a pure-ish function (one JSON
read/write) designed to be called repeatedly -- by a real sleep/wake loop in
production, or directly by tests -- rather than driving an untestable infinite loop
itself. State transitions are deterministic and logged; failure classification never
lets a P1/news/persistence failure silently stop P0.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from runtime_state.store import JsonKeyValueStore

from ag_scheduler_v2 import SCHEDULER_ID, SCHEDULER_VERSION
from ag_scheduler_v2.resource_classes import p1_research_permitted
from ag_scheduler_v2.schedule import resolve_state

_DEFAULT_CHECKPOINT_PATH = "journal/ag_scheduler_v2/checkpoint.json"
_CHECKPOINT_KEY = "scheduler_checkpoint"

# Failure classification (spec section 38). A P1/news failure must never stop P0; a
# persistence failure touching canonical evidence fails that cycle closed, not the
# whole scheduler.
DATA_FAILURE = "DATA_FAILURE"
BROKER_STATUS_FAILURE = "BROKER_STATUS_FAILURE"
NEWS_PROVIDER_FAILURE = "NEWS_PROVIDER_FAILURE"
STRATEGY_FAILURE = "STRATEGY_FAILURE"
PERSISTENCE_FAILURE = "PERSISTENCE_FAILURE"
P1_RESEARCH_FAILURE = "P1_RESEARCH_FAILURE"
SCHEDULER_FAILURE = "SCHEDULER_FAILURE"

_NEVER_STOPS_P0 = frozenset({P1_RESEARCH_FAILURE, NEWS_PROVIDER_FAILURE})
_FAILS_CYCLE_CLOSED = frozenset({PERSISTENCE_FAILURE})


@dataclass(frozen=True)
class ClockDriftStatus:
    status: str  # "OK" | "DEGRADED"
    drift_seconds: Optional[float]


def check_clock_drift(*, wall_clock_utc: dt.datetime, reference_utc: Optional[dt.datetime], max_drift_seconds: float) -> ClockDriftStatus:
    """`reference_utc` is whatever trusted external time source existing infra can
    supply (e.g. broker server time); None means no reference was available, which is
    reported as DEGRADED rather than silently trusting the wall clock (spec 39)."""
    if reference_utc is None:
        return ClockDriftStatus(status="DEGRADED", drift_seconds=None)
    drift = abs((wall_clock_utc - reference_utc).total_seconds())
    return ClockDriftStatus(status="OK" if drift <= max_drift_seconds else "DEGRADED", drift_seconds=drift)


def failure_containment(failure_kind: str) -> str:
    """Returns 'STOP_CYCLE_ONLY', 'STOP_P1_ONLY', or 'STOP_SCHEDULER' -- the containment
    scope for a given failure classification. P0 (the scheduler and market evaluation)
    never stops because of a P1 or news-provider failure."""
    if failure_kind in _NEVER_STOPS_P0:
        return "STOP_P1_ONLY" if failure_kind == P1_RESEARCH_FAILURE else "STOP_CYCLE_ONLY"
    if failure_kind in _FAILS_CYCLE_CLOSED:
        return "STOP_CYCLE_ONLY"
    if failure_kind == SCHEDULER_FAILURE:
        return "STOP_SCHEDULER"
    return "STOP_CYCLE_ONLY"


@dataclass(frozen=True)
class TickResult:
    state: str
    previous_state: Optional[str]
    transitioned: bool
    p1_permitted: bool
    now_utc: dt.datetime


class AGDailyOpportunitySchedulerV2:
    def __init__(self, checkpoint_path: str = _DEFAULT_CHECKPOINT_PATH):
        self._store = JsonKeyValueStore(checkpoint_path)

    def load_checkpoint(self) -> dict:
        return self._store.get(_CHECKPOINT_KEY) or {
            "scheduler_version": SCHEDULER_VERSION,
            "current_state": None,
            "last_transition_utc": None,
            "last_completed_cycle": None,
        }

    def tick(self, now_utc: dt.datetime, *, allow_p1_research: Optional[bool] = None) -> TickResult:
        checkpoint = self.load_checkpoint()
        previous_state = checkpoint.get("current_state")
        state = resolve_state(now_utc)
        transitioned = state != previous_state

        checkpoint["scheduler_id"] = SCHEDULER_ID
        checkpoint["scheduler_version"] = SCHEDULER_VERSION
        checkpoint["current_state"] = state
        if transitioned:
            checkpoint["last_transition_utc"] = now_utc.astimezone(dt.timezone.utc).isoformat()
        self._store.put(_CHECKPOINT_KEY, checkpoint)

        return TickResult(
            state=state,
            previous_state=previous_state,
            transitioned=transitioned,
            p1_permitted=p1_research_permitted(state, allow_p1_research=allow_p1_research),
            now_utc=now_utc,
        )

    def record_last_completed_cycle(self, cycle_id: str, now_utc: dt.datetime) -> None:
        checkpoint = self.load_checkpoint()
        checkpoint["last_completed_cycle"] = {"cycle_id": cycle_id, "at_utc": now_utc.astimezone(dt.timezone.utc).isoformat()}
        self._store.put(_CHECKPOINT_KEY, checkpoint)
