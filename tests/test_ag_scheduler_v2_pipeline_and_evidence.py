import datetime as dt

import pytest

from assistant.models import CONTEXT_READY, STATUS_NO_SETUP, STATUS_TRADE_CANDIDATE, MarketContext, StrategyResult
from strategy_manager.manager import ManagerResult

from ag_scheduler_v2.config_loader import config_hash
from ag_scheduler_v2.cycle_identity import CompletedCycleStore, LIVE_WINDOW
from ag_scheduler_v2.evidence import SchedulerIdentity
from ag_scheduler_v2.m15_clock import BarSettlementPolicy
from ag_scheduler_v2.news_provider import CalendarFetchResult, STATUS_OK
from ag_scheduler_v2.news_risk import NewsRiskWindow
from ag_scheduler_v2.pipeline import process_m15_cycle, requires_m1_fetch
from ag_scheduler_v2.report import build_daily_report
from ag_scheduler_v2.scheduler import AGDailyOpportunitySchedulerV2


def _utc(y, mo, d, h, mi):
    return dt.datetime(y, mo, d, h, mi, tzinfo=dt.timezone.utc)


def _context(symbol, now):
    return MarketContext(
        symbol=symbol, broker_resolved_symbol=symbol, timestamp_utc=now, session_date=now.date(),
        account_login=1, account_server="demo", account_is_demo=True, current_bid=1.1, current_ask=1.1002,
        tick_time_utc=now, status=CONTEXT_READY,
    )


def _make_evaluator(status, setup=None, reason_codes=()):
    def _evaluate(strategy_id, symbol, cycle, mode):
        now = _utc(2026, 9, 10, 8, 15)
        return ManagerResult(
            context=_context(symbol, now),
            strategy_result=StrategyResult(
                strategy_id=strategy_id, strategy_version="1.0.0", symbol=symbol, cycle=cycle,
                session_date=now.date(), status=status, setup=setup, reason_codes=reason_codes,
            ),
        )
    return _evaluate


def _identity():
    return SchedulerIdentity.build(strategy_id="SESSION_TRADE_V1", strategy_version="1.0.0", path=None)


class TestPipelineNoMockFallback:
    def test_qualified_candidate_only_from_real_strategy_result(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        outcome = process_m15_cycle(
            strategy_id="SESSION_TRADE_V1", strategy_id_alias="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version="1.0.0",
            symbol="EURUSD", session_pair="ASIAN_LONDON", cycle_label="ASIAN_LONDON", bar_close_utc=bar_close,
            now_utc=bar_close + dt.timedelta(seconds=6), is_recovered=False, provider_latest_closed_bar_utc=bar_close,
            settlement_policy=BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60),
            cycle_store=store, scheduler_identity=_identity(),
            calendar_fetch=CalendarFetchResult(status=STATUS_OK, events=tuple(), provider="test", retrieved_at_utc=bar_close),
            news_window=NewsRiskWindow(impact="HIGH", minutes_before=15, minutes_after=15),
            strategy_evaluator=_make_evaluator(STATUS_TRADE_CANDIDATE, setup="S1_SWEEP"),
        )
        assert outcome.processed
        assert outcome.evidence.qualified
        assert outcome.evidence.setup_type == "S1_SWEEP"
        assert outcome.evidence.scheduler_identity.strategy_id == "SESSION_TRADE_V1"
        assert requires_m1_fetch(outcome)

    def test_no_setup_result_is_not_qualified_and_no_fabricated_proposal(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        outcome = process_m15_cycle(
            strategy_id="SESSION_TRADE_V1", strategy_id_alias="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version="1.0.0",
            symbol="EURUSD", session_pair="ASIAN_LONDON", cycle_label="ASIAN_LONDON", bar_close_utc=bar_close,
            now_utc=bar_close + dt.timedelta(seconds=6), is_recovered=False, provider_latest_closed_bar_utc=bar_close,
            settlement_policy=BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60),
            cycle_store=store, scheduler_identity=_identity(),
            calendar_fetch=CalendarFetchResult(status=STATUS_OK, events=tuple(), provider="test", retrieved_at_utc=bar_close),
            news_window=NewsRiskWindow(impact="HIGH", minutes_before=15, minutes_after=15),
            strategy_evaluator=_make_evaluator(STATUS_NO_SETUP),
        )
        assert outcome.processed
        assert not outcome.evidence.qualified
        assert outcome.evidence.setup_type is None
        assert not requires_m1_fetch(outcome)

    def test_stale_data_blocks_qualified_proposal_and_does_not_mark_completed(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        outcome = process_m15_cycle(
            strategy_id="SESSION_TRADE_V1", strategy_id_alias="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version="1.0.0",
            symbol="EURUSD", session_pair="ASIAN_LONDON", cycle_label="ASIAN_LONDON", bar_close_utc=bar_close,
            now_utc=bar_close + dt.timedelta(seconds=90), is_recovered=False, provider_latest_closed_bar_utc=None,
            settlement_policy=BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60),
            cycle_store=store, scheduler_identity=_identity(),
            calendar_fetch=CalendarFetchResult(status=STATUS_OK, events=tuple(), provider="test", retrieved_at_utc=bar_close),
            news_window=NewsRiskWindow(impact="HIGH", minutes_before=15, minutes_after=15),
            strategy_evaluator=_make_evaluator(STATUS_TRADE_CANDIDATE, setup="S1_SWEEP"),
        )
        assert not outcome.processed
        assert outcome.skip_reason == "DATA_STALE"
        assert outcome.evidence is None
        assert not store.is_completed(outcome.cycle_id)

    def test_duplicate_cycle_is_skipped_on_second_call(self, tmp_path):
        store = CompletedCycleStore(str(tmp_path / "cycles.json"))
        bar_close = _utc(2026, 9, 10, 8, 15)
        kwargs = dict(
            strategy_id="SESSION_TRADE_V1", strategy_id_alias="ST_SESSION_SWEEP_CONTINUATION_V1", strategy_version="1.0.0",
            symbol="EURUSD", session_pair="ASIAN_LONDON", cycle_label="ASIAN_LONDON", bar_close_utc=bar_close,
            now_utc=bar_close + dt.timedelta(seconds=6), is_recovered=False, provider_latest_closed_bar_utc=bar_close,
            settlement_policy=BarSettlementPolicy(close_settlement_seconds=5, maximum_wait_seconds=60),
            cycle_store=store, scheduler_identity=_identity(),
            calendar_fetch=CalendarFetchResult(status=STATUS_OK, events=tuple(), provider="test", retrieved_at_utc=bar_close),
            news_window=NewsRiskWindow(impact="HIGH", minutes_before=15, minutes_after=15),
            strategy_evaluator=_make_evaluator(STATUS_TRADE_CANDIDATE, setup="S1_SWEEP"),
        )
        first = process_m15_cycle(**kwargs)
        second = process_m15_cycle(**kwargs)
        assert first.processed
        assert not second.processed
        assert second.skip_reason == "DUPLICATE_SKIP"


