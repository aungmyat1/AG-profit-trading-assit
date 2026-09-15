"""SVOS hypothesis validation micro-lifecycle (AG G0-G8 foundation, WP-SV1/WP-B).

This module tracks where a single HYPOTHESIS (e.g. HYP_002_SETUP_SELECTIVITY) sits in
its own research-to-evidence pipeline. It is deliberately NOT a second strategy
lifecycle: `validation_framework.models.LifecycleStage` remains the ONLY authority over
a strategy's promotion/execution-eligibility state (OFFLINE_RESEARCH ... LIVE_AUTHORIZED),
unchanged by this module. A strategy can sit at LifecycleStage.OFFLINE_RESEARCH for its
entire life while dozens of individual hypotheses cycle through HypothesisStage below --
exactly what already happened, informally, for ST_SESSION_SWEEP_CONTINUATION_V1's
HYP_001 (blocked, NEEDS_PREREGISTRATION_REPAIR) and HYP_002 (closed VALIDATED_NEGATIVE);
see artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json's
pre-existing (informal) `active_stage`/`active_gate` fields, which this module formalizes.

Passing HypothesisStage.VIRTUAL_DEMO produces EVIDENCE a strategy's own AG-EGSVF gates
(e.g. FOUNDATIONAL_INVARIANTS' `HISTORICAL_REPLAY`/`DETERMINISM` in
validation_framework/evaluator.py) can cite. It never itself mutates lifecycle_stage,
demo_eligible, demo_authorized, or live_authorized -- those remain owner-issued facts
recorded elsewhere (config/governance/strategy_lifecycle.yaml, strategies/<ID>.yaml),
exactly as evaluator.py's module docstring already establishes for LifecycleStage.

Stage sequence (adjacent-only, like LIFECYCLE_ORDER):

    DRAFT -> INTAKE -> AUDIT -> REFINEMENT -> HISTORICAL_REPLAY -> BACKTEST
    -> STATISTICAL_VALIDATION -> ROBUSTNESS_VALIDATION -> VIRTUAL_DEMO

Plus exactly one legal non-adjacent edge: BACKTEST -(FAIL)-> REFINEMENT, the
observed real-world pattern (HYP_002 Attempt 1 INCONCLUSIVE -> owner-authorized
Attempt 2 after adding warmup context, i.e. a refinement loop) formalized as data
rather than left implicit in prose.

Note on name overlap: `HypothesisStage.HISTORICAL_REPLAY` and the AG-EGSVF gate name
`"HISTORICAL_REPLAY"` (evaluator.FOUNDATIONAL_INVARIANTS) are deliberately DIFFERENT
concepts at different scopes (a coarse hypothesis pipeline stage vs. a fine-grained
per-strategy gate requirement) that happen to share an English name because both
describe the same real-world activity. Code must never treat completing this stage as
equivalent to a PASS `GateResult` for that gate -- gate evidence is emitted by adapters
from concrete artifacts (see adapters/), not inferred from stage position.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

import yaml


class HypothesisStage(str, Enum):
    DRAFT = "DRAFT"
    INTAKE = "INTAKE"
    AUDIT = "AUDIT"
    REFINEMENT = "REFINEMENT"
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    BACKTEST = "BACKTEST"
    STATISTICAL_VALIDATION = "STATISTICAL_VALIDATION"
    ROBUSTNESS_VALIDATION = "ROBUSTNESS_VALIDATION"
    VIRTUAL_DEMO = "VIRTUAL_DEMO"


HYPOTHESIS_STAGE_ORDER: Tuple[HypothesisStage, ...] = (
    HypothesisStage.DRAFT,
    HypothesisStage.INTAKE,
    HypothesisStage.AUDIT,
    HypothesisStage.REFINEMENT,
    HypothesisStage.HISTORICAL_REPLAY,
    HypothesisStage.BACKTEST,
    HypothesisStage.STATISTICAL_VALIDATION,
    HypothesisStage.ROBUSTNESS_VALIDATION,
    HypothesisStage.VIRTUAL_DEMO,
)

# The one explicitly-authorized non-adjacent edge: a failed BACKTEST returns the
# hypothesis to REFINEMENT rather than terminating it outright, mirroring HYP_002's own
# Attempt-1-inconclusive -> Attempt-2 pattern. No other backward or skipping edge is
# legal.
_EXTRA_EDGES: Tuple[Tuple[HypothesisStage, HypothesisStage], ...] = (
    (HypothesisStage.BACKTEST, HypothesisStage.REFINEMENT),
)


class HypothesisStageError(Exception):
    """Fail-closed hypothesis-stage failure: illegal transition, missing/malformed
    registry entry, or a semantic_version mismatch. Never silently resolved."""


def is_legal_transition(source: HypothesisStage, target: HypothesisStage) -> bool:
    if source == target:
        return False
    if (source, target) in _EXTRA_EDGES:
        return True
    try:
        return HYPOTHESIS_STAGE_ORDER.index(target) - HYPOTHESIS_STAGE_ORDER.index(source) == 1
    except ValueError:
        return False


def get_next_stage(current: HypothesisStage) -> Optional[HypothesisStage]:
    idx = HYPOTHESIS_STAGE_ORDER.index(current)
    if idx + 1 >= len(HYPOTHESIS_STAGE_ORDER):
        return None
    return HYPOTHESIS_STAGE_ORDER[idx + 1]


@dataclass(frozen=True)
class HypothesisStageTransition:
    hypothesis_id: str
    source_stage: HypothesisStage
    target_stage: HypothesisStage
    reason: str


def apply_transition(
    current: HypothesisStage, target: HypothesisStage, hypothesis_id: str, reason: str
) -> HypothesisStageTransition:
    """Pure. Raises HypothesisStageError on any illegal transition -- never clamps or
    silently no-ops. Callers persist the result themselves (see
    write_hypothesis_stage_record); this function performs no I/O."""
    if not is_legal_transition(current, target):
        raise HypothesisStageError(
            f"{hypothesis_id}: illegal hypothesis-stage transition {current.value} -> "
            f"{target.value} (legal edges: adjacent HYPOTHESIS_STAGE_ORDER steps, plus "
            f"BACKTEST -> REFINEMENT on failure)"
        )
    return HypothesisStageTransition(hypothesis_id, current, target, reason)


# --- Persistence -------------------------------------------------------------------
#
# One registry file per strategy, isolated under artifacts/validation/<strategy_id>/,
# alongside that strategy's other hypothesis evidence -- NOT a single repo-wide file
# like config/governance/strategy_lifecycle.yaml, because hypothesis stage is
# strategy-and-hypothesis-scoped working state, not cross-strategy governance truth.
# Mutating lifecycle_stage in strategy_lifecycle.yaml remains a separate, owner-gated
# governance action this module never touches.

DEFAULT_REGISTRY_RELATIVE_PATH = "HYPOTHESIS_STAGE_REGISTRY.json"


def _registry_path(repo_root: str, strategy_id: str) -> str:
    return os.path.join(repo_root, "artifacts", "validation", strategy_id, DEFAULT_REGISTRY_RELATIVE_PATH)


def read_hypothesis_stage_registry(repo_root: str, strategy_id: str) -> Dict[str, Dict]:
    """Read-only. Returns {} if no registry file exists yet (a brand-new strategy has
    tracked no hypotheses under this scheme) -- never fabricates an entry."""
    path = _registry_path(repo_root, strategy_id)
    if not os.path.isfile(path):
        return {}
    import json

    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise HypothesisStageError(f"malformed hypothesis-stage registry at {path!r}: expected a JSON object")
    return data


def write_hypothesis_stage_record(
    repo_root: str,
    strategy_id: str,
    hypothesis_id: str,
    stage: HypothesisStage,
    strategy_semantic_version: str,
) -> str:
    """Persists {hypothesis_id: {stage, strategy_semantic_version}} into the
    per-strategy registry. Version-bound like lifecycle_registry.py: a caller must pass
    the exact semantic_version the stage applies to (never inferred)."""
    import json

    path = _registry_path(repo_root, strategy_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    registry = read_hypothesis_stage_registry(repo_root, strategy_id)
    registry[hypothesis_id] = {
        "stage": stage.value,
        "strategy_semantic_version": strategy_semantic_version,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(registry, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path


def get_hypothesis_stage(
    repo_root: str, strategy_id: str, hypothesis_id: str, strategy_semantic_version: str
) -> HypothesisStage:
    """Fail-closed: raises HypothesisStageError if the hypothesis has no registry entry,
    or if the registered strategy_semantic_version does not match the caller's -- a
    stale registry entry must never be silently used to evaluate a different strategy
    version's hypothesis."""
    registry = read_hypothesis_stage_registry(repo_root, strategy_id)
    entry = registry.get(hypothesis_id)
    if entry is None:
        raise HypothesisStageError(f"{strategy_id}/{hypothesis_id}: no hypothesis-stage registry entry")
    recorded_version = entry.get("strategy_semantic_version")
    if recorded_version != strategy_semantic_version:
        raise HypothesisStageError(
            f"{strategy_id}/{hypothesis_id}: registry semantic_version {recorded_version!r} "
            f"does not match caller's {strategy_semantic_version!r}"
        )
    stage_name = entry.get("stage")
    try:
        return HypothesisStage(stage_name)
    except ValueError:
        raise HypothesisStageError(f"{strategy_id}/{hypothesis_id}: unknown stage {stage_name!r}")
