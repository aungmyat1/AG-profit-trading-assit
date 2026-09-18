"""Tests for svos.historical_runner -- canonical historical runner contract (P3)."""
from __future__ import annotations

import pytest

from svos.historical_runner import (
    AdmittedDataset,
    FrictionContractRef,
    HistoricalOccurrence,
    HistoricalValidationRequest,
    run_historical_validation,
)


def _request() -> HistoricalValidationRequest:
    return HistoricalValidationRequest(
        strategy_id="ST_TEST_V1",
        strategy_version="1.0.0",
        dataset=AdmittedDataset(
            dataset_id="DS1", symbol="EURUSD", timeframe="M15",
            utc_start="2026-01-01", utc_end="2026-03-01", fingerprint="abc123",
            hashes={"candles": "h1", "manifest": "h2"},
        ),
        friction_contract=FrictionContractRef(contract_id="FR1", contract_hash="f1f2f3"),
        replay_adapter="tests.stub_replay",
    )


def _occ(i: int, setup: str = "S1", direction: str = "LONG", gross: float = 1.0,
         net: float = 0.9, cost_status: str = "KNOWN") -> HistoricalOccurrence:
    return HistoricalOccurrence(
        occurrence_id=f"occ-{i}", symbol="EURUSD", session="ASIAN_LONDON",
        direction=direction, setup=setup, exit_path="RUNNER_TARGET",
        outcome="RESOLVED_RUNNER_TARGET", gross_R=gross, friction_R=gross - net,
        net_R=net, cost_status=cost_status,
    )


def test_runner_computes_metrics_and_decomposition():
    occurrences = [
        _occ(0, setup="S1", direction="LONG", gross=1.0, net=0.8),
        _occ(1, setup="S2", direction="SHORT", gross=-1.0, net=-1.2),
    ]
    result = run_historical_validation(_request(), occurrences)
    assert result.metrics.sample_size == 2
    assert result.metrics.wins == 1
    assert result.metrics.losses == 1
    assert "by_setup" in result.decomposition
    assert set(result.decomposition["by_setup"]) == {"S1", "S2"}
    assert result.evidence_hashes["dataset_fingerprint"] == "abc123"
    assert result.evidence_hashes["population_hash"]


def test_runner_fails_closed_on_missing_dataset_fingerprint():
    req = _request()
    req = HistoricalValidationRequest(
        strategy_id=req.strategy_id, strategy_version=req.strategy_version,
        dataset=AdmittedDataset(
            dataset_id="DS1", symbol="EURUSD", timeframe="M15",
            utc_start="", utc_end="", fingerprint="",
        ),
        friction_contract=req.friction_contract,
        replay_adapter=req.replay_adapter,
    )
    with pytest.raises(ValueError):
        run_historical_validation(req, [])


def test_runner_fails_closed_on_missing_friction_hash():
    req = _request()
    req = HistoricalValidationRequest(
        strategy_id=req.strategy_id, strategy_version=req.strategy_version,
        dataset=req.dataset,
        friction_contract=FrictionContractRef(contract_id="FR1", contract_hash=""),
        replay_adapter=req.replay_adapter,
    )
    with pytest.raises(ValueError):
        run_historical_validation(req, [])


def test_occurrences_are_immutable_and_hashed():
    occurrences = [_occ(0)]
    result = run_historical_validation(_request(), occurrences)
    assert isinstance(result.occurrences, tuple)
    assert result.occurrences[0].evidence_hash
    # changing an input occurrence after the run must not mutate the result
    assert result.occurrences[0].gross_R == 1.0
