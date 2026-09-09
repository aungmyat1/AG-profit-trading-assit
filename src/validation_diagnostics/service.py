"""Orchestration + artifact persistence for the Advisory Validation Diagnostic Agent
(P2/P17/P20). This module is the ONLY place in this package that touches the
filesystem for writes -- every write lands under artifacts/validation_diagnostics/ (P17),
never under strategies/, config/governance/, or any validation_framework evidence path.

Read-only inputs: a validation_framework.models.StrategyValidationRecord already built
by an existing adapter (validation_framework.adapters.fx_adapter.build_fx_record() etc.)
-- this module never calls a strategy engine, broker, or lifecycle mutation function
(P4). See diagnose_gate_failure() for the single public entry point most callers need.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import yaml

from validation_diagnostics import classifier, experiment
from validation_diagnostics.models import (
    ADVISORY_AUTHORITY,
    DiagnosticTrace,
    ExperimentProposal,
    FailureEvent,
)
from validation_diagnostics.registry import DEFAULT_APPLICATION_RELEASE
from validation_framework.models import GateStatus, StrategyValidationRecord

DEFAULT_OUTPUT_DIR = os.path.join("artifacts", "validation_diagnostics")

# Gate statuses eligible to become a diagnostic FailureEvent (P3). PASS is never
# diagnosed (a passing gate is not a failure); NOT_APPLICABLE is never diagnosed either
# -- it means the gate does not apply to this transition, not that it failed.
_DIAGNOSABLE_STATUSES = frozenset({
    GateStatus.FAIL, GateStatus.PARTIAL, GateStatus.BLOCKED,
    GateStatus.UNSIGNED, GateStatus.NOT_VERIFIED,
})


class NotAFailureError(Exception):
    """Raised when asked to build a diagnostic event from a gate that is PASS or
    NOT_APPLICABLE -- P3: the agent must never reinterpret a passing/inapplicable gate
    as a failure."""


def get_git_commit(repo_root: str = ".") -> str:
    """Best-effort, read-only `git rev-parse HEAD`. Never raises -- git metadata is
    identity-binding context for the event (P2), not something this advisory package
    should ever fail closed over if git is unavailable in a given execution
    environment."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            capture_output=True, text=True, timeout=10, check=False,
        )
        commit = result.stdout.strip()
        return commit if commit else "UNKNOWN"
    except Exception:
        return "UNKNOWN"


