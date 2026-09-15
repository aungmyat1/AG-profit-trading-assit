"""SVOS typed/versioned validation contracts (WP-SV2 / WORK PACKAGE C).

These dataclasses give the ad hoc JSON shapes already hand-produced for
ST_SESSION_SWEEP_CONTINUATION_V1's HYP_001/HYP_002 (see
artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/*/population_manifest.json,
CURRENT_VALIDATION_STATE.json) a single typed, importable, testable schema -- so a
future hypothesis does not need to reinvent the same fields by hand, and so downstream
code (G2/G3, svos_context_export) can consume a known shape instead of parsing loose
dicts. This module does not compute anything itself and does not read/write files.

Deliberately reuses `validation_framework.models.GateResult`/`GateStatus` for gate
outcomes rather than defining a parallel "ValidationGateResult" type -- AG-EGSVF already
has exactly that shape (gate_name, status, evidence_refs, evaluated_at,
evaluator_version, details) and duplicating it would create a second, divergent
representation of the same fact.

Research thresholds (minimum sample size, minimum net expectancy, etc.) belong in
`ValidationPolicy`, loaded from a versioned/signed config file -- never hardcoded here
or in hypothesis_stage.py/g2_population_identity.py/g3_economic_gate.py. This module
also never invents a threshold value: `ValidationPolicy` is a typed VIEW over whatever a
caller already loaded (e.g. economic_gate.load_contract()'s existing signed-YAML
mechanism), not a second source of threshold truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class DatasetFingerprint:
    """Identity of one admitted historical dataset package (mirrors the real fields in
    FRESH_DATA_ADMISSION/*_ADMISSION.json)."""

    package_id: str
    fingerprint: str  # sha256
    admission_status: str
    admission_artifact: str


@dataclass(frozen=True)
class PopulationFingerprint:
    """G2 deterministic population identity (mirrors the real fields already hand-
    produced in population_manifest.json for HYP_002). `population_hash` is computed by
    g2_population_identity.compute_population_identity() from every field below except
    itself -- this dataclass is the typed carrier, not the hashing logic."""

    strategy_id: str
    strategy_version: str
    hypothesis_id: str
    preregistration_hash: str
    validation_methodology_id: str
    git_sha: str
    dataset_fingerprint: str
    symbol: str
    timeframes: Tuple[str, ...]
    window_start: str  # ISO8601 UTC
    window_end: str  # ISO8601 UTC
    timezone_session_contract_hash: str
    config_hash: str
    population_hash: str
    reproducible: bool
    occurrence_count: int


@dataclass(frozen=True)
class HoldoutState:
    """Read-only view of a strategy/hypothesis's holdout usage. `sealed=True` and
    `access_count=0` must remain the default for any hypothesis this module has not been
    explicitly told was authorized for a one-shot holdout run (G6, out of this mission's
    scope) -- see AG_SSC_HYP001/2 status docs, both holdout_run_count=0."""

    strategy_id: str
    sealed: bool
    access_count: int
    last_accessed_utc: Optional[str] = None


@dataclass(frozen=True)
class HypothesisRegistration:
    """G1 preregistration record. Every field is required at freeze time; nothing here
    may be edited after `preregistration_hash` is computed and recorded -- freezing
    happens before G2 (population), matching HYP_002's real "G1 preregistration freeze
    -> G2 population" ordering. `preregistration_hash` is one of the fields
    g2_population_identity.compute_population_identity() binds into a population's
    identity, so a population computed under a different (e.g. superseded) hash is
    provably distinguishable (see tests/test_g2_population_identity.py)."""

    hypothesis_id: str
    strategy_id: str
    parent_version: str
    candidate_version: str
    mechanism: str
    mutable_parameters: Mapping[str, Any]
    immutable_parameters: Mapping[str, Any]
    search_space: Mapping[str, Any]
    dataset_roles: Mapping[str, str]  # e.g. {"development": "...", "holdout": "..."}
    holdout_identity: Optional[str]
    success_policy: str
    failure_policy: str
    preregistration_hash: str
    frozen_at_utc: str


@dataclass(frozen=True)
class ValidationPolicy:
    """Typed view over an already-loaded, already-signed policy document (e.g.
    economic_gate.load_contract()'s dict). Carries no default/implicit threshold values
    -- every field must be populated from the signed source or this contract must not be
    constructed. `raw` retains the full loaded document for gates needing fields this
    typed subset does not itemize."""

    policy_id: str
    policy_version: str
    status: str  # must equal "SIGNED" to be usable -- enforced by callers, not here
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_signed(self) -> bool:
        return self.status == "SIGNED"


@dataclass(frozen=True)
class G3EconomicGateOutcome:
    """G3 result, one level above the raw EconomicGateVerdict (economic_gate.py) --
    adds explicit `blocks_downstream` so callers never have to re-derive "does this
    block G4+" from a verdict string themselves (WORK PACKAGE E requirement)."""

    strategy_id: str
    strategy_version: str
    hypothesis_id: str
    verdict: str
    reason: str
    blocks_downstream: bool
    contract_id: Optional[str] = None
    contract_version: Optional[str] = None
