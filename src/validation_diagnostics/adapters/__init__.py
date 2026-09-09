"""Strategy-specific diagnostic adapters (P6/P7/P8/P9).

Each adapter module is a thin, read-only translator: it reads a strategy's already-built
validation_framework.models.StrategyValidationRecord (and, where a gate's own `details`
are insufficient, the same primary evidence files the corresponding
validation_framework adapter itself reads -- never a second, divergent copy of that
evidence) and returns a RawDiagnosis for one named gate.

Every adapter module exposes exactly:

    STRATEGY_ID: str
    SUPPORTED_GATES: FrozenSet[str]
    diagnose_gate(gate_name, record, repo_root) -> RawDiagnosis

No adapter writes a file, calls a broker, mutates `record`, or imports anything from
authorization/ or execution/ -- diagnosis is pure read-and-classify.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

from validation_diagnostics.models import FailureMode


@dataclass(frozen=True)
class RawDiagnosis:
    """Adapter output before the service layer wraps it into a DiagnosticTrace (adds
    event_id/diagnosed_at/classifier_version, which are event-scoped, not gate-scoped
    facts an adapter should know about)."""

    primary_failure_mode: FailureMode
    secondary_failure_modes: Tuple[FailureMode, ...]
    confidence: str
    evidence_refs: Tuple[str, ...]
    rationale: str
    observed_metrics: Mapping[str, Any]
