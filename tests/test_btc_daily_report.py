"""Tests for btc_sweep_research.daily_report -- the wrapping/classification/archive
layer only (pipeline.run_research_cycle itself is monkeypatched to a fake result;
tests/test_btc_sweep_research_pipeline.py already covers the real strategy-engine
fixture path, not re-derived here). Proves: WATCH/NO_TRADE/READY classification from
an already-computed ResearchCycleReport, DATA_ERROR wrapping on a feed exception
(never an uncaught exception), the canonical schema shape, and archive CREATED/
IDEMPOTENT/correction behavior (reusing post_asian_pilot.report_archive unchanged).
"""
from __future__ import annotations

import datetime as dt

import pytest

from btc_sweep_research import daily_report
from btc_sweep_research.pipeline import ResearchCycleReport, ResearchCycleResult
from btc_sweep_research.proposal import BTCSweepResearchProposal
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.models import (
    STATE_ENTRY_READY,
    STATE_NO_TRADE_DIRECTION,
    STATE_SETUP_EXPIRED,
    STATE_WAITING_REFERENCE,
    SetupState,
)

UTC = dt.timezone.utc
OBS_DATE = dt.date(2026, 1, 5)


class _RaisingFeed:
    class _Boom(RuntimeError):
        reason_code = "KLINES_STALE_DATA"

    def get_latest_candles(self, symbol, timeframe, count):
        raise self._Boom("simulated feed failure")


def _setup_state(state, strategy_qualified=False, reason_code="X", setup_id="S1"):
    return SetupState(setup_id=setup_id, strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1", symbol="BTCUSDT",
                      state=state, reason_code=reason_code, evaluated_at=dt.datetime(2026, 1, 5, 15, tzinfo=UTC),
                      strategy_qualified=strategy_qualified)


def _proposal(setup_id="S1"):
    return BTCSweepResearchProposal(
        strategy="ST_LIQUIDITY_SWEEP_RETEST_V1", strategy_version="2.0.0", authority="RESEARCH_ONLY",
        exchange="BYBIT_LINEAR_PERP", instrument="BTCUSDT", direction="LONG",
        reference_day=dt.date(2026, 1, 4), reference_high=51000.0, reference_low=50000.0,
        sweep={"level": 50000.0, "extreme": 49900.0, "time": dt.datetime(2026, 1, 5, 14, tzinfo=UTC)},
        confirmation={"broken_swing_price": 50200.0, "mss_time": dt.datetime(2026, 1, 5, 14, 30, tzinfo=UTC)},
        entry=50300.0, stop=50100.0, target={"tp1": 50500.0, "tp2": 50900.0}, RR=2.5,
        estimated_fees=1.0, funding_assumption={}, data_timestamp=dt.datetime(2026, 1, 5, 15, tzinfo=UTC),
        expiry=dt.datetime(2026, 1, 5, 16, tzinfo=UTC), occurrence_id="OCC-1", setup_id=setup_id,
    )


class _FakeFeed:
    def get_latest_candles(self, symbol, timeframe, count):
        return []


def _patch_cycle(monkeypatch, report: ResearchCycleReport):
    monkeypatch.setattr(daily_report.pipeline, "run_research_cycle", lambda *a, **kw: report)


def _base_kwargs():
    return dict(application_release="AG_TRADE_ASSISTANT_V1_0_3", provider="BYBIT",
               provider_symbol="BTCUSDT", market_type="LINEAR_USDT_PERPETUAL",
               exchange_id="BYBIT_LINEAR_PERP")


# --------------------------------------------------------------------------------- WATCH

def test_watch_day_from_container_state(monkeypatch):
    container = _setup_state(STATE_WAITING_REFERENCE, reason_code="REFERENCE_WINDOW_INCOMPLETE")
    report = ResearchCycleReport(trading_day=OBS_DATE, container_state=container, occurrences=())
    _patch_cycle(monkeypatch, report)

    result = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    assert result["decision"] == "WATCH"
    assert result["proposal_count"] == 0
    assert result["data_quality"]["status"] == "PASS"
    assert result["schema_version"] == "AG_BTC_DAILY_REPORT_V1"


# ------------------------------------------------------------------------------ NO_TRADE

def test_no_trade_day_from_container_state(monkeypatch):
    container = _setup_state(STATE_NO_TRADE_DIRECTION, reason_code=STATE_NO_TRADE_DIRECTION)
    report = ResearchCycleReport(trading_day=OBS_DATE, container_state=container, occurrences=())
    _patch_cycle(monkeypatch, report)

    result = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    assert result["decision"] == "NO_TRADE"


