"""Deterministic failure-mode classifier (P5). Runs strictly BEFORE any free-form
reasoning -- there is no LLM call, heuristic prose interpretation, or "best guess" path
anywhere in this module or the adapters it dispatches to. Every DiagnosticTrace this
module returns traces back to a concrete adapter rule over concrete evidence (P5/P24 #3).

classify() is a pure function over its inputs: given the same FailureEvent, the same
StrategyValidationRecord, and the same repo_root evidence on disk, it returns a
byte-identical DiagnosticTrace (module-level determinism check exercised in
tests/test_validation_diagnostics.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

from validation_diagnostics.models import DiagnosticTrace, FailureEvent
from validation_diagnostics.registry import UnsupportedDiagnosticTargetError, get_adapter
from validation_framework.models import StrategyValidationRecord

CLASSIFIER_VERSION = "AG_VALIDATION_DIAGNOSTICS_CLASSIFIER_V1"


def classify(
    failure_event: FailureEvent,
    record: StrategyValidationRecord,
    repo_root: str = ".",
) -> DiagnosticTrace:
    """Dispatches to the strategy's registered adapter for `failure_event.gate_id`.
    Raises UnsupportedDiagnosticTargetError (P25 stop condition) rather than guessing a
    root cause for a strategy/gate combination this package has not been explicitly
    taught -- see registry.py."""
    adapter = get_adapter(failure_event.strategy_id)
    if failure_event.gate_id not in adapter.SUPPORTED_GATES:
        raise UnsupportedDiagnosticTargetError(
            f"{failure_event.strategy_id}: adapter {adapter.__name__} does not support "
            f"gate_id={failure_event.gate_id!r}; supported={sorted(adapter.SUPPORTED_GATES)}"
        )

    raw = adapter.diagnose_gate(failure_event.gate_id, record, repo_root)

    return DiagnosticTrace(
        event_id=failure_event.event_id,
        diagnosed_at=datetime.now(timezone.utc),
        classifier_version=CLASSIFIER_VERSION,
        primary_failure_mode=raw.primary_failure_mode,
        secondary_failure_modes=raw.secondary_failure_modes,
        confidence=raw.confidence,
        evidence_refs=raw.evidence_refs,
        rationale=raw.rationale,
    )
