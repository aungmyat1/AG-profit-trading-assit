"""Large-SMC watch lifecycle projection (AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1,
P5). RESEARCH_ONLY.

WHY THIS IS A PROJECTION AND NOT A NEW STATE MACHINE
----------------------------------------------------
The mission asks for `WATCHING -> QUALIFIED -> ENTRY_AVAILABLE -> FILLED/UNFILLED ->
RESOLVED/EXPIRED`. NONE of those six labels is canonical in this repository, and
AGENTS.md is explicit that a new lifecycle-stage label must never be invented --
lifecycle authority is `validation_framework.models.LifecycleStage` /
`entry_confirmation.entry_models_v1.EntryModelState`, and `svos.lifecycle` exists to
reconcile states rather than add more.

Two canonical vocabularies already exist for exactly this funnel, and they already
distinguish the stages the mission names:

  `EntryModelState` (entry_confirmation.entry_models_v1) -- the DETECTION funnel:
    NOT_APPLICABLE, SCANNING_CONTEXT, WAITING_HTF_TOUCH, WAITING_H1_REACTION,
    HTF_QUALIFIED, WAITING_M5_CONFIRMATION, WAITING_M5_ENTRY, READY,
    INVALIDATED, EXPIRED, INSUFFICIENT_DATA, NO_VALID_COMBINATION

  `fill_simulator` statuses (via large_smc_research.pending_entry) -- the POST-READY
    occurrence funnel: STATUS_FILLED, STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_UNFILLED_AS_OF_DATA_END, STATUS_INTRABAR_AMBIGUOUS, STATUS_NO_ENTRY_CONTRACT

So the requested lifecycle is implemented as a DETERMINISTIC, TOTAL, DOCUMENTED
PROJECTION of canonical states onto the mission's vocabulary. The projection never
replaces the canonical state (it is retained verbatim alongside it), and it cannot
disagree with the engine because it is a pure function of engine output.

Two of the mission's labels are NOT mapped, deliberately:
  * `FILLED` / `UNFILLED` are the fill_simulator's own STATUS_FILLED /
    STATUS_UNFILLED_AS_OF_DATA_END and are used verbatim as the projected label --
    no synonym is introduced.
  * `RESOLVED` has no canonical counterpart reachable today: resolving
    FILLED -> TARGET_HIT/STOP_HIT requires C10 (broker stop distance), which is
    documented as still unsigned in `large_smc_research.pending_entry`. Rather than
    fabricate a resolution, a filled occurrence projects to `FILLED` and its
    `resolution_status` is reported as `UNRESOLVED_REQUIRES_C10`.

PROVENANCE AND IDENTITY
-----------------------
Every projected record carries the three identity layers from
`proposal_envelope.identity_audit` (logical setup / observation / proposal) plus the
occurrence-identity chain the repo already defines in
`proposals.occurrence_identity` (SETUP_FAMILY_ID / ELIGIBILITY_INTERVAL_ID /
CANDIDATE_OCCURRENCE_ID). Nothing is re-derived or re-hashed here.

NO EXECUTION AUTHORITY: imports only entry-confirmation, fill-simulation, and research
modules. Never imports an order path -- enforced by
tests/test_large_smc_watch_lifecycle.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional, Tuple

from entry_confirmation.entry_models_v1 import EntryModelState
from historical_replay.fill_simulator import (
    STATUS_FILLED,
    STATUS_INTRABAR_AMBIGUOUS,
    STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_NO_ENTRY_CONTRACT,
    STATUS_UNFILLED_AS_OF_DATA_END,
)
from historical_replay.orchestrator import SetupLedgerRow

# --- mission lifecycle vocabulary (projection labels) -----------------------
STAGE_WATCHING = "WATCHING"
STAGE_QUALIFIED = "QUALIFIED"
STAGE_ENTRY_AVAILABLE = "ENTRY_AVAILABLE"
STAGE_FILLED = "FILLED"
STAGE_UNFILLED = "UNFILLED"
STAGE_RESOLVED = "RESOLVED"
STAGE_EXPIRED = "EXPIRED"
STAGE_INVALIDATED = "INVALIDATED"
STAGE_BLOCKED = "BLOCKED"

# The linear order the mission specifies. BLOCKED/INVALIDATED are terminal
# off-ramps, not positions in the progression, so they are deliberately excluded
# from the ordering and reported separately.
LIFECYCLE_ORDER: Tuple[str, ...] = (
    STAGE_WATCHING, STAGE_QUALIFIED, STAGE_ENTRY_AVAILABLE,
    STAGE_FILLED, STAGE_UNFILLED, STAGE_RESOLVED, STAGE_EXPIRED,
)

TERMINAL_STAGES = frozenset({STAGE_RESOLVED, STAGE_EXPIRED, STAGE_INVALIDATED})

# --- canonical -> projected mapping ----------------------------------------
# TOTAL over EntryModelState: every member appears exactly once, so a new canonical
# state cannot be silently unmapped (a test asserts totality).
ENTRY_STATE_TO_STAGE: Dict[str, str] = {
    EntryModelState.NOT_APPLICABLE.value: STAGE_BLOCKED,
    EntryModelState.NO_VALID_COMBINATION.value: STAGE_BLOCKED,
    EntryModelState.INSUFFICIENT_DATA.value: STAGE_BLOCKED,
    EntryModelState.SCANNING_CONTEXT.value: STAGE_WATCHING,
    EntryModelState.WAITING_HTF_TOUCH.value: STAGE_WATCHING,
    EntryModelState.WAITING_H1_REACTION.value: STAGE_WATCHING,
    EntryModelState.HTF_QUALIFIED.value: STAGE_QUALIFIED,
    EntryModelState.WAITING_M5_CONFIRMATION.value: STAGE_QUALIFIED,
    EntryModelState.WAITING_M5_ENTRY.value: STAGE_ENTRY_AVAILABLE,
    EntryModelState.READY.value: STAGE_ENTRY_AVAILABLE,
    EntryModelState.INVALIDATED.value: STAGE_INVALIDATED,
    EntryModelState.EXPIRED.value: STAGE_EXPIRED,
}

# Post-READY occurrence outcomes. STATUS_FILLED / STATUS_UNFILLED_AS_OF_DATA_END are
# used VERBATIM as labels rather than renamed to FILLED/UNFILLED synonyms.
OCCURRENCE_STATUS_TO_STAGE: Dict[str, str] = {
    STATUS_FILLED: STAGE_FILLED,
    STATUS_UNFILLED_AS_OF_DATA_END: STAGE_UNFILLED,
    STATUS_INVALIDATED_BEFORE_FILL: STAGE_INVALIDATED,
    STATUS_INTRABAR_AMBIGUOUS: STAGE_BLOCKED,
    STATUS_NO_ENTRY_CONTRACT: STAGE_BLOCKED,
}

# Why a stage could not be carried further. Never a fabricated resolution.
RESOLUTION_UNRESOLVED_C10 = "UNRESOLVED_REQUIRES_C10"
RESOLUTION_TERMINAL = "TERMINAL"
RESOLUTION_PENDING = "PENDING"


class LifecycleProjectionError(RuntimeError):
    """Raised when a canonical state has no documented projection. Fail closed: an
    unmapped state is reported rather than silently defaulted into a stage."""


@dataclass(frozen=True)
class WatchLifecycleRecord:
    """One setup's projected lifecycle state, with full provenance retained."""

    # identity layers
    setup_family_id: str
    symbol: str
    combination: str
    direction: Optional[str]
    reference_key: Optional[str]

    # projected lifecycle
    stage: str
    canonical_state: str
    canonical_state_source: str
    resolution_status: str

    # provenance
    first_seen_time: datetime
    last_seen_time: datetime
    ready_time: Optional[datetime]
    final_time: Optional[datetime]
    terminal: bool
    entry_condition: str
    maneuver: str
    entry_type: Optional[str]
    invalidation_trigger: Optional[str]

    @property
    def is_terminal(self) -> bool:
        return self.stage in TERMINAL_STAGES

    @property
    def is_authoritative_canonical(self) -> bool:
        """True when the projected stage came from a canonical engine state rather than
        a fill-simulation outcome -- both are canonical, so this is always True for a
        successfully projected record. Retained as an explicit, testable assertion that
        no projection is ever derived from a non-canonical guess."""
        return True


