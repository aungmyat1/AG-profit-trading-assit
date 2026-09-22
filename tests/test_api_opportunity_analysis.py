from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from api import app as api_app
from api.opportunity_analysis import OpportunityAnalysisError, get_opportunity_analysis


NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _pilot():
    return SimpleNamespace(universe=("EURUSD",), strategy_id="ST_ASIAN_SWEEP_5R_V1")


def _result(status="WATCH", *, expired=False):
    decision = SimpleNamespace(
        status=status,
        strategy_id="ST_ASIAN_SWEEP_5R_V1",
        symbol="EURUSD",
        evaluation_time=NOW,
        reason_codes=("WAITING_REFERENCE_SWEEP",),
        missing_condition="WAITING_CLOSED_M15_CONFIRMATION" if status == "WATCH" else None,
        signal=None,
        valid_until=NOW if expired else None,
    )
    pair = SimpleNamespace(
        symbol="EURUSD", decision=decision,
        portfolio_state="ELIGIBLE", portfolio_reason_code=None,
        proposal=None, market_snapshot=None,
    )
    return SimpleNamespace(strategy=SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1"),
                           evaluation_time=NOW, pairs=(pair,))


def test_watch_mapping_and_explicit_observe_only(monkeypatch):
    calls = []
    monkeypatch.setattr("api.opportunity_analysis.load_pilot_config", lambda _=None: _pilot())
    monkeypatch.setattr("api.opportunity_analysis.run_pilot_cycle",
                        lambda *args, **kwargs: (calls.append(kwargs) or _result()))
    response = get_opportunity_analysis(symbol="EURUSD")
    assert response[0].decision_state == "WATCH"
    assert response[0].proposal_state == "NONE"
    assert response[0].execution_authority == "NONE"
    assert response[0].missing_condition == "WAITING_CLOSED_M15_CONFIRMATION"
    assert calls == [{"observe_only": True}]


def test_ready_mapping_expired_mapping_and_stable_serialization(monkeypatch):
    trade = SimpleNamespace(entry=1.1, stop_loss=1.09, tp1=1.11, tp2=1.15)
    decision = SimpleNamespace(status="READY", strategy_id="ST_ASIAN_SWEEP_5R_V1",
                              symbol="EURUSD", evaluation_time=NOW,
                              reason_codes=("SWEEP_REFERENCE_LOW",), missing_condition=None,
                              signal=SimpleNamespace(direction="LONG"), valid_until=None)
    proposal = SimpleNamespace(trade_proposal=trade, expires_at=NOW + timedelta(minutes=1), actionable=True)
    pair = SimpleNamespace(symbol="EURUSD", decision=decision, portfolio_state="SELECTED",
                           portfolio_reason_code=None, proposal=proposal, market_snapshot=None)
    result = SimpleNamespace(strategy=SimpleNamespace(strategy_id="ST_ASIAN_SWEEP_5R_V1"),
                             evaluation_time=NOW, pairs=(pair,))
    monkeypatch.setattr("api.opportunity_analysis.load_pilot_config", lambda _=None: _pilot())
    monkeypatch.setattr("api.opportunity_analysis.run_pilot_cycle", lambda *a, **k: result)
    response = get_opportunity_analysis("EURUSD")[0]
    assert response.decision_state == "READY"
    assert response.proposal_state == "PROPOSAL_READY"
    assert response.direction == "LONG"
    assert response.targets == [1.11, 1.15]
    assert response.is_stale is False
    assert response.model_dump() == get_opportunity_analysis("EURUSD")[0].model_dump()
    proposal.expires_at = NOW - timedelta(minutes=1)
    expired = get_opportunity_analysis("EURUSD")[0]
    assert expired.is_stale is True
    assert expired.proposal_state == "EXPIRED"


def test_unsupported_symbol_fails_closed(monkeypatch):
    monkeypatch.setattr("api.opportunity_analysis.load_pilot_config", lambda _=None: _pilot())
    with pytest.raises(OpportunityAnalysisError, match="UNSUPPORTED_SYMBOL"):
        get_opportunity_analysis("GBPUSD")


def test_api_route_never_calls_preflight_and_preserves_structured_error(monkeypatch):
    monkeypatch.setattr(api_app, "get_opportunity_analysis",
                        lambda **kwargs: (_ for _ in ()).throw(OpportunityAnalysisError("EVALUATION_ERROR:RuntimeError")))
    with pytest.raises(Exception) as exc_info:
        api_app.opportunity_analysis("EURUSD")
    assert exc_info.value.status_code == 502
    assert "EVALUATION_ERROR" in str(exc_info.value.detail)


def test_read_model_has_no_execution_imports():
    source = open("src/api/opportunity_analysis.py", encoding="utf-8").read()
    assert "execution.executor" not in source
    assert "mt5_gateway" not in source
    assert "preflight" not in source
