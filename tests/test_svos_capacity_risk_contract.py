from svos.capacity_risk_contract import (
    CAPACITY_RISK_HASH,
    CAPACITY_RISK_VERSION,
    CapacityRiskContract,
    CapacityRiskError,
    DEFAULT_CAPACITY_RISK_CONTRACT,
    compute_capacity_risk_hash,
    validate_capacity_risk_contract,
)


def test_capacity_risk_contract_is_frozen_and_hashes_stably():
    digest = validate_capacity_risk_contract()
    assert CAPACITY_RISK_VERSION == "VD_CAPACITY_RISK_V1"
    assert CAPACITY_RISK_HASH == digest
    assert DEFAULT_CAPACITY_RISK_CONTRACT.hash == digest
    assert compute_capacity_risk_hash() == digest


def test_capacity_risk_contract_uses_existing_authority_only():
    contract = CapacityRiskContract()
    assert contract.initial_virtual_equity == 0.0
    assert contract.max_concurrent_positions == 1
    assert contract.sizing_rule == "ENGINEERING_NORMALIZED_1"
    assert contract.risk_per_occurrence is None
    assert "broker leverage" in contract.deferred_execution_parity
    assert contract.risk_authority == "UNSPECIFIED_IN_REPO_AUTHORITY"
    assert contract.to_virtual_account_kwargs() == {
        "starting_engineering_balance": 0.0,
        "max_open_positions": 1,
    }


def test_capacity_risk_contract_fails_on_unbounded_invention():
    with __import__("pytest").raises(CapacityRiskError):
        CapacityRiskContract(initial_virtual_equity=-1.0)
    with __import__("pytest").raises(CapacityRiskError):
        CapacityRiskContract(max_concurrent_positions=0)
    with __import__("pytest").raises(CapacityRiskError):
        CapacityRiskContract(risk_per_occurrence=0.0)
