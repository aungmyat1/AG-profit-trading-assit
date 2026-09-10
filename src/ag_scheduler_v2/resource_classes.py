"""P0/P1 resource classes and preemption (spec sections 5-7). P0 always preempts P1;
P1 must never delay a scheduled M15 evaluation. Research jobs are cancelled only via an
explicit checkpoint/stop signal -- this module never kills a worker itself, it only
decides *whether* P1 work is currently permitted and signals when it must stop.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from ag_scheduler_v2.config_loader import load_standby_policy
from ag_scheduler_v2.schedule import P0_STATES, P1_STATES, STANDBY, next_boundary_utc

P0_MARKET = "P0_MARKET"
P1_RESEARCH_CLASS = "P1_RESEARCH"

# P1 preemption sequence (spec section 7) -- signalled, never enforced by force-kill here.
SIGNAL_STOP = "SIGNAL_RESEARCH_STOP"
STEP_CHECKPOINT = "CHECKPOINT_PROGRESS"
STEP_FLUSH = "FLUSH_SAFE_STATE"
STEP_CANCEL = "CANCEL_STOP_WORKER"
STEP_CONFIRM_INACTIVE = "CONFIRM_P1_INACTIVE"
STEP_P0_PREFLIGHT = "ENTER_P0_PREFLIGHT"

PREEMPTION_SEQUENCE = (SIGNAL_STOP, STEP_CHECKPOINT, STEP_FLUSH, STEP_CANCEL, STEP_CONFIRM_INACTIVE, STEP_P0_PREFLIGHT)


def resource_class_for_state(state: str, *, allow_p1_research: Optional[bool] = None) -> str:
    if state in P0_STATES:
        return P0_MARKET
    if state in P1_STATES:
        return P1_RESEARCH_CLASS
    if state == STANDBY:
        if allow_p1_research is None:
            allow_p1_research = load_standby_policy().allow_p1_research
        return P1_RESEARCH_CLASS if allow_p1_research else P0_MARKET
    raise ValueError(f"UNKNOWN_SCHEDULE_STATE: {state!r} has no resource-class mapping")


def p1_research_permitted(state: str, *, allow_p1_research: Optional[bool] = None) -> bool:
    return resource_class_for_state(state, allow_p1_research=allow_p1_research) == P1_RESEARCH_CLASS


@dataclass(frozen=True)
class P1Checkpoint:
    """Progress marker a research job must be able to produce on demand, so preemption
    never leaves half-written canonical evidence (spec section 7). `resumable=True`
    means the job supports checkpoint+resume/idempotent-restart/transactional temp
    output; a job that cannot honestly report `resumable=True` must not be scheduled
    into a preemptible window at all."""

    job_id: str
    resumable: bool
    progress_fraction: float
    checkpoint_at_utc: dt.datetime


def seconds_until_p1_must_stop(now_utc: dt.datetime, path: Optional[str] = None) -> Optional[float]:
    """How long P1 work has left before the next P0-owning boundary, or None if the
    current state has no scheduled end (should not happen for a preemptible state)."""
    from ag_scheduler_v2.schedule import resolve_state

    state = resolve_state(now_utc, path)
    if resource_class_for_state(state) != P1_RESEARCH_CLASS:
        return 0.0
    boundary = next_boundary_utc(now_utc, path)
    return (boundary - now_utc).total_seconds()
