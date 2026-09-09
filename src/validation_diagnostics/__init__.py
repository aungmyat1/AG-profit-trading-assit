"""AG Advisory Validation Diagnostic Agent V1.

Strategy-neutral, read-only diagnostic layer that sits AFTER
validation_framework.evaluator.evaluate_transition() and BEFORE any human decision:

    validation_framework evidence/gates -> evaluator -> FAIL/PARTIAL/NOT_VERIFIED gate
        -> validation_diagnostics.service.diagnose_gate_failure()
        -> FailureEvent + DiagnosticTrace + (at most one) ExperimentProposal
        -> owner/human review
        -> a separate, not-yet-built experiment runner

This package has zero lifecycle promotion authority, zero Demo/Live authorization
authority, zero order-execution authority, and zero automatic strategy-modification
authority (see service.py's module docstring and models.ADVISORY_AUTHORITY). The
existing validation_framework evaluator remains the sole promotion-eligibility
authority; nothing here overrides or bypasses it.
"""
from __future__ import annotations
