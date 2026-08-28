"""Focused tests for DAYTRADING_LTF_EXECUTION_RUNTIME_V1 pipeline wiring: does
evaluate_daytrading() thread the canonical H1 protected level, M5 CLOSED candles, and
canonical M5 gap bounds into evaluate_ltf_execution() -- without re-deriving any of them
from M5 structure or inventing a synthetic value. Narrative Bias / Liquidity Affinity's
own logic is already covered by tests/test_narrative_bias.py and
tests/test_daytrading_liquidity_affinity.py -- here they are stubbed to isolate the LTF
wiring itself (spec section 20: avoid redundant lower-level coverage)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import daytrading.pipeline as pipeline
from daytrading.models import (
    AFFINITY_RESOLVED,
    BIAS_BULLISH,
    DayTradingLiquidityAffinityResult,
    LTF_WAITING,
    LTFExecutionResult,
    NarrativeBiasResult,
)
from entry_confirmation import CandidateDirection
from market_structure.models import STATE_BULLISH, StructurePoint, StructurePointKind, StructureTier, TieredStructureResult
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneQueryResult, ZoneResult, ZoneStatus

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
SYMBOL = "EURUSD"

PROTECTED_HIGH = 1.2000
PROTECTED_LOW = 1.1500
GAP_LOW = 1.1000
GAP_HIGH = 1.1010


def _m5_candles(count=21):
    return [Candle(time=T0 + timedelta(minutes=5 * i), open=1.15, high=1.1505, low=1.1495, close=1.1502)
            for i in range(count)]


def _patch_common(monkeypatch, m5_candles):
    narrative = NarrativeBiasResult(symbol=SYMBOL, reference_timeframe="D1", bias=BIAS_BULLISH,
                                     status="OK", evaluation_time=T0)
    affinity = DayTradingLiquidityAffinityResult(symbol=SYMBOL, narrative_bias=BIAS_BULLISH, status=AFFINITY_RESOLVED)

    monkeypatch.setattr(pipeline, "evaluate_narrative_bias", lambda *a, **k: narrative)
    monkeypatch.setattr(pipeline, "evaluate_liquidity_affinity", lambda *a, **k: affinity)

    ltf_mock = MagicMock(return_value=LTFExecutionResult(symbol=SYMBOL, execution_timeframe="M5", status=LTF_WAITING))
    monkeypatch.setattr(pipeline, "evaluate_ltf_execution", ltf_mock)

    # --- D1/H1 fetch stage (upstream of the now-stubbed narrative_bias -- return values are
    # never inspected by the stub, only need to not raise). ---
    import market_structure
    import liquidity
    import supply_demand
    import daytrading.true_day as true_day_mod
    import mt5.market_data as market_data_mod
    import market_structure.tiers as tiers_mod
    import liquidity.hierarchy as hierarchy_mod

    monkeypatch.setattr(market_structure, "analyze_structure", lambda *a, **k: MagicMock(status="VALID"))
    monkeypatch.setattr(liquidity, "liquidity_result", lambda *a, **k: MagicMock(status="LIQUIDITY_OK"))
    monkeypatch.setattr(supply_demand, "premium_discount_from_previous_day", lambda *a, **k: None)
    monkeypatch.setattr(true_day_mod, "true_day_window", lambda t: MagicMock(day_start_utc=t - timedelta(hours=1)))
    monkeypatch.setattr(market_data_mod, "get_candles", lambda *a, **k: ())

    h1_external = StructureTier(
        tier="EXTERNAL", swing_length=50, direction=STATE_BULLISH, swings=(), events=(),
        latest_swing_high=StructurePoint(time_utc=T0, price=PROTECTED_HIGH, kind=StructurePointKind.SWING_HIGH),
        latest_swing_low=StructurePoint(time_utc=T0, price=PROTECTED_LOW, kind=StructurePointKind.SWING_LOW),
    )
    h1_tiers = TieredStructureResult(symbol=SYMBOL, timeframe="H1", status="VALID", reason_codes=(), external=h1_external)
    monkeypatch.setattr(tiers_mod, "analyze_structure_tiers", lambda *a, **k: h1_tiers)
    monkeypatch.setattr(hierarchy_mod, "external_swing_liquidity", lambda *a, **k: ())
    monkeypatch.setattr(hierarchy_mod, "scope_liquidity_levels", lambda *a, **k: ())
    monkeypatch.setattr(market_data_mod, "get_tick", lambda *a, **k: MagicMock(bid=1.1502))

    m5_fvg = ZoneQueryResult(
        symbol=SYMBOL, timeframe="M5", family=ZoneFamily.FVG, status="OK",
        zones=(ZoneResult(symbol=SYMBOL, timeframe="M5", family=ZoneFamily.FVG, role="REFERENCE",
                           direction=ZoneDirection.BULLISH, status=ZoneStatus.FRESH, source="smc.fvg",
                           low=GAP_LOW, high=GAP_HIGH, origin_time=T0),),
    )

    def _fvg_side_effect(symbol, timeframe, *a, **k):
        return m5_fvg if timeframe == "M5" else ZoneQueryResult(symbol=symbol, timeframe=timeframe, family=ZoneFamily.FVG, status="OK")

    monkeypatch.setattr(supply_demand, "fair_value_gaps_for", _fvg_side_effect)

    monkeypatch.setattr(market_structure, "analyze_structure", lambda *a, **k: MagicMock(status="VALID"))
    monkeypatch.setattr(market_data_mod, "get_latest_candles", lambda *a, **k: list(m5_candles))

    return ltf_mock


def test_pipeline_threads_protected_level_and_h1_structure_direction(monkeypatch):
    m5_candles = _m5_candles()
    ltf_mock = _patch_common(monkeypatch, m5_candles)

    pipeline.evaluate_daytrading(SYMBOL, candidate_direction=CandidateDirection.LONG)

    _, kwargs = ltf_mock.call_args
    assert kwargs["protected_high"] == PROTECTED_HIGH
    assert kwargs["protected_low"] == PROTECTED_LOW
    assert kwargs["h1_structure_direction"] == STATE_BULLISH


def test_pipeline_threads_closed_m5_candles_only(monkeypatch):
    m5_candles = _m5_candles()
    ltf_mock = _patch_common(monkeypatch, m5_candles)

    pipeline.evaluate_daytrading(SYMBOL, candidate_direction=CandidateDirection.LONG)

    _, kwargs = ltf_mock.call_args
    threaded = kwargs["m5_closed_candles"]
    assert list(threaded) == m5_candles  # exactly the CLOSED bars get_latest_candles() returned, nothing more
    assert kwargs.get("m5_forming_candle") is None  # never fabricated -- no forming-bar API used


def test_pipeline_threads_gap_bounds_matching_candidate_direction(monkeypatch):
    m5_candles = _m5_candles()
    ltf_mock = _patch_common(monkeypatch, m5_candles)

    pipeline.evaluate_daytrading(SYMBOL, candidate_direction=CandidateDirection.LONG)

    _, kwargs = ltf_mock.call_args
    assert kwargs["gap_low"] == GAP_LOW
    assert kwargs["gap_high"] == GAP_HIGH


def test_pipeline_protected_level_not_replaced_by_m5_structure(monkeypatch):
    """structure_m5 (analyze_structure(symbol, 'M5')) is a MagicMock with arbitrary
    attributes; protected_high/protected_low must come ONLY from the H1 EXTERNAL tier,
    never from whatever attribute access on the M5 structure mock happens to return."""
    m5_candles = _m5_candles()
    ltf_mock = _patch_common(monkeypatch, m5_candles)

    pipeline.evaluate_daytrading(SYMBOL, candidate_direction=CandidateDirection.LONG)

    _, kwargs = ltf_mock.call_args
    assert kwargs["protected_high"] == PROTECTED_HIGH
    assert kwargs["protected_low"] == PROTECTED_LOW


def test_ltf_execution_module_has_no_broker_or_risk_coupling():
    import inspect

    import daytrading.execution_models as execution_models
    import daytrading.ltf_execution as ltf_execution

    source = inspect.getsource(ltf_execution) + inspect.getsource(execution_models)
    for forbidden in ("order_send", "order_check", "account_equity", "lot_size", "position_size", "MetaTrader5"):
        assert forbidden not in source, f"{forbidden!r} must not appear in the LTF execution layer."
