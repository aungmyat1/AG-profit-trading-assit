"""ValidationGateState -- Cycle-1 remediation V2, replacing the removed
`hypothesis_stage.HypothesisStage` enum entirely (not merely neutering it).

DeepSeek's Cycle-1 audit flagged `HypothesisStage` (DRAFT..VIRTUAL_DEMO) as looking like
an independent lifecycle vocabulary. The V2 remediation brief goes further than the
first fix attempt: AG must not invent ANY named pipeline-stage label of its own,
including a purely-derived one -- progress is reported exclusively in terms of the
canonical `ag_validation_methodology.GATE_NAMES` (G0..G10), never as
DRAFT/INTAKE/AUDIT/HISTORICAL_REPLAY/BACKTEST/etc.

INVARIANT:

    SVOS (`validation_framework.models.LifecycleStage`, read via
    `lifecycle_registry.get_lifecycle_stage`) = lifecycle/governance authority.
    AG G0-G10 (`GateResult`/`GateStatus`) = subordinate validation evidence.

This module performs NO persistence, NO mutation, and NO write to
`config/governance/strategy_lifecycle.yaml`. `describe_validation_gate_state` READS the
strategy's real canonical LifecycleStage (never accepts a pre-fetched/guessable value)
so that missing SVOS authority fails closed by construction: if the registry has no
entry for (strategy_id, strategy_version), `lifecycle_registry.LifecycleRegistryError`
propagates and no summary can be produced at all -- there is no code path that reports
gate progress without first successfully establishing the real canonical SVOS stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from . import lifecycle_registry
from .ag_validation_methodology import GATE_NAMES, METHODOLOGY_ID
from .models import GateResult, GateStatus, LifecycleStage


def furthest_verified_gate(gate_results: Mapping[str, GateStatus]) -> Optional[str]:
    """Pure. Returns the last gate name (canonical G0..G10 order) in the longest
    CONTIGUOUS prefix of PASS statuses starting at G0, or None if even G0 is missing/
    non-PASS. A gap (e.g. G0 PASS, G1 missing, G2 PASS) stops at G0 -- G2's PASS never
    counts, matching "never skip/infer" gate discipline. This is the ONLY derived
    progress indicator AG reports; it is a canonical gate name, never an invented stage
    label."""
    furthest = None
    for gate_name in GATE_NAMES:
        if gate_results.get(gate_name) != GateStatus.PASS:
            break
        furthest = gate_name
    return furthest


@dataclass(frozen=True)
class ValidationGateStateSummary:
    strategy_id: str
    strategy_version: str
    hypothesis_id: Optional[str]
    methodology_id: str
    svos_lifecycle_stage: LifecycleStage  # the REAL canonical authority, read not guessed
    furthest_verified_gate: Optional[str]
    gate_results: Mapping[str, GateResult]


def describe_validation_gate_state(
    strategy_id: str,
    strategy_version: str,
    hypothesis_id: Optional[str],
    gate_results: Mapping[str, GateResult],
    repo_root: str = ".",
) -> ValidationGateStateSummary:
    """The one entry point for reporting AG gate progress. Fails closed
    (`lifecycle_registry.LifecycleRegistryError`) if the strategy has no canonical SVOS
    lifecycle-stage registry entry -- see module docstring. Read-only: performs no
    write anywhere, cannot promote or otherwise mutate the canonical SVOS lifecycle."""
    svos_stage = lifecycle_registry.get_lifecycle_stage(strategy_id, strategy_version, repo_root)
    statuses = {name: result.status for name, result in gate_results.items()}
    return ValidationGateStateSummary(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        hypothesis_id=hypothesis_id,
        methodology_id=METHODOLOGY_ID,
        svos_lifecycle_stage=svos_stage,
        furthest_verified_gate=furthest_verified_gate(statuses),
        gate_results=dict(gate_results),
    )