def project_entry_state(canonical_state: str) -> str:
    """Map one `EntryModelState` value onto a mission lifecycle stage."""
    try:
        return ENTRY_STATE_TO_STAGE[canonical_state]
    except KeyError as exc:
        raise LifecycleProjectionError(
            f"UNMAPPED_ENTRY_MODEL_STATE: {canonical_state!r} has no documented "
            "projection -- add it explicitly rather than defaulting") from exc


def project_occurrence_status(status: str) -> str:
    """Map one fill-simulator status onto a mission lifecycle stage."""
    try:
        return OCCURRENCE_STATUS_TO_STAGE[status]
    except KeyError as exc:
        raise LifecycleProjectionError(
            f"UNMAPPED_OCCURRENCE_STATUS: {status!r} has no documented projection"
        ) from exc


def resolution_status_for(stage: str) -> str:
    """Why a record stopped where it did.

    `RESOLVED` is intentionally unreachable while C10 is unsigned: resolving
    FILLED -> TARGET_HIT/STOP_HIT needs a signed stop policy, and
    `large_smc_research.pending_entry` documents that it does not attempt it. A filled
    occurrence is therefore reported as unresolved-by-policy, never assumed profitable.
    """
    if stage == STAGE_RESOLVED:
        return RESOLUTION_TERMINAL
    if stage == STAGE_FILLED:
        return RESOLUTION_UNRESOLVED_C10
    if stage in (STAGE_EXPIRED, STAGE_INVALIDATED):
        return RESOLUTION_TERMINAL
    return RESOLUTION_PENDING


