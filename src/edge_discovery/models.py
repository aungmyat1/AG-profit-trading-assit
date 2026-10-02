"""Candidate Factory V0 data model (AG_EDGE_DISCOVERY_ACCELERATION_R1, Phase 4).

Design rules:
  - A candidate manifest is created BEFORE any economic result is observed and never
    mutates afterwards; any later strategy-rule change is a NEW candidate (C002, ...).
    Immutability is enforced twice: frozen dataclasses in memory, sha256 freeze records
    on disk (see manifest sha256 helpers).
  - Status vocabulary separates research prioritization (FAST_SCREEN_*) from edge truth
    (EDGE_VERIFIED / EDGE_REJECTED). No function in this package may map a fast-screen
    outcome onto EDGE_VERIFIED.
  - The model is asset-class generic (CRYPTO_CFD today, FX later): nothing here assumes
    pips, sessions, ticks, or any instrument-specific convention -- cost assumptions and
    parameters are opaque frozen mappings interpreted by per-asset friction/replay code.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

import yaml

MANIFEST_SCHEMA_VERSION = "EDGE_DISCOVERY_CANDIDATE_MANIFEST_V0"


class CandidateStatus(str, Enum):
    """Pipeline statuses. FAST_SCREEN_PASS is research prioritization only."""

    DISCOVERED = "DISCOVERED"
    CONTRACTABLE = "CONTRACTABLE"
    FAST_SCREEN_PASS = "FAST_SCREEN_PASS"
    FAST_SCREEN_FAIL = "FAST_SCREEN_FAIL"
    FAST_SCREEN_INCONCLUSIVE = "FAST_SCREEN_INCONCLUSIVE"
    FROZEN_FOR_VERIFICATION = "FROZEN_FOR_VERIFICATION"
    FULL_VERIFICATION_PENDING = "FULL_VERIFICATION_PENDING"
    EDGE_VERIFIED = "EDGE_VERIFIED"      # only the existing verification authority may set this
    EDGE_REJECTED = "EDGE_REJECTED"


# Statuses this package's own gates are allowed to emit. EDGE_VERIFIED/EDGE_REJECTED are
# deliberately excluded: they belong to the existing full-verification authority.
FACTORY_EMITTABLE_STATUSES: Tuple[CandidateStatus, ...] = (
    CandidateStatus.DISCOVERED,
    CandidateStatus.CONTRACTABLE,
    CandidateStatus.FAST_SCREEN_PASS,
    CandidateStatus.FAST_SCREEN_FAIL,
    CandidateStatus.FAST_SCREEN_INCONCLUSIVE,
    CandidateStatus.FROZEN_FOR_VERIFICATION,
    CandidateStatus.FULL_VERIFICATION_PENDING,
)


class CandidateSource(str, Enum):
    INTERNAL_FROZEN_CONTRACT = "INTERNAL_FROZEN_CONTRACT"
    # Future queue metadata may identify a source; its external performance assertion
    # is never evidence until AG preregisters and independently screens a contract.
    OPEN_SOURCE = "OPEN_SOURCE"
    ACADEMIC = "ACADEMIC"
    PUBLIC_STRATEGY_LIBRARY = "PUBLIC_STRATEGY_LIBRARY"
    INTERNAL_HYPOTHESIS = "INTERNAL_HYPOTHESIS"
    EXTERNAL_SPEC = "EXTERNAL_SPEC"              # retained R1 compatibility
    FAMILY_PLACEHOLDER = "FAMILY_PLACEHOLDER"    # queue entries without preregistered rules


class DatasetRole(str, Enum):
    DEV = "DEV"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"
    FINAL_OOS = "FINAL_OOS"


# Roles whose access always requires an explicit governance approval id (Phase 12).
RESTRICTED_ROLES: Tuple[DatasetRole, ...] = (DatasetRole.HOLDOUT, DatasetRole.FINAL_OOS)


@dataclass(frozen=True)
class CandidateManifest:
    """Immutable candidate identity. Field set mirrors the mission's minimum model."""

    candidate_id: str
    strategy_id: str
    strategy_version: str
    source_type: str
    source_reference: Mapping[str, Any]
    asset_class: str
    symbols: Tuple[str, ...]
    timeframes: Tuple[str, ...]
    hypothesis: str
    entry_contract: str
    exit_contract: str
    parameters: Mapping[str, Any]
    parameters_frozen: bool
    cost_assumptions: Mapping[str, Any]
    dataset_roles_allowed: Tuple[str, ...]
    created_before_results: bool
    parent_candidate: Optional[str]
    discretionary_conditions: Tuple[str, ...] = ()
    future_data_dependencies: Tuple[str, ...] = ()

    REQUIRED_FIELDS = (
        "candidate_id", "strategy_id", "strategy_version", "source_type",
        "source_reference", "asset_class", "symbols", "timeframes", "hypothesis",
        "entry_contract", "exit_contract", "parameters", "cost_assumptions",
        "dataset_roles_allowed", "created_before_results", "parent_candidate",
    )


