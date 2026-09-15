"""Tests for validation_framework.svos_context_export -- WORK PACKAGE F compact state
export, updated per Cycle-1 remediation V2 (svos_lifecycle_stage/furthest_verified_gate
replace the removed AG-invented hypothesis_stage label)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from validation_framework.models import GateResult, GateStatus, LifecycleStage
from validation_framework.svos_contracts import HoldoutState
from validation_framework.svos_context_export import build_svos_context, write_svos_context


def _gate(name, status):
    return GateResult(
        gate_name=name, status=status, evidence_refs=("artifacts/x.json",),
        evaluated_at=datetime(2026, 9, 15, tzinfo=timezone.utc), evaluator_version="test_v1",
    )


def _holdout():
    return HoldoutState(strategy_id="ST_X", sealed=True, access_count=0, last_accessed_utc=None)


def _build(**overrides):
    kwargs = dict(
        strategy_id="ST_X", strategy_version="1.0.0", hypothesis_id="HYP_A",
        branch="main", head_sha="abc123", svos_lifecycle_stage=LifecycleStage.OFFLINE_RESEARCH.value,
        furthest_verified_gate=None, gate_results={"G1": _gate("G1", GateStatus.PASS)},
        evidence_hashes={"population": "deadbeef"}, holdout=_holdout(),
        blocking_issues=["G3 not yet evaluated"], next_authorized_action="run G3 economic gate",
    )
    kwargs.update(overrides)
    return build_svos_context(**kwargs)


def test_build_context_only_reports_supplied_gates():
    ctx = _build()
    assert set(ctx["gates"].keys()) == {"G1"}
    assert "G2" not in ctx["gates"]
    assert "G3" not in ctx["gates"]
    assert ctx["holdout"]["sealed"] is True
    assert ctx["holdout"]["access_count"] == 0


def test_context_reports_real_svos_stage_not_an_ag_invented_label():
    ctx = _build(svos_lifecycle_stage=LifecycleStage.OFFLINE_RESEARCH.value, furthest_verified_gate="G2")
    assert ctx["svos_lifecycle_stage"] == "OFFLINE_RESEARCH"
    assert ctx["furthest_verified_gate"] == "G2"
    assert ctx["validation_methodology_id"] == "AG_VALIDATION_G0_G10_V1"


def test_context_excludes_raw_data_by_construction():
    ctx = _build(hypothesis_id=None, gate_results={}, evidence_hashes={}, blocking_issues=[],
                 svos_lifecycle_stage=None, furthest_verified_gate=None)
    serialized = json.dumps(ctx)
    assert "candle" not in serialized.lower()
    assert len(serialized) < 5000


def test_write_svos_context_round_trips(tmp_path):
    ctx = _build()
    path = str(tmp_path / "svos_context.json")
    write_svos_context(ctx, path)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["strategy_id"] == "ST_X"


def test_write_svos_context_rejects_oversized_string_field(tmp_path):
    ctx = _build(blocking_issues=["x" * 3000])
    with pytest.raises(ValueError):
        write_svos_context(ctx, str(tmp_path / "svos_context.json"))


def test_write_svos_context_rejects_oversized_list(tmp_path):
    ctx = _build(blocking_issues=[f"issue_{i}" for i in range(600)])
    with pytest.raises(ValueError):
        write_svos_context(ctx, str(tmp_path / "svos_context.json"))


def test_context_contains_no_raw_candle_population_secret_or_holdout_content():
    """Adversarial (V2 test #13): confirms the built context, across every gate/evidence
    field, never carries anything beyond compact labels/hashes/paths."""
    ctx = _build(
        gate_results={"G1": _gate("G1", GateStatus.PASS), "G2": _gate("G2", GateStatus.PASS),
                      "G3": _gate("G3", GateStatus.FAIL)},
        evidence_hashes={"g1": "a" * 64, "g2": "b" * 64, "g3": None},
    )
    serialized = json.dumps(ctx).lower()
    for forbidden in ("candle", "ohlc", "tick", "occurrence_id", "password", "secret", "token", "api_key"):
        assert forbidden not in serialized
    assert ctx["holdout"]["access_count"] == 0
    assert ctx["holdout"]["sealed"] is True