def _hash_evidence_ref(repo_root: str, ref: str) -> Optional[str]:
    candidate = os.path.join(repo_root, ref)
    if not os.path.isfile(candidate):
        return None
    h = hashlib.sha256()
    with open(candidate, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _event_id(strategy_id: str, strategy_version: str, application_release: str,
              git_commit: str, gate_id: str, gate_status: str) -> str:
    """Deterministic: the same (strategy identity, release, commit, gate, status)
    always yields the same event_id -- required for 'same event produces deterministic
    classification' (P23)."""
    basis = "|".join([strategy_id, strategy_version, application_release, git_commit, gate_id, gate_status])
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"VALFAIL-{strategy_id}-{gate_id}-{digest}"


def build_failure_event(
    record: StrategyValidationRecord,
    gate_id: str,
    repo_root: str = ".",
    application_release: str = DEFAULT_APPLICATION_RELEASE,
    git_commit: Optional[str] = None,
) -> FailureEvent:
    """Builds a canonical FailureEvent from one gate already evaluated by
    validation_framework (P3) -- this function performs no gate evaluation of its own."""
    gate = record.gates.get(gate_id)
    if gate is None:
        raise NotAFailureError(f"{record.identity.strategy_id}: no gate named {gate_id!r} on this record")
    if gate.status not in _DIAGNOSABLE_STATUSES:
        raise NotAFailureError(
            f"{record.identity.strategy_id}.{gate_id}: status={gate.status.value} is not a "
            "diagnosable failure/incomplete status -- refusing to fabricate a failure event "
            "for a PASS or NOT_APPLICABLE gate."
        )

    resolved_commit = git_commit if git_commit is not None else get_git_commit(repo_root)
    event_id = _event_id(
        record.identity.strategy_id, record.identity.semantic_version, application_release,
        resolved_commit, gate_id, gate.status.value,
    )

    details = dict(gate.details or {})
    required_thresholds = {k: v for k, v in details.items() if "target" in k.lower() or "threshold" in k.lower()}
    observed_metrics = {k: v for k, v in details.items() if k not in required_thresholds}

    artifact_hashes = tuple(
        h for h in (_hash_evidence_ref(repo_root, ref) for ref in gate.evidence_refs) if h is not None
    )

    diagnostic_input_complete = bool(gate.evidence_refs) or bool(details)

    return FailureEvent(
        event_id=event_id,
        created_at=datetime.now(timezone.utc),
        strategy_id=record.identity.strategy_id,
        strategy_version=record.identity.semantic_version,
        application_release=application_release,
        git_commit=resolved_commit,
        current_lifecycle_stage=record.lifecycle_stage.value,
        target_lifecycle_stage=record.next_transition.value if record.next_transition else None,
        gate_id=gate_id,
        gate_status=gate.status.value,
        observed_metrics=observed_metrics,
        required_thresholds=required_thresholds,
        threshold_authority={"source": "validation_framework.evaluator.STAGE_PREREQUISITES"},
        blocker_codes=(gate_id,),
        evidence_refs=tuple(gate.evidence_refs),
        artifact_hashes=artifact_hashes,
        diagnostic_input_complete=diagnostic_input_complete,
    )


def diagnose(event: FailureEvent, record: StrategyValidationRecord, repo_root: str = ".") -> DiagnosticTrace:
    return classifier.classify(event, record, repo_root)


def propose_experiment(event: FailureEvent, trace: DiagnosticTrace) -> Optional[ExperimentProposal]:
    return experiment.generate_experiment(event, trace)


# ---------------------------------------------------------------------------
# Serialization + persistence (P17). Every artifact stamps authority=ADVISORY_ONLY,
# requires_human_approval=true, promotion_authority=false, execution_authority=false --
# see the *_authority_block() helpers below, never left implicit.
# ---------------------------------------------------------------------------


def _authority_block() -> Dict[str, Any]:
    return {
        "authority": ADVISORY_AUTHORITY,
        "requires_human_approval": True,
        "promotion_authority": False,
        "execution_authority": False,
    }


def serialize_failure_event(event: FailureEvent) -> Dict[str, Any]:
    d = asdict(event)
    d["created_at"] = event.created_at.isoformat()
    d.update(_authority_block())
    return d


def serialize_diagnostic_trace(trace: DiagnosticTrace) -> Dict[str, Any]:
    d = asdict(trace)
    d["diagnosed_at"] = trace.diagnosed_at.isoformat()
    d["primary_failure_mode"] = trace.primary_failure_mode.value
    d["secondary_failure_modes"] = [m.value for m in trace.secondary_failure_modes]
    d.update(_authority_block())
    return d


def serialize_experiment_proposal(proposal: ExperimentProposal) -> Dict[str, Any]:
    d = asdict(proposal)
    d["experiment_class"] = proposal.experiment_class.value
    d["state"] = proposal.state.value
    return {"experiment_proposal": d}


def persist(
    event: FailureEvent,
    trace: DiagnosticTrace,
    proposal: Optional[ExperimentProposal],
    repo_root: str = ".",
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Dict[str, str]:
    """Writes failure_event.json / diagnostic_trace.json / experiment_proposal.yaml
    under artifacts/validation_diagnostics/<strategy_id>/<event_id>/ (P17). `proposal`
    may be None (FailureMode.UNKNOWN or a rejected OOS-contaminating proposal) -- in
    that case no experiment_proposal.yaml is written, matching 'at most one' (P10)."""
    event_dir = os.path.join(repo_root, output_dir, event.strategy_id, event.event_id)
    os.makedirs(event_dir, exist_ok=True)

    paths: Dict[str, str] = {}

    failure_event_path = os.path.join(event_dir, "failure_event.json")
    with open(failure_event_path, "w", encoding="utf-8") as fh:
        json.dump(serialize_failure_event(event), fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    paths["failure_event_path"] = failure_event_path

    trace_path = os.path.join(event_dir, "diagnostic_trace.json")
    with open(trace_path, "w", encoding="utf-8") as fh:
        json.dump(serialize_diagnostic_trace(trace), fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")
    paths["diagnostic_trace_path"] = trace_path

    if proposal is not None:
        proposal_path = os.path.join(event_dir, "experiment_proposal.yaml")
        with open(proposal_path, "w", encoding="utf-8") as fh:
            yaml.safe_dump(serialize_experiment_proposal(proposal), fh, sort_keys=False, default_flow_style=False)
        paths["experiment_proposal_path"] = proposal_path

    return paths


def diagnose_gate_failure(
    record: StrategyValidationRecord,
    gate_id: str,
    repo_root: str = ".",
    application_release: str = DEFAULT_APPLICATION_RELEASE,
    git_commit: Optional[str] = None,
    persist_artifacts: bool = True,
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> Tuple[FailureEvent, DiagnosticTrace, Optional[ExperimentProposal], Dict[str, str]]:
    """Single-call convenience entry point: build the failure event, classify it,
    propose at most one experiment, and (by default) persist the advisory artifacts.
    Returns (event, trace, proposal_or_None, artifact_paths) -- artifact_paths is {} if
    persist_artifacts=False."""
    event = build_failure_event(record, gate_id, repo_root, application_release, git_commit)
    trace = diagnose(event, record, repo_root)
    proposal = propose_experiment(event, trace)
    paths = persist(event, trace, proposal, repo_root, output_dir) if persist_artifacts else {}
    return event, trace, proposal, paths
