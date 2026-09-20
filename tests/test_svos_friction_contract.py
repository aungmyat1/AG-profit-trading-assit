from svos.friction_contract import (
    FRICTION_HASH,
    FRICTION_STATUS,
    FRICTION_VERSION,
    DEFAULT_FRICTION_CONTRACT,
    FrictionContract,
    FrictionContractError,
    compute_friction_hash,
    validate_friction_contract,
)


def test_friction_contract_is_frozen_and_hashes_stably():
    digest = validate_friction_contract()
    assert FRICTION_VERSION == "VD_FRICTION_V1"
    assert FRICTION_STATUS == "FROZEN"
    assert FRICTION_HASH == digest
    assert DEFAULT_FRICTION_CONTRACT.hash == digest
    assert compute_friction_hash() == digest


def test_friction_contract_requires_fail_closed_unavailable_components():
    contract = FrictionContract()
    assert contract.spread_status == "UNAVAILABLE"
    assert contract.commission_status == "UNAVAILABLE"
    assert contract.slippage_status == "UNAVAILABLE"
    assert contract.latency_status == "UNAVAILABLE"
    assert "spread" in contract.unavailable_components
    assert "commission" in contract.unavailable_components
    assert "slippage" in contract.unavailable_components
    assert "latency" in contract.unavailable_components
    assert contract.strategy_semantics_changed is False
    assert contract.large_smc_friction_reused is False


def test_unknown_component_cannot_silently_become_zero():
    contract = FrictionContract()
    assert contract.unavailable_components
    assert all(component not in contract.preregistered_dev_assumptions for component in contract.unavailable_components)
    assert contract.spread_value_or_model is None
    assert contract.commission_value_or_model is None
    assert contract.slippage_value_or_model is None
    assert contract.latency_value_or_model is None
    with __import__("pytest").raises(FrictionContractError):
        FrictionContract(spread_status="KNOWN", spread_value_or_model=0.0)


def test_friction_contract_keeps_economic_accounting_separate_from_structure():
    contract = FrictionContract()
    assert contract.friction_application_policy["entry_spread_treatment"] == "UNAVAILABLE_COMPONENT_FAIL_CLOSED"
    assert contract.friction_application_policy["stop_execution_treatment"] == "UNAVAILABLE_COMPONENT_FAIL_CLOSED"
    assert contract.strategy_semantics_changed is False
    assert contract.campaign_run is False
    assert contract.campaign_results_inspected is False
