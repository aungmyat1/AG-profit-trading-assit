"""Read-only strategy-specific adapters for the common optimization program.

Adapters snapshot only canonical configuration, registry/lifecycle identity, and named
status references. They never merge economics or datasets across strategy IDs and never
invoke replay, candidate optimization, or execution code.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import yaml


@dataclass(frozen=True)
class StrategyTrackAdapter:
    strategy_id: str
    config_ref: str
    validation_adapter_ref: str
    evidence_refs: Tuple[str, ...]
    recommendation_focus: str
    recommendation_source: str = "USER_RECOMMENDATION_2026-09-24"
    validation_state_ref: Optional[str] = None


STRATEGY_TRACK_ADAPTERS: Tuple[StrategyTrackAdapter, ...] = (
    StrategyTrackAdapter(
        strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
        config_ref="strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml",
        validation_adapter_ref="validation_framework.adapters.session_sweep_continuation_adapter.build_session_sweep_continuation_record",
        validation_state_ref="artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json",
        evidence_refs=(
            "docs/status/AG_SSC_HYP001_POST_V1_0_1_REASSESSMENT_STATUS.md",
            "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_POST_V1_0_1_REASSESSMENT/HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT.md",
            "artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_ECONOMIC_RESULT_ATTEMPT_2/economic_evaluation.json",
        ),
        recommendation_focus=(
            "Keep the frozen SSC hypotheses separate; first resolve the existing owner-adjudication gate. "
            "Do not start WP4B, a new replay, or parameter search in this package."
        ),
    ),
    StrategyTrackAdapter(
        strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1",
        config_ref="strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml",
        validation_adapter_ref="validation_framework.adapters.btc_adapter.build_btc_record",
        evidence_refs=(
            "docs/status/AG_TASK_C_PER_SYMBOL_POSITION_GUARD_V1_STATUS.md",
            "artifacts/optimization/evidence/AG_LIQUIDITY_SWEEP_RETEST_BASELINE_PROVENANCE_SEARCH_V1.json",
            "artifacts/backtests/entry_only_result.json",
            "artifacts/validation_evidence/determinism/ST_LIQUIDITY_SWEEP_RETEST_V1_2_0_0/",
        ),
        recommendation_focus=(
            "Recover the exact 99/50/49/48 control population and friction assumptions before any paired replay. "
            "The Task C implementation may be recorded, but its economics remain unavailable."
        ),
    ),
    StrategyTrackAdapter(
        strategy_id="ST_LARGE_SMC_V1",
        config_ref="strategies/ST_LARGE_SMC_V1.yaml",
        validation_adapter_ref="validation_framework.adapters.large_smc_adapter.build_large_smc_record",
        evidence_refs=(
            "docs/status/AG_LARGE_SMC_V1_FORWARD_TO_SHADOW_EVIDENCE_CONTRACT_V1_STATUS.md",
            "strategies/STRATEGY_LEDGER.md",
            "artifacts/validation_evidence/determinism/ST_LARGE_SMC_V1_1_0_7/",
        ),
        recommendation_focus=(
            "Keep Large-SMC's E-to-M and C10 computability questions in its own track; "
            "no measurement work is started by this inventory."
        ),
    ),
    StrategyTrackAdapter(
        strategy_id="ST_ASIAN_SWEEP_5R_V1",
        config_ref="strategies/ST_ASIAN_SWEEP_5R_V1.yaml",
        validation_adapter_ref="validation_framework.adapters.fx_adapter.build_fx_record",
        evidence_refs=(
            "strategies/STRATEGY_LEDGER.md",
            "artifacts/validation_evidence/determinism/ST_ASIAN_SWEEP_5R_V1_1_1/",
            "tests/test_fx_shadow_entry_gate.py",
        ),
        recommendation_focus=(
            "Preserve Asian Sweep as an independent strategy/version and verify any weak-edge concern "
            "against its own evidence before proposing a change; no replay or optimization is performed here."
        ),
    ),
)


def _load_yaml(path: Path) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read strategy governance YAML: {path}") from exc
    if not isinstance(value, Mapping):
        raise ValueError(f"strategy governance YAML is not a mapping: {path}")
    return value


def _sha256_bytes(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()


def _strict_bool(entry: Mapping[str, Any], field: str) -> bool:
    value = entry.get(field)
    if type(value) is not bool:
        raise ValueError(f"strategy authority field must be an explicit boolean: {field}")
    return value


def _read_validation_version(repo_root: Path, ref: Optional[str]) -> Optional[str]:
    if ref is None:
        return None
    path = repo_root / ref
    try:
        import json
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, Mapping):
        return None
    for key in ("strategy_version", "semantic_version", "version"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    identity = payload.get("strategy")
    if isinstance(identity, Mapping):
        for key in ("strategy_version", "semantic_version", "version"):
            if identity.get(key) is not None:
                return str(identity[key])
    return None


def build_track_snapshot(repo_root: str | Path, adapter: StrategyTrackAdapter) -> Mapping[str, Any]:
    """Return one strategy's config, authority, lifecycle, and provenance references."""
    root = Path(repo_root)
    config_path = root / adapter.config_ref
    config = _load_yaml(config_path)
    if str(config.get("strategy_id", "")) != adapter.strategy_id:
        raise ValueError(f"canonical strategy ID mismatch: {adapter.config_ref}")
    version = str(config.get("version", ""))
    if not version:
        raise ValueError(f"canonical strategy version missing: {adapter.config_ref}")

    registry_ref = "strategies/registry.yaml"
    registry = _load_yaml(root / registry_ref).get("strategies", {})
    lifecycle_ref = "config/governance/strategy_lifecycle.yaml"
    lifecycle = _load_yaml(root / lifecycle_ref).get("strategies", {})
    registry_entry = registry.get(adapter.strategy_id) if isinstance(registry, Mapping) else None
    lifecycle_entry = lifecycle.get(adapter.strategy_id) if isinstance(lifecycle, Mapping) else None
    if not isinstance(registry_entry, Mapping):
        raise ValueError(f"strategy missing from authority registry: {adapter.strategy_id}")
    if not isinstance(lifecycle_entry, Mapping):
        raise ValueError(f"strategy missing from lifecycle registry: {adapter.strategy_id}")

    lifecycle_version = str(lifecycle_entry.get("semantic_version", ""))
    lifecycle_stage = str(lifecycle_entry.get("lifecycle_stage", ""))
    conflicts = []
    if lifecycle_version != version:
        conflicts.append({
            "source": lifecycle_ref,
            "canonical_version": version,
            "observed_version": lifecycle_version,
            "classification": "CANONICAL_VERSION_MISMATCH_FAIL_CLOSED",
        })
    validation_version = _read_validation_version(root, adapter.validation_state_ref)
    if validation_version and validation_version != version:
        conflicts.append({
            "source": adapter.validation_state_ref,
            "canonical_version": version,
            "observed_version": validation_version,
            "classification": "STALE_OR_VERSION_MISMATCHED_EVIDENCE_SNAPSHOT_NOT_CANONICAL_AUTHORITY",
        })

    source_hashes = {
        adapter.config_ref: _sha256_bytes(config_path.read_bytes()),
        registry_ref: _sha256_bytes((root / registry_ref).read_bytes()),
        lifecycle_ref: _sha256_bytes((root / lifecycle_ref).read_bytes()),
    }
    return {
        "strategy_id": adapter.strategy_id,
        "canonical_version": version,
        "canonical_config_ref": adapter.config_ref,
        "canonical_config_status": str(config.get("status", "NOT_DECLARED")),
        "canonical_lifecycle_stage": lifecycle_stage,
        "lifecycle_version": lifecycle_version,
        "strategy_authority": {
            "registered": _strict_bool(registry_entry, "registered"),
            "active": _strict_bool(registry_entry, "active"),
            "research": _strict_bool(registry_entry, "research"),
            "demo_authorized": _strict_bool(registry_entry, "demo_authorized"),
            "live_authorized": _strict_bool(registry_entry, "live_authorized"),
        },
        "validation_adapter_ref": adapter.validation_adapter_ref,
        "validation_state_ref": adapter.validation_state_ref,
        "version_conflicts": conflicts,
        "recommendation_focus": adapter.recommendation_focus,
        "recommendation_source": adapter.recommendation_source,
        "recommendation_independently_revalidated": False,
        "evidence_refs": list(adapter.evidence_refs),
        "source_sha256": source_hashes,
        "inventory_scope": "IDENTITY_AND_EXISTING_STATUS_REFERENCES_ONLY_NO_REPLAY_NO_DATASET_CONSUMPTION",
    }


__all__ = ["STRATEGY_TRACK_ADAPTERS", "StrategyTrackAdapter", "build_track_snapshot"]
