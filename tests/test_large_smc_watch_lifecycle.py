"""P5 focused tests: Large-SMC watch lifecycle projection
(AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_V1).

Asserts that the mission's requested lifecycle
(WATCHING -> QUALIFIED -> ENTRY_AVAILABLE -> FILLED/UNFILLED -> RESOLVED/EXPIRED) is a
DOCUMENTED, TOTAL, DETERMINISTIC projection of existing canonical states -- not a new
lifecycle authority. Also asserts provenance/identity retention and that Large SMC
remains RESEARCH_ONLY.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(REPO_ROOT / "src"))

from entry_confirmation.entry_models_v1 import EntryModelState  # noqa: E402
from historical_replay.fill_simulator import (  # noqa: E402
    STATUS_FILLED,
    STATUS_INTRABAR_AMBIGUOUS,
    STATUS_INVALIDATED_BEFORE_FILL,
    STATUS_NO_ENTRY_CONTRACT,
    STATUS_UNFILLED_AS_OF_DATA_END,
)
from historical_replay.orchestrator import SetupLedgerRow  # noqa: E402
from large_smc_research.watch_lifecycle import (  # noqa: E402
    ENTRY_STATE_TO_STAGE,
    LIFECYCLE_ORDER,
    OCCURRENCE_STATUS_TO_STAGE,
    RESOLUTION_PENDING,
    RESOLUTION_TERMINAL,
    RESOLUTION_UNRESOLVED_C10,
    STAGE_BLOCKED,
    STAGE_ENTRY_AVAILABLE,
    STAGE_EXPIRED,
    STAGE_FILLED,
    STAGE_INVALIDATED,
    STAGE_QUALIFIED,
    STAGE_RESOLVED,
    STAGE_UNFILLED,
    STAGE_WATCHING,
    LifecycleProjectionError,
    assert_projection_is_total,
    funnel_advances,
    project_entry_state,
    project_occurrence_status,
    project_setup_row,
    project_setup_rows,
    resolution_status_for,
    stage_counts,
)

UTC = timezone.utc
LIFECYCLE_MODULE = REPO_ROOT / "src" / "large_smc_research" / "watch_lifecycle.py"


def _row(**overrides) -> SetupLedgerRow:
    base = dict(
        setup_id="SETUP-EURUSD-E2M1-abc123",
        symbol="EURUSD",
        combination="E2M1",
        entry_condition="E2",
        maneuver="M1",
        direction="SHORT",
        reference_key="POI|1.15|1.16|None",
        first_seen_time=datetime(2026, 9, 1, 8, 0, tzinfo=UTC),
        last_seen_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        ready_time=datetime(2026, 9, 1, 11, 30, tzinfo=UTC),
        entry_type="LIMIT",
        final_state=EntryModelState.READY.value,
        final_time=datetime(2026, 9, 1, 11, 30, tzinfo=UTC),
        terminal=False,
    )
    base.update(overrides)
    return SetupLedgerRow(**base)


# ===========================================================================
# The requested vocabulary exists and is ordered
# ===========================================================================

def test_mission_lifecycle_stages_are_present_and_ordered():
    assert LIFECYCLE_ORDER == (
        STAGE_WATCHING, STAGE_QUALIFIED, STAGE_ENTRY_AVAILABLE,
        STAGE_FILLED, STAGE_UNFILLED, STAGE_RESOLVED, STAGE_EXPIRED,
    )


def test_projection_is_total_over_every_canonical_entry_state():
    """No canonical state may be silently unmapped -- that is how a projection quietly
    becomes a divergent second state machine."""
    assert_projection_is_total()
    for state in EntryModelState:
        assert state.value in ENTRY_STATE_TO_STAGE
        assert project_entry_state(state.value) in (
            set(LIFECYCLE_ORDER) | {STAGE_INVALIDATED, STAGE_BLOCKED})


def test_projection_is_total_over_every_fill_status():
    for status in (STATUS_FILLED, STATUS_UNFILLED_AS_OF_DATA_END,
                   STATUS_INVALIDATED_BEFORE_FILL, STATUS_INTRABAR_AMBIGUOUS,
                   STATUS_NO_ENTRY_CONTRACT):
        assert project_occurrence_status(status) in (
            set(LIFECYCLE_ORDER) | {STAGE_INVALIDATED, STAGE_BLOCKED})


# ===========================================================================
# Canonical -> projected mapping semantics
# ===========================================================================

def test_scanning_states_project_to_watching():
    for state in (EntryModelState.SCANNING_CONTEXT, EntryModelState.WAITING_HTF_TOUCH,
                  EntryModelState.WAITING_H1_REACTION):
        assert project_entry_state(state.value) == STAGE_WATCHING


def test_htf_qualified_states_project_to_qualified():
    for state in (EntryModelState.HTF_QUALIFIED, EntryModelState.WAITING_M5_CONFIRMATION):
        assert project_entry_state(state.value) == STAGE_QUALIFIED


def test_ready_states_project_to_entry_available():
    for state in (EntryModelState.WAITING_M5_ENTRY, EntryModelState.READY):
        assert project_entry_state(state.value) == STAGE_ENTRY_AVAILABLE


def test_terminal_detection_states_project_to_their_own_stages():
    assert project_entry_state(EntryModelState.EXPIRED.value) == STAGE_EXPIRED
    assert project_entry_state(EntryModelState.INVALIDATED.value) == STAGE_INVALIDATED


def test_not_engaged_states_project_to_blocked_not_watching():
    """A composer that never engaged this E/M/direction is NOT 'watching' -- reporting
    it as watching would inflate the funnel."""
    for state in (EntryModelState.NOT_APPLICABLE, EntryModelState.NO_VALID_COMBINATION,
                  EntryModelState.INSUFFICIENT_DATA):
        assert project_entry_state(state.value) == STAGE_BLOCKED


def test_filled_and_unfilled_use_canonical_fill_statuses_verbatim():
    """No FILLED/UNFILLED synonym is invented -- the fill simulator's own statuses map
    to the mission's labels one-to-one."""
    assert project_occurrence_status(STATUS_FILLED) == STAGE_FILLED
    assert project_occurrence_status(STATUS_UNFILLED_AS_OF_DATA_END) == STAGE_UNFILLED