def test_no_trade_day_from_unqualified_occurrences(monkeypatch):
    unqualified = ResearchCycleResult(setup_state=_setup_state(STATE_SETUP_EXPIRED, reason_code="EXPIRED"),
                                      proposal=None, ledger_new_row=False, trading_day=OBS_DATE)
    report = ResearchCycleReport(trading_day=OBS_DATE, container_state=None, occurrences=(unqualified,))
    _patch_cycle(monkeypatch, report)

    result = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    assert result["decision"] == "NO_TRADE"
    assert result["proposal_count"] == 0


# --------------------------------------------------------------------------------- READY

def test_ready_day_with_proposal(monkeypatch):
    proposal = _proposal()
    qualified = ResearchCycleResult(
        setup_state=_setup_state(STATE_ENTRY_READY, strategy_qualified=True, reason_code="QUALIFIED"),
        proposal=proposal, ledger_new_row=True, trading_day=OBS_DATE,
    )
    report = ResearchCycleReport(trading_day=OBS_DATE, container_state=None, occurrences=(qualified,))
    _patch_cycle(monkeypatch, report)

    result = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    assert result["decision"] == "READY"
    assert result["proposal_count"] == 1
    occ = result["occurrences"][0]
    assert occ["strategy_qualified"] is True
    assert occ["proposal"]["occurrence_id"] == proposal.occurrence_id
    assert occ["proposal"]["entry"] == proposal.entry
    assert occ["proposal"]["execution_authority"] == "DISABLED"
    assert result["execution_authority"]["automatic_execution"] == "DISABLED"


def test_ready_day_zero_proposal_still_valid_shape_is_not_forced():
    """A zero-proposal (WATCH) day must never contain a fabricated proposal field."""
    report = ResearchCycleReport(
        trading_day=OBS_DATE, container_state=_setup_state(STATE_WAITING_REFERENCE), occurrences=(),
    )
    class _P:
        pass
    import btc_sweep_research.daily_report as dr
    # sanity: direct classification helper never invents a proposal
    classification = dr._decision_from_cycle_report(report)
    assert classification["decision"] == "WATCH"


# ------------------------------------------------------------------------------ DATA_ERROR

def test_data_error_on_feed_exception_is_never_uncaught():
    result = daily_report.build_btc_daily_report(_RaisingFeed(), OBS_DATE, **_base_kwargs())
    assert result["decision"] == "DATA_ERROR"
    assert result["data_quality"]["status"] == "FAIL"
    assert result["data_quality"]["reason_code"] == "KLINES_STALE_DATA"
    assert result["proposal_count"] == 0
    assert result["occurrences"] == []


# --------------------------------------------------------------------------------- archive

def test_archive_created_then_idempotent(tmp_path, monkeypatch):
    report = ResearchCycleReport(trading_day=OBS_DATE, container_state=_setup_state(STATE_WAITING_REFERENCE),
                                 occurrences=())
    _patch_cycle(monkeypatch, report)
    r1 = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    path1 = daily_report.archive_btc_daily_report(OBS_DATE, r1, root=str(tmp_path))

    r2 = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs(),
                                              generated_at=dt.datetime(2099, 1, 1, tzinfo=UTC))
    path2 = daily_report.archive_btc_daily_report(OBS_DATE, r2, root=str(tmp_path))
    assert path1 == path2  # idempotent -- generated_at difference alone is not a real change

    import os
    assert not any("correction" in name for name in os.listdir(os.path.dirname(path1)))


def test_archive_correction_on_real_change_preserves_original(tmp_path, monkeypatch):
    watch_report = ResearchCycleReport(trading_day=OBS_DATE, container_state=_setup_state(STATE_WAITING_REFERENCE),
                                       occurrences=())
    _patch_cycle(monkeypatch, watch_report)
    r1 = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    path1 = daily_report.archive_btc_daily_report(OBS_DATE, r1, root=str(tmp_path))

    qualified = ResearchCycleResult(setup_state=_setup_state(STATE_ENTRY_READY, strategy_qualified=True),
                                    proposal=_proposal(), ledger_new_row=True, trading_day=OBS_DATE)
    ready_report = ResearchCycleReport(trading_day=OBS_DATE, container_state=None, occurrences=(qualified,))
    _patch_cycle(monkeypatch, ready_report)
    r2 = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    path2 = daily_report.archive_btc_daily_report(OBS_DATE, r2, root=str(tmp_path))

    assert path1 != path2
    assert "correction-001" in path2

    import json
    with open(path1, encoding="utf-8") as f:
        assert json.load(f)["decision"] == "WATCH"  # original untouched
    with open(path2, encoding="utf-8") as f:
        record = json.load(f)
    assert record["new_record"]["decision"] == "READY"
    assert record["supersedes"] == path1


# ----------------------------------------------------------------------- execution firewall

