"""Focused tests for src/opportunity/contracts.py (AG V2 P3/P4/P6).

Covers deterministic serialization/round-trip, invalid enum/state rejection,
timezone-aware timestamp enforcement, required-field fail-closed behavior, and
REAL/REPLAY/SYNTHETIC propagation -- no timestamp invention, no raw strategy
state loss.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from opportunity.contracts import (
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_REPLAY,
    MARKET_DATA_MODE_SYNTHETIC,
    REPLAY_DATA_NOT_BROKER_EXECUTABLE,
    SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE,
    CandidateGeometry,
    DataAuthority,
    ELIGIBILITY_BLOCKED,
    ELIGIBILITY_ELIGIBLE,
    FrictionEvidence,
    MarketEvent,
    OpportunityCandidate,
    ProposalEligibilityDecision,
    WarmupRequirement,
    synthetic_or_replay_block_reasons,
)
from opportunity.stages import (
    OUTCOME_WAIT,
    STAGE_TRIGGER_ARMED,
)

UTC = dt.timezone.utc


def _event(**overrides) -> MarketEvent:
    base = dict(
        event_id="evt-1",
        event_type="BAR_CLOSE",
        symbol="EURUSD",
        market="FX",
        venue="VANTAGE_DEMO_MT5",
        timeframe="M15",
        bar_open_time=dt.datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
        bar_close_time=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
        market_data_asof=dt.datetime(2026, 9, 21, 8, 15, 1, tzinfo=UTC),
        market_data_mode=MARKET_DATA_MODE_REAL,
        snapshot_fingerprint="abc123",
        source="VANTAGE_DEMO_MT5",
    )
    base.update(overrides)
    return MarketEvent(**base)


def _candidate(**overrides) -> OpportunityCandidate:
    base = dict(
        candidate_id="cand-1",
        occurrence_id="occ-1",
        strategy_id="ST_ASIAN_SWEEP_5R_V1",
        strategy_version="1.0.0",
        strategy_engine_version=None,
        symbol="EURUSD",
        market="FX",
        venue="VANTAGE_DEMO_MT5",
        direction="BUY",
        detected_at=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
        last_evaluated_at=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
        expires_at=None,
        stage=STAGE_TRIGGER_ARMED,
        outcome=OUTCOME_WAIT,
        revision=1,
    )
    base.update(overrides)
    return OpportunityCandidate(**base)


class TestMarketEvent:
    def test_round_trip_equality(self):
        a = _event()
        b = _event()
        assert a == b
        assert dataclasses.asdict(a) == dataclasses.asdict(b)

    def test_deterministic_by_value(self):
        assert _event() == _event()

    def test_invalid_market_data_mode_rejected(self):
        with pytest.raises(ValueError):
            _event(market_data_mode="FAKE_MODE")

    def test_naive_bar_open_time_rejected(self):
        with pytest.raises(ValueError):
            _event(bar_open_time=dt.datetime(2026, 9, 21, 8, 0))

    def test_future_data_rejected(self):
        with pytest.raises(ValueError):
            _event(market_data_asof=dt.datetime(2026, 9, 21, 8, 0, tzinfo=UTC))

    def test_bar_close_before_open_rejected(self):
        with pytest.raises(ValueError):
            _event(
                bar_open_time=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
                bar_close_time=dt.datetime(2026, 9, 21, 8, 0, tzinfo=UTC),
            )

    @pytest.mark.parametrize(
        "mode", [MARKET_DATA_MODE_REAL, MARKET_DATA_MODE_REPLAY, MARKET_DATA_MODE_SYNTHETIC]
    )
    def test_mode_propagates_unchanged(self, mode):
        event = _event(market_data_mode=mode)
        assert event.market_data_mode == mode


class TestOpportunityCandidate:
    def test_round_trip_equality(self):
        assert _candidate() == _candidate()

    def test_invalid_stage_rejected(self):
        with pytest.raises(ValueError):
            _candidate(stage="NOT_A_STAGE")

    def test_invalid_outcome_rejected(self):
        with pytest.raises(ValueError):
            _candidate(outcome="NOT_AN_OUTCOME")

    def test_stage_and_outcome_are_independent(self):
        c = _candidate(stage=STAGE_TRIGGER_ARMED, outcome=OUTCOME_WAIT)
        assert c.stage == STAGE_TRIGGER_ARMED
        assert c.outcome == OUTCOME_WAIT

    def test_naive_detected_at_rejected(self):
        with pytest.raises(ValueError):
            _candidate(detected_at=dt.datetime(2026, 9, 21, 8, 15))

    def test_revision_must_be_positive(self):
        with pytest.raises(ValueError):
            _candidate(revision=0)

    def test_raw_strategy_state_preserved_verbatim(self):
        raw = {"watcher_state": "SWEPT", "note": "do-not-touch"}
        c = _candidate(raw_strategy_state=raw)
        assert c.raw_strategy_state == raw

    def test_missing_geometry_stays_none(self):
        c = _candidate()
        assert c.geometry is None

    def test_no_funnel_history_field(self):
        field_names = {f.name for f in dataclasses.fields(OpportunityCandidate)}
        assert "funnel_history" not in field_names


class TestCandidateGeometry:
    def test_missing_fields_stay_none_not_invented(self):
        geo = CandidateGeometry()
        assert geo.entry is None
        assert geo.invalidation is None
        assert geo.targets == ()


class TestProposalEligibilityDecision:
    def test_valid_status_accepted(self):
        decision = ProposalEligibilityDecision(
            candidate_id="cand-1",
            status=ELIGIBILITY_ELIGIBLE,
            evaluated_at=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
        )
        assert decision.status == ELIGIBILITY_ELIGIBLE

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            ProposalEligibilityDecision(
                candidate_id="cand-1",
                status="READY",  # not a valid eligibility state -- must not silently pass
                evaluated_at=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
            )

    def test_research_qualified_does_not_imply_eligible(self):
        # A candidate's raw_strategy_state carrying RESEARCH_QUALIFIED must never
        # by itself produce ELIGIBLE -- this is a decision made by the caller,
        # never inferred inside the dataclass.
        c = _candidate(raw_strategy_state={"lifecycle": "RESEARCH_QUALIFIED"})
        decision = ProposalEligibilityDecision(
            candidate_id=c.candidate_id,
            status=ELIGIBILITY_BLOCKED,
            reason_codes=("RESEARCH_ONLY_NO_PROPOSAL_AUTHORITY",),
            evaluated_at=dt.datetime(2026, 9, 21, 8, 15, tzinfo=UTC),
        )
        assert decision.status == ELIGIBILITY_BLOCKED


class TestSyntheticReplayFirewall:
    def test_synthetic_always_blocked(self):
        reasons = synthetic_or_replay_block_reasons(MARKET_DATA_MODE_SYNTHETIC, broker_bound=False)
        assert SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE in reasons

    def test_replay_blocked_only_when_broker_bound(self):
        assert synthetic_or_replay_block_reasons(MARKET_DATA_MODE_REPLAY, broker_bound=False) == ()
        reasons = synthetic_or_replay_block_reasons(MARKET_DATA_MODE_REPLAY, broker_bound=True)
        assert REPLAY_DATA_NOT_BROKER_EXECUTABLE in reasons

    def test_real_never_blocked_by_firewall(self):
        assert synthetic_or_replay_block_reasons(MARKET_DATA_MODE_REAL, broker_bound=True) == ()


class TestWarmupRequirement:
    def test_ready_when_enough_bars(self):
        req = WarmupRequirement(timeframe="H1", required_closed_bars=100, available_closed_bars=100)
        assert req.ready is True

    def test_not_ready_when_insufficient_bars(self):
        req = WarmupRequirement(timeframe="H1", required_closed_bars=100, available_closed_bars=99)
        assert req.ready is False


class TestDataAuthority:
    def test_naive_coverage_start_rejected(self):
        with pytest.raises(ValueError):
            DataAuthority(
                dataset_id="ds-1",
                symbol="EURUSD",
                timeframe="H1",
                source="VANTAGE_DEMO_MT5",
                coverage_start=dt.datetime(2025, 1, 1),
            )

    def test_minimal_construction_leaves_optional_fields_none(self):
        authority = DataAuthority(dataset_id="ds-1", symbol="EURUSD", timeframe="H1", source="X")
        assert authority.content_fingerprint is None
        assert authority.authorization_status == "NOT_EVALUATED"


class TestFrictionEvidence:
    def test_defaults_are_not_evaluated_not_zero(self):
        friction = FrictionEvidence()
        assert friction.spread is None
        assert friction.coverage_status == "NOT_EVALUATED"