def test_ambiguous_and_contractless_occurrences_are_blocked_not_resolved():
    assert project_occurrence_status(STATUS_INTRABAR_AMBIGUOUS) == STAGE_BLOCKED
    assert project_occurrence_status(STATUS_NO_ENTRY_CONTRACT) == STAGE_BLOCKED


def test_unmapped_entry_state_fails_closed():
    with pytest.raises(LifecycleProjectionError, match="UNMAPPED_ENTRY_MODEL_STATE"):
        project_entry_state("SOME_NEW_STATE")


def test_unmapped_occurrence_status_fails_closed():
    with pytest.raises(LifecycleProjectionError, match="UNMAPPED_OCCURRENCE_STATUS"):
        project_occurrence_status("SOMETHING_ELSE")


# ===========================================================================
# RESOLVED is deliberately unreachable (C10 unsigned)
# ===========================================================================

def test_filled_resolution_is_unresolved_pending_c10():
    """FILLED must NOT be reported as resolved: resolving to TARGET_HIT/STOP_HIT needs a
    signed stop policy, which is documented as still unsigned. Assuming a favourable
    resolution would be exactly the optimistic bias this project prohibits."""
    assert resolution_status_for(STAGE_FILLED) == RESOLUTION_UNRESOLVED_C10


def test_resolved_is_not_reachable_from_any_canonical_state():
    assert STAGE_RESOLVED not in set(ENTRY_STATE_TO_STAGE.values())
    assert STAGE_RESOLVED not in set(OCCURRENCE_STATUS_TO_STAGE.values())


def test_terminal_stages_report_terminal_resolution():
    for stage in (STAGE_EXPIRED, STAGE_INVALIDATED):
        assert resolution_status_for(stage) == RESOLUTION_TERMINAL


def test_in_progress_stages_report_pending_resolution():
    for stage in (STAGE_WATCHING, STAGE_QUALIFIED, STAGE_ENTRY_AVAILABLE, STAGE_UNFILLED):
        assert resolution_status_for(stage) == RESOLUTION_PENDING


# ===========================================================================
# Provenance retention
# ===========================================================================

def test_projected_record_retains_canonical_state_and_identity():
    row = _row()
    record = project_setup_row(row)
    assert record.setup_family_id == row.setup_id
    assert record.symbol == "EURUSD"
    assert record.combination == "E2M1"
    assert record.direction == "SHORT"
    assert record.reference_key == row.reference_key
    assert record.canonical_state == EntryModelState.READY.value
    assert record.canonical_state_source == "EntryModelState"
    assert record.stage == STAGE_ENTRY_AVAILABLE


def test_projected_record_retains_timestamps():
    row = _row()
    record = project_setup_row(row)
    assert record.first_seen_time == row.first_seen_time
    assert record.last_seen_time == row.last_seen_time
    assert record.ready_time == row.ready_time
    assert record.final_time == row.final_time


