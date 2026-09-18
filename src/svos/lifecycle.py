"""SVOS lifecycle reconciliation + transition guard (P2).

The mission requests lifecycle states (REGISTERED, DATA_ADMITTED, BASELINE_BACKTESTED,
... DEMO_ELIGIBLE). Per the Cycle-1 remediation V2 ADR, AG must NOT invent any named
pipeline-stage label of its own: progress is reported exclusively as canonical
`AG_VALIDATION_G0_G10_V1` gate names, and the only lifecycle authority is
`validation_framework.models.LifecycleStage` (read via lifecycle_registry).

This module therefore provides:

  * `MISSION_STATE_TO_GATE` -- a frozen, informational map from each mission-requested
    state name to the canonical gate (and, where applicable, the required GateStatus)
    that represents it. This is a compatibility map (same role as
    ag_validation_methodology.COMPATIBILITY_NOTES), NEVER an authoritative enum.
  * `evaluate_transition` -- the deterministic transition guard. A transition is
    ALLOWED only when every prerequisite gate is PASS with explicit evidence refs and
    the contiguous-prefix discipline holds. Transitions are never auto-advanced.

No function here writes to config/governance/strategy_lifecycle.yaml or any store.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from validation_framework.ag_validation_methodology import GATE_NAMES
from validation_framework.models import GateStatus

# The mission's requested lifecycle vocabulary, reconciled as canonical gate evidence.
# A value of None marks a milestone that is NOT itself a gate (e.g. registration /
# candidate freeze) -- presence is checked structurally by callers, not by a gate.
MISSION_STATE_TO_GATE: Mapping[str, Optional[Tuple[str, Optional[str]]]] = {
    "REGISTERED": None,                                     # strategies/registry.yaml + lifecycle_registry entry
    "DATA_ADMITTED": None,                                  # validation_admission PASS (pre-G0)
    "BASELINE_BACKTESTED": ("G2", GateStatus.PASS.value),   # deterministic population / replay
    "ECONOMIC_GATE_PASS": ("G3", GateStatus.PASS.value),
    "ECONOMIC_GATE_FAIL": ("G3", GateStatus.FAIL.value),
    "DIAGNOSIS_REQUIRED": ("G3", GateStatus.FAIL.value),    # same gate, different downstream action
    "HYPOTHESIS_PREREGISTERED": ("G1", GateStatus.PASS.value),
    "OPTIMIZATION_IN_PROGRESS": ("G4", None),               # in-flight, not yet terminal
    "CANDIDATE_FROZEN": None,                               # candidate freeze artifact exists (svos.candidate)
    "ROBUSTNESS_PASS": ("G5", GateStatus.PASS.value),
    "ROBUSTNESS_FAIL": ("G5", GateStatus.FAIL.value),
    "HOLDOUT_AUTHORIZED": ("G6", None),
    "HOLDOUT_PASS": ("G6", GateStatus.PASS.value),
    "HOLDOUT_FAIL": ("G6", GateStatus.FAIL.value),
    "FORWARD_ELIGIBLE": ("G8", None),
    "FORWARD_VALIDATING": ("G8", None),
    "FORWARD_PASS": ("G8", GateStatus.PASS.value),
    "FORWARD_FAIL": ("G8", GateStatus.FAIL.value),
    "DEMO_ELIGIBLE": ("G9", GateStatus.PASS.value),
}


def gate_for_state(state_name: str) -> Optional[Tuple[str, Optional[str]]]:
    return MISSION_STATE_TO_GATE.get(state_name)


@dataclass(frozen=True)
class TransitionDecision:
    allowed: bool
    blockers: Tuple[str, ...]
    evidence_required: Tuple[str, ...]


def _prev_gate(gate_name: str) -> Optional[str]:
    idx = GATE_NAMES.index(gate_name)
    return GATE_NAMES[idx - 1] if idx > 0 else None


def evaluate_transition(
    *,
    requested_gate: str,
    gate_results: Mapping[str, str],
    evidence_refs: Mapping[str, Tuple[str, ...]],
    candidate_frozen: bool = False,
    holdout_used: bool = False,
) -> TransitionDecision:
    """Deterministic lifecycle transition guard over canonical G0..G10 evidence.

    Rules (fail-closed; a missing/unknown gate is never PASS):
      1. The requested gate must be a canonical gate name (ValueError otherwise).
      2. Contiguous-prefix discipline: every gate before `requested_gate` must be PASS.
      3. Every PASS gate must carry at least one explicit evidence ref (no "file exists"
         shortcuts are enforced here -- that is the caller's evidence discipline -- but
         an empty evidence tuple can never satisfy a required PASS).
      4. G5+ (robustness/holdout/forward/demo) additionally requires `candidate_frozen`.
      5. G6 (holdout) is one-shot: `holdout_used=True` blocks a second G6 run.
    """
    blockers: list[str] = []
    evidence_required: list[str] = []

    if requested_gate not in GATE_NAMES:
        raise ValueError(f"{requested_gate!r} is not a canonical gate name")

    # contiguous prefix
    for gate in GATE_NAMES:
        if gate == requested_gate:
            break
        status = gate_results.get(gate)
        if status != GateStatus.PASS.value:
            blockers.append(f"PREREQUISITE_{gate}_NOT_PASS (status={status!r})")
        else:
            evidence_required.append(gate)
            if not evidence_refs.get(gate):
                blockers.append(f"PREREQUISITE_{gate}_MISSING_EVIDENCE")

    idx = GATE_NAMES.index(requested_gate)
    if idx >= GATE_NAMES.index("G5") and not candidate_frozen:
        blockers.append("CANDIDATE_NOT_FROZEN")

    if requested_gate == "G6":
        if holdout_used:
            blockers.append("HOLDOUT_ONE_SHOT_ALREADY_USED")
        evidence_required.append("G6")

    return TransitionDecision(
        allowed=not blockers,
        blockers=tuple(blockers),
        evidence_required=tuple(dict.fromkeys(evidence_required)),
    )
