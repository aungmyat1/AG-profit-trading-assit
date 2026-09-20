from __future__ import annotations

from svos.friction_contract import FrictionContract, FrictionContractError
from svos.lifecycle import evaluate_transition
from svos.optimization_admission import evaluate_optimization_admission


def test_lifecycle_transition_is_contiguous_prefix_fail_closed():
    decision = evaluate_transition(
        requested_gate="G5",
        gate_results={"G2": "PASS", "G3": "PASS", "G4": "FAIL", "G5": "PASS"},
        evidence_refs={"G2": ("e1",), "G3": ("e2",), "G4": ("e3",)},
        candidate_frozen=True,
    )
    assert decision.allowed is False
    assert any("PREREQUISITE_G4_NOT_PASS" in blocker for blocker in decision.blockers)


def test_optimization_admission_blocks_protected_data_access():
    result = evaluate_optimization_admission(
        {
            "economic_gate_result": "FAIL",
            "data_integrity": "PASS",
            "semantic_integrity": "PASS",
            "population_role": "DEVELOPMENT",
            "failure_diagnosis_complete": True,
            "mechanism_identified": True,
            "hypothesis_preregistered": True,
            "search_budget_frozen": True,
            "protected_data_access_count": 1,
            "optimization_population_authorized": True,
        }
    )
    assert result.eligible is False
    assert result.status == "OPTIMIZATION_BLOCKED"
    assert "PROTECTED_DATA_ACCESS_COUNT_MUST_BE_ZERO" in " ".join(result.blockers)


def test_friction_contract_remains_fail_closed_for_missing_costs():
    contract = FrictionContract()
    assert contract.spread_status == "UNAVAILABLE"
    assert contract.commission_status == "UNAVAILABLE"
    assert contract.slippage_status == "UNAVAILABLE"
    assert contract.latency_status == "UNAVAILABLE"
    assert contract.strategy_semantics_changed is False
    assert contract.campaign_run is False
    assert contract.campaign_results_inspected is False
    try:
        FrictionContract(spread_status="KNOWN", spread_value_or_model=0.0)
    except FrictionContractError:
        pass
    else:
        raise AssertionError("zero-cost fallback should fail closed")