def test_occurrence_status_takes_precedence_over_detection_state():
    """A realized fill is strictly later information than the detection funnel."""
    row = _row(final_state=EntryModelState.READY.value)
    record = project_setup_row(row, STATUS_FILLED)
    assert record.stage == STAGE_FILLED
    assert record.canonical_state == STATUS_FILLED
    assert record.canonical_state_source == "fill_simulator"


def test_invalidated_before_fill_overrides_ready_detection_state():
    row = _row(final_state=EntryModelState.READY.value)
    record = project_setup_row(row, STATUS_INVALIDATED_BEFORE_FILL)
    assert record.stage == STAGE_INVALIDATED
    assert record.resolution_status == RESOLUTION_TERMINAL


def test_projection_is_always_canonically_sourced():
    record = project_setup_row(_row())
    assert record.is_authoritative_canonical is True


# ===========================================================================
# Determinism / aggregation
# ===========================================================================

def test_projection_is_deterministic():
    row = _row()
    assert project_setup_row(row) == project_setup_row(row)


def test_batch_projection_is_deterministically_ordered():
    rows = [
        _row(setup_id="SETUP-B", first_seen_time=datetime(2026, 9, 2, 8, 0, tzinfo=UTC)),
        _row(setup_id="SETUP-A", first_seen_time=datetime(2026, 9, 1, 8, 0, tzinfo=UTC)),
    ]
    first = project_setup_rows(rows)
    second = project_setup_rows(list(reversed(rows)))
    assert first == second, "ordering must not depend on input order"
    assert [r.setup_family_id for r in first] == ["SETUP-A", "SETUP-B"]


def test_batch_projection_applies_occurrence_statuses_by_setup():
    rows = [
        _row(setup_id="SETUP-A"),
        _row(setup_id="SETUP-B"),
    ]
    records = project_setup_rows(rows, {"SETUP-B": STATUS_FILLED})
    by_id = {r.setup_family_id: r for r in records}
    assert by_id["SETUP-A"].stage == STAGE_ENTRY_AVAILABLE
    assert by_id["SETUP-B"].stage == STAGE_FILLED


def test_stage_counts_are_zero_filled():
    counts = stage_counts([project_setup_row(_row())])
    assert counts[STAGE_ENTRY_AVAILABLE] == 1
    assert counts[STAGE_WATCHING] == 0
    assert counts[STAGE_RESOLVED] == 0
    assert set(counts) >= set(LIFECYCLE_ORDER)


def test_funnel_advances_counts_reached_at_least():
    """'Reached ENTRY_AVAILABLE' must include records that progressed past it."""
    records = [
        project_setup_row(_row(setup_id="A")),
        project_setup_row(_row(setup_id="B"), STATUS_FILLED),
    ]
    advances = funnel_advances(records)
    assert advances[STAGE_WATCHING] == 2
    assert advances[STAGE_QUALIFIED] == 2
    assert advances[STAGE_ENTRY_AVAILABLE] == 2
    assert advances[STAGE_FILLED] == 1
    assert advances[STAGE_RESOLVED] == 0


def test_blocked_and_invalidated_are_not_counted_as_progress():
    records = [project_setup_row(_row(final_state=EntryModelState.INVALIDATED.value))]
    advances = funnel_advances(records)
    assert all(v == 0 for v in advances.values())


def test_empty_ledger_projects_to_empty():
    assert project_setup_rows([]) == ()


# ===========================================================================
# RESEARCH_ONLY boundary
# ===========================================================================

def test_lifecycle_module_has_no_execution_reach():
    tree = ast.parse(LIFECYCLE_MODULE.read_text(encoding="utf-8"), filename=str(LIFECYCLE_MODULE))
    forbidden = {"execution.executor", "execution.coordinator", "execution.adapter",
                 "mt5.management_gateway", "execution.mt5_gateway", "MetaTrader5"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, f"imports {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert module not in forbidden, f"imports from {module}"
            assert not module.startswith("execution."), f"imports from {module}"


def test_lifecycle_module_never_calls_order_functions():
    source = LIFECYCLE_MODULE.read_text(encoding="utf-8")
    for name in ("order_send", "order_check", "positions_close", "positions_modify"):
        assert name not in source


def test_large_smc_remains_research_only():
    """No demo/live eligibility may be asserted anywhere in this projection."""
    source = LIFECYCLE_MODULE.read_text(encoding="utf-8")
    for claim in ("DEMO_ELIGIBLE", "LIVE_ELIGIBLE", "ECONOMIC_EDGE"):
        assert claim not in source
    assert "RESEARCH_ONLY" in source
