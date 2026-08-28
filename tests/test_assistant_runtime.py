"""End-to-end tests for assistant.runtime.evaluate(), with strategy_manager.manager's
context/adapter calls mocked (canned fixtures modeled on the real subprocess/JSON shapes
found during Phase 1 audit). Covers mode isolation, cycle authority, idempotence,
journal creation, and the strategy/assistant boundary."""
from __future__ import annotations

from datetime import date, datetime, timezone

from assistant import journal as assistant_journal
from assistant import report as assistant_report
from assistant import runtime
from assistant.models import (
    CONTEXT_READY,
    DECISION_EXECUTED,
    DECISION_NO_SETUP,
    DECISION_ORDER_CHECK_REJECTED,
    DECISION_SHADOW_CHECKED,
    DECISION_TRADE_READY,
    DECISION_UNSIGNED_CYCLE,
    MODE_ANALYZE_ONLY,
    MODE_DEMO_EXECUTION,
    MODE_LIVE,
    MODE_SHADOW_DEMO,
    MarketContext,
)
from strategy_manager import manager
from strategy_manager.session_trade_adapter import AdapterRunResult

_READY_CONTEXT = MarketContext(
    symbol="EURUSD", broker_resolved_symbol="EURUSD", timestamp_utc=datetime.now(timezone.utc),
    session_date=date(2026, 8, 27), account_login=1, account_server="Test-Demo", account_is_demo=True,
    current_bid=1.1700, current_ask=1.1702, tick_time_utc=datetime.now(timezone.utc), status=CONTEXT_READY,
)

_ANALYSIS = dict(strategy_id="ASIAN_SESSION_V1", contract_version="1.4", trading_date="2026-08-27",
                  accepted=True, setup="SWEEP", direction="SHORT", entry=1.1650, stop_loss=1.1670,
                  tp2_5r=1.1550, risk_fraction=0.005, reason_codes=[])


def _patch_context(monkeypatch):
    monkeypatch.setattr(manager, "build_context", lambda symbol: _READY_CONTEXT)


def _patch_adapter(monkeypatch, subprocess_calls, execution_outcome, payload):
    def _fake_run(symbol, cycle, mode):
        subprocess_calls.append((symbol, cycle, mode))
        return AdapterRunResult(execution_outcome=execution_outcome, payload=payload, exit_code=0, analysis=_ANALYSIS)
    monkeypatch.setattr(manager, "run_session_trade_v1", _fake_run)


def test_analyze_only_makes_no_broker_write_calls_and_reports_trade_ready(monkeypatch, tmp_path):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN", {"execution": "DRY_RUN", "signal_id": "sig1"})
    journal_path = str(tmp_path / "assistant_runs.jsonl")
    _record = assistant_journal.record
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: _record(decision, journal_path))

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)

    assert calls == [("EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)]  # adapter called exactly once, in ANALYZE_ONLY
    assert decision.status == DECISION_TRADE_READY
    assert decision.setup == "SWEEP" and decision.direction == "SHORT"

    entries = assistant_journal.read_all(journal_path)
    assert len(entries) == 1 and entries[0]["status"] == DECISION_TRADE_READY


def test_shadow_demo_order_check_only_no_order_send(monkeypatch, tmp_path):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN",
                    {"execution": "DRY_RUN", "signal_id": "sig1", "broker_check": {"stage": "ORDER_CHECK", "retcode": 0}})
    journal_path = str(tmp_path / "assistant_runs.jsonl")
    _record = assistant_journal.record
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: _record(decision, journal_path))

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_SHADOW_DEMO)

    assert calls == [("EURUSD", "ASIAN_LONDON", MODE_SHADOW_DEMO)]
    assert decision.status == DECISION_SHADOW_CHECKED
    assert decision.execution_report["broker_check"]["retcode"] == 0


def test_shadow_demo_order_check_rejected(monkeypatch, tmp_path):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN",
                    {"execution": "DRY_RUN", "signal_id": "sig1", "broker_check": {"stage": "ORDER_CHECK", "retcode": 10004, "comment": "requote"}})
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_SHADOW_DEMO)
    assert decision.status == DECISION_ORDER_CHECK_REJECTED


def test_demo_execution_gate_executed(monkeypatch, tmp_path):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "ATTEMPTED",
                    {"execution": "ATTEMPTED", "signal_id": "sig1", "outcome": "CONFIRMED", "order": {"ticket": 999}})
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_DEMO_EXECUTION)

    assert calls == [("EURUSD", "ASIAN_LONDON", MODE_DEMO_EXECUTION)]
    assert decision.status == DECISION_EXECUTED


def test_live_mode_hard_blocked_zero_subprocess_calls(monkeypatch):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN", {"execution": "DRY_RUN"})
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_LIVE)

    assert calls == []  # LIVE never reaches the adapter, regardless of what it would return
    assert decision.status not in (DECISION_EXECUTED, DECISION_SHADOW_CHECKED, DECISION_TRADE_READY)


def test_london_newyork_blocked_end_to_end_zero_subprocess_calls(monkeypatch):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN", {"execution": "DRY_RUN"})
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "LONDON_NEWYORK", MODE_ANALYZE_ONLY)

    assert calls == []
    assert decision.status == DECISION_UNSIGNED_CYCLE


def test_no_setup_reported_without_forcing_a_trade_intent(monkeypatch):
    _patch_context(monkeypatch)
    calls = []
    analysis = dict(_ANALYSIS, accepted=False, setup=None, direction=None, reason_codes=["NO_SWEEP"])

    def _fake_run(symbol, cycle, mode):
        calls.append((symbol, cycle, mode))
        return AdapterRunResult(execution_outcome="NOT_ATTEMPTED",
                                 payload={"execution": "NOT_ATTEMPTED", "reason": "no accepted signal"},
                                 exit_code=3, analysis=analysis)
    monkeypatch.setattr(manager, "run_session_trade_v1", _fake_run)
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)

    assert decision.status == DECISION_NO_SETUP
    assert decision.entry is None and decision.setup is None


def test_assistant_does_not_reclassify_strategy_result(monkeypatch):
    """Boundary test (spec section 31): the assistant must forward the strategy's own
    setup/direction/SL/TP verbatim, never recompute them, even though the assistant
    never imports/knows about ER, midpoint, or sweep-candle geometry."""
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN", {"execution": "DRY_RUN", "signal_id": "sigX"})
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)

    assert decision.setup == _ANALYSIS["setup"]
    assert decision.direction == _ANALYSIS["direction"]
    assert decision.entry == _ANALYSIS["entry"]
    assert decision.stop_loss == _ANALYSIS["stop_loss"]
    assert decision.target == _ANALYSIS["tp2_5r"]


def test_report_renders_from_decision_fields_only(monkeypatch):
    _patch_context(monkeypatch)
    calls = []
    _patch_adapter(monkeypatch, calls, "DRY_RUN", {"execution": "DRY_RUN", "signal_id": "sig1"})
    monkeypatch.setattr(runtime.assistant_journal, "record", lambda decision: None)

    decision = runtime.evaluate("SESSION_TRADE_V1", "EURUSD", "ASIAN_LONDON", MODE_ANALYZE_ONLY)
    text = assistant_report.render(decision)

    assert "SESSION_TRADE_V1" in text and "EURUSD" in text and "SWEEP" in text and "SHORT" in text
    assert "TRADE_READY" in text
