"""Tests for validation_framework.validation_admission -- Portability WP2."""
from __future__ import annotations

from validation_framework.svos_contracts import HoldoutState, StrategyValidationProfile
from validation_framework.validation_admission import (
    AdmissionResult,
    REASON_DUPLICATE_STRATEGY_VERSION,
    REASON_EXECUTION_AUTHORITY_NOT_ISOLATED,
    REASON_MISSING_DATASET_ROLES,
    REASON_MISSING_FRICTION_POLICY,
    REASON_MISSING_HOLDOUT_BOUNDARY,
    REASON_MISSING_HYPOTHESIS_BASELINE_MODE,
    REASON_MISSING_IMPLEMENTATION_REF,
    REASON_MISSING_SESSION_TIMEZONE_CONTRACT,
    REASON_MISSING_SPEC_REF,
    REASON_MISSING_TIMEFRAMES,
    REASON_MISSING_VALIDATION_POLICY,
    REASON_SYMBOL_NOT_IN_CANONICAL_UNIVERSE,
    run_validation_admission,
)


def _complete_profile(**overrides) -> StrategyValidationProfile:
    base = dict(
        strategy_id="ST_TEST_V1", strategy_version="1.0.0", methodology_id="AG_VALIDATION_G0_G10_V1",
        strategy_spec_ref="docs/specs/TEST_SPEC.md", strategy_spec_hash="a" * 64,
        implementation_ref="src/test_engine/engine.py",
        symbols=("EURUSD",), timeframes=("H1", "M5"),
        session_timezone_contract_ref="UTC, no session boundary",
        dataset_roles={"development": "PKG_A"},
        friction_policy_ref="config/friction/test.yaml",
        validation_policy_ref="config/governance/economic_gate_contract.yaml",
        hypothesis_state="BASELINE_ONLY",
        mutable_parameters={}, immutable_parameters={"atr_period": 14},
        holdout_metadata=HoldoutState(strategy_id="ST_TEST_V1", sealed=True, access_count=0),
        execution_authority_metadata={"demo_authorized": False, "live_authorized": False, "proposal_generation_authorized": False},
    )
    base.update(overrides)
    return StrategyValidationProfile(**base)


def test_fully_declared_profile_passes_admission():
    result = run_validation_admission(_complete_profile(), symbol="EURUSD")
    assert result.result == AdmissionResult.PASS
    assert result.reason_codes == ()


def test_admission_pass_does_not_imply_anything_about_g0():
    """Documentation-as-test: AdmissionResult carries no gate field at all -- there is
    no way to derive a G0 verdict from it."""
    result = run_validation_admission(_complete_profile(), symbol="EURUSD")
    assert not hasattr(result, "g0_status")
    assert not hasattr(result, "gate_results")


def test_symbol_outside_canonical_universe_is_blocked():
    result = run_validation_admission(_complete_profile(symbols=("EURUSD",)), symbol="GBPUSD")
    assert result.result == AdmissionResult.BLOCKED
    assert REASON_SYMBOL_NOT_IN_CANONICAL_UNIVERSE in result.reason_codes


def test_missing_dataset_roles_blocks():
    result = run_validation_admission(_complete_profile(dataset_roles={}), symbol="EURUSD")
    assert result.result == AdmissionResult.BLOCKED
    assert REASON_MISSING_DATASET_ROLES in result.reason_codes


def test_missing_friction_policy_blocks():
    result = run_validation_admission(_complete_profile(friction_policy_ref=None), symbol="EURUSD")
    assert result.result == AdmissionResult.BLOCKED
    assert REASON_MISSING_FRICTION_POLICY in result.reason_codes


def test_missing_spec_ref_blocks():
    result = run_validation_admission(_complete_profile(strategy_spec_ref=None), symbol="EURUSD")
    assert REASON_MISSING_SPEC_REF in result.reason_codes


def test_missing_implementation_ref_blocks():
    result = run_validation_admission(_complete_profile(implementation_ref=None), symbol="EURUSD")
    assert REASON_MISSING_IMPLEMENTATION_REF in result.reason_codes


def test_missing_timeframes_blocks():
    result = run_validation_admission(_complete_profile(timeframes=()), symbol="EURUSD")
    assert REASON_MISSING_TIMEFRAMES in result.reason_codes


def test_missing_session_timezone_contract_blocks():
    result = run_validation_admission(_complete_profile(session_timezone_contract_ref=None), symbol="EURUSD")
    assert REASON_MISSING_SESSION_TIMEZONE_CONTRACT in result.reason_codes


def test_missing_validation_policy_blocks():
    result = run_validation_admission(_complete_profile(validation_policy_ref=None), symbol="EURUSD")
    assert REASON_MISSING_VALIDATION_POLICY in result.reason_codes


def test_missing_hypothesis_state_blocks():
    result = run_validation_admission(_complete_profile(hypothesis_state=None), symbol="EURUSD")
    assert REASON_MISSING_HYPOTHESIS_BASELINE_MODE in result.reason_codes


def test_missing_holdout_metadata_blocks():
    result = run_validation_admission(_complete_profile(holdout_metadata=None), symbol="EURUSD")
    assert REASON_MISSING_HOLDOUT_BOUNDARY in result.reason_codes


def test_execution_authority_not_isolated_is_fail_not_blocked():
    """A safety violation (authority already granted pre-gates) is FAIL, distinct from
    an ordinary incomplete-declaration BLOCKED."""
    result = run_validation_admission(
        _complete_profile(execution_authority_metadata={"demo_authorized": True, "live_authorized": False,
                                                          "proposal_generation_authorized": False}),
        symbol="EURUSD",
    )
    assert result.result == AdmissionResult.FAIL
    assert REASON_EXECUTION_AUTHORITY_NOT_ISOLATED in result.reason_codes


def test_duplicate_strategy_version_is_fail():
    result = run_validation_admission(
        _complete_profile(), symbol="EURUSD",
        known_admitted_strategy_versions=(("ST_TEST_V1", "1.0.0"),),
    )
    assert result.result == AdmissionResult.FAIL
    assert REASON_DUPLICATE_STRATEGY_VERSION in result.reason_codes


def test_multiple_missing_fields_all_reported():
    result = run_validation_admission(
        _complete_profile(friction_policy_ref=None, validation_policy_ref=None, holdout_metadata=None),
        symbol="EURUSD",
    )
    assert result.result == AdmissionResult.BLOCKED
    assert REASON_MISSING_FRICTION_POLICY in result.reason_codes
    assert REASON_MISSING_VALIDATION_POLICY in result.reason_codes
    assert REASON_MISSING_HOLDOUT_BOUNDARY in result.reason_codes


def test_admission_never_writes_anywhere():
    """Adversarial: admission is pure -- calling it twice must be side-effect-free and
    deterministic."""
    profile = _complete_profile()
    a = run_validation_admission(profile, symbol="EURUSD")
    b = run_validation_admission(profile, symbol="EURUSD")
    assert a == b
