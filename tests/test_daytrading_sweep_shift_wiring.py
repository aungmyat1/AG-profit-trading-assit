"""Focused tests for AG_TRADING_ASSISTANT_WORKFLOW_V1's sweep-shift-array corroboration
wiring (spec section 16): entry_confirmation.engine_v2_1's SMCSweepShiftArrayResult is
optional corroborating evidence over daytrading.ltf_execution's own v1-based decision --
never a second independent confirmation engine, never able to upgrade a NOT_CONFIRMED/
WAITING result to CONFIRMED on its own, and a no-op when the caller supplies no
`sweep_shift_request` (regression pin for the pre-existing 30 tests in
test_daytrading_ltf_execution_models.py / test_daytrading_pipeline_ltf_wiring.py)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import daytrading.ltf_execution as ltf_execution
import daytrading.pipeline as pipeline
from daytrading.ltf_execution import evaluate_ltf_execution
from daytrading.models import (
    AFFINITY_RESOLVED,
    BIAS_BULLISH,
    DayTradingLiquidityAffinityResult,
    LTF_CONFIRMED,
    LTF_NOT_CONFIRMED,
    NarrativeBiasResult,
)
from entry_confirmation import CandidateDirection
from entry_confirmation.models import (
    ConfirmationState,
    DisplacementEvidence,
    EntryConfirmationResult,
    EventSequenceEvidence,
    LiquidityAlignment,
    OverallState,
    RejectionEvidence,
    StructureAlignment,
)
from entry_confirmation.models_v2_1 import SMCSweepShiftArrayResult
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
SYMBOL = "EURUSD"


def _narrative():
    return NarrativeBiasResult(symbol=SYMBOL, reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")


def _affinity():
    return DayTradingLiquidityAffinityResult(symbol=SYMBOL, narrative_bias=BIAS_BULLISH, status=AFFINITY_RESOLVED)


def _confirmed_ec_result() -> EntryConfirmationResult:
    return EntryConfirmationResult(
        symbol=SYMBOL, timeframe="M5", candidate_direction="LONG", status="EVALUATED",
        displacement=DisplacementEvidence(status=ConfirmationState.PASS, direction="BULLISH"),
        structure_shift=StructureAlignment(status=ConfirmationState.PASS, event_kind="BULLISH_CHOCH"),
        liquidity_reclaim=LiquidityAlignment(status=ConfirmationState.PASS),
        rejection=RejectionEvidence(status=ConfirmationState.NOT_REQUESTED),
        event_sequence=EventSequenceEvidence(status=ConfirmationState.PASS),
        overall_state=OverallState.CONFIRMED,
    )


def _call_ltf(monkeypatch, sweep_shift_request, sweep_shift_result_status):
    monkeypatch.setattr(ltf_execution, "evaluate_entry_confirmation", lambda req: _confirmed_ec_result())
    if sweep_shift_result_status is not None:
        monkeypatch.setattr(
            ltf_execution, "evaluate_sweep_shift_array",
            lambda req: SMCSweepShiftArrayResult(symbol=SYMBOL, timeframe="M5", aggregation_status=sweep_shift_result_status,
                                                  status="ENTRY_REFERENCE_AVAILABLE" if sweep_shift_result_status == "CONFIRMED" else "NOT_CONFIRMED"),
        )
    return evaluate_ltf_execution(
        SYMBOL, "M5", _narrative(), _affinity(), CandidateDirection.LONG, ec_request=object(),
        sweep_shift_request=sweep_shift_request,
    )


def test_no_sweep_shift_request_leaves_v1_decision_unchanged(monkeypatch):
    result = _call_ltf(monkeypatch, sweep_shift_request=None, sweep_shift_result_status=None)
    assert result.status == LTF_CONFIRMED
    assert result.sweep_shift_result is None


def test_confirmed_corroboration_leaves_confirmed(monkeypatch):
    result = _call_ltf(monkeypatch, sweep_shift_request=object(), sweep_shift_result_status="CONFIRMED")
    assert result.status == LTF_CONFIRMED
    assert result.sweep_shift_result is not None
    assert result.sweep_shift_result.aggregation_status == "CONFIRMED"


def test_disagreeing_corroboration_demotes_to_not_confirmed(monkeypatch):
    result = _call_ltf(monkeypatch, sweep_shift_request=object(), sweep_shift_result_status="NOT_CONFIRMED")
    assert result.status == LTF_NOT_CONFIRMED
    assert "sweep_shift_result disagreed" in result.reason


def test_partial_corroboration_does_not_change_v1_status(monkeypatch):
    result = _call_ltf(monkeypatch, sweep_shift_request=object(), sweep_shift_result_status="PARTIAL")
    assert result.status == LTF_CONFIRMED
    assert result.sweep_shift_result.aggregation_status == "PARTIAL"


def test_pipeline_builds_sweep_shift_request_when_swept_level_exists(monkeypatch):
    from test_daytrading_pipeline_ltf_wiring import _m5_candles, _patch_common

    m5_candles = _m5_candles()
    ltf_mock = _patch_common(monkeypatch, m5_candles)
    # _patch_common's structure_m5/liquidity_m5 stubs are bare MagicMocks -- fine for the
    # kwargs it asserts on, but real evaluate_entry_confirmation() would raise on them.
    # This test isolates _build_sweep_shift_request()'s own evidence-assembly logic, so
    # entry_confirmation's engine is stubbed out the same way the rest of the fixture is.
    monkeypatch.setattr(pipeline, "evaluate_entry_confirmation", lambda req: _confirmed_ec_result())

    import liquidity as liquidity_mod

    swept_level = LiquidityLevel(
        symbol=SYMBOL, timeframe="H1", side=LiquiditySide.SELL_SIDE, source="SWING_LOW",
        price=1.1490, origin_time=T0, status=LiquidityStatus.RECLAIMED, sweep_time=T0,
    )
    monkeypatch.setattr(liquidity_mod, "liquidity_result", lambda *a, **k: MagicMock(status="LIQUIDITY_OK", levels=(swept_level,)))

    pipeline.evaluate_daytrading(SYMBOL, candidate_direction=CandidateDirection.LONG)

    _, kwargs = ltf_mock.call_args
    assert kwargs["sweep_shift_request"] is not None
    assert kwargs["sweep_shift_request"].sweep_level is swept_level


def test_pipeline_passes_none_when_no_swept_level(monkeypatch):
    from test_daytrading_pipeline_ltf_wiring import _m5_candles, _patch_common

    m5_candles = _m5_candles()
    ltf_mock = _patch_common(monkeypatch, m5_candles)
    # _patch_common's default liquidity.liquidity_result mock has no real `.levels`
    # iterable -- exercises the fail-closed except-branch in evaluate_daytrading.

    pipeline.evaluate_daytrading(SYMBOL, candidate_direction=CandidateDirection.LONG)

    _, kwargs = ltf_mock.call_args
    assert kwargs["sweep_shift_request"] is None