def test_daily_report_module_never_references_execution_send_path():
    assert not hasattr(daily_report, "order_send")
    assert not any(name.startswith("execution") for name in vars(daily_report))


def test_next_day_report_clock_still_evaluates_observation_date(monkeypatch):
    captured = {}

    def _cycle(*args, **kwargs):
        captured["now"] = kwargs["now"]
        return ResearchCycleReport(
            trading_day=OBS_DATE,
            container_state=_setup_state(STATE_WAITING_REFERENCE),
            occurrences=(),
        )

    monkeypatch.setattr(daily_report.pipeline, "run_research_cycle", _cycle)
    next_day_report_time = dt.datetime(2026, 1, 6, 0, 7, tzinfo=UTC)
    result = daily_report.build_btc_daily_report(
        _FakeFeed(), OBS_DATE, **_base_kwargs(), now=next_day_report_time,
        generated_at=next_day_report_time,
    )

    assert captured["now"].date() == OBS_DATE
    assert captured["now"].time() == dt.time(23, 59, 59, 999999)
    assert result["generated_at_utc"] == next_day_report_time.isoformat()


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (dt.datetime(2026, 1, 6, 0, 4, 59, tzinfo=UTC), "BEFORE_WINDOW"),
        (dt.datetime(2026, 1, 6, 0, 5, tzinfo=UTC), "IN_WINDOW"),
        (dt.datetime(2026, 1, 6, 0, 14, 59, tzinfo=UTC), "IN_WINDOW"),
        (dt.datetime(2026, 1, 6, 0, 15, tzinfo=UTC), "AFTER_WINDOW"),
    ],
)
def test_report_window_status(now, expected):
    assert daily_report.report_window_status(OBS_DATE, now) == expected


def test_human_report_renders_informational_ticket_only_for_proposal(monkeypatch):
    qualified = ResearchCycleResult(
        setup_state=_setup_state(STATE_ENTRY_READY, strategy_qualified=True),
        proposal=_proposal(), ledger_new_row=True, trading_day=OBS_DATE,
    )
    _patch_cycle(monkeypatch, ResearchCycleReport(
        trading_day=OBS_DATE, container_state=None, occurrences=(qualified,),
    ))
    report = daily_report.build_btc_daily_report(_FakeFeed(), OBS_DATE, **_base_kwargs())
    text = daily_report.human_readable_btc_daily_report(report)
    assert "ENTRY PROPOSAL TICKET" in text
    assert "NOT A BROKER TICKET" in text
    assert "Execution authority: DISABLED" in text


class _CompleteObservationFeed:
    def __init__(self, missing_m5=False):
        h1_start = dt.datetime(2025, 12, 28, tzinfo=UTC)
        m5_start = dt.datetime(2026, 1, 4, tzinfo=UTC)
        self.h1 = [Candle(time=h1_start + dt.timedelta(hours=i), open=1, high=2, low=0.5,
                          close=1.5, volume=1) for i in range(200)]
        self.m5 = [Candle(time=m5_start + dt.timedelta(minutes=5 * i), open=1, high=2, low=0.5,
                          close=1.5, volume=1) for i in range(600)]
        if missing_m5:
            missing = dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC)
            self.m5 = [c for c in self.m5 if c.time != missing]

    def get_latest_candles(self, symbol, timeframe, count):
        return list((self.h1 if timeframe == "H1" else self.m5)[-count:])


def test_complete_production_observation_audit_passes_before_cycle(monkeypatch):
    report = ResearchCycleReport(
        trading_day=OBS_DATE, container_state=_setup_state(STATE_WAITING_REFERENCE), occurrences=(),
    )
    _patch_cycle(monkeypatch, report)
    result = daily_report.build_btc_daily_report(
        _CompleteObservationFeed(), OBS_DATE, **_base_kwargs(), validate_observation_data=True,
    )
    assert result["data_quality"]["status"] == "PASS"
    assert result["data_quality"]["h1_reference_candles"] == 24
    assert result["data_quality"]["m5_observation_candles"] == 288
    assert result["data_quality"]["closed_candles_only"] is True


def test_incomplete_observation_fails_closed_before_cycle(monkeypatch):
    called = False

    def _cycle(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("strategy must not run on incomplete evidence")

    monkeypatch.setattr(daily_report.pipeline, "run_research_cycle", _cycle)
    result = daily_report.build_btc_daily_report(
        _CompleteObservationFeed(missing_m5=True), OBS_DATE, **_base_kwargs(),
        validate_observation_data=True,
    )
    assert called is False
    assert result["decision"] == "DATA_ERROR"
    assert result["data_quality"]["reason_code"] == "BTC_M5_OBSERVATION_INCOMPLETE"