class TestSchedulerIdentity:
    def test_identity_includes_scheduler_and_config_hash(self):
        identity = _identity()
        assert identity.scheduler_id == "AG_DAILY_OPPORTUNITY_SCHEDULER_V2"
        assert identity.config_hash == config_hash()
        assert identity.strategy_id == "SESSION_TRADE_V1"


class TestDailyReportMissedCycleAccounting:
    def test_missed_rate_computed_from_expected_vs_completed(self):
        report = build_daily_report(
            scheduler_id="AG_DAILY_OPPORTUNITY_SCHEDULER_V2", scheduler_version="1.0.0",
            evidence_records=[], expected_cycles=100, completed_live_cycles=90, catch_up_cycles=5,
        )
        assert report.missed_cycles == 5
        assert report.missed_observation_cycle_rate == pytest.approx(0.05)

    def test_report_counts_qualified_and_news_states(self):
        records = [
            {"symbol": "EURUSD", "session_pair": "ASIAN_LONDON", "setup_type": "S1_SWEEP", "qualified": True, "reason_codes": [], "news_state": "NORMAL", "priority_action": "WOULD_PRIORITIZE"},
            {"symbol": "GBPUSD", "session_pair": "ASIAN_LONDON", "setup_type": None, "qualified": False, "reason_codes": ["NO_SETUP"], "news_state": "NEWS_RISK", "priority_action": None},
        ]
        report = build_daily_report(scheduler_id="X", scheduler_version="1.0.0", evidence_records=records, expected_cycles=2, completed_live_cycles=2, catch_up_cycles=0)
        assert report.total_qualified_opportunities == 1
        assert report.total_rejected_opportunities == 1
        assert report.news_risk_count == 1
        assert report.normal_count == 1
        assert report.rejection_reason_counts == {"NO_SETUP": 1}


class TestSchedulerCheckpoint:
    def test_tick_persists_state_and_transition(self, tmp_path):
        sched = AGDailyOpportunitySchedulerV2(str(tmp_path / "checkpoint.json"))
        first = sched.tick(_utc(2026, 9, 10, 6, 30))
        assert first.state == "BTC_OBSERVE"
        assert first.transitioned

        second = sched.tick(_utc(2026, 9, 10, 6, 32))
        assert second.state == "BTC_OBSERVE"
        assert not second.transitioned

        third = sched.tick(_utc(2026, 9, 10, 6, 45))
        assert third.state == "BTC_FINALIZE"
        assert third.transitioned
        assert third.previous_state == "BTC_OBSERVE"

    def test_checkpoint_survives_new_instance_restart(self, tmp_path):
        path = str(tmp_path / "checkpoint.json")
        sched1 = AGDailyOpportunitySchedulerV2(path)
        sched1.tick(_utc(2026, 9, 10, 7, 0))
        sched2 = AGDailyOpportunitySchedulerV2(path)
        checkpoint = sched2.load_checkpoint()
        assert checkpoint["current_state"] == "WINDOW_ASIAN_LONDON"
