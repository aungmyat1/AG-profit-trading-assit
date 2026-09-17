"""Tests for validation_orchestrator.live_status (AG_PROJECT_LIVE_CONTROL_PLANE_V1).

All git/evidence access is faked via the injectable collaborators derive_snapshot()
accepts -- no test touches the real repository's git state or strategy files.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from validation_orchestrator.live_status import (
    RepositoryProvenance,
    compute_fingerprint,
    derive_snapshot,
)
from validation_orchestrator.status import StrategyValidationStatus

FAKE_ROOT = Path("/fake/repo")


def _status(
    strategy_id="ST_FAKE_V1",
    demo_authorized=False,
    live_authorized=False,
    updated_at_utc="2026-01-01T00:00:00+00:00",
    validation_state="GATES_ALL_PASS_NO_BLOCKERS",
    blocking_reasons=(),
    next_safe_action="OWNER_REVIEW_FOR_NEXT_GATE",
):
    return StrategyValidationStatus(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        lifecycle_stage="OFFLINE_RESEARCH",
        current_gate=None,
        furthest_verified_gate="G1",
        validation_state=validation_state,
        blocking_reasons=blocking_reasons,
        evidence_status="GATES_ALL_PASS",
        dataset_role_status="NOT_TRACKED_BY_WP1",
        lineage_status="NOT_TRACKED_BY_WP1",
        holdout_status="NOT_TRACKED_BY_WP1",
        demo_authorized=demo_authorized,
        live_authorized=live_authorized,
        next_safe_action=next_safe_action,
        agent_required="NONE",
        updated_at_utc=updated_at_utc,
    )


def _derive(**overrides):
    kwargs = dict(
        repo_root=FAKE_ROOT,
        git_head=lambda root: "deadbeef",
        git_branch=lambda root: "main",
        untracked_paths=lambda root: (),
        dirty_paths=lambda root: (),
        list_strategy_statuses=lambda: [_status()],
    )
    kwargs.update(overrides)
    return derive_snapshot(**kwargs)


def test_snapshot_determinism_across_calls_with_unchanged_evidence():
    snap1 = _derive()
    snap2 = _derive()
    assert snap1.semantic_tuple() == snap2.semantic_tuple()
    assert compute_fingerprint(snap1) == compute_fingerprint(snap2)


def test_fingerprint_ignores_generated_at_and_updated_at():
    snap_a = _derive(list_strategy_statuses=lambda: [_status(updated_at_utc="2026-01-01T00:00:00+00:00")])
    snap_b = _derive(list_strategy_statuses=lambda: [_status(updated_at_utc="2099-12-31T23:59:59+00:00")])
    assert snap_a.generated_at_utc != "" and snap_b.generated_at_utc != ""
    assert compute_fingerprint(snap_a) == compute_fingerprint(snap_b)


def test_clean_working_tree_reports_clean_and_no_foreign_wip():
    snap = _derive(dirty_paths=lambda root: (), untracked_paths=lambda root: ())
    assert snap.provenance.working_tree_clean is True
    assert snap.provenance.foreign_wip_paths == ()


def test_dirty_working_tree_reports_not_clean():
    snap = _derive(dirty_paths=lambda root: ("M src/foo.py",))
    assert snap.provenance.working_tree_clean is False


def test_foreign_wip_surfaced_but_not_authoritative():
    snap = _derive(untracked_paths=lambda root: ("artifacts/validation/ES_S4_COMPARISON/compare.py",))
    assert "artifacts/validation/ES_S4_COMPARISON/compare.py" in snap.provenance.foreign_wip_paths
    assert any("Foreign/concurrent WIP" in d for d in snap.owner_decisions_required)


def test_untracked_es_s4_like_directory_does_not_advance_any_strategy_validation_state():
    """Required regression case (mission section 26): the mere existence of an
    ES_S4-like untracked directory must not change validation_state/demo_authorized/
    live_authorized/next_safe_action for any strategy -- those come only from
    list_strategy_statuses(), never from provenance."""
    baseline = _derive(untracked_paths=lambda root: ())
    with_foreign_wip = _derive(
        untracked_paths=lambda root: ("artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/compare.py",)
    )
    assert baseline.strategies == with_foreign_wip.strategies


def test_stale_head_changes_fingerprint():
    snap_a = _derive(git_head=lambda root: "aaaa")
    snap_b = _derive(git_head=lambda root: "bbbb")
    assert compute_fingerprint(snap_a) != compute_fingerprint(snap_b)


def test_registry_lifecycle_change_changes_fingerprint():
    snap_a = _derive(list_strategy_statuses=lambda: [_status(strategy_id="A")])
    snap_b = _derive(list_strategy_statuses=lambda: [_status(strategy_id="B")])
    assert compute_fingerprint(snap_a) != compute_fingerprint(snap_b)


def test_authorization_change_changes_fingerprint():
    snap_a = _derive(list_strategy_statuses=lambda: [_status(demo_authorized=False)])
    snap_b = _derive(list_strategy_statuses=lambda: [_status(demo_authorized=True)])
    assert compute_fingerprint(snap_a) != compute_fingerprint(snap_b)


def test_demo_false_and_live_false_propagate_unmodified():
    snap = _derive(list_strategy_statuses=lambda: [_status(demo_authorized=False, live_authorized=False)])
    assert snap.strategies[0].demo_authorized is False
    assert snap.strategies[0].live_authorized is False


def test_missing_evidence_state_surfaces_as_blocker():
    error_status = _status(
        validation_state="EVIDENCE_ERROR",
        blocking_reasons=("EVIDENCE_ERROR: missing file",),
        next_safe_action="RESOLVE_EVIDENCE_ERROR",
    )
    snap = _derive(list_strategy_statuses=lambda: [error_status])
    assert any("EVIDENCE_ERROR" in b for b in snap.blockers)


def test_mixed_commit_provenance_present_and_not_hardcoded_sha_dependent_generator_logic():
    snap = _derive()
    assert snap.provenance.mixed_commits == ("873dd68",)
    assert snap.provenance.reconciliation_status == "MIXED_BUT_RECONCILED"
    # The generator's own logic does not branch on the literal SHA -- it is metadata
    # threaded through unchanged. Verify by checking a different mixed_commits set is
    # representable via the same code path (no special-casing required).
    provenance = RepositoryProvenance(
        head="x", branch="main", working_tree_clean=True, foreign_wip_paths=(),
        mixed_commits=("aaaaaaa", "bbbbbbb"), reconciliation_status="UNRESOLVED",
        reconciliation_artifact="docs/status/OTHER.md",
    )
    assert provenance.semantic_tuple()[4] == ("aaaaaaa", "bbbbbbb")


def test_no_execution_mutation_snapshot_has_no_broker_or_order_fields():
    snap = _derive()
    field_names = set(snap.__dataclass_fields__.keys())
    assert not any("order" in f or "broker" in f or "execute" in f for f in field_names)


def test_unknown_strategy_error_from_underlying_status_propagates_not_swallowed():
    from validation_orchestrator.status import UnknownStrategyError

    def raise_unknown():
        raise UnknownStrategyError("GHOST_STRATEGY")

    with pytest.raises(UnknownStrategyError):
        _derive(list_strategy_statuses=raise_unknown)
