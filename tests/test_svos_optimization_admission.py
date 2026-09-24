"""Tests for svos.optimization_admission -- fail-closed optimization admission (WP12)."""
from __future__ import annotations

import pytest

from svos.optimization_admission import (
    OPTIMIZATION_BLOCKED,
    OPTIMIZATION_ELIGIBLE,
    evaluate_optimization_admission,
    evaluate_under_contract,
)


def _conditions(**overrides) -> dict:
    base = {
        "economic_gate_result": "FAIL",
        "data_integrity": "PASS",
        "semantic_integrity": "PASS",
        "population_role": "DEVELOPMENT",
        "failure_diagnosis_complete": True,
        "mechanism_identified": True,
        "hypothesis_preregistered": True,
        "search_budget_frozen": True,
        "protected_data_access_count": 0,
        "optimization_population_authorized": True,
    }
    base.update(overrides)
    return base


def test_all_conditions_pass_is_eligible():
    result = evaluate_optimization_admission(_conditions())
    assert result.eligible is True
    assert result.status == OPTIMIZATION_ELIGIBLE


def test_economic_fail_alone_does_not_authorize():
    result = evaluate_optimization_admission({"economic_gate_result": "FAIL"})
    assert result.eligible is False
    assert result.status == OPTIMIZATION_BLOCKED
    assert any(b.startswith("MISSING_") for b in result.blockers)


def test_economic_gate_pass_blocks_optimization():
    result = evaluate_optimization_admission(_conditions(economic_gate_result="PASS"))
    assert result.eligible is False
    assert any("ECONOMIC_GATE_RESULT" in b for b in result.blockers)


def test_protected_data_access_blocks():
    result = evaluate_optimization_admission(_conditions(protected_data_access_count=1))
    assert result.eligible is False
    assert any("PROTECTED_DATA_ACCESS_COUNT" in b for b in result.blockers)


def test_missing_mechanism_blocks():
    result = evaluate_optimization_admission(_conditions(mechanism_identified=False))
    assert result.eligible is False
    assert any("MECHANISM_IDENTIFIED" in b for b in result.blockers)


def test_unsigned_contract_blocks():
    contract = {"identity": {"contract_id": "AG_OPTIMIZATION_ADMISSION_CONTRACT_V1", "status": "PROPOSED"}}
    result = evaluate_under_contract(contract, _conditions())
    assert result.eligible is False
    assert result.status == OPTIMIZATION_BLOCKED
    assert "CONTRACT_NOT_SIGNED" in result.blockers


def test_signed_contract_with_passing_conditions_is_eligible():
    contract = {"identity": {"contract_id": "AG_OPTIMIZATION_ADMISSION_CONTRACT_V1", "status": "SIGNED"}}
    result = evaluate_under_contract(contract, _conditions())
    assert result.eligible is True
    assert result.status == OPTIMIZATION_ELIGIBLE


def test_malformed_contract_and_conditions_fail_closed_without_raising():
    invalid_contract = evaluate_under_contract([], _conditions())
    invalid_conditions = evaluate_optimization_admission(None)
    assert invalid_contract.eligible is False
    assert "CONTRACT_INVALID" in invalid_contract.blockers
    assert invalid_conditions.eligible is False
    assert "OPTIMIZATION_CONDITIONS_MUST_BE_A_MAPPING" in invalid_conditions.blockers


def test_signed_but_wrong_contract_identity_blocks():
    contract = {"identity": {"contract_id": "OTHER_POLICY", "status": "SIGNED"}}
    result = evaluate_under_contract(contract, _conditions())
    assert result.eligible is False
    assert "CONTRACT_ID_MISMATCH" in result.blockers


def test_truthy_strings_and_string_zero_do_not_satisfy_typed_admission_conditions():
    result = evaluate_optimization_admission(
        _conditions(
            mechanism_identified="false",
            protected_data_access_count="0",
        )
    )
    assert result.eligible is False
    assert any("MECHANISM_IDENTIFIED_MUST_BE_BOOLEAN_TRUE" in item for item in result.blockers)
    assert any("PROTECTED_DATA_ACCESS_COUNT_MUST_BE_ZERO_INTEGER" in item for item in result.blockers)
