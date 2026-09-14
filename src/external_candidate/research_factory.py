"""Research Factory V1 governance primitives.

Filesystem-only, fail-closed infrastructure.  This module never imports broker or
execution code, never runs a strategy, and never grants Demo or Live authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import hashlib
import json
import os
import re
import shutil

import yaml

DATASET_SCHEMA_VERSION = "AG_DATASET_MANIFEST_V1"
CANDIDATE_SCHEMA_VERSION = "AG_CANDIDATE_MANIFEST_V1"
ECONOMIC_SCHEMA_VERSION = "AG_ECONOMIC_CONTRACT_V1"
LIFECYCLE = (
    "DRAFT", "EXPERIMENTING", "ROBUSTNESS_REVIEW", "FREEZE_ELIGIBLE",
    "ARTIFACT_PERSISTENCE_CHECK", "FROZEN_FOR_HOLDOUT", "HOLDOUT_PASS",
    "HOLDOUT_FAIL", "CANONICAL_IMPORT_CHECK", "CANONICAL_INTEGRATION",
    "PARITY_PASS", "PARITY_FAIL", "R6_REVIEW", "R6_PASS", "R6_FAIL",
    "DEMO_ELIGIBILITY_REVIEW", "DEMO_AUTHORIZATION_REVIEW", "STAGE1_DEMO",
)
PRE_HOLDOUT_FILES = (
    "candidate.json", "effective_candidate_config.yaml", "strategy_rules.md",
    "provenance.json", "candidate_manifest.json", "dataset_manifest.json",
    "split_manifest.json", "economic_contract.json", "discovery_result.json",
    "validation_result.json", "walkforward_result.json", "friction_report.json",
    "robustness_report.json", "red_team_report.md", "occurrences.parquet",
    "trades.parquet", "SHA256SUMS.txt", "README_IMPORT.md",
)
SEMANTIC_FIELDS = (
    "occurrence_id", "symbol", "timestamp", "direction", "setup_type",
    "decision_state", "reason_codes", "entry", "stop_loss", "take_profit",
    "campaign_admission",
)
HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PersistenceResult(ValidationResult):
    first_pass_hash_stable: bool = False
    second_pass_hash_stable: bool = False
    manifest_readable: bool = False
    package_complete: bool = False
    hashes: Mapping[str, str] | None = None


@dataclass(frozen=True)
class HoldoutFirewallResult:
    allowed: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ImportCheckResult(ValidationResult):
    candidate_hash: str = ""


@dataclass(frozen=True)
class ParityResult:
    status: str
    mismatch_count: int
    first_mismatch: Mapping[str, Any] | None = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    with path.open("rb") as fh:
        digest = hashlib.sha256()
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required(mapping: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    return [f"missing required field: {name}" for name in fields if name not in mapping]


def _hash_errors(value: Any, label: str) -> list[str]:
    return [] if isinstance(value, str) and HEX64.fullmatch(value) else [f"{label} must be exactly 64 hexadecimal characters"]


def validate_dataset_manifest(value: Mapping[str, Any]) -> tuple[str, ...]:
    required = ("schema_version", "dataset_id", "symbol", "timeframe", "source", "timezone",
                "start_timestamp", "end_timestamp", "row_count", "sha256", "creation_timestamp", "mutable")
    errors = _required(value, required)
    if value.get("schema_version") != DATASET_SCHEMA_VERSION:
        errors.append(f"schema_version must be {DATASET_SCHEMA_VERSION}")
    errors += _hash_errors(value.get("sha256"), "sha256")
    if value.get("mutable") is not False:
        errors.append("mutable must be false")
    if not isinstance(value.get("row_count"), int) or value.get("row_count", 0) < 0:
        errors.append("row_count must be a non-negative integer")
    return tuple(errors)


def validate_candidate_manifest(value: Mapping[str, Any]) -> tuple[str, ...]:
    required = ("schema_version", "candidate_id", "generation_id", "strategy_id", "strategy_version",
                "strategy_family", "candidate_state", "rules_hash", "code_hash", "effective_config_hash",
                "dataset_hashes", "split_hashes", "economic_contract_hash", "parameters", "risk_contract",
                "friction_contract", "session_contract", "source_commit", "creation_timestamp", "mutable")
    errors = _required(value, required)
    if value.get("schema_version") != CANDIDATE_SCHEMA_VERSION:
        errors.append(f"schema_version must be {CANDIDATE_SCHEMA_VERSION}")
    for field in ("rules_hash", "code_hash", "effective_config_hash", "economic_contract_hash"):
        errors += _hash_errors(value.get(field), field)
    for group in ("dataset_hashes", "split_hashes"):
        hashes = value.get(group)
        if not isinstance(hashes, Mapping) or not hashes:
            errors.append(f"{group} must be a non-empty mapping")
        else:
            for key, digest in hashes.items():
                errors += _hash_errors(digest, f"{group}.{key}")
    if value.get("mutable") is not False:
        errors.append("mutable must be false")
    return tuple(errors)


def validate_economic_contract(value: Mapping[str, Any]) -> tuple[str, ...]:
    required = ("schema_version", "minimum_sample", "minimum_net_expectancy", "profit_factor_requirement",
                "maximum_drawdown", "friction_stress_requirements", "walk_forward_requirements",
                "parameter_stability_requirements", "semantic_parity_requirement", "holdout_requirements",
                "failure_conditions", "frozen")
    errors = _required(value, required)
    if value.get("schema_version") != ECONOMIC_SCHEMA_VERSION:
        errors.append(f"schema_version must be {ECONOMIC_SCHEMA_VERSION}")
    if value.get("frozen") is not True:
        errors.append("economic contract must be frozen")
    if value.get("semantic_parity_requirement") != 1.0:
        errors.append("semantic_parity_requirement must be 1.0")
    return tuple(errors)


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path.name} must contain an object")
    return value


def _parse_sums(path: Path) -> tuple[dict[str, str], list[str]]:
    sums: dict[str, str] = {}
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2 or not HEX64.fullmatch(parts[0]):
            errors.append(f"invalid SHA256SUMS line: {line!r}")
            continue
        name = parts[1].replace("\\", "/")
        if name in sums:
            errors.append(f"duplicate ambiguous path in SHA256SUMS: {name}")
        sums[name] = parts[0].lower()
    return sums, errors


def _hash_pass(root: Path, sums: Mapping[str, str], reader: Callable[[Path], bytes] | None = None) -> tuple[dict[str, str], list[str]]:
    actual: dict[str, str] = {}
    errors: list[str] = []
    for name, expected in sums.items():
        path = root / name
        if not path.is_file():
            errors.append(f"missing artifact: {name}")
            continue
        if path.stat().st_size <= 0:
            errors.append(f"empty artifact: {name}")
        try:
            digest = sha256_bytes(reader(path)) if reader else sha256_file(path)
        except Exception as exc:
            errors.append(f"reopen failure: {name}: {exc}")
            continue
        actual[name] = digest
        if digest != expected:
            errors.append(f"SHA256SUMS mismatch: {name}")
    return actual, errors


def verify_artifact_persistence(root: str | Path, *, opener: Callable[[Path], bytes] | None = None) -> PersistenceResult:
    root = Path(root)
    if not root.is_dir():
        return PersistenceResult(False, ("physical candidate package does not exist",))
    missing = [name for name in PRE_HOLDOUT_FILES if not (root / name).is_file()]
    if missing:
        return PersistenceResult(False, tuple(f"missing artifact: {n}" for n in missing), package_complete=False)
    try:
        manifest = _load_json(root / "candidate_manifest.json")
        dataset = _load_json(root / "dataset_manifest.json")
        economic = _load_json(root / "economic_contract.json")
        sums, reasons = _parse_sums(root / "SHA256SUMS.txt")
    except Exception as exc:
        return PersistenceResult(False, (f"manifest/package unreadable: {exc}",), manifest_readable=False, package_complete=True)
    reasons += list(validate_candidate_manifest(manifest))
    reasons += list(validate_dataset_manifest(dataset))
    reasons += list(validate_economic_contract(economic))
    first, first_errors = _hash_pass(root, sums, opener)
    reasons += first_errors
    # Independent pass: reopen every file and hash fresh bytes, not cached pass-one data.
    second, second_errors = _hash_pass(root, sums, opener)
    reasons += second_errors
    if first != second:
        reasons.append("second reopen/hash instability")
    config_hash = sha256_file(root / "effective_candidate_config.yaml")
    econ_hash = sha256_file(root / "economic_contract.json")
    if manifest.get("effective_config_hash") != config_hash:
        reasons.append("effective-config hash mismatch")
    if manifest.get("economic_contract_hash") != econ_hash:
        reasons.append("economic-contract hash mismatch")
    identity_fields = ("candidate_id", "strategy_id", "strategy_version", "effective_config_hash", "economic_contract_hash")
    for name in ("split_manifest.json", "validation_result.json"):
        try:
            evidence = _load_json(root / name)
            for field in identity_fields:
                if evidence.get(field) != manifest.get(field):
                    reasons.append(f"{name} {field} mismatch")
            for field in ("dataset_hashes", "split_hashes"):
                if evidence.get(field) != manifest.get(field):
                    reasons.append(f"{name} {field} mismatch")
        except Exception as exc:
            reasons.append(f"{name} unreadable: {exc}")
    stable1 = not first_errors
    stable2 = not second_errors and first == second
    return PersistenceResult(not reasons, tuple(reasons), stable1, stable2, True, True, second)


def freeze_candidate_package(root: str | Path, artifacts: Mapping[str, bytes], manifest: Mapping[str, Any]) -> PersistenceResult:
    """Create a new package only; existing destinations are never overwritten."""
    root = Path(root)
    if any(root.iterdir()) if root.exists() else False:
        raise FileExistsError(f"candidate destination is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    manifest_errors = validate_candidate_manifest(manifest)
    if manifest_errors:
        raise ValueError("; ".join(manifest_errors))
    for name in PRE_HOLDOUT_FILES:
        if name in {"candidate_manifest.json", "SHA256SUMS.txt"}:
            continue
        if name not in artifacts:
            raise ValueError(f"missing pre-Holdout artifact: {name}")
    for name, data in artifacts.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
    manifest_path = root / "candidate_manifest.json"
    with manifest_path.open("xb") as fh:
        fh.write(json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8") + b"\n")
        fh.flush(); os.fsync(fh.fileno())
    names = sorted(name for name in PRE_HOLDOUT_FILES if name != "SHA256SUMS.txt")
    sums = "".join(f"{sha256_file(root / name)}  {name}\n" for name in names)
    with (root / "SHA256SUMS.txt").open("xb") as fh:
        fh.write(sums.encode("ascii")); fh.flush(); os.fsync(fh.fileno())
    return verify_artifact_persistence(root)


def export_candidate_package(source: str | Path, destination: str | Path) -> PersistenceResult:
    """Copy a verified package without rewriting any artifact or supplied digest."""
    source, destination = Path(source), Path(destination)
    source_result = verify_artifact_persistence(source)
    if not source_result.passed:
        return source_result
    if destination.exists():
        return PersistenceResult(False, (f"export destination already exists: {destination}",))
    shutil.copytree(source, destination, copy_function=shutil.copy2)
    exported = verify_artifact_persistence(destination)
    if exported.hashes != source_result.hashes:
        return PersistenceResult(False, ("export changed physical artifact bytes",))
    return exported


def holdout_firewall(root: str | Path, ledger_path: str | Path, run_authorization_id: str) -> HoldoutFirewallResult:
    persistence = verify_artifact_persistence(root)
    if not persistence.passed:
        return HoldoutFirewallResult(False, persistence.reasons)
    root = Path(root)
    manifest = _load_json(root / "candidate_manifest.json")
    if manifest.get("candidate_state") != "FROZEN_FOR_HOLDOUT":
        return HoldoutFirewallResult(False, ("candidate_state is not FROZEN_FOR_HOLDOUT",))
    ledger_path = Path(ledger_path)
    ledger = _load_json(ledger_path) if ledger_path.exists() else {"schema_version": "AG_HOLDOUT_LEDGER_V1", "runs": []}
    candidate_hash = sha256_file(root / "candidate.json")
    if any(run.get("candidate_hash") == candidate_hash for run in ledger["runs"]):
        return HoldoutFirewallResult(False, ("MAX_HOLDOUT_RUNS_PER_CANDIDATE=1; identity already consumed",))
    record = {
        "candidate_id": manifest["candidate_id"], "candidate_hash": candidate_hash,
        "effective_config_hash": manifest["effective_config_hash"],
        "economic_contract_hash": manifest["economic_contract_hash"],
        "holdout_dataset_hash": manifest["dataset_hashes"].get("HOLDOUT", "UNRESOLVED"),
        "holdout_split_hash": manifest["split_hashes"].get("HOLDOUT", "UNRESOLVED"),
        "run_authorization_id": run_authorization_id, "holdout_state": "CONSUMED",
    }
    ledger["runs"].append(record)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    temp = ledger_path.with_suffix(ledger_path.suffix + ".tmp")
    with temp.open("x", encoding="utf-8") as fh:
        json.dump(ledger, fh, sort_keys=True, indent=2); fh.flush(); os.fsync(fh.fileno())
    os.replace(temp, ledger_path)
    return HoldoutFirewallResult(True, ())


def canonical_import_check(root: str | Path) -> ImportCheckResult:
    root = Path(root)
    candidate_hash = sha256_file(root / "candidate.json") if (root / "candidate.json").is_file() else ""
    persistence = verify_artifact_persistence(root)
    reasons = list(persistence.reasons)
    holdout_path = root / "holdout_result.json"
    if not holdout_path.is_file():
        reasons.append("holdout_result.json missing")
    else:
        manifest = _load_json(root / "candidate_manifest.json")
        holdout = _load_json(holdout_path)
        expected = {
            "candidate_id": manifest.get("candidate_id"), "candidate_hash": candidate_hash,
            "effective_config_hash": manifest.get("effective_config_hash"),
            "economic_contract_hash": manifest.get("economic_contract_hash"),
        }
        for field, value in expected.items():
            if holdout.get(field) != value:
                reasons.append(f"holdout_result.json {field} mismatch")
        if holdout.get("result") != "PASS": reasons.append("HOLDOUT_RESULT is not PASS")
        if holdout.get("holdout_state") != "CONSUMED": reasons.append("HOLDOUT_STATE is not CONSUMED")
        if holdout.get("run_number") != 1: reasons.append("holdout run_number must be 1")
    return ImportCheckResult(not reasons, tuple(reasons), candidate_hash)


def compare_semantic_records(left: Sequence[Mapping[str, Any]], right: Sequence[Mapping[str, Any]], *, numeric_tolerance: float = 0.0) -> ParityResult:
    if len(left) != len(right):
        return ParityResult("PARITY_FAIL", abs(len(left) - len(right)), {"field": "record_count", "left": len(left), "right": len(right)})
    mismatches = 0
    first = None
    for index, (a, b) in enumerate(zip(left, right)):
        for field in SEMANTIC_FIELDS:
            av, bv = a.get(field), b.get(field)
            equal = abs(av - bv) <= numeric_tolerance if isinstance(av, (int, float)) and isinstance(bv, (int, float)) else av == bv
            if not equal:
                mismatches += 1
                if first is None: first = {"index": index, "field": field, "left": av, "right": bv}
    return ParityResult("PARITY_PASS" if mismatches == 0 else "PARITY_FAIL", mismatches, first)


def governance_transition(state: str) -> Mapping[str, bool]:
    if state not in LIFECYCLE and state not in {"DEMO_ELIGIBLE", "DEMO_AUTHORIZED"}:
        raise ValueError(f"unknown lifecycle state: {state}")
    return {
        "demo_eligible": state in {"DEMO_ELIGIBLE", "DEMO_AUTHORIZATION_REVIEW", "DEMO_AUTHORIZED", "STAGE1_DEMO"},
        "demo_authorized": state in {"DEMO_AUTHORIZED", "STAGE1_DEMO"},
        "live_authorized": False,
    }
