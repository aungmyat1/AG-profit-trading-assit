"""Tests for the V1.2 proposal-platform layer of the live-status snapshot
(AG_PROJECT_LIVE_CONTROL_PLANE_V2, mission P5/P6).

Proves the GOVERNANCE/RUNTIME separation on the proposal axis:
  - SSC (ST_SESSION_SWEEP_CONTINUATION_V1) is reported at version 1.0.1 with
    proposal_capable=true but economic_edge_established=false and
    execution_eligible=false;
  - LSMC (ST_LARGE_SMC_V1) reports proposal_generation_authorized=false from its own
    strategy YAML authority block;
  - proposal capability never implies economic edge or execution authority;
  - a meaningful proposal-platform change changes the governance fingerprint.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from validation_orchestrator.live_status import (  # noqa: E402
    ProposalPlatformEntry,
    compute_fingerprint,
    derive_snapshot,
)
from validation_orchestrator.render import render_markdown  # noqa: E402
from validation_orchestrator.status import StrategyValidationStatus  # noqa: E402


def _status(strategy_id="ST_FAKE_V1"):
    return StrategyValidationStatus(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        lifecycle_stage="OFFLINE_RESEARCH",
        current_gate=None,
        furthest_verified_gate="G1",
        validation_state="GATES_ALL_PASS_NO_BLOCKERS",
        blocking_reasons=(),
        evidence_status="GATES_ALL_PASS",
        dataset_role_status="NOT_TRACKED_BY_WP1",
        lineage_status="NOT_TRACKED_BY_WP1",
        holdout_status="NOT_TRACKED_BY_WP1",
        demo_authorized=False,
        live_authorized=False,
        next_safe_action="OWNER_REVIEW_FOR_NEXT_GATE",
        agent_required="NONE",
        updated_at_utc="2026-01-01T00:00:00+00:00",
    )


def _real_snapshot():
    return derive_snapshot(repo_root=REPO_ROOT)


def test_ssc_reported_at_v1_0_1_with_capability_but_no_edge_or_execution():
    snap = _real_snapshot()
    ssc = next(s for s in snap.strategies if s.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1")
    assert ssc.strategy_version == "1.0.1"

    entry = next(p for p in snap.proposal_platform if p.strategy_id == "ST_SESSION_SWEEP_CONTINUATION_V1")
    assert entry.proposal_capable is True
    assert entry.economic_edge_established is False
    assert entry.execution_eligible is False
    assert entry.broker_mutation_blocked is True


def test_lsmc_reports_proposal_generation_authorized_false():
    snap = _real_snapshot()
    entry = next(p for p in snap.proposal_platform if p.strategy_id == "ST_LARGE_SMC_V1")
    assert entry.proposal_capable is True  # adapter present
    assert entry.proposal_generation_authorized is False  # strategy YAML denies it
    assert entry.economic_edge_established is False
    assert entry.execution_eligible is False
    assert entry.broker_mutation_blocked is True


def test_proposal_capable_never_implies_economic_edge():
    for entry in _real_snapshot().proposal_platform:
        if entry.proposal_capable:
            assert entry.economic_edge_established is False


def test_proposal_capable_never_implies_execution_authority():
    for entry in _real_snapshot().proposal_platform:
        if entry.proposal_capable:
            assert entry.execution_eligible is False
            assert entry.broker_mutation_blocked is True


def test_proposal_platform_change_changes_governance_fingerprint():
    def make(gen_authorized: bool):
        return derive_snapshot(
            repo_root=Path("/fake"),
            git_head=lambda root: "deadbeef",
            git_branch=lambda root: "main",
            untracked_paths=lambda root: (),
            dirty_paths=lambda root: (),
            list_strategy_statuses=lambda: [_status()],
            proposal_platform_resolver=lambda root, strategies: (
                ProposalPlatformEntry(
                    strategy_id="ST_FAKE_V1",
                    proposal_capable=True,
                    proposal_generation_authorized=gen_authorized,
                    economic_edge_established=False,
                    execution_eligible=False,
                    broker_mutation_blocked=True,
                ),
            ),
        )

    fp_a = compute_fingerprint(make(False))
    fp_b = compute_fingerprint(make(True))
    assert fp_a != fp_b


def test_render_includes_proposal_platform_section():
    snap = _real_snapshot()
    fp = compute_fingerprint(snap)
    out = render_markdown(snap, fp)
    assert "## 6. Proposal Platform Status (V1.2)" in out
    assert "| ST_SESSION_SWEEP_CONTINUATION_V1 |" in out
    assert "| ST_LARGE_SMC_V1 |" in out
    assert "economic_edge_established" in out
    assert "execution_eligible" in out


def test_proposal_platform_is_part_of_governance_not_runtime():
    """The proposal-platform entry belongs to the governance snapshot/fingerprint, not
    to the optional runtime observation layer."""
    snap = _real_snapshot()
    field_names = set(snap.__dataclass_fields__.keys())
    assert "proposal_platform" in field_names
    assert compute_fingerprint(snap)  # proposal_platform feeds semantic_tuple
