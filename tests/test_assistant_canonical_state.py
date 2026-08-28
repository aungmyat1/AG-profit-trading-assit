"""One case per canonical top-level state (spec section 22) mapped from each existing
detailed DayTradingResult.trade_state / FiveSkillAnalysisResult.overall_status."""
from __future__ import annotations

from assistant.canonical_state import (
    INVALIDATED,
    NO_CONTEXT,
    NO_TRADE,
    RISK_CHECK,
    TRADE_PROPOSAL_READY,
    UNRESOLVED,
    WAIT_CONFIRMATION,
    WAIT_POI,
    daytrading_canonical_state,
    smc_canonical_state,
)
from assistant.analysis_models import FiveSkillAnalysisResult
from daytrading.models import (
    BIAS_BULLISH,
    BIAS_UNRESOLVED,
    DayTradingResult,
    NarrativeBiasResult,
    STATE_INVALIDATED,
    STATE_NO_TRADE,
    STATE_TRADE_READY_LONG,
    STATE_TRADE_READY_SHORT,
    STATE_WAIT_AFFINITY,
    STATE_WAIT_LTF_EXECUTION,
    STATE_WAIT_NARRATIVE,
    STATE_WAIT_RISK,
)
from datetime import datetime, timezone

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def _narrative(bias=BIAS_BULLISH):
    return NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=bias, status="OK")


def _result(trade_state, bias=BIAS_BULLISH):
    return DayTradingResult(symbol="EURUSD", narrative_bias=_narrative(bias), trade_state=trade_state)


def test_unresolved_narrative_maps_to_no_context():
    assert daytrading_canonical_state(_result(STATE_WAIT_NARRATIVE, bias=BIAS_UNRESOLVED)) == NO_CONTEXT
    assert daytrading_canonical_state(_result(STATE_NO_TRADE, bias=BIAS_UNRESOLVED)) == NO_CONTEXT


def test_wait_affinity_maps_to_wait_poi():
    assert daytrading_canonical_state(_result(STATE_WAIT_AFFINITY)) == WAIT_POI


def test_wait_ltf_execution_maps_to_wait_confirmation():
    assert daytrading_canonical_state(_result(STATE_WAIT_LTF_EXECUTION)) == WAIT_CONFIRMATION


def test_wait_risk_maps_to_risk_check():
    assert daytrading_canonical_state(_result(STATE_WAIT_RISK)) == RISK_CHECK


def test_trade_ready_maps_to_trade_proposal_ready():
    assert daytrading_canonical_state(_result(STATE_TRADE_READY_LONG)) == TRADE_PROPOSAL_READY
    assert daytrading_canonical_state(_result(STATE_TRADE_READY_SHORT)) == TRADE_PROPOSAL_READY


def test_no_trade_maps_to_no_trade():
    assert daytrading_canonical_state(_result(STATE_NO_TRADE)) == NO_TRADE


def test_invalidated_maps_to_invalidated():
    assert daytrading_canonical_state(_result(STATE_INVALIDATED)) == INVALIDATED


def test_smc_overall_status_mapping():
    def _smc(overall_status):
        return FiveSkillAnalysisResult(symbol="EURUSD", timeframe="M15", timestamp_utc=T0,
                                        market_context_status="OK", overall_status=overall_status)

    assert smc_canonical_state(_smc("READY")) == TRADE_PROPOSAL_READY
    assert smc_canonical_state(_smc("PARTIAL")) == WAIT_CONFIRMATION
    assert smc_canonical_state(_smc("BLOCKED")) == NO_CONTEXT
    assert smc_canonical_state(_smc("SOMETHING_UNKNOWN")) == UNRESOLVED
