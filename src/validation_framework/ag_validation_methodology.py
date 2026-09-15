"""AG_VALIDATION_G0_G10_V1 -- the one canonical AG validation-gate vocabulary
(Cycle-1 remediation P1-03).

Before this module, gate numbering existed only informally, split across:

- ad hoc prose in HYP_001/HYP_002 status docs ("G1 preregistration freeze -> G2
  population -> G3/G4 economic evaluation");
- `CURRENT_VALIDATION_STATE.json`'s own `active_stage: "STAGE_2"` /
  `active_gate: "TERMINAL_FAIL"` convention (a different, strategy-local numbering,
  unrelated to and NOT superseded by this module -- see COMPATIBILITY_NOTES);
- `evaluator.FOUNDATIONAL_INVARIANTS`, which independently uses the gate NAME
  `"HISTORICAL_REPLAY"` for a concrete AG-EGSVF lifecycle-promotion requirement.

No existing canonical machine-readable G0-G10 identity was found repository-wide
(verified by search: no hit for "G0_G10", "G0-G10", "AG_VALIDATION_G0" prior to this
module). `AG_VALIDATION_G0_G10_V1` is therefore adopted as new, not colliding with any
prior canonical ID.

This module does NOT rewrite, relabel, or reinterpret any historical artifact --
`CURRENT_VALIDATION_STATE.json`, `G1_AUDIT_REPORT.json`, and every `*_manifest.json`
under `artifacts/validation/` remain byte-identical and keep using their own original
terminology permanently. This module only gives NEW artifacts and code one shared,
versioned vocabulary to converge on, plus explicit (non-authoritative, informational
only) compatibility notes cross-referencing the old ad hoc terms.
"""
from __future__ import annotations

from typing import Dict, Tuple

METHODOLOGY_ID = "AG_VALIDATION_G0_G10_V1"

GATE_NAMES: Tuple[str, ...] = (
    "G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10",
)

GATE_DESCRIPTIONS: Dict[str, str] = {
    "G0": "Contract Audit",
    "G1": "Hypothesis Preregistration",
    "G2": "Deterministic Population",
    "G3": "Economic Gate",
    "G4": "Controlled Optimization",
    "G5": "Robustness",
    "G6": "Untouched Holdout",
    "G7": "Canonical Parity",
    "G8": "Forward Shadow",
    "G9": "Demo Eligibility",
    "G10": "Demo Execution Validation",
}

# Cycle 1 (this mission's authorized scope) covers G0-G3 only. G4-G10 are named here for
# a complete, versioned vocabulary, but no code in this module (or anywhere in Cycle 1)
# evaluates, satisfies, or reports evidence for them -- see g3_gate.g3_blocks_downstream,
# which is the sole enforcement point keeping G4+ blocked on a non-PASS G3.
CYCLE_1_AUTHORIZED_GATES: Tuple[str, ...] = ("G0", "G1", "G2", "G3")

# Purely informational cross-references from AG_VALIDATION_G0_G10_V1 gate names to
# terminology already used elsewhere in this repository. NEVER used programmatically to
# infer one from the other (no code path treats a HYP_002-style "Gate 2"/"Gate-3" prose
# reference, or evaluator.py's "HISTORICAL_REPLAY" gate name, as equivalent evidence for
# G2/G3 here) -- purely a human-readable map to prevent confusion when reading older
# artifacts next to new ones.
COMPATIBILITY_NOTES: Dict[str, str] = {
    "G1": (
        "HYP_002/HYP_001 status docs' prose \"G1 preregistration freeze\" describes the "
        "same real-world activity as this G1, but their preregistration_hash fields are "
        "the actual evidence -- never this module's existence."
    ),
    "G2": (
        "HYP_002/HYP_001 status docs' prose \"G2 population\" and "
        "sample_adequacy.json's \"Gate 2 (population + adequacy)\" describe the same "
        "real-world activity as this G2. Distinct from, and never a substitute for, "
        "evaluator.FOUNDATIONAL_INVARIANTS' concrete gate name \"HISTORICAL_REPLAY\" "
        "(an AG-EGSVF lifecycle-promotion requirement at the STRATEGY level, evaluated "
        "independently by that framework's own adapters)."
    ),
    "G3": (
        "HYP_002/HYP_001 status docs' prose \"G3/G4 economic evaluation\" and "
        "sample_adequacy.json's \"a separate, explicit Gate-3 script\" describe the same "
        "real-world activity as this G3. `economic_gate.py`'s AG_R6_ECONOMIC_GATE_CONTRACT "
        "is the actual reusable G3 evaluator (wrapped, not replaced, by g3_gate.py)."
    ),
}


def validate_no_ambiguous_gate_name(gate_name: str) -> None:
    """Raises ValueError if `gate_name` is not a canonical AG_VALIDATION_G0_G10_V1 gate
    name. Intended for NEW artifact-producing code to call before writing a gate_name
    field, so new artifacts cannot silently introduce a new/ambiguous numbering
    (e.g. a stray "Gate-3" or "G_3") alongside this canonical set. Never applied
    retroactively to historical artifacts."""
    if gate_name not in GATE_NAMES:
        raise ValueError(
            f"{gate_name!r} is not a canonical {METHODOLOGY_ID} gate name "
            f"(expected one of {GATE_NAMES}) -- new artifacts must use canonical gate "
            "names; historical artifacts are exempt (see module docstring)."
        )