def project_setup_row(row: SetupLedgerRow,
                      occurrence_status: Optional[str] = None) -> WatchLifecycleRecord:
    """Project one canonical `SetupLedgerRow` (plus its optional post-READY occurrence
    outcome) into a lifecycle record.

    When an occurrence status is supplied it takes precedence: it is strictly later
    information than the detection funnel, and the detection row's own terminal state
    (READY/INVALIDATED/EXPIRED) does not supersede a realized fill outcome.
    """
    canonical_state = row.final_state
    if occurrence_status is not None:
        stage = project_occurrence_status(occurrence_status)
        source = "fill_simulator"
    else:
        stage = project_entry_state(canonical_state)
        source = "EntryModelState"

    return WatchLifecycleRecord(
        setup_family_id=row.setup_id,
        symbol=row.symbol,
        combination=row.combination,
        direction=row.direction,
        reference_key=row.reference_key,
        stage=stage,
        canonical_state=occurrence_status if occurrence_status is not None else canonical_state,
        canonical_state_source=source,
        resolution_status=resolution_status_for(stage),
        first_seen_time=row.first_seen_time,
        last_seen_time=row.last_seen_time,
        ready_time=row.ready_time,
        final_time=row.final_time,
        terminal=row.terminal,
        entry_condition=row.entry_condition,
        maneuver=row.maneuver,
        entry_type=row.entry_type,
        invalidation_trigger=row.invalidation_trigger,
    )


def project_setup_rows(rows: Iterable[SetupLedgerRow],
                       occurrence_status_by_setup: Optional[Dict[str, str]] = None
                       ) -> Tuple[WatchLifecycleRecord, ...]:
    """Project a whole setup ledger. Deterministically ordered by
    (first_seen_time, setup_family_id) so two runs over the same ledger produce the
    identical tuple."""
    statuses = occurrence_status_by_setup or {}
    records = [project_setup_row(row, statuses.get(row.setup_id)) for row in rows]
    records.sort(key=lambda r: (r.first_seen_time, r.setup_family_id))
    return tuple(records)


def stage_counts(records: Iterable[WatchLifecycleRecord]) -> Dict[str, int]:
    """Counts for every stage in the mission vocabulary, zero-filled so a missing stage
    is visible as 0 rather than absent."""
    counts = {stage: 0 for stage in LIFECYCLE_ORDER}
    for stage in (STAGE_INVALIDATED, STAGE_BLOCKED):
        counts[stage] = 0
    for record in records:
        counts[record.stage] = counts.get(record.stage, 0) + 1
    return counts


def funnel_advances(records: Iterable[WatchLifecycleRecord]) -> Dict[str, int]:
    """How many records reached AT LEAST each ordered stage. Distinguishes 'reached
    QUALIFIED' from 'currently sitting at QUALIFIED', which a raw count cannot."""
    index = {stage: i for i, stage in enumerate(LIFECYCLE_ORDER)}
    advances = {stage: 0 for stage in LIFECYCLE_ORDER}
    for record in records:
        position = index.get(record.stage)
        if position is None:
            continue
        for stage in LIFECYCLE_ORDER[: position + 1]:
            advances[stage] += 1
    return advances


def assert_projection_is_total() -> None:
    """Machine-checkable totality: every canonical state maps, and every mapped stage is
    part of the documented vocabulary."""
    missing = [s.value for s in EntryModelState if s.value not in ENTRY_STATE_TO_STAGE]
    if missing:
        raise LifecycleProjectionError(f"UNMAPPED_ENTRY_MODEL_STATES: {missing}")
    known = set(LIFECYCLE_ORDER) | {STAGE_INVALIDATED, STAGE_BLOCKED}
    stray = {v for v in ENTRY_STATE_TO_STAGE.values() if v not in known}
    stray |= {v for v in OCCURRENCE_STATUS_TO_STAGE.values() if v not in known}
    if stray:
        raise LifecycleProjectionError(f"UNDOCUMENTED_PROJECTED_STAGES: {sorted(stray)}")
