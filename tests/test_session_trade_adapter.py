"""Tests for strategy_manager.session_trade_adapter: JSON-block extraction from mixed
stdout and analysis.json -> StrategyResult mapping. Pure functions, no subprocess/MT5
needed -- fixtures model the REAL shapes read from execute_session_signal.py."""
from __future__ import annotations

import pytest

from assistant.models import STATUS_INVALID_CONTEXT, STATUS_NO_SETUP, STATUS_TRADE_READY
from strategy_manager.session_trade_adapter import (
    AdapterRunResult,
    OUTCOME_DRY_RUN,
    SessionTradeAdapterError,
    extract_last_json_object,
    to_strategy_result,
)

_MARKDOWN_PREFIX = "# Session Trade Ticket\n\nSome markdown table here.\n| a | b |\n|---|---|\n\n"


def test_extract_last_json_object_after_markdown():
    text = _MARKDOWN_PREFIX + (
        '{\n  "execution": "DRY_RUN",\n  "signal_id": "abc123",\n  "would_submit": {\n    "symbol": "EURUSD"\n  }\n}\n'
    )
    result = extract_last_json_object(text)
    assert result == {"execution": "DRY_RUN", "signal_id": "abc123", "would_submit": {"symbol": "EURUSD"}}


def test_extract_last_json_object_with_nested_broker_check():
    text = (
        '{\n  "execution": "DRY_RUN",\n  "signal_id": "xyz",\n'
        '  "broker_check": {\n    "stage": "ORDER_CHECK",\n    "retcode": 0,\n    "comment": "ok"\n  }\n}\n'
    )
    result = extract_last_json_object(text)
    assert result["broker_check"]["retcode"] == 0


def test_extract_last_json_object_picks_last_of_multiple():
    text = '{"noise": true}\nsome text\n{"execution": "REFUSED", "signal_id": "s1"}\n'
    result = extract_last_json_object(text)
    assert result == {"execution": "REFUSED", "signal_id": "s1"}


def test_extract_last_json_object_returns_none_when_absent():
    assert extract_last_json_object("no json here at all") is None


def _analysis(**overrides) -> dict:
    base = dict(
        strategy_id="ASIAN_SESSION_V1", contract_version="1.4", trading_date="2026-08-27",
        accepted=True, setup="SWEEP", direction="SHORT", entry=1.16500, stop_loss=1.16700,
        tp2_5r=1.15500, risk_fraction=0.005, reason_codes=[],
    )
    base.update(overrides)
    return base


def test_to_strategy_result_trade_ready():
    run_result = AdapterRunResult(
        execution_outcome=OUTCOME_DRY_RUN,
        payload={"execution": "DRY_RUN", "signal_id": "sig123"},
        exit_code=0, analysis=_analysis(),
    )
    result = to_strategy_result(run_result, "EURUSD", "ASIAN_LONDON")
    assert result.status == STATUS_TRADE_READY
    assert result.setup == "SWEEP" and result.direction == "SHORT"
    assert result.entry == 1.16500 and result.stop_loss == 1.16700 and result.target == 1.15500
    assert result.risk_percent == 0.5
    assert result.signal_id == "sig123"


def test_to_strategy_result_no_setup():
    run_result = AdapterRunResult(
        execution_outcome="NOT_ATTEMPTED",
        payload={"execution": "NOT_ATTEMPTED", "reason": "no accepted signal"},
        exit_code=3, analysis=_analysis(accepted=False, setup=None, direction=None, reason_codes=["NO_SWEEP"]),
    )
    result = to_strategy_result(run_result, "EURUSD", "ASIAN_LONDON")
    assert result.status == STATUS_NO_SETUP
    assert result.reason_codes == ("NO_SWEEP",)


def test_to_strategy_result_invalid_context_on_error():
    run_result = AdapterRunResult(
        execution_outcome="ERROR",
        payload={"error": "connected account is 'real', not demo; refusing"},
        exit_code=1, analysis={},
    )
    result = to_strategy_result(run_result, "EURUSD", "ASIAN_LONDON")
    assert result.status == STATUS_INVALID_CONTEXT


def test_to_strategy_result_missing_analysis_fails_closed():
    run_result = AdapterRunResult(
        execution_outcome=OUTCOME_DRY_RUN,
        payload={"execution": "DRY_RUN", "signal_id": "sig123"},
        exit_code=0,
        analysis=None,
    )

    with pytest.raises(SessionTradeAdapterError, match="ANALYSIS_MISSING"):
        to_strategy_result(run_result, "EURUSD", "ASIAN_LONDON")


def test_to_strategy_result_malformed_analysis_fails_closed():
    run_result = AdapterRunResult(
        execution_outcome=OUTCOME_DRY_RUN,
        payload={"execution": "DRY_RUN", "signal_id": "sig123"},
        exit_code=0,
        analysis=["not", "an", "object"],
    )

    with pytest.raises(SessionTradeAdapterError, match="ANALYSIS_INVALID"):
        to_strategy_result(run_result, "EURUSD", "ASIAN_LONDON")
