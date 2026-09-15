"""Tests for validation_framework.hypothesis_stage -- the SVOS hypothesis micro-
lifecycle (WP-SV1/WORK PACKAGE B). Uses a temp directory for registry persistence so no
test ever touches real strategy evidence under artifacts/validation/."""
from __future__ import annotations

import pytest

from validation_framework.hypothesis_stage import (
    HYPOTHESIS_STAGE_ORDER,
    HypothesisStage,
    HypothesisStageError,
    apply_transition,
    get_hypothesis_stage,
    get_next_stage,
    is_legal_transition,
    read_hypothesis_stage_registry,
    write_hypothesis_stage_record,
)


def test_stage_order_matches_spec_sequence():
    assert [s.value for s in HYPOTHESIS_STAGE_ORDER] == [
        "DRAFT", "INTAKE", "AUDIT", "REFINEMENT", "HISTORICAL_REPLAY",
        "BACKTEST", "STATISTICAL_VALIDATION", "ROBUSTNESS_VALIDATION", "VIRTUAL_DEMO",
    ]


@pytest.mark.parametrize("source,target", [
    (HypothesisStage.DRAFT, HypothesisStage.INTAKE),
    (HypothesisStage.INTAKE, HypothesisStage.AUDIT),
    (HypothesisStage.AUDIT, HypothesisStage.REFINEMENT),
    (HypothesisStage.REFINEMENT, HypothesisStage.HISTORICAL_REPLAY),
    (HypothesisStage.HISTORICAL_REPLAY, HypothesisStage.BACKTEST),
    (HypothesisStage.BACKTEST, HypothesisStage.STATISTICAL_VALIDATION),
    (HypothesisStage.STATISTICAL_VALIDATION, HypothesisStage.ROBUSTNESS_VALIDATION),
    (HypothesisStage.ROBUSTNESS_VALIDATION, HypothesisStage.VIRTUAL_DEMO),
])
def test_legal_adjacent_transitions(source, target):
    assert is_legal_transition(source, target) is True


def test_backtest_fail_to_refinement_is_legal():
    assert is_legal_transition(HypothesisStage.BACKTEST, HypothesisStage.REFINEMENT) is True


@pytest.mark.parametrize("source,target", [
    (HypothesisStage.DRAFT, HypothesisStage.AUDIT),  # skip
    (HypothesisStage.DRAFT, HypothesisStage.VIRTUAL_DEMO),  # big skip
    (HypothesisStage.BACKTEST, HypothesisStage.DRAFT),  # arbitrary backward
    (HypothesisStage.STATISTICAL_VALIDATION, HypothesisStage.REFINEMENT),  # only BACKTEST may do this
    (HypothesisStage.DRAFT, HypothesisStage.DRAFT),  # self
])
def test_illegal_transitions_rejected(source, target):
    assert is_legal_transition(source, target) is False
    with pytest.raises(HypothesisStageError):
        apply_transition(source, target, "HYP_TEST", "illegal")


def test_get_next_stage_terminal_is_none():
    assert get_next_stage(HypothesisStage.VIRTUAL_DEMO) is None
    assert get_next_stage(HypothesisStage.DRAFT) == HypothesisStage.INTAKE


def test_apply_transition_returns_record_on_legal_edge():
    t = apply_transition(HypothesisStage.DRAFT, HypothesisStage.INTAKE, "HYP_TEST", "data admitted")
    assert t.source_stage == HypothesisStage.DRAFT
    assert t.target_stage == HypothesisStage.INTAKE


def test_registry_missing_file_returns_empty(tmp_path):
    registry = read_hypothesis_stage_registry(str(tmp_path), "ST_DOES_NOT_EXIST")
    assert registry == {}


def test_write_then_read_round_trip(tmp_path):
    path = write_hypothesis_stage_record(str(tmp_path), "ST_X", "HYP_A", HypothesisStage.INTAKE, "1.0.0")
    assert path.endswith("HYPOTHESIS_STAGE_REGISTRY.json")
    stage = get_hypothesis_stage(str(tmp_path), "ST_X", "HYP_A", "1.0.0")
    assert stage == HypothesisStage.INTAKE


def test_get_stage_fails_closed_on_missing_entry(tmp_path):
    with pytest.raises(HypothesisStageError):
        get_hypothesis_stage(str(tmp_path), "ST_X", "HYP_MISSING", "1.0.0")


def test_get_stage_fails_closed_on_version_mismatch(tmp_path):
    write_hypothesis_stage_record(str(tmp_path), "ST_X", "HYP_A", HypothesisStage.BACKTEST, "1.0.0")
    with pytest.raises(HypothesisStageError):
        get_hypothesis_stage(str(tmp_path), "ST_X", "HYP_A", "1.1.0")


def test_write_preserves_other_hypotheses(tmp_path):
    write_hypothesis_stage_record(str(tmp_path), "ST_X", "HYP_A", HypothesisStage.DRAFT, "1.0.0")
    write_hypothesis_stage_record(str(tmp_path), "ST_X", "HYP_B", HypothesisStage.INTAKE, "1.0.0")
    registry = read_hypothesis_stage_registry(str(tmp_path), "ST_X")
    assert set(registry.keys()) == {"HYP_A", "HYP_B"}
