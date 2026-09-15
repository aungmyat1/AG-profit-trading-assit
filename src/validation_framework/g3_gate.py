"""G3 economic rejection gate (WP-SV3 / WORK PACKAGE E).

This is NOT a new economic evaluator: `economic_gate.py` already IS a deterministic,
fail-closed, signed-contract-driven economic gate (AG_R6_ECONOMIC_GATE_CONTRACT). This
module only adapts its verdict into the G3 vocabulary this mission's roadmap uses
(gate_name="G3", `models.GateResult`/`GateStatus`, and an explicit
`blocks_downstream` flag) so callers never have to re-derive "does this block G4+"
from a verdict string. It computes no metrics itself, invents no threshold, and mutates
nothing.

Fail-closed by construction: any verdict other than EDGE_VALIDATED blocks downstream
(G4+) evaluation. A PARTIAL/INSUFFICIENT_EVIDENCE/NOT_EVALUABLE_* verdict is reported as
GateStatus.BLOCKED (never FAIL) -- FAIL is reserved for an evaluated, complete result
that failed its bounds (EDGE_REJECTED), matching GateStatus's own fail-closed
vocabulary (models.py: "unknown/missing evidence must never be reported as PASS", which
by the same logic must never be reported as a definitive FAIL either).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .economic_gate import (
    VERDICT_EDGE_REJECTED,
    VERDICT_EDGE_VALIDATED,
    EconomicGateVerdict,
    evaluate_economic_gate,
)
from .models import GateResult, GateStatus
from .svos_contracts import G3EconomicGateOutcome

_EVALUATOR_VERSION = "g3_gate_v1"

_VERDICT_TO_STATUS = {
    VERDICT_EDGE_VALIDATED: GateStatus.PASS,
    VERDICT_EDGE_REJECTED: GateStatus.FAIL,
}


def run_g3_economic_gate(
    strategy_id: str,
    strategy_version: str,
    hypothesis_id: str,
    metrics,
    evidence_complete: bool,
    contract: Optional[Dict[str, Any]],
    evidence_refs: tuple = (),
) -> GateResult:
    """Runs the existing economic_gate.evaluate_economic_gate() and reports it as a G3
    GateResult. `metrics`/`evidence_complete`/`contract` have the exact same meaning and
    fail-closed behavior as economic_gate.evaluate_economic_gate's own parameters --
    this function adds no new fail-closed rule of its own, it only re-labels the
    existing one's output."""
    verdict: EconomicGateVerdict = evaluate_economic_gate(
        strategy_id, strategy_version, metrics, evidence_complete, contract
    )
    status = _VERDICT_TO_STATUS.get(verdict.verdict, GateStatus.BLOCKED)
    return GateResult(
        gate_name="G3",
        status=status,
        evidence_refs=tuple(evidence_refs) + ((verdict.contract_id,) if verdict.contract_id else ()),
        evaluated_at=datetime.now(timezone.utc),
        evaluator_version=_EVALUATOR_VERSION,
        details={
            "hypothesis_id": hypothesis_id,
            "verdict": verdict.verdict,
            "reason": verdict.reason,
            "contract_version": verdict.contract_version,
        },
    )


def to_outcome(strategy_id: str, strategy_version: str, hypothesis_id: str, gate_result: GateResult) -> G3EconomicGateOutcome:
    """Adapts a G3 GateResult into the compact G3EconomicGateOutcome shape, computing
    `blocks_downstream` in exactly one place so it can never drift from `status`."""
    return G3EconomicGateOutcome(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        hypothesis_id=hypothesis_id,
        verdict=str(gate_result.details.get("verdict")),
        reason=str(gate_result.details.get("reason")),
        blocks_downstream=g3_blocks_downstream(gate_result),
        contract_id=gate_result.evidence_refs[-1] if gate_result.evidence_refs else None,
        contract_version=gate_result.details.get("contract_version"),
    )


def g3_blocks_downstream(gate_result: GateResult) -> bool:
    """True unless G3 explicitly PASSed. Any BLOCKED/FAIL status (insufficient
    evidence, missing/unsigned contract, or an evaluated economic rejection) blocks
    G4+ -- there is no partial-credit path past G3."""
    return gate_result.status != GateStatus.PASS
