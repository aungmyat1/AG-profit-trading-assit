"""Deterministic weekday `--once` scheduling for the FX session pilots
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1, P1).

WHAT THIS REPLACES (and why the existing tasks were not sufficient)
-------------------------------------------------------------------
Two live tasks (`AG_FX_ASIAN_LONDON_SHADOW`, `AG_FX_LONDON_NEWYORK_SHADOW`) already
existed, but their triggers were `TimeTrigger` with `Repetition/Interval=PT15M`, no
`DaysOfWeek`, no `EndBoundary`, and no offset -- i.e. they fired every 15 minutes
around the clock, every day of the week, forever. That has three concrete defects this
module fixes:

  1. NO WINDOW BOUND. A window-scoped proposal cycle was being invoked outside its own
     execution window, where the pilot's own contract has nothing to say.
  2. NO WEEKDAY BOUND. Saturday/Sunday invocations run against a closed market and can
     only ever produce `DATA_ERROR` (observed: the 2026-09-20 Sunday runs logged
     `strategy_state=DATA_ERROR`, `reason_codes=[DATA_MISSING]`). Noise, not signal.
  3. FIRING AT THE M15 OPEN, NOT THE CLOSE. A `PT15M` repetition anchored at
     `00:00:00` fires at `:00`/`:15`/`:30`/`:45` -- the instant a bar OPENS. The
     pilot's whole premise is acting on a CLOSED bar, so the trigger must land a short
     settle interval after the close (20s), never at the open.

This module supplies the schedule as PURE functions so it is testable without touching
Task Scheduler, and so the installed trigger set can be verified against it.

FAIL-CLOSED GATES (enforced by the runner, expressed here as pure predicates)
-----------------------------------------------------------------------------
  * inside-window       -- an invocation outside [start, end] UTC refuses.
  * weekday             -- Saturday/Sunday UTC refuses.
  * friction-window     -- while the frozen WP3A.1 friction campaign is still
                           collecting, any slot colliding with one of its four frozen
                           UTC windows refuses, so scheduled FX polling cannot perturb
                           spread evidence that a frozen manifest governs.
  * slot-idempotency    -- the same (cycle, trading date, slot) refuses a second run,
                           so a restart/overlap cannot double-evaluate one M15 close.

Never `--watch`: this module's whole point is one bounded cycle per closed bar. The
runner rejects `--watch` explicitly rather than silently ignoring it.

Research/operational scheduling only -- nothing here imports an order path, and the
delegated pilot runs `PROPOSAL_ONLY` (`automatic_execution: false`,
`live_execution: false`).

RECONCILIATION WITH THE PRE-EXISTING `ag_scheduler_v2` (documented, not silent)
-------------------------------------------------------------------------------
`src/ag_scheduler_v2/` (`AG_DAILY_OPPORTUNITY_SCHEDULER_V2`, `status: RESEARCH`) is an
earlier, *unwired* scheduling design: it has no `scripts/` entrypoint and no Task
Scheduler registration (verified by repo-wide search). It is therefore NOT operational
authority, and this module does not import it -- coupling operational FX scheduling to
a RESEARCH-status package would be the wrong direction of dependency.

Two facts about it are worth recording, because they bear on this module's correctness:

  1. INDEPENDENT AGREEMENT ON WINDOWS. `config/ag_scheduler_v2.yaml` defines
     `WINDOW_ASIAN_LONDON` 07:00-11:00 UTC and `WINDOW_LONDON_NEWYORK` 12:00-15:00 UTC,
     mapping them to cycle ids `ASIAN_LONDON` / `LONDON_NEWYORK` -- exactly this
     module's `CYCLE_WINDOWS` and exactly the pilots' own `execution_window` values.
     Three independent sources agreeing is corroboration, not duplication.
  2. A DIFFERENT SETTLEMENT INTERVAL. Its `m15_clock.close_settlement_seconds` is `5`;
     this module uses 20s, per this mission's explicit "M15 close + ~20 seconds"
     requirement. Both express "wake after the close, never at the open"; the value is
     a mission parameter, not a contradiction. `M15_CLOSE_SETTLE_SECONDS` is named so
     the installed trigger set and the verification tool cannot drift apart.

Its `m15_clock.next_m15_close_utc` / `previous_m15_close_utc` are genuinely reusable
primitives; this module's `_current_slot` performs the same "most recent close at or
before now" derivation. If `ag_scheduler_v2` is ever promoted out of RESEARCH and wired,
that helper is the natural shared home -- reconciling the two is deliberately left out
of scope here rather than refactoring a RESEARCH package under a scheduling mission.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# The settle interval after an M15 close. Bars close at :00/:15/:30/:45; firing exactly
# on the boundary races the broker's own bar finalization, so every slot waits this
# long. Named, not inlined, so the installed trigger set and the verification tool
# cannot drift apart.
M15_CLOSE_SETTLE_SECONDS = 20

M15_MINUTES = 15

# Cycle definitions. Windows are the pilots' OWN canonical `execution_window` values
# (config/pilot/*.yaml: ASIAN_LONDON 07:00-11:00 UTC, LONDON_NEWYORK 12:00-15:00 UTC),
# repeated here as the scheduling authority rather than re-parsed at trigger-install
# time so an install cannot silently pick up an edited window.
@dataclass(frozen=True)
class CycleWindow:
    cycle_id: str
    start_utc: time
    end_utc: time
    pilot_config: str

    @property
    def start_minutes(self) -> int:
        return self.start_utc.hour * 60 + self.start_utc.minute

    @property
    def end_minutes(self) -> int:
        return self.end_utc.hour * 60 + self.end_utc.minute

    @property
    def duration_minutes(self) -> int:
        return self.end_minutes - self.start_minutes


CYCLE_WINDOWS: Tuple[CycleWindow, ...] = (
    CycleWindow(
        cycle_id="ASIAN_LONDON",
        start_utc=time(7, 0),
        end_utc=time(11, 0),
        pilot_config="config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml",
    ),
    CycleWindow(
        cycle_id="LONDON_NEWYORK",
        start_utc=time(12, 0),
        end_utc=time(15, 0),
        pilot_config="config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml",
    ),
)

CYCLE_BY_ID: Dict[str, CycleWindow] = {c.cycle_id: c for c in CYCLE_WINDOWS}

FRICTION_CAMPAIGN_DIR = (
    "artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/"
    "friction_campaign_wp3a1"
)
FRICTION_CAMPAIGN_MANIFEST = f"{FRICTION_CAMPAIGN_DIR}/campaign_manifest.json"


# ---------------------------------------------------------------------------
# Schedule computation
# ---------------------------------------------------------------------------

def m15_close_slots(start_utc: time, end_utc: time,
                    settle_seconds: int = M15_CLOSE_SETTLE_SECONDS) -> List[time]:
    """Every M15 CLOSE instant within [start, end] inclusive, each shifted by the
    settle interval. A 07:00-11:00 window yields 17 slots (07:00:20 .. 11:00:20)."""
    start_minutes = start_utc.hour * 60 + start_utc.minute
    end_minutes = end_utc.hour * 60 + end_utc.minute
    slots: List[time] = []
    minute = start_minutes
    while minute <= end_minutes:
        slots.append(time(minute // 60, minute % 60, settle_seconds))
        minute += M15_MINUTES
    return slots


def slot_datetimes(cycle: CycleWindow, trading_date: date) -> List[datetime]:
    """Aware-UTC datetimes for one cycle on one UTC calendar date."""
    return [
        datetime.combine(trading_date, slot, tzinfo=timezone.utc)
        for slot in m15_close_slots(cycle.start_utc, cycle.end_utc)
    ]


def is_weekday_utc(day: date) -> bool:
    """Mon-Fri UTC. FX is closed Sat/Sun UTC; the frozen campaign manifest's own
    `trading_day_definition` uses the same rule."""
    return day.weekday() < 5


def is_inside_window(cycle: CycleWindow, moment: datetime) -> bool:
    """True when `moment` (aware UTC) is within the cycle's own execution window on
    `moment`'s UTC date, inclusive of both bounds."""
    local_minutes = moment.hour * 60 + moment.minute
    return cycle.start_minutes <= local_minutes <= cycle.end_minutes


