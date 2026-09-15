"""Tests for validation_framework.g2_population_identity -- G2 deterministic population
identity (WP-SV3 / WORK PACKAGE D), hardened per Cycle-1 remediation V2 to bind
preregistration_hash and validation_methodology_id (P1-05 closure)."""
from __future__ import annotations

from validation_framework.ag_validation_methodology import METHODOLOGY_ID
from validation_framework.g2_population_identity import (
    compute_population_identity,
    verify_population_identity,
)
from validation_framework.svos_contracts import PopulationFingerprint

_BASE_KWARGS = dict(
    strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
    strategy_version="1.0.0",
    hypothesis_id="HYP_002_SETUP_SELECTIVITY",
    preregistration_hash="4e2e4f21c8bf2fe5b461b29ceff670e769445be913d3f193a73e96cc84492fb7",
    validation_methodology_id=METHODOLOGY_ID,
    git_sha="7c75f89a8c6f30c3bec0f4881d2b378575f9ebf0",
    dataset_fingerprint="f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa",
    symbol="EURUSD",
    timeframes=("H1", "M15", "M1"),
    window_start="2026-08-01T00:00:00Z",
    window_end="2026-09-14T23:59:59Z",
    timezone_session_contract_hash="utc_v1",
    config_hash="e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf",
)


def test_deterministic_same_inputs_same_hash():
    h1 = compute_population_identity(**_BASE_KWARGS)
    h2 = compute_population_identity(**_BASE_KWARGS)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_field_order_independence_timeframes():
    kwargs_a = dict(_BASE_KWARGS, timeframes=("H1", "M15", "M1"))
    kwargs_b = dict(_BASE_KWARGS, timeframes=["H1", "M15", "M1"])
    assert compute_population_identity(**kwargs_a) == compute_population_identity(**kwargs_b)


def test_single_field_change_changes_hash():
    base = compute_population_identity(**_BASE_KWARGS)
    for field_name, new_value in [
        ("strategy_version", "1.0.1"),
        ("dataset_fingerprint", "0" * 64),
        ("symbol", "GBPUSD"),
        ("config_hash", "1" * 64),
        ("window_end", "2026-09-15T00:00:00Z"),
    ]:
        mutated = dict(_BASE_KWARGS)
        mutated[field_name] = new_value
        assert compute_population_identity(**mutated) != base, f"{field_name} change did not alter hash"


def test_superseded_preregistration_hash_changes_population_identity():
    """P1-05 closure: a population bound to a SUPERSEDED draft preregistration hash
    must produce a provably different identity than one bound to the frozen
    authoritative hash -- exactly the real HYP_001_GBPUSD_REPLICATION_R1 discrepancy
    (b401e974... draft vs 7ee1554c... frozen)."""
    frozen = compute_population_identity(**_BASE_KWARGS)
    superseded = compute_population_identity(
        **dict(_BASE_KWARGS, preregistration_hash="b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e")
    )
    assert frozen != superseded


def test_methodology_version_change_changes_population_identity():
    base = compute_population_identity(**_BASE_KWARGS)
    bumped = compute_population_identity(**dict(_BASE_KWARGS, validation_methodology_id="AG_VALIDATION_G0_G10_V2"))
    assert base != bumped


def test_timeframe_set_change_changes_hash():
    base = compute_population_identity(**_BASE_KWARGS)
    mutated = dict(_BASE_KWARGS, timeframes=("H1", "M15"))
    assert compute_population_identity(**mutated) != base


def _fingerprint(population_hash, **overrides):
    kwargs = dict(_BASE_KWARGS)
    kwargs.update(overrides)
    return PopulationFingerprint(
        strategy_id=kwargs["strategy_id"], strategy_version=kwargs["strategy_version"],
        hypothesis_id=kwargs["hypothesis_id"], preregistration_hash=kwargs["preregistration_hash"],
        validation_methodology_id=kwargs["validation_methodology_id"], git_sha=kwargs["git_sha"],
        dataset_fingerprint=kwargs["dataset_fingerprint"], symbol=kwargs["symbol"],
        timeframes=kwargs["timeframes"], window_start=kwargs["window_start"], window_end=kwargs["window_end"],
        timezone_session_contract_hash=kwargs["timezone_session_contract_hash"], config_hash=kwargs["config_hash"],
        population_hash=population_hash, reproducible=True, occurrence_count=21,
    )


def test_verify_population_identity_true_for_consistent_fingerprint():
    computed_hash = compute_population_identity(**_BASE_KWARGS)
    fp = _fingerprint(computed_hash)
    assert verify_population_identity(fp) is True


def test_verify_population_identity_false_for_tampered_fingerprint():
    fp = _fingerprint("deadbeef" * 8)
    assert verify_population_identity(fp) is False


def test_verify_population_identity_false_when_preregistration_hash_swapped_after_hashing():
    """A fingerprint whose stored population_hash was computed under one
    preregistration_hash, then edited to claim a different one, must fail
    verification -- catches exactly the P1-05 class of tampering/drift."""
    computed_hash = compute_population_identity(**_BASE_KWARGS)
    fp = _fingerprint(computed_hash, preregistration_hash="b401e9745e1be90b5a510e41c60923a79262fa9907a6dc49d7d92ee4c7a2853e")
    assert verify_population_identity(fp) is False
