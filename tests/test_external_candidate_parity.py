"""TEST_ONLY SYNTHETIC fixtures throughout -- exercises the comparator/verdict
logic in src/external_candidate/parity/, never real strategy trade data.
"""
from __future__ import annotations

from performance.calculator import compute_trade_metrics
from performance.models import ResolvedTradeSample

from external_candidate.parity.economic_comparator import compare_economics
from external_candidate.parity.signal_comparator import compare_signals
from external_candidate.parity.trade_comparator import compare_trades
from external_candidate.parity.verdict import (
    PARITY_FAIL,
    PARITY_NOT_PROVABLE,
    PARITY_PASS,
    compute_parity_verdict,
)


def _sample(record_id: str, gross_R: float) -> ResolvedTradeSample:
    return ResolvedTradeSample(
        source_record_id=record_id, source_path="TEST_ONLY", strategy_id="ST_SYNTHETIC_TEST_ONLY_V1",
        strategy_version="1.0.0", symbol="EURUSD", cycle=record_id, resolved_at="2026-09-01T00:00:00+00:00",
        gross_R=gross_R, net_R=gross_R, cost_status="NOT_INCLUDED", outcome="RESOLVED_SL" if gross_R < 0 else "RESOLVED_TP1",
    )


def test_identical_signals_match():
    external = [{"cycle": "c1", "setup_type": "S1", "direction": "LONG", "entry": 1.1, "stop_loss": 1.09, "take_profit": 1.12, "expiry": None, "state": "READY"}]
    repo = [dict(external[0])]
    result = compare_signals(external, repo, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    assert result.matched_cycles == 1
    assert result.mismatched_cycles == 0
    assert result.first_mismatch is None


def test_diverging_direction_is_first_mismatch_and_classified_signal():
    external = [{"cycle": "c1", "setup_type": "S1", "direction": "LONG", "entry": 1.1, "stop_loss": 1.09, "take_profit": 1.12, "expiry": None, "state": "READY"}]
    repo = [{"cycle": "c1", "setup_type": "S1", "direction": "SHORT", "entry": 1.1, "stop_loss": 1.09, "take_profit": 1.12, "expiry": None, "state": "READY"}]
    result = compare_signals(external, repo, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    assert result.mismatched_cycles == 1
    assert result.first_mismatch is not None
    assert result.first_mismatch.field_name == "direction"
    assert result.first_mismatch.category == "SIGNAL"


def test_unmatched_keys_count_as_mismatched():
    external = [{"cycle": "c1", "direction": "LONG"}]
    repo = []
    result = compare_signals(external, repo, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    assert result.unmatched_external_keys == ("c1",)
    assert result.mismatched_cycles == 1


def test_trade_comparator_matches_within_tolerance():
    external = [{"cycle": "c1", "direction": "LONG", "entry": 1.10000, "stop_loss": 1.09000, "take_profit": 1.12000, "exit_price": 1.12000, "outcome": "WIN", "gross_R": 2.0, "net_R": 1.9}]
    repo = [{"cycle": "c1", "direction": "LONG", "entry": 1.10000, "stop_loss": 1.09000, "take_profit": 1.12000, "exit_price": 1.12000, "outcome": "WIN", "gross_R": 2.0000001, "net_R": 1.9}]
    result = compare_trades(external, repo, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    assert result.matched_cycles == 1
    assert result.mismatched_cycles == 0


def test_trade_comparator_catches_genuine_price_divergence():
    external = [{"cycle": "c1", "direction": "LONG", "entry": 1.1000, "stop_loss": 1.09, "take_profit": 1.12, "exit_price": 1.12, "outcome": "WIN", "gross_R": 2.0, "net_R": 1.9}]
    repo = [{"cycle": "c1", "direction": "LONG", "entry": 1.1005, "stop_loss": 1.09, "take_profit": 1.12, "exit_price": 1.12, "outcome": "WIN", "gross_R": 2.0, "net_R": 1.9}]
    result = compare_trades(external, repo, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    assert result.mismatched_cycles == 1
    assert result.first_mismatch.field_name == "entry"
    assert result.first_mismatch.category == "ENTRY"


def test_economic_comparator_matches_identical_metrics():
    samples = [_sample("a", 1.0), _sample("b", -1.0)]
    metrics_a = compute_trade_metrics(samples)
    metrics_b = compute_trade_metrics(samples)
    result = compare_economics(metrics_a, metrics_b)
    assert result.matches


def test_economic_comparator_flags_divergent_expectancy():
    metrics_a = compute_trade_metrics([_sample("a", 1.0), _sample("b", -1.0)])
    metrics_b = compute_trade_metrics([_sample("a", 5.0), _sample("b", -1.0)])
    result = compare_economics(metrics_a, metrics_b)
    assert not result.matches
    assert "gross_total_R" in result.mismatched_fields


def test_verdict_requires_semantic_evidence_not_aggregate_only():
    # No signal/trade comparator supplied at all -- even if an economic comparator
    # somehow existed, aggregate-only agreement must never yield PASS.
    verdict = compute_parity_verdict(None, None, None)
    assert verdict == PARITY_NOT_PROVABLE


def test_verdict_pass_requires_clean_trade_parity():
    trades_external = [{"cycle": "c1", "direction": "LONG", "gross_R": 1.0, "net_R": 1.0}]
    trade_result = compare_trades(trades_external, trades_external, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    verdict = compute_parity_verdict(None, trade_result, None)
    assert verdict == PARITY_PASS


def test_verdict_fails_on_trade_mismatch_even_if_economics_agree():
    trades_external = [{"cycle": "c1", "direction": "LONG", "gross_R": 1.0, "net_R": 1.0}]
    trades_repo = [{"cycle": "c1", "direction": "SHORT", "gross_R": 1.0, "net_R": 1.0}]
    trade_result = compare_trades(trades_external, trades_repo, candidate_fingerprint="fp", dataset_fingerprint="dfp")
    metrics = compute_trade_metrics([_sample("a", 1.0)])
    economic_result = compare_economics(metrics, metrics)
    verdict = compute_parity_verdict(None, trade_result, economic_result)
    assert verdict == PARITY_FAIL