def manifest_from_mapping(doc: Mapping[str, Any]) -> CandidateManifest:
    """Build an immutable manifest from a parsed YAML mapping (missing keys raise)."""
    return CandidateManifest(
        candidate_id=doc["candidate_id"],
        strategy_id=doc["strategy_id"],
        strategy_version=str(doc["strategy_version"]),
        source_type=doc["source_type"],
        source_reference=dict(doc["source_reference"]),
        asset_class=doc["asset_class"],
        symbols=tuple(doc["symbols"]),
        timeframes=tuple(doc["timeframes"]),
        hypothesis=doc["hypothesis"],
        entry_contract=doc["entry_contract"],
        exit_contract=doc["exit_contract"],
        parameters=dict(doc["parameters"]),
        parameters_frozen=bool(doc.get("parameters_frozen", False)),
        cost_assumptions=dict(doc["cost_assumptions"]),
        dataset_roles_allowed=tuple(doc["dataset_roles_allowed"]),
        created_before_results=bool(doc["created_before_results"]),
        parent_candidate=doc.get("parent_candidate"),
        discretionary_conditions=tuple(doc.get("discretionary_conditions", ()) or ()),
        future_data_dependencies=tuple(doc.get("future_data_dependencies", ()) or ()),
    )


def load_manifest(path: Path) -> CandidateManifest:
    doc = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return manifest_from_mapping(doc)


def sha256_of_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_freeze_record(manifest_path: Path, freeze_record_path: Path) -> dict:
    """Byte-level immutability check: the manifest file must hash to the value captured
    at freeze time. Returns {'frozen': bool, 'expected': ..., 'actual': ...}."""
    record = json.loads(Path(freeze_record_path).read_text(encoding="utf-8"))
    actual = sha256_of_file(manifest_path)
    expected = record["manifest_sha256"]
    return {"frozen": actual == expected, "expected": expected, "actual": actual,
            "candidate_id": record.get("candidate_id")}


@dataclass(frozen=True)
class ContractabilityResult:
    candidate_id: str
    status: str                                 # "PASS" | "FAIL" (fail closed, no score)
    checks: Mapping[str, str]                   # check_name -> "PASS" | "FAIL"
    reason_codes: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FrictionResult:
    symbol: str
    scenario: str                               # BASE | STRESS | SEVERE
    model_id: str
    evidence_kind: str                          # OBSERVED_LIVE_SPREAD_* -- never HISTORICAL truth
    spread_price: float                         # scenario spread in broker price units
    observed_spread_price: float                # the raw single live observation
    multiplier: float


@dataclass(frozen=True)
class FastScreenResult:
    candidate_id: str
    dataset_ids: Tuple[str, ...]
    friction_scenario: str
    metrics: Mapping[str, Any]
    status: str                                 # FAST_SCREEN_PASS/FAIL/INCONCLUSIVE
    reason_codes: Tuple[str, ...] = ()
    # Hard invariant carried on every result object:
    edge_verified: bool = False


@dataclass(frozen=True)
class PromotionDecision:
    """Research prioritization decision. next_status NEVER equals EDGE_VERIFIED."""

    candidate_id: str
    decision: str                               # FAST_SCREEN_PASS/FAIL/INCONCLUSIVE
    reason_codes: Tuple[str, ...]
    next_status: CandidateStatus
    full_verification_status: str               # e.g. FULL_VERIFICATION_PENDING / NOT_EVALUATED
    edge_verified: bool = False
    policy_id: str = ""

    def __post_init__(self):
        if self.next_status not in FACTORY_EMITTABLE_STATUSES:
            raise ValueError(
                f"PromotionDecision may not emit {self.next_status}: EDGE_VERIFIED/"
                "EDGE_REJECTED belong to the existing full-verification authority")
        if self.edge_verified:
            raise ValueError("PromotionDecision can never carry edge_verified=True")


@dataclass(frozen=True)
class DatasetAccessRecord:
    candidate_id: str
    dataset_id: str
    dataset_role: str
    access_reason: str
    timestamp_utc: str
    result_visibility: str                      # e.g. METRICS_VISIBLE / BLIND / DENIED
    granted: bool
    denial_reason: Optional[str] = None
    governance_approval_id: Optional[str] = None
    repeat_access_count: int = 0                # prior GRANTED accesses of same candidate+dataset+role
    independence_claim: str = "NOT_APPLICABLE"  # restricted roles: INDEPENDENT_FIRST_ACCESS or not
    # Explicit stage makes C001 fast-screen holdout-denial mechanically auditable.
    access_stage: str = "UNSPECIFIED"

    def as_json_line(self) -> str:
        return json.dumps({f.name: getattr(self, f.name) for f in fields(self)},
                          sort_keys=True)
