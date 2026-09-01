from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from entry_confirmation.e3_liquidity_sweep import evaluate_e3_htf_liquidity_sweep
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from strategy_engine.semantic_guard import (
    EvidenceAuthority,
    REJECT_AUTHORITY_LEAKAGE,
    REJECT_FUTURE_EVIDENCE,
    REJECT_RETROSPECTIVE_QUALIFICATION,
    REJECT_TIMEFRAME_LEAKAGE,
    SemanticEvidence,
    validate_semantic_evidence,
)
from strategy_engine.session import Candle, ReferenceBox
from strategy_engine.session.setups import entry_2_sweep


ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
NOW = datetime(2026, 1, 5, 7, 0, tzinfo=UTC)


def test_both_strategy_contracts_enable_same_guard_version():
    for name in ("ST_ASIAN_SWEEP_5R_V1.yaml", "ST_LARGE_SMC_V1.yaml"):
        raw = yaml.safe_load((ROOT / "strategies" / name).read_text(encoding="utf-8"))
        guard = raw["semantic_safety_contract"]
        assert guard["version"] == "SMC_TRAP_GUARD_V1"
        assert guard["authority_boundary"] == "STRATEGY_ENGINE_ONLY"
        assert guard["invariants"]["liquidity_event_is_not_trade_signal"] is True


def test_observation_cannot_claim_trade_direction():
    evidence = SemanticEvidence("LIQUIDITY_SWEEP", EvidenceAuthority.OBSERVATION, NOW, NOW,
                                timeframe="M5", claims_trade_decision=True)
    assert validate_semantic_evidence(evidence) == (REJECT_AUTHORITY_LEAKAGE,)


def test_future_and_retrospective_evidence_fail_closed():
    evidence = SemanticEvidence("INDUCEMENT", EvidenceAuthority.CONTEXT, NOW + timedelta(minutes=5), NOW,
                                timeframe="M5", creates_past_qualification=True)
    assert validate_semantic_evidence(evidence) == (
        REJECT_FUTURE_EVIDENCE, REJECT_RETROSPECTIVE_QUALIFICATION,
    )


def test_m5_internal_event_cannot_override_h1_context():
    evidence = SemanticEvidence("INTERNAL_CHOCH", EvidenceAuthority.CONFIRMATION, NOW, NOW,
                                timeframe="M5", overrides_timeframe="H1")
    assert validate_semantic_evidence(evidence) == (REJECT_TIMEFRAME_LEAKAGE,)


def test_asian_penetration_without_reclaim_is_not_a_sweep_signal():
    box = ReferenceBox(
        session_name="Asian", session_open=1.1000, session_high=1.1050,
        session_low=1.0950, session_close=1.1000, session_range=0.0100,
        session_mid=1.1000, path_length=0.0100, displacement=0.0,
        efficiency_ratio=0.0, bar_count=24, expected_bar_count=24,
        session_complete=True,
    )
    outside_close = Candle(NOW, 1.1040, 1.1060, 1.1030, 1.1055)
    decision = entry_2_sweep("ST_ASIAN_SWEEP_5R_V1", "EURUSD", box, NOW.date(), [outside_close])
    assert decision.reason_code == "NO_QUALIFIED_SWEEP_IN_WINDOW"
    assert decision.direction is None


def test_large_smc_e3_sweep_without_reclaim_is_not_eligible():
    level = LiquidityLevel(
        symbol="EURUSD", timeframe="H1", side=LiquiditySide.BUY_SIDE,
        source="EXTERNAL_SWING_HIGH", price=1.1050, origin_time=NOW - timedelta(hours=2),
        status=LiquidityStatus.CONSUMED, sweep_time=NOW - timedelta(minutes=5),
    )
    result = evaluate_e3_htf_liquidity_sweep("EURUSD", level)
    assert result.sweep is True
    assert result.reclaim is False
    assert result.eligible_for_confirmation is False
