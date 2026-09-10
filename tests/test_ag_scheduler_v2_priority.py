import datetime as dt

import pytest

from ag_scheduler_v2.priority import (
    STATUS_INSUFFICIENT_ROLLING_SAMPLE, STATUS_SCORED, WOULD_PRIORITIZE, Candidate, PriorityConfig,
    ResolvedTradeOutcome, compute_priority, rank_candidates,
)


def _utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


CONFIG = PriorityConfig(rolling_sample_trades=30, deterministic_symbol_fallback_order=("EURUSD", "GBPUSD"))


def _history(n, r_multiple=1.0, start=_utc(2026, 9, 1, 0, 0)):
    return [ResolvedTradeOutcome(resolved_at_utc=start + dt.timedelta(hours=i), r_multiple=r_multiple) for i in range(n)]


class TestRollingSample:
    def test_below_30_trades_is_insufficient_sample(self):
        cand = Candidate(symbol="EURUSD", setup_type="S1_SWEEP", current_spread=1.0, baseline_spread=1.0)
        result = compute_priority(cand, history_before_t=_history(29), as_of_utc=_utc(2026, 9, 5, 0, 0), config=CONFIG)
        assert result.priority_status == STATUS_INSUFFICIENT_ROLLING_SAMPLE
        assert result.priority_score is None
        assert result.expectancy_sample_n == 29

    def test_exactly_30_trades_is_scored(self):
        cand = Candidate(symbol="EURUSD", setup_type="S1_SWEEP", current_spread=1.0, baseline_spread=1.0)
        result = compute_priority(cand, history_before_t=_history(30), as_of_utc=_utc(2026, 9, 5, 0, 0), config=CONFIG)
        assert result.priority_status == STATUS_SCORED
        assert result.expectancy_sample_n == 30
        assert result.expectancy_value == pytest.approx(1.0)  # all wins of size 1.0


class TestLookaheadProtection:
    def test_future_outcome_raises(self):
        cand = Candidate(symbol="EURUSD", setup_type="S1_SWEEP", current_spread=1.0, baseline_spread=1.0)
        as_of = _utc(2026, 9, 1, 0, 0)
        history = [ResolvedTradeOutcome(resolved_at_utc=as_of + dt.timedelta(hours=1), r_multiple=1.0)]
        with pytest.raises(ValueError, match="RANKING_LOOKAHEAD"):
            compute_priority(cand, history_before_t=history, as_of_utc=as_of, config=CONFIG)

    def test_same_instant_outcome_raises(self):
        cand = Candidate(symbol="EURUSD", setup_type="S1_SWEEP", current_spread=1.0, baseline_spread=1.0)
        as_of = _utc(2026, 9, 1, 0, 0)
        history = [ResolvedTradeOutcome(resolved_at_utc=as_of, r_multiple=1.0)]
        with pytest.raises(ValueError, match="RANKING_LOOKAHEAD"):
            compute_priority(cand, history_before_t=history, as_of_utc=as_of, config=CONFIG)


class TestSpreadRatio:
    def test_wider_current_spread_lowers_priority_score(self):
        as_of = _utc(2026, 9, 5, 0, 0)
        tight = Candidate(symbol="EURUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0)
        wide = Candidate(symbol="EURUSD", setup_type="S1", current_spread=2.0, baseline_spread=1.0)
        history = _history(30)
        r_tight = compute_priority(tight, history_before_t=history, as_of_utc=as_of, config=CONFIG)
        r_wide = compute_priority(wide, history_before_t=history, as_of_utc=as_of, config=CONFIG)
        assert r_wide.priority_score < r_tight.priority_score


class TestDeterministicTieBreak:
    def test_eurusd_beats_gbpusd_when_otherwise_equal(self):
        as_of = _utc(2026, 9, 5, 0, 0)
        eur = Candidate(symbol="EURUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0)
        gbp = Candidate(symbol="GBPUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0)
        results = [
            compute_priority(eur, history_before_t=(), as_of_utc=as_of, config=CONFIG),
            compute_priority(gbp, history_before_t=(), as_of_utc=as_of, config=CONFIG),
        ]
        ranked = rank_candidates([eur, gbp], results, config=CONFIG)
        assert ranked[0].candidate.symbol == "EURUSD"
        assert ranked[0].rank == 1
        assert ranked[1].candidate.symbol == "GBPUSD"

    def test_ineligible_candidate_ranks_below_eligible_regardless_of_score(self):
        as_of = _utc(2026, 9, 5, 0, 0)
        ineligible = Candidate(symbol="EURUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0, news_eligible=False)
        eligible = Candidate(symbol="GBPUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0)
        results = [
            compute_priority(ineligible, history_before_t=_history(30, r_multiple=5.0), as_of_utc=as_of, config=CONFIG),
            compute_priority(eligible, history_before_t=(), as_of_utc=as_of, config=CONFIG),
        ]
        ranked = rank_candidates([ineligible, eligible], results, config=CONFIG)
        assert ranked[0].candidate.symbol == "GBPUSD"

    def test_all_candidates_retained_regardless_of_rank(self):
        as_of = _utc(2026, 9, 5, 0, 0)
        eur = Candidate(symbol="EURUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0)
        gbp = Candidate(symbol="GBPUSD", setup_type="S1", current_spread=1.0, baseline_spread=1.0)
        results = [
            compute_priority(eur, history_before_t=(), as_of_utc=as_of, config=CONFIG),
            compute_priority(gbp, history_before_t=(), as_of_utc=as_of, config=CONFIG),
        ]
        ranked = rank_candidates([eur, gbp], results, config=CONFIG)
        assert len(ranked) == 2
        assert all(r.action == WOULD_PRIORITIZE for r in ranked)
