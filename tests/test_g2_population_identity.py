"""Tests for validation_framework.g2_population_identity -- G2 deterministic population
identity (WP-SV3 / WORK PACKAGE D)."""
from __future__ import annotations

from validation_framework.g2_population_identity import (
    compute_population_identity,
    verify_population_identity,
)
from validation_framework.svos_contracts import PopulationFingerprint

_BASE_KWARGS = dict(
    strategy_id="ST_SESSION_SWEEP_CONTINUATION_V1",
    strategy_version="1.0.0",
    hypothesis_id="HYP_002_SETUP_SELECTIVITY",
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


def test_timeframe_set_change_changes_hash():
    base = compute_population_identity(**_BASE_KWARGS)
    mutated = dict(_BASE_KWARGS, timeframes=("H1", "M15"))
    assert compute_population_identity(**mutated) != base


def test_verify_population_identity_true_for_consistent_fingerprint():
    computed_hash = compute_population_identity(**_BASE_KWARGS)
    fp = PopulationFingerprint(
        strategy_id=_BASE_KWARGS["strategy_id"],
        strategy_version=_BASE_KWARGS["strategy_version"],
        hypothesis_id=_BASE_KWARGS["hypothesis_id"],
        git_sha=_BASE_KWARGS["git_sha"],
        dataset_fingerprint=_BASE_KWARGS["dataset_fingerprint"],
        symbol=_BASE_KWARGS["symbol"],
        timeframes=_BASE_KWARGS["timeframes"],
        window_start=_BASE_KWARGS["window_start"],
        window_end=_BASE_KWARGS["window_end"],
        timezone_session_contract_hash=_BASE_KWARGS["timezone_session_contract_hash"],
        config_hash=_BASE_KWARGS["config_hash"],
        population_hash=computed_hash,
        reproducible=True,
        occurrence_count=21,
    )
    assert verify_population_identity(fp) is True


def test_verify_population_identity_false_for_tampered_fingerprint():
    fp = PopulationFingerprint(
        strategy_id=_BASE_KWARGS["strategy_id"],
        strategy_version=_BASE_KWARGS["strategy_version"],
        hypothesis_id=_BASE_KWARGS["hypothesis_id"],
        git_sha=_BASE_KWARGS["git_sha"],
        dataset_fingerprint=_BASE_KWARGS["dataset_fingerprint"],
        symbol=_BASE_KWARGS["symbol"],
        timeframes=_BASE_KWARGS["timeframes"],
        window_start=_BASE_KWARGS["window_start"],
        window_end=_BASE_KWARGS["window_end"],
        timezone_session_contract_hash=_BASE_KWARGS["timezone_session_contract_hash"],
        config_hash=_BASE_KWARGS["config_hash"],
        population_hash="deadbeef" * 8,
        reproducible=True,
        occurrence_count=21,
    )
    assert verify_population_identity(fp) is False
