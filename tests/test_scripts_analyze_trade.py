"""Smoke tests for scripts/analyze_trade.py (spec section 34-36): default/--json/
--verbose output shapes for a fixture DayTradingResult and FiveSkillAnalysisResult, MT5
connect() and analyze_by_technique() both stubbed -- no live connection, no network."""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assistant.analysis_models import FiveSkillAnalysisResult
from daytrading.models import (
    AFFINITY_RESOLVED,
    BIAS_BULLISH,
    DayTradingLiquidityAffinityResult,
    DayTradingResult,
    NarrativeBiasResult,
    STATE_WAIT_AFFINITY,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _load_script():
    spec = importlib.util.spec_from_file_location("analyze_trade_cli", REPO_ROOT / "scripts" / "analyze_trade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _daytrading_result():
    narrative = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH,
                                     status="OK", evaluation_time=T0, expected_profile="BULLISH_REVERSAL_DAY",
                                     preferred_direction="LONG", primary_draw="BUY_SIDE")
    affinity = DayTradingLiquidityAffinityResult(symbol="EURUSD", narrative_bias=BIAS_BULLISH, status=AFFINITY_RESOLVED)
    return DayTradingResult(symbol="EURUSD", narrative_bias=narrative, liquidity_affinity=affinity,
                             trade_state=STATE_WAIT_AFFINITY, reasons=("liquidity_affinity not yet evaluated.",))


def _smc_result():
    return FiveSkillAnalysisResult(symbol="EURUSD", timeframe="M15", timestamp_utc=T0,
                                    market_context_status="OK", overall_status="PARTIAL")


def _run(monkeypatch, capsys, module, result, argv):
    monkeypatch.setattr(module, "connect", lambda: None)
    monkeypatch.setattr(module, "analyze_by_technique", lambda *a, **k: result)
    rc = module.main(argv)
    return rc, capsys.readouterr().out


def test_daytrading_default_output(monkeypatch, capsys):
    module = _load_script()
    rc, out = _run(monkeypatch, capsys, module, _daytrading_result(), ["EURUSD", "--technique", "DAYTRADING"])
    assert rc == 0
    assert "AG TRADING ASSISTANT" in out
    assert "BULLISH_REVERSAL_DAY" in out
    assert "WAIT_POI" in out  # canonical mapping of STATE_WAIT_AFFINITY


def test_daytrading_verbose_output(monkeypatch, capsys):
    module = _load_script()
    rc, out = _run(monkeypatch, capsys, module, _daytrading_result(), ["EURUSD", "--technique", "DAYTRADING", "--verbose"])
    assert rc == 0
    assert "--- VERBOSE ---" in out
    assert "trade_state: WAIT_AFFINITY" in out


def test_daytrading_json_output(monkeypatch, capsys):
    module = _load_script()
    rc, out = _run(monkeypatch, capsys, module, _daytrading_result(), ["EURUSD", "--technique", "DAYTRADING", "--json"])
    assert rc == 0
    payload = json.loads(out)
    assert payload["symbol"] == "EURUSD"
    assert payload["trade_state"] == "WAIT_AFFINITY"
    assert payload["narrative_bias"]["expected_profile"] == "BULLISH_REVERSAL_DAY"


def test_smc_default_output(monkeypatch, capsys):
    module = _load_script()
    rc, out = _run(monkeypatch, capsys, module, _smc_result(), ["EURUSD", "--technique", "SMC"])
    assert rc == 0
    assert "AG TRADE ASSISTANT" in out
    assert "WAIT_CONFIRMATION" in out  # canonical mapping of overall_status=PARTIAL
