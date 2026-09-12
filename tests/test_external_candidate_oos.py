"""TEST_ONLY SYNTHETIC evidence -- exercises src/external_candidate/oos_evaluator.py
only. Never cite these numbers as real strategy performance.
"""
from __future__ import annotations

from performance.models import ResolvedTradeSample

from _fixtures_external_candidate import make_dataset

from external_candidate.models import DatasetRole
from external_candidate.oos_evaluator import evaluate_oos


def _sample(record_id: str, gross_R: float) -> ResolvedTradeSample:
    return ResolvedTradeSample(
        source_record_id=record_id, source_path="TEST_ONLY", strategy_id="ST_SYNTHETIC_TEST_ONLY_V1",
        strategy_version="1.0.0", symbol="EURUSD", cycle=record_id, resolved_at="2026-09-01T00:00:00+00:00",
        gross_R=gross_R, net_R=gross_R, cost_status="NOT_INCLUDED", outcome="TEST_ONLY",
    )


def test_oos_evidence_aggregates_supplied_samples_without_mutation():
    dataset = make_dataset(DatasetRole.HOLDOUT, "SYNTHETIC_OOS", "2026-07-01T00:00:00+00:00", "2026-07-31T00:00:00+00:00")
    samples = [_sample("a", 1.0), _sample("b", -1.0), _sample("c", 1.0)]
    evidence = evaluate_oos("ST_SYNTHETIC_TEST_ONLY_V1", "1.1.0", "CANDIDATE_TEST_0001", dataset, samples)
    assert evidence.metrics.sample_size == 3
    assert evidence.dataset_identity == "SYNTHETIC_OOS"
    assert evidence.evidence_fingerprint  # non-empty deterministic hash


def test_oos_evidence_fingerprint_is_deterministic():
    dataset = make_dataset(DatasetRole.HOLDOUT, "SYNTHETIC_OOS", "2026-07-01T00:00:00+00:00", "2026-07-31T00:00:00+00:00")
    samples = [_sample("a", 1.0)]
    e1 = evaluate_oos("ST_X", "1.0.0", "C1", dataset, samples)
    e2 = evaluate_oos("ST_X", "1.0.0", "C1", dataset, samples)
    assert e1.evidence_fingerprint == e2.evidence_fingerprint
