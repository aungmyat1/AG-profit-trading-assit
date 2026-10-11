"""SVOS authority map (P1) -- the single, frozen mapping from each mission authority
domain to its existing canonical authority in this repository, its reuse status, and
any remaining gap. Search-before-create was performed (see docs/svos/SVOS_AUTHORITY_MAP.md);
nothing here creates a competing authority -- REUSE > EXTEND > CREATE.

This module is data + one pure reconciliation function. It performs no I/O, grants no
authority, and never mutates a registry. If a requested lifecycle state cannot be
reconciled to canonical gate evidence WITHOUT inventing a new authoritative lifecycle
label, `ArchitecturalAdjudicationRequired` is raised and the caller must stop.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple


class ArchitecturalAdjudicationRequired(Exception):
    """Raised when an SVOS requirement conflicts with an existing canonical authority
    and cannot be reconciled without inventing a competing lifecycle label. The caller
    must STOP and surface the conflict; it must not silently replace authority."""


class ReuseStatus(str, Enum):
    REUSE = "REUSE"              # consume the existing authority unchanged
    EXTEND = "EXTEND"            # consume + add a subordinate adapter/evidence view
    CREATE = "CREATE"            # genuine gap, newly implemented in src/svos/
    REFERENCE_ONLY = "REFERENCE_ONLY"  # out-of-repo / locked; not adopted


@dataclass(frozen=True)
class AuthorityEntry:
    domain: str
    existing_authority: str
    reuse_status: ReuseStatus
    gap: str


AUTHORITY_MAP: Tuple[AuthorityEntry, ...] = (
    AuthorityEntry(
        "STRATEGY_CONTRACT",
        "strategies/<ID>.yaml + src/strategy_engine/ (per-strategy native entrypoint); "
        "STRATEGY_ID/STRATEGY_VERSION constants per package",
        ReuseStatus.REUSE,
        "none -- the canonical strategy authority is per-strategy; historical and forward "
        "paths must call the SAME entrypoint (P16 proof).",
    ),
    AuthorityEntry(
        "DATA_ADMISSION",
        "src/validation_framework/validation_admission.py + svos_contracts.StrategyValidationProfile",
        ReuseStatus.REUSE,
        "none.",
    ),
    AuthorityEntry(
        "HISTORICAL_REPLAY",
        "per-strategy replay entrypoints (e.g. session_sweep_continuation.replay.run_replay, "
        "historical_replay.orchestrator.ChronologicalReplay) + performance.calculator.compute_trade_metrics",
        ReuseStatus.EXTEND,
        "no strategy-neutral historical runner contract -- added as svos.historical_runner (P3).",
    ),
    AuthorityEntry(
        "ECONOMIC_METRICS",
        "src/validation_framework/economic_gate.py + g3_gate.py (G3); performance/calculator.py",
        ReuseStatus.REUSE,
        "G3 is fail-closed while config/governance/economic_gate_contract.yaml remains PROPOSED "
        "(owner sign-off required -- not performed by SVOS).",
    ),
    AuthorityEntry(
        "HYPOTHESIS_PREREGISTRATION",
        "svos_contracts.HypothesisRegistration + G1 artifacts",
        ReuseStatus.EXTEND,
        "no optimization-oriented HypothesisContract -- added as svos.hypothesis (P5).",
    ),
    AuthorityEntry(
        "BOUNDED_OPTIMIZATION",
        "external_candidate.DatasetRole + research_factory_v1.yaml governance",
        ReuseStatus.CREATE,
        "no in-repo bounded optimizer -- added as svos.optimization (P6).",
    ),
    AuthorityEntry(
        "ROBUSTNESS",
        "external_candidate.walk_forward / oos_evaluator; economic_gate_contract robustness block",
        ReuseStatus.EXTEND,
        "G5 gate named but not evaluated -- svos.lifecycle maps it to canonical G5; no new "
        "thresholds are invented.",
    ),
    AuthorityEntry(
        "HOLDOUT/OOS",
        "external_candidate.DatasetRole.HOLDOUT + HoldoutDeclaration; HoldoutState (svos_contracts)",
        ReuseStatus.REUSE,
        "holdout is one-shot; svos.optimization enforces the protected-data firewall (P8).",
    ),
    AuthorityEntry(
        "PROPOSAL",
        "src/proposal_envelope/ (CanonicalProposal, ProposalLedger, formation_gate)",
        ReuseStatus.REUSE,
        "forward campaign emits VirtualBroker proposals, not canonical envelopes -- a "
        "PROPOSAL is never an ORDER.",
    ),
    AuthorityEntry(
        "FRICTION",
        "src/performance/cost_model.py + src/fx_friction_research/ + per-strategy friction "
        "(e.g. session_sweep_continuation.friction.FrictionEstimate)",
        ReuseStatus.EXTEND,
        "no strategy-neutral component-state FrictionProfile -- added as svos.friction_profile "
        "(P10). UNAVAILABLE never converts to zero.",
    ),
    AuthorityEntry(
        "EXECUTION",
        "src/execution/executor.py + mt5_gateway.py; src/mt5/management_gateway.py",
        ReuseStatus.REFERENCE_ONLY,
        "NEVER imported by src/svos/. The VirtualBroker has zero reach to order_send/order_check "
        "(statically verified).",
    ),
    AuthorityEntry(
        "FORWARD_EVIDENCE",
        "scripts/resolve_forward_shadow_outcomes.py (AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED)",
        ReuseStatus.CREATE,
        "no virtual forward campaign/orchestrator -- added as svos.forward + svos.virtual_broker "
        "(P9/P11/P12/P14).",
    ),
    AuthorityEntry(
        "LIFECYCLE_STATE",
        "validation_framework.models.LifecycleStage via lifecycle_registry; "
        "AG_VALIDATION_G0_G10_V1 gates; config/governance/research_factory_v1.yaml research lifecycle",
        ReuseStatus.REUSE,
        "the mission's requested lifecycle vocabulary is RECONCILED as canonical gate evidence "
        "(svos.lifecycle), never as a new authoritative stage enum.",
    ),
)


def get_authority(domain: str) -> AuthorityEntry:
    for entry in AUTHORITY_MAP:
        if entry.domain == domain:
            return entry
    raise KeyError(f"unknown SVOS authority domain {domain!r}")


def reconcile_requires_new_lifecycle_label(state_name: str) -> bool:
    """True if reconciling `state_name` would require inventing a NEW authoritative
    lifecycle-stage label (prohibited by the Cycle-1 remediation V2 ADR). Every mission
    state in svos.lifecycle.MISSION_STATE_TO_GATE is false -- they all reconcile to
    existing canonical gates / milestones. Kept as an explicit guard so a future state
    that does NOT reconcile fails loudly instead of silently introducing a stage label."""
    from .lifecycle import MISSION_STATE_TO_GATE  # local import to avoid cycle at module load

    return state_name not in MISSION_STATE_TO_GATE


def assert_reconcilable(state_name: str) -> None:
    if reconcile_requires_new_lifecycle_label(state_name):
        raise ArchitecturalAdjudicationRequired(
            f"SVOS lifecycle state {state_name!r} has no canonical gate/milestone mapping "
            "and would require inventing a new authoritative lifecycle label -- "
            "ARCHITECTURAL_ADJUDICATION_REQUIRED (no authority change performed)."
        )
