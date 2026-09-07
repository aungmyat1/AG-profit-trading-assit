"""validation_framework.lifecycle_registry -- the single canonical machine-readable
lifecycle-stage authority (AG_PROJECT_READINESS_POST_LARGE_SMC_PROMOTION_
IMPLEMENTATION_V2 / AG_ALL_STRATEGIES_DEMO_ELIGIBILITY_IMPLEMENTATION_V1, P0).

Proves: all three real adapters read their lifecycle_stage from the same registry file
(not an independent hardcoded constant); missing-strategy/missing-stage/unknown-enum/
version-mismatch all fail closed rather than defaulting; get_next_stage is derived from
the single canonical LIFECYCLE_ORDER, not a second stored fact.
"""
from __future__ import annotations

import os

import pytest

from validation_framework.adapters.btc_adapter import build_btc_record
from validation_framework.adapters.fx_adapter import build_fx_record
from validation_framework.adapters.large_smc_adapter import build_large_smc_record
from validation_framework.lifecycle_registry import (
    LifecycleRegistryError,
    get_lifecycle_stage,
    get_next_stage,
)
from validation_framework.models import LifecycleStage

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_REGISTRY_YAML = """\
schema_version: "1"
strategies:
  ST_GOOD_V1:
    semantic_version: "1.0.0"
    lifecycle_stage: OPERATIONAL_SHADOW
  ST_BAD_STAGE_V1:
    semantic_version: "1.0.0"
    lifecycle_stage: NOT_A_REAL_STAGE
  ST_NO_STAGE_V1:
    semantic_version: "1.0.0"
"""

_MALFORMED_YAML = """\
schema_version: "1"
not_strategies_key: {}
"""


def _write_registry(tmp_path, content):
    repo_root = tmp_path / "repo"
    gov_dir = repo_root / "config" / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "strategy_lifecycle.yaml").write_text(content, encoding="utf-8")
    return str(repo_root)


# --------------------------------------------------------------------------- real-adapter reads


def test_fx_lifecycle_read_from_registry():
    record = build_fx_record(repo_root=REPO_ROOT)
    assert record.lifecycle_stage == LifecycleStage.OPERATIONAL_SHADOW
    assert get_lifecycle_stage("ST_ASIAN_SWEEP_5R_V1", "1.1.1", repo_root=REPO_ROOT) == LifecycleStage.OPERATIONAL_SHADOW


def test_btc_lifecycle_read_from_registry():
    record = build_btc_record(repo_root=REPO_ROOT)
    assert record.lifecycle_stage == LifecycleStage.FORWARD_RESEARCH
    assert get_lifecycle_stage("ST_LIQUIDITY_SWEEP_RETEST_V1", "2.0.0", repo_root=REPO_ROOT) == LifecycleStage.FORWARD_RESEARCH


def test_large_smc_lifecycle_read_from_registry_is_forward_research():
    record = build_large_smc_record(repo_root=REPO_ROOT)
    assert record.lifecycle_stage == LifecycleStage.FORWARD_RESEARCH
    assert get_lifecycle_stage("ST_LARGE_SMC_V1", "1.0.7", repo_root=REPO_ROOT) == LifecycleStage.FORWARD_RESEARCH


def test_no_independent_adapter_lifecycle_constant_remains():
    """The three adapter modules must not contain a bare `LifecycleStage.<X>` literal
    assigned directly to a `lifecycle_stage` variable -- the only way to obtain a stage
    must be through get_lifecycle_stage()."""
    import ast
    import inspect

    import validation_framework.adapters.btc_adapter as btc_mod
    import validation_framework.adapters.fx_adapter as fx_mod
    import validation_framework.adapters.large_smc_adapter as smc_mod

    for module in (fx_mod, btc_mod, smc_mod):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if "lifecycle_stage" in targets:
                    # The only permitted RHS is a call (get_lifecycle_stage(...)), never
                    # a bare LifecycleStage.X attribute access.
                    assert isinstance(node.value, ast.Call), (
                        f"{module.__name__}: lifecycle_stage is assigned a non-call "
                        f"value ({ast.dump(node.value)}) -- adapters must not own "
                        "lifecycle state independently of the registry"
                    )


# --------------------------------------------------------------------------- fail-closed


def test_missing_strategy_fails_closed(tmp_path):
    repo_root = _write_registry(tmp_path, _REGISTRY_YAML)
    with pytest.raises(LifecycleRegistryError, match="no lifecycle registry entry"):
        get_lifecycle_stage("ST_DOES_NOT_EXIST_V1", "1.0.0", repo_root=repo_root)


def test_invalid_lifecycle_enum_fails_closed(tmp_path):
    repo_root = _write_registry(tmp_path, _REGISTRY_YAML)
    with pytest.raises(LifecycleRegistryError, match="unknown lifecycle_stage"):
        get_lifecycle_stage("ST_BAD_STAGE_V1", "1.0.0", repo_root=repo_root)


def test_missing_lifecycle_stage_field_fails_closed(tmp_path):
    repo_root = _write_registry(tmp_path, _REGISTRY_YAML)
    with pytest.raises(LifecycleRegistryError, match="no lifecycle_stage"):
        get_lifecycle_stage("ST_NO_STAGE_V1", "1.0.0", repo_root=repo_root)


def test_version_mismatch_fails_closed(tmp_path):
    repo_root = _write_registry(tmp_path, _REGISTRY_YAML)
    with pytest.raises(LifecycleRegistryError, match="does not match caller's semantic_version"):
        get_lifecycle_stage("ST_GOOD_V1", "9.9.9", repo_root=repo_root)


def test_missing_registry_file_fails_closed(tmp_path):
    repo_root = str(tmp_path / "empty_repo")
    os.makedirs(repo_root)
    with pytest.raises(LifecycleRegistryError, match="lifecycle registry not found"):
        get_lifecycle_stage("ST_GOOD_V1", "1.0.0", repo_root=repo_root)


def test_malformed_registry_fails_closed(tmp_path):
    repo_root = _write_registry(tmp_path, _MALFORMED_YAML)
    with pytest.raises(LifecycleRegistryError, match="malformed lifecycle registry"):
        get_lifecycle_stage("ST_GOOD_V1", "1.0.0", repo_root=repo_root)


def test_matching_version_succeeds(tmp_path):
    repo_root = _write_registry(tmp_path, _REGISTRY_YAML)
    assert get_lifecycle_stage("ST_GOOD_V1", "1.0.0", repo_root=repo_root) == LifecycleStage.OPERATIONAL_SHADOW


# --------------------------------------------------------------------------- next-stage derivation


def test_get_next_stage_derives_from_canonical_order():
    assert get_next_stage(LifecycleStage.OFFLINE_RESEARCH) == LifecycleStage.FORWARD_RESEARCH
    assert get_next_stage(LifecycleStage.FORWARD_RESEARCH) == LifecycleStage.OPERATIONAL_SHADOW
    assert get_next_stage(LifecycleStage.OPERATIONAL_SHADOW) == LifecycleStage.DEMO_ELIGIBLE
    assert get_next_stage(LifecycleStage.LIVE_AUTHORIZED) is None  # terminal stage
