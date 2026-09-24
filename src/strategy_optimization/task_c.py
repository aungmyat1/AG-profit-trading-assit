"""Read-only Task C registration helper; it never replays data or compares arms."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

import yaml

from post_asian_pilot.fingerprint import fingerprint
from .models import (
    BaselineStatus,
    CandidateStrategy,
    ExperimentHypothesis,
    ExperimentManifest,
    HypothesisStatus,
    StrategyBaseline,
)
from .registry import ExperimentRegistry
from .state_machine import CandidateState

TASK_C_EXPERIMENT_ID = "AG_LSR_TASK_C_PER_SYMBOL_POSITION_GUARD_V1"
TASK_C_BASELINE_SEARCH_REF = (
    "artifacts/optimization/evidence/AG_LIQUIDITY_SWEEP_RETEST_BASELINE_PROVENANCE_SEARCH_V1.json"
)
_TASK_C_IMPLEMENTATION_PATHS = (
    "src/execution/position_guard.py",
    "src/strategy_engine/sweep_retest/engine.py",
)
_TASK_C_TEST_PATHS = (
    "tests/test_liquidity_sweep_retest_strategy.py",
    "tests/test_btc_sweep_research_pipeline.py",
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_task_c_manifest(
    repo_root: str | Path,
    *,
    created_at_utc: Optional[str] = None,
) -> ExperimentManifest:
    """Create the Task C identity record from config/source bytes and status evidence."""
    root = Path(repo_root)
    strategy_id = "ST_LIQUIDITY_SWEEP_RETEST_V1"
    config_ref = "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"
    config_path = root / config_ref
    config_sha256 = _sha256_file(config_path)
    try:
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError("cannot read canonical LSR strategy config") from exc
    if not isinstance(config, Mapping) or str(config.get("strategy_id", "")) != strategy_id:
        raise ValueError("canonical LSR strategy identity mismatch")
    config_version = str(config.get("version", ""))
    if not config_version:
        raise ValueError("canonical LSR strategy version missing")
    implementation_hashes: Mapping[str, str] = {
        path: _sha256_file(root / path) for path in _TASK_C_IMPLEMENTATION_PATHS
    }
    verification_hashes: Mapping[str, str] = {
        path: _sha256_file(root / path) for path in _TASK_C_TEST_PATHS
    }
    implementation_sha256 = fingerprint(dict(implementation_hashes))

    baseline = StrategyBaseline(
        strategy_id=strategy_id,
        strategy_version=config_version,
        canonical_config_ref=config_ref,
        canonical_config_sha256=config_sha256,
        baseline_status=BaselineStatus.NOT_REPRODUCIBLE,
        baseline_sha256=None,
        dataset_id=None,
        dataset_sha256=None,
        population_hash=None,
        friction_profile_ref=None,
        friction_profile_sha256=None,
        source_refs=(
            "docs/status/AG_TASK_C_PER_SYMBOL_POSITION_GUARD_V1_STATUS.md",
            TASK_C_BASELINE_SEARCH_REF,
        ),
        blockers=(
            "EXACT_CONTROL_POPULATION_NOT_REPRODUCED",
            "ORIGINAL_REPLAY_SCRIPT_AND_CONFIG_NOT_IDENTIFIED",
            "POPULATION_MEMBERSHIP_AND_EXCLUSION_RULES_NOT_VERIFIED",
            "FRICTION_PROFILE_AND_ASSUMPTIONS_NOT_REPRODUCED",
        ),
    )
    hypothesis = ExperimentHypothesis(
        hypothesis_id="TASK_C_ENGINEERING_CHANGE_NOT_AN_ECONOMIC_HYPOTHESIS",
        strategy_id=strategy_id,
        parent_version=config_version,
        statement=(
            "Task C records an implemented guard-semantics candidate only; no causal economic "
            "hypothesis or improvement claim has been preregistered."
        ),
        mechanism="ENGINEERING_SEMANTICS_ONLY_ECONOMIC_MECHANISM_NOT_CLAIMED",
        permitted_delta=(
            "Liquidity Sweep Retest passes its setup symbol to the open-position guard, "
            "using the separate per-symbol cap.",
            "The open-position guard is checked after strategy qualification so a blocked "
            "setup retains its qualification evidence.",
        ),
        forbidden_deltas=(
            "No-symbol OpenPositionGuard callers retain the existing global cap.",
            "Do not wire max_open_strategy_positions or alter unrelated strategy callers.",
            "No strategy economics, entry/exit logic, sizing, or canonical strategy config changes.",
        ),
        status=HypothesisStatus.NOT_PREREGISTERED,
    )
    candidate = CandidateStrategy(
        strategy_id=strategy_id,
        parent_version=config_version,
        candidate_version=None,
        candidate_config_sha256=config_sha256,
        candidate_implementation_sha256=implementation_sha256,
        implementation_ref=(
            "working-tree candidate; user-cited commit 18947755 is not present in the local/remote refs"
        ),
        permitted_delta=hypothesis.permitted_delta,
        forbidden_deltas=hypothesis.forbidden_deltas,
        version_assignment_status="PENDING_OWNER_ASSIGNMENT",
        source_status="IMPLEMENTED_WORKTREE_PATCH_UNCOMMITTED",
    )
    return ExperimentManifest(
        experiment_id=TASK_C_EXPERIMENT_ID,
        strategy_id=strategy_id,
        baseline=baseline,
        hypothesis=hypothesis,
        candidate=candidate,
        dataset=None,
        created_at_utc=created_at_utc or _utc_now(),
        related_evidence_refs=(
            *baseline.source_refs,
            *implementation_hashes.keys(),
            *verification_hashes.keys(),
        ),
        notes=(
            "Implementation status: IMPLEMENTED (engineering candidate only).",
            "Experiment status: BLOCKED_REPRODUCIBILITY; the exact baseline is not verified.",
            "Economic claim: NOT_AVAILABLE; no control/candidate comparison or replay was run.",
            "The reported 99 setups / 50 taken / 49 blocked / 48 historical rejections are unverified provenance claims, not experiment metrics.",
            "No dataset was registered, consumed, or relabeled for this experiment.",
            "No candidate strategy version was assigned and no promotion decision was made.",
            "Candidate source SHA-256 map: " + repr(dict(implementation_hashes)),
            "Test source SHA-256 map: " + repr(dict(verification_hashes)),
        ),
    )


def register_task_c_experiment(
    repo_root: str | Path,
    registry_root: str | Path,
    *,
    actor: str = "strategy-optimization-bootstrap",
    created_at_utc: Optional[str] = None,
) -> ExperimentManifest:
    """Register Task C directly into the explicit terminal reproducibility block."""
    manifest = build_task_c_manifest(repo_root, created_at_utc=created_at_utc)
    registry = ExperimentRegistry(registry_root, repo_root=repo_root)
    registry.register(manifest, actor=actor, at_utc=created_at_utc)
    registry.transition(
        manifest.experiment_id,
        CandidateState.BLOCKED_REPRODUCIBILITY,
        actor=actor,
        evidence_refs={"baseline_provenance_search": [TASK_C_BASELINE_SEARCH_REF]},
        details={
            "implementation_status": "IMPLEMENTED",
            "experiment_status": "BLOCKED_REPRODUCIBILITY",
            "economic_claim": "NOT_AVAILABLE",
            "resume_policy": "NO_RESUME_OR_SUBSTITUTE_DATA; new owner-approved experiment required after baseline reproduction",
        },
        at_utc=created_at_utc,
    )
    return manifest


__all__ = [
    "TASK_C_BASELINE_SEARCH_REF", "TASK_C_EXPERIMENT_ID", "build_task_c_manifest",
    "register_task_c_experiment",
]
