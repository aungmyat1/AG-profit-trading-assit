"""validate_external_candidate_package() -- the candidate admission gate (mission
section 11).

Deterministic, fail-closed, read-only: never mutates the package, never mutates
`config/governance/strategy_lifecycle.yaml`, never grants lifecycle/Demo/Live
authority. Reuses `version_guard.check_version_mutation` and
`post_asian_pilot.fingerprint.fingerprint` rather than re-implementing either.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from .models import (
    REQUIRED_RULE_SECTIONS,
    SCHEMA_VERSION,
    AdmissionResult,
    AdmissionStatus,
    DatasetRole,
    ExternalCandidatePackage,
)
from .version_guard import check_version_mutation

DEFAULT_LIFECYCLE_REGISTRY = os.path.join("config", "governance", "strategy_lifecycle.yaml")


def _load_lifecycle_registry(repo_root: str, path: str) -> Dict[str, Any]:
    full_path = os.path.join(repo_root, path)
    if not os.path.isfile(full_path):
        return {}
    with open(full_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("strategies") or {}


def _ranges_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    # ISO-8601 strings compare correctly lexicographically only when both are
    # normalized (same offset representation); this repository's dataset manifests
    # already normalize to explicit UTC (`+00:00`), so string comparison is safe
    # here without re-parsing -- same convention used elsewhere in these manifests.
    return a_start <= b_end and b_start <= a_end


def validate_external_candidate_package(
    package: ExternalCandidatePackage,
    *,
    repo_root: str = ".",
    lifecycle_registry_path: str = DEFAULT_LIFECYCLE_REGISTRY,
    known_version_fingerprints: Optional[Mapping[Tuple[str, str], str]] = None,
) -> AdmissionResult:
    reasons: List[str] = []
    details: Dict[str, Any] = {}

    # -- schema --
    if package.schema_version != SCHEMA_VERSION:
        return AdmissionResult(
            AdmissionStatus.INCOMPLETE, package.candidate_id,
            (f"unrecognized schema_version {package.schema_version!r}, expected {SCHEMA_VERSION!r}",),
        )

    # -- freeze / holdout integrity (checked first: mission section 8 is a hard reject,
    #    never softened by otherwise-complete evidence elsewhere in the package) --
    if not package.candidate_frozen:
        return AdmissionResult(
            AdmissionStatus.REJECTED_NOT_FROZEN, package.candidate_id,
            ("candidate_frozen is False -- an unfrozen candidate cannot be admitted for validation",),
        )
    if package.holdout is None:
        return AdmissionResult(
            AdmissionStatus.INCOMPLETE, package.candidate_id,
            ("no HoldoutDeclaration present -- compliance is never inferred from its absence",),
        )
    if package.holdout.holdout_used_for_optimization or package.holdout.rules_changed_after_holdout:
        leak_reasons = []
        if package.holdout.holdout_used_for_optimization:
            leak_reasons.append("holdout_used_for_optimization=True")
        if package.holdout.rules_changed_after_holdout:
            leak_reasons.append("rules_changed_after_holdout=True")
        return AdmissionResult(
            AdmissionStatus.REJECTED_HOLDOUT_LEAKAGE, package.candidate_id, tuple(leak_reasons)
        )

    # -- strategy/version identity --
    lifecycle_strategies = _load_lifecycle_registry(repo_root, lifecycle_registry_path)
    if not package.strategy_id:
        reasons.append("strategy_id is empty")
    if package.parent_strategy_version:
        entry = lifecycle_strategies.get(package.strategy_id)
        recorded_version = entry.get("semantic_version") if entry else None
        if recorded_version is not None and recorded_version != package.parent_strategy_version:
            return AdmissionResult(
                AdmissionStatus.REJECTED_VERSION_CONFLICT, package.candidate_id,
                (
                    f"parent_strategy_version {package.parent_strategy_version!r} does not match "
                    f"the lifecycle registry's recorded semantic_version {recorded_version!r} for "
                    f"{package.strategy_id!r}",
                ),
            )
        if package.candidate_version == package.parent_strategy_version:
            return AdmissionResult(
                AdmissionStatus.REJECTED_VERSION_CONFLICT, package.candidate_id,
                ("candidate_version is identical to parent_strategy_version -- a frozen candidate must "
                 "be admitted as a NEW immutable version",),
            )

    version_check = check_version_mutation(
        package.strategy_id, package.candidate_version, package.provenance.candidate_config_hash,
        known_version_fingerprints,
    )
    if not version_check.ok:
        return AdmissionResult(
            AdmissionStatus.REJECTED_VERSION_MUTATION, package.candidate_id, (version_check.reason,)
        )

    # -- rules / parameters completeness --
    missing_sections = [s for s in REQUIRED_RULE_SECTIONS if not package.rules.rule_sections.get(s)]
    if missing_sections:
        reasons.append(f"missing rule_sections: {', '.join(missing_sections)}")
    if not package.rules.strategy_config_ref:
        reasons.append("rules.strategy_config_ref is empty -- candidate must reference an existing strategy config")
    elif not os.path.isfile(os.path.join(repo_root, package.rules.strategy_config_ref)):
        reasons.append(f"rules.strategy_config_ref {package.rules.strategy_config_ref!r} does not exist in repo")
    if not package.rules.parameters:
        reasons.append("parameters map is empty")
    else:
        for key, value in package.rules.parameters.items():
            if not key or not isinstance(key, str):
                reasons.append(f"parameter key {key!r} is not a non-empty string")
            if value is None:
                reasons.append(f"parameter {key!r} has no value -- missing parameters are never silently defaulted")

    # -- dataset identity: HOLDOUT must exist and must not overlap OPTIMIZATION/DISCOVERY --
    by_role: Dict[DatasetRole, list] = {}
    for ds in package.datasets:
        by_role.setdefault(ds.role, []).append(ds)
        if not ds.dataset_fingerprint or not ds.utc_start or not ds.utc_end or not ds.dataset_id:
            reasons.append(f"dataset partition {ds.dataset_id or '<unnamed>'!r} ({ds.role}) is incomplete")

    holdout_sets = by_role.get(DatasetRole.HOLDOUT, [])
    if not holdout_sets:
        reasons.append("no HOLDOUT dataset partition present")
    non_holdout_sets = by_role.get(DatasetRole.OPTIMIZATION, []) + by_role.get(DatasetRole.DISCOVERY, [])
    if not non_holdout_sets:
        reasons.append("no OPTIMIZATION or DISCOVERY dataset partition present")
    for hs in holdout_sets:
        for os_ds in non_holdout_sets:
            if hs.symbol == os_ds.symbol and hs.timeframe == os_ds.timeframe and _ranges_overlap(
                hs.utc_start, hs.utc_end, os_ds.utc_start, os_ds.utc_end
            ):
                return AdmissionResult(
                    AdmissionStatus.REJECTED_HOLDOUT_LEAKAGE, package.candidate_id,
                    (
                        f"HOLDOUT partition {hs.dataset_id!r} ({hs.utc_start}..{hs.utc_end}) overlaps "
                        f"{os_ds.role.value} partition {os_ds.dataset_id!r} ({os_ds.utc_start}..{os_ds.utc_end}) "
                        f"on {hs.symbol}/{hs.timeframe}",
                    ),
                )
    if package.holdout.holdout_dataset_id and holdout_sets:
        if not any(hs.dataset_id == package.holdout.holdout_dataset_id for hs in holdout_sets):
            reasons.append(
                f"holdout.holdout_dataset_id {package.holdout.holdout_dataset_id!r} does not match any "
                "HOLDOUT dataset partition's dataset_id"
            )

    # -- friction --
    if not package.friction.is_stated():
        reasons.append("friction assumptions incomplete: spread/commission/slippage must all be stated")

    # -- provenance --
    if not package.provenance.candidate_config_hash:
        reasons.append("provenance.candidate_config_hash is empty")
    if not package.provenance.dataset_fingerprints:
        reasons.append("provenance.dataset_fingerprints is empty")

    if reasons:
        return AdmissionResult(AdmissionStatus.INCOMPLETE, package.candidate_id, tuple(reasons), details)

    return AdmissionResult(AdmissionStatus.ACCEPTED, package.candidate_id, (), details)
