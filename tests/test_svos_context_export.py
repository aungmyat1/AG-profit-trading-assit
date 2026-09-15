"""Tests for validation_framework.svos_context_export -- WORK PACKAGE F compact state
export."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from validation_framework.models import GateResult, GateStatus
from validation_framework.svos_contracts import HoldoutState
from validation_framework.svos_context_export import build_svos_context, write_svos_context


def _gate(name, status):
    return GateResult(
        gate_name=name, status=status, evidence_refs=("artifacts/x.json",),
        evaluated_at=datetime(2026, 9, 15, tzinfo=timezone.utc), evaluator_version="test_v1",
    )


def _holdout():
    return HoldoutState(strategy_id="ST_X", sealed=True, access_count=0, last_accessed_utc=None)


def test_build_context_only_reports_supplied_gates():
    ctx = build_svos_context(
        strategy_id="ST_X", strategy_version="1.0.0", hypothesis_id="HYP_A",
        branch="main", head_sha="abc123", hypothesis_stage="BACKTEST",
        gate_results={"G1": _gate("G1", GateStatus.PASS)},
        evidence_hashes={"population": "deadbeef"},
        holdout=_holdout(), blocking_issues=["G3 not yet evaluated"],
        next_authorized_action="run G3 economic gate",
    )
    assert set(ctx["gates"].keys()) == {"G1"}
    assert "G2" not in ctx["gates"]
    assert "G3" not in ctx["gates"]
    assert ctx["holdout"]["sealed"] is True
    assert ctx["holdout"]["access_count"] == 0


def test_context_excludes_raw_data_by_construction():
    ctx = build_svos_context(
        strategy_id="ST_X", strategy_version="1.0.0", hypothesis_id=None,
        branch="main", head_sha="abc123", hypothesis_stage=None,
        gate_results={}, evidence_hashes={}, holdout=_holdout(),
        blocking_issues=[], next_authorized_action="none",
    )
    serialized = json.dumps(ctx)
    assert "candle" not in serialized.lower()
    assert len(serialized) < 5000


def test_write_svos_context_round_trips(tmp_path):
    ctx = build_svos_context(
        strategy_id="ST_X", strategy_version="1.0.0", hypothesis_id="HYP_A",
        branch="main", head_sha="abc123", hypothesis_stage="DRAFT",
        gate_results={}, evidence_hashes={}, holdout=_holdout(),
        blocking_issues=[], next_authorized_action="none",
    )
    path = str(tmp_path / "svos_context.json")
    write_svos_context(ctx, path)
    with open(path, encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["strategy_id"] == "ST_X"


def test_write_svos_context_rejects_oversized_string_field(tmp_path):
    ctx = build_svos_context(
        strategy_id="ST_X", strategy_version="1.0.0", hypothesis_id="HYP_A",
        branch="main", head_sha="abc123", hypothesis_stage="DRAFT",
        gate_results={}, evidence_hashes={}, holdout=_holdout(),
        blocking_issues=["x" * 3000], next_authorized_action="none",
    )
    with pytest.raises(ValueError):
        write_svos_context(ctx, str(tmp_path / "svos_context.json"))


def test_write_svos_context_rejects_oversized_list(tmp_path):
    ctx = build_svos_context(
        strategy_id="ST_X", strategy_version="1.0.0", hypothesis_id="HYP_A",
        branch="main", head_sha="abc123", hypothesis_stage="DRAFT",
        gate_results={}, evidence_hashes={}, holdout=_holdout(),
        blocking_issues=[f"issue_{i}" for i in range(600)], next_authorized_action="none",
    )
    with pytest.raises(ValueError):
        write_svos_context(ctx, str(tmp_path / "svos_context.json"))
