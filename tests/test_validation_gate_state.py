"""Tests for validation_framework.validation_gate_state -- Cycle-1 remediation V2:
replaces the removed HypothesisStage enum with a pure gate-evidence projection that
reads (never guesses, never writes) the real canonical SVOS LifecycleStage."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from validation_framework.lifecycle_registry import LifecycleRegistryError
from validation_framework.models import GateResult, GateStatus, LifecycleStage
from validation_framework.validation_gate_state import (
    describe_validation_gate_state,
    furthest_verified_gate,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _result(name, status):
    return GateResult(gate_name=name, status=status, evidence_refs=(),
                       evaluated_at=datetime(2026, 9, 15, tzinfo=timezone.utc), evaluator_version="test_v1")


def test_furthest_verified_gate_none_when_g0_missing():
    assert furthest_verified_gate({}) is None
    assert furthest_verified_gate({"G1": GateStatus.PASS}) is None  # G0 missing -- G1 never counts


def test_furthest_verified_gate_contiguous_prefix():
    statuses = {"G0": GateStatus.PASS, "G1": GateStatus.PASS, "G2": GateStatus.PASS}
    assert furthest_verified_gate(statuses) == "G2"


def test_furthest_verified_gate_stops_at_gap():
    """G0/G1 PASS, G2 missing, G3 PASS -- G3 must never count; a gap always wins."""
    statuses = {"G0": GateStatus.PASS, "G1": GateStatus.PASS, "G3": GateStatus.PASS}
    assert furthest_verified_gate(statuses) == "G1"


@pytest.mark.parametrize("blocking_status", [GateStatus.FAIL, GateStatus.BLOCKED, GateStatus.PARTIAL,
                                               GateStatus.UNSIGNED, GateStatus.NOT_VERIFIED])
def test_non_pass_status_blocks_further_gates(blocking_status):
    statuses = {"G0": GateStatus.PASS, "G1": GateStatus.PASS, "G2": GateStatus.PASS, "G3": blocking_status}
    assert furthest_verified_gate(statuses) == "G2"


def test_describe_state_reads_real_registry_for_known_strategy():
    """Uses the real repository registry -- ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.0 is
    OFFLINE_RESEARCH there today (config/governance/strategy_lifecycle.yaml)."""
    summary = describe_validation_gate_state(
        "ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.0", "HYP_002_SETUP_SELECTIVITY",
        {"G1": _result("G1", GateStatus.PASS), "G2": _result("G2", GateStatus.PASS),
         "G3": _result("G3", GateStatus.FAIL)},
        repo_root=REPO_ROOT,
    )
    assert summary.svos_lifecycle_stage == LifecycleStage.OFFLINE_RESEARCH
    assert summary.furthest_verified_gate is None  # G0 was never supplied -- gap wins
    assert summary.methodology_id == "AG_VALIDATION_G0_G10_V1"


def test_missing_svos_authority_fails_closed():
    """Adversarial: a strategy with no canonical registry entry must raise, never
    silently default to some LifecycleStage -- this is the enforced "missing SVOS
    authority fails closed" boundary."""
    with pytest.raises(LifecycleRegistryError):
        describe_validation_gate_state(
            "ST_DOES_NOT_EXIST", "9.9.9", None, {}, repo_root=REPO_ROOT,
        )


def test_describe_state_never_writes_to_lifecycle_registry_file():
    """Adversarial: calling this function must never mutate
    config/governance/strategy_lifecycle.yaml -- AG gate evidence cannot promote SVOS."""
    registry_path = os.path.join(REPO_ROOT, "config", "governance", "strategy_lifecycle.yaml")
    before = os.path.getmtime(registry_path)
    describe_validation_gate_state(
        "ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.0", None,
        {"G0": _result("G0", GateStatus.PASS)}, repo_root=REPO_ROOT,
    )
    after = os.path.getmtime(registry_path)
    assert before == after


def test_describe_state_does_not_advance_svos_stage_regardless_of_gate_evidence():
    """Even full G0-G3 PASS evidence must never change the reported svos_lifecycle_stage
    -- it always reflects the real registry value, independent of AG gate results."""
    all_pass = {name: _result(name, GateStatus.PASS) for name in ("G0", "G1", "G2", "G3")}
    summary = describe_validation_gate_state(
        "ST_SESSION_SWEEP_CONTINUATION_V1", "1.0.0", None, all_pass, repo_root=REPO_ROOT,
    )
    assert summary.svos_lifecycle_stage == LifecycleStage.OFFLINE_RESEARCH
