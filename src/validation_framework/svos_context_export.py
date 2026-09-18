"""Compact, deterministic, read-only SVOS context export (WORK PACKAGE F).

Produces the small JSON object an AI agent (or DeepSeek's independent audit) can load
without ever touching raw candles, full populations, or holdout contents. This module
never scans arbitrary artifact directories to auto-assign gate statuses -- every
GateResult it reports must be explicitly supplied by the caller, who is responsible for
having derived it from real evidence. This keeps "unknown lineage must never become PASS
evidence" true structurally: a gate this function is not explicitly told about is
reported as absent (None), never inferred as PASS/FAIL/NOT_APPLICABLE.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence

from .ag_validation_methodology import METHODOLOGY_ID
from .models import GateResult
from .svos_contracts import SCHEMA_VERSION, HoldoutState

CONTEXT_SCHEMA_VERSION = "1.2"


def build_svos_context(
    strategy_id: str,
    strategy_version: str,
    hypothesis_id: Optional[str],
    branch: str,
    head_sha: str,
    svos_lifecycle_stage: Optional[str],
    furthest_verified_gate: Optional[str],
    gate_results: Mapping[str, GateResult],
    evidence_hashes: Mapping[str, Optional[str]],
    holdout: HoldoutState,
    blocking_issues: Sequence[str],
    next_authorized_action: str,
    generated_at_utc: Optional[str] = None,
    candidate_manifest: Optional[Mapping[str, Any]] = None,
    hypotheses: Optional[Mapping[str, Any]] = None,
    economic_gate: Optional[Mapping[str, Any]] = None,
    forward: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Pure function -- builds the dict, performs no I/O. `gate_results` keys are
    canonical AG_VALIDATION_G0_G10_V1 gate names (e.g. "G1","G2","G3"); only gates the
    caller actually evaluated should be present. `evidence_hashes` is a flat
    {artifact_label: sha256_or_None} map -- hashes only, never artifact contents.

    `svos_lifecycle_stage` must be the REAL canonical LifecycleStage value (e.g. from
    `validation_gate_state.describe_validation_gate_state`), never an AG-invented label
    -- SVOS remains the only lifecycle authority (Cycle-1 remediation V2, P1).
    `furthest_verified_gate` is the AG progress indicator, always a canonical gate name
    (or None), never a stage label.

    `generated_at_utc` makes output deterministic when supplied (tests); when omitted it
    defaults to the current UTC time. `candidate_manifest` / `hypotheses` /
    `economic_gate` / `forward` are additive, caller-supplied authority summaries; each
    is omitted from the output when None (backward compatible)."""
    gates_out = {}
    for gate_name, result in gate_results.items():
        gates_out[gate_name] = {
            "status": result.status.value,
            "evaluated_at": result.evaluated_at.isoformat(),
            "evaluator_version": result.evaluator_version,
            "evidence_refs": list(result.evidence_refs),
        }

    result = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "contracts_schema_version": SCHEMA_VERSION,
        "validation_methodology_id": METHODOLOGY_ID,
        "generated_at_utc": generated_at_utc or datetime.now(timezone.utc).isoformat(),
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "hypothesis_id": hypothesis_id,
        "branch": branch,
        "head_sha": head_sha,
        "svos_lifecycle_stage": svos_lifecycle_stage,
        "furthest_verified_gate": furthest_verified_gate,
        "gates": gates_out,
        "evidence_hashes": dict(evidence_hashes),
        "holdout": {
            "strategy_id": holdout.strategy_id,
            "sealed": holdout.sealed,
            "access_count": holdout.access_count,
            "last_accessed_utc": holdout.last_accessed_utc,
        },
        "blocking_issues": list(blocking_issues),
        "next_authorized_action": next_authorized_action,
    }
    if candidate_manifest is not None:
        result["candidate_manifest"] = dict(candidate_manifest)
    if hypotheses is not None:
        result["hypotheses"] = dict(hypotheses)
    if economic_gate is not None:
        result["economic_gate"] = dict(economic_gate)
    if forward is not None:
        result["forward"] = dict(forward)
    return result


def write_svos_context(context: Dict[str, Any], path: str) -> str:
    """Writes `context` as deterministic (sorted-key) JSON. Raises if `context` contains
    anything resembling large embedded data (a crude but explicit guard, not a full
    schema validator) -- see _reject_oversized_payload."""
    _reject_oversized_payload(context)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(context, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


_MAX_STRING_FIELD_LEN = 2000  # generous for a path/reason string, far below a candle dump


def _reject_oversized_payload(obj: Any, _path: str = "$") -> None:
    if isinstance(obj, str):
        if len(obj) > _MAX_STRING_FIELD_LEN:
            raise ValueError(
                f"svos_context field at {_path} is {len(obj)} chars -- looks like embedded "
                "raw data, not a compact context value; refusing to write"
            )
    elif isinstance(obj, Mapping):
        for key, value in obj.items():
            _reject_oversized_payload(value, f"{_path}.{key}")
    elif isinstance(obj, (list, tuple)):
        if len(obj) > 500:
            raise ValueError(f"svos_context field at {_path} has >500 elements -- refusing to write")
        for i, item in enumerate(obj):
            _reject_oversized_payload(item, f"{_path}[{i}]")
