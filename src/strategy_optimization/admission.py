"""Adapter to the existing signed optimization-admission governance authority."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import yaml

from post_asian_pilot.fingerprint import fingerprint
from svos.optimization_admission import (
    OPTIMIZATION_BLOCKED,
    OptimizationAdmissionResult,
    evaluate_under_contract,
)


class OptimizationAdmissionBlocked(PermissionError):
    def __init__(self, result: OptimizationAdmissionResult):
        self.result = result
        super().__init__(", ".join(self.result.blockers) or OPTIMIZATION_BLOCKED)


def _blocked(reason: str) -> OptimizationAdmissionResult:
    return OptimizationAdmissionResult(
        eligible=False,
        status=OPTIMIZATION_BLOCKED,
        blockers=(reason,),
    )


def evaluate_contract_snapshot(
    raw: bytes,
    conditions: Mapping[str, Any],
) -> Tuple[OptimizationAdmissionResult, Optional[str], Optional[str], Optional[str]]:
    """Evaluate exact UTF-8 contract bytes and retain the snapshot identity."""
    try:
        text = raw.decode("utf-8")
        contract = yaml.safe_load(text)
    except (UnicodeDecodeError, yaml.YAMLError):
        return _blocked("OPTIMIZATION_ADMISSION_CONTRACT_INVALID"), hashlib.sha256(raw).hexdigest(), None, None
    contract_sha256 = hashlib.sha256(raw).hexdigest()
    if not isinstance(contract, Mapping):
        return _blocked("OPTIMIZATION_ADMISSION_CONTRACT_INVALID"), contract_sha256, None, text
    identity = contract.get("identity", {})
    contract_status = str(identity.get("status")) if isinstance(identity, Mapping) else None
    try:
        result = evaluate_under_contract(contract, conditions)
    except (TypeError, ValueError, OverflowError):
        result = _blocked("OPTIMIZATION_ADMISSION_CONDITIONS_INVALID")
    return result, contract_sha256, contract_status, text


def evaluate_repository_admission_snapshot(
    repo_root: str | Path,
    conditions: Mapping[str, Any],
) -> Tuple[OptimizationAdmissionResult, Optional[str], Optional[str], Optional[str]]:
    """Evaluate one exact contract byte snapshot and return its hash/status/text."""
    path = Path(repo_root) / "config/governance/optimization_admission_contract.yaml"
    try:
        raw = path.read_bytes()
    except OSError:
        return _blocked("OPTIMIZATION_ADMISSION_CONTRACT_UNAVAILABLE"), None, None, None
    return evaluate_contract_snapshot(raw, conditions)


def evaluate_stored_admission_evidence(
    contract_snapshot_utf8: str,
    expected_contract_sha256: str,
    contract_status: str,
    conditions: Mapping[str, Any],
    expected_conditions_sha256: str,
) -> OptimizationAdmissionResult:
    """Re-evaluate the exact contract and condition snapshots recorded in a ledger."""
    if not isinstance(contract_snapshot_utf8, str):
        return _blocked("OPTIMIZATION_ADMISSION_CONTRACT_SNAPSHOT_MISSING")
    try:
        result, contract_sha256, status, _ = evaluate_contract_snapshot(
            contract_snapshot_utf8.encode("utf-8"), conditions
        )
    except (UnicodeEncodeError, TypeError, ValueError):
        return _blocked("OPTIMIZATION_ADMISSION_CONTRACT_SNAPSHOT_INVALID")
    try:
        actual_conditions_sha256 = fingerprint(conditions)
    except (TypeError, ValueError):
        return _blocked("OPTIMIZATION_ADMISSION_CONDITIONS_INVALID")
    if (
        contract_sha256 != expected_contract_sha256
        or status != contract_status
        or actual_conditions_sha256 != expected_conditions_sha256
    ):
        return _blocked("OPTIMIZATION_ADMISSION_EVIDENCE_IDENTITY_MISMATCH")
    return result


def evaluate_repository_admission(
    repo_root: str | Path,
    conditions: Mapping[str, Any],
) -> OptimizationAdmissionResult:
    """Read and evaluate the canonical contract; never repairs or signs it."""
    result, _, _, _ = evaluate_repository_admission_snapshot(repo_root, conditions)
    return result


def require_repository_admission(
    repo_root: str | Path,
    conditions: Mapping[str, Any],
) -> OptimizationAdmissionResult:
    result = evaluate_repository_admission(repo_root, conditions)
    if not result.eligible:
        raise OptimizationAdmissionBlocked(result)
    return result


__all__ = [
    "OptimizationAdmissionBlocked", "evaluate_repository_admission",
    "evaluate_repository_admission_snapshot", "evaluate_stored_admission_evidence",
    "require_repository_admission",
]