# ---------------------------------------------------------------------------
# Friction-campaign protection
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrictionCampaignStatus:
    campaign_id: str
    active: bool
    complete_days: int
    minimum_days: int
    reason: str

    @property
    def windows(self) -> List[Tuple[str, time, time]]:
        return list(_friction_windows)  # populated by caller via load_friction_campaign


_friction_windows: List[Tuple[str, time, time]] = []


class FrictionCampaignError(RuntimeError):
    """Raised when a campaign manifest EXISTS but cannot be read/parsed. Fail closed:
    a corrupted manifest must never be silently treated as 'no campaign'."""


def load_friction_campaign(manifest_path: str = FRICTION_CAMPAIGN_MANIFEST,
                           sessions_dir: Optional[str] = None) -> FrictionCampaignStatus:
    """Read the FROZEN campaign manifest and count completed collection days.

    Read-only. Never writes to the campaign directory -- WP3A.1 evidence is frozen and
    must stay byte-identical while collection is incomplete.

    `active` is True while fewer than the manifest's own `minimum_trading_days` have
    been fully collected. A complete day = every declared window for that day has a
    summary with `sample_count >= samples_per_window_minimum`.
    """
    global _friction_windows
    path = Path(manifest_path)
    if not path.exists():
        _friction_windows = []
        return FrictionCampaignStatus(
            campaign_id="", active=False, complete_days=0, minimum_days=0,
            reason="CAMPAIGN_MANIFEST_ABSENT",
        )

    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        windows = manifest["windows"]
        minimum_days = int(manifest["minimum_trading_days"])
        samples_min = int(manifest["samples_per_window_minimum"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise FrictionCampaignError(
            f"FRICTION_CAMPAIGN_MANIFEST_UNREADABLE: {manifest_path}: {exc}") from exc

    parsed: List[Tuple[str, time, time]] = []
    for w in windows:
        try:
            parsed.append((
                str(w["window_id"]),
                time(int(str(w["start_utc_hhmm"])[:2]), int(str(w["start_utc_hhmm"])[3:])),
                time(int(str(w["end_utc_hhmm"])[:2]), int(str(w["end_utc_hhmm"])[3:])),
            ))
        except (KeyError, TypeError, ValueError) as exc:
            raise FrictionCampaignError(
                f"FRICTION_CAMPAIGN_WINDOW_UNREADABLE: {w!r}: {exc}") from exc
    _friction_windows = parsed

    sessions = Path(sessions_dir or f"{FRICTION_CAMPAIGN_DIR}/sessions")
    per_day: Dict[str, set] = {}
    if sessions.exists():
        for summary in sessions.glob("*_summary.json"):
            stem = summary.name[: -len("_summary.json")]
            day, _, window_id = stem.partition("_")
            try:
                payload = json.loads(summary.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if int(payload.get("sample_count", 0)) >= samples_min:
                per_day.setdefault(day, set()).add(window_id)

    required = {wid for wid, _, _ in parsed}
    complete_days = sum(1 for windows_seen in per_day.values() if required <= windows_seen)
    active = complete_days < minimum_days
    return FrictionCampaignStatus(
        campaign_id=str(manifest.get("campaign_id", "")),
        active=active,
        complete_days=complete_days,
        minimum_days=minimum_days,
        reason="CAMPAIGN_COLLECTING" if active else "CAMPAIGN_MINIMUM_DAYS_MET",
    )


def friction_window_conflict(moment: datetime,
                             status: Optional[FrictionCampaignStatus] = None
                             ) -> Optional[str]:
    """Name of the frozen campaign window `moment` (aware UTC) collides with, or None.

    Returns None when no campaign is active -- there is nothing to protect once the
    manifest's own minimum day count is met.
    """
    st = status if status is not None else load_friction_campaign()
    if not st.active:
        return None
    minutes = moment.hour * 60 + moment.minute
    for window_id, start, end in _friction_windows:
        if (start.hour * 60 + start.minute) <= minutes <= (end.hour * 60 + end.minute):
            return window_id
    return None


def conflicting_slots(status: Optional[FrictionCampaignStatus] = None
                      ) -> List[Tuple[str, str, time]]:
    """(cycle_id, window_id, slot) for every scheduled slot currently suppressed by an
    active friction campaign. Pure reporting -- used by the verification tool."""
    st = status if status is not None else load_friction_campaign()
    out: List[Tuple[str, str, time]] = []
    if not st.active:
        return out
    for cycle in CYCLE_WINDOWS:
        for slot in m15_close_slots(cycle.start_utc, cycle.end_utc):
            moment = datetime.combine(date(2026, 1, 5), slot, tzinfo=timezone.utc)  # a Monday
            window_id = friction_window_conflict(moment, st)
            if window_id:
                out.append((cycle.cycle_id, window_id, slot))
    return out


# ---------------------------------------------------------------------------
# Slot idempotency
# ---------------------------------------------------------------------------

SLOT_LEDGER_PATH = "state/fx_schedule/slot_ledger.json"


class SlotAlreadyClaimed(RuntimeError):
    """Raised when this (cycle, trading date, slot) already ran. Fail closed -- a
    restart or Task Scheduler overlap must not double-evaluate one closed bar."""


def slot_key(cycle_id: str, trading_date: date, slot_utc: datetime) -> str:
    return f"{cycle_id}|{trading_date.isoformat()}|{slot_utc.isoformat()}"


class SlotLedger:
    """Deterministic, restart-safe record of which scheduled slots have executed.

    Deliberately separate from the pilot's own daily-opportunity ledger: that one
    governs TRADE capacity (how many proposals a day), this one governs SCHEDULE
    execution (whether this trigger already fired). Conflating them would let a slot
    claim consume trade capacity, or a trade claim mask a missed slot.
    """

    def __init__(self, path: str = SLOT_LEDGER_PATH):
        from runtime_state.store import JsonKeyValueStore

        self._store = JsonKeyValueStore(path)

    def claim(self, cycle_id: str, trading_date: date, slot_utc: datetime,
              outcome: Optional[str] = None) -> None:
        key = slot_key(cycle_id, trading_date, slot_utc)
        if self._store.get(key) is not None:
            raise SlotAlreadyClaimed(
                f"SLOT_ALREADY_CLAIMED: {key} already executed "
                "(one evaluation per closed M15 bar, never two)")
        self._store.put(key, {
            "cycle_id": cycle_id,
            "trading_date": trading_date.isoformat(),
            "slot_utc": slot_utc.isoformat(),
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
        })

    def has_claimed(self, cycle_id: str, trading_date: date, slot_utc: datetime) -> bool:
        return self._store.get(slot_key(cycle_id, trading_date, slot_utc)) is not None
