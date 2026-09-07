"""ST_LARGE_SMC_V1 research-only engine (large_smc_research/engine.py).

Two layers of test:
  - `_evaluate_combination`/`_evaluate_event` exercised directly with hand-built
    QualifiedEEvent/SMCConditionalEntryAnalysis fixtures (the same construction
    pattern tests/test_candidate_occurrence_identity.py already uses) -- no MT5, no
    historical_data_context, for every decision-state branch that needs no I/O.
  - `evaluate()` exercised end to end with `historical_replay.stage2.
    evaluate_entry_stage_canonical_v2` and the target-model data calls monkeypatched,
    for the symbol-universe guard, DATA_ERROR propagation, and the C18
    multi-combination/occurrence-identity behavior.

Never touches real MT5 or a real historical dataset -- fully offline.
"""
from __future__ import annotations

import datetime as dt

import pytest

import large_smc_research.engine as engine_module
from entry_confirmation.composer import compose
from entry_confirmation.entry_models_v1 import EConditionResult, EntryModelState, SMCConditionalEntryAnalysis
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result
from historical_replay.stage1 import DirectionalLiquidityTimeline, QualifiedEEvent, Stage1Dataset
from large_smc_research.c10_stop_policy import ATR_PERIOD, MIN_BUFFER_PIPS, PIP_SIZE_EURUSD
from large_smc_research.decision import (
    REASON_C10_STOP_MISSING_DATA,
    REASON_REJECT_NO_TARGET,
    REASON_SYMBOL_NOT_IN_FROZEN_UNIVERSE,
    LargeSMCDecisionState,
)
from large_smc_research.engine import STRATEGY_VERSION, LargeSMCResearchEngine
from large_smc_research.target_model import TargetSelection
from market_structure.models import StructurePoint, StructurePointKind, StructureTier
from mt5.market_data import MarketDataError

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_EMPTY_TIMELINE = DirectionalLiquidityTimeline(buy=(), sell=())


def _event(entry_condition="E1", direction="SHORT", intervals=((T0, T0 + dt.timedelta(hours=8)),),
           symbol="EURUSD", reference_key="GAP|1.17|1.18|None"):
    return QualifiedEEvent(
        event_id=f"QE-{symbol}-{entry_condition}-abcd", producer_version="TEST", symbol=symbol,
        entry_condition=entry_condition, direction=direction, qualification_time=intervals[0][0],
        reference_type="GAP", reference_low=1.17, reference_high=1.18, reference_level=None,
        reference_key=reference_key, eligibility_intervals=intervals,
    )


def _m1(state, direction="SHORT", entry_price=1.1000, source_id="M1-src", invalidation_price=None):
    return M1Result(symbol="EURUSD", entry_condition="E1", direction=direction, state=state,
                     entry_array_type="FVG" if entry_price is not None else "NONE",
                     entry_array_low=entry_price - 0.001 if entry_price is not None else None,
                     entry_array_high=entry_price + 0.001 if entry_price is not None else None,
                     source_id=source_id, invalidation_price=invalidation_price)


def _analysis_with_combo(m_state, direction="SHORT", entry_price=1.1000, invalidation_price=None):
    e_condition = EConditionResult(symbol="EURUSD", entry_condition="E1", direction=direction,
                                    eligible_for_confirmation=True, reference_type="GAP",
                                    reference_low=1.17, reference_high=1.18)
    m1 = _m1(m_state, direction=direction, entry_price=entry_price, invalidation_price=invalidation_price)
    combo = compose(e_condition, m1)
    assert combo is not None, f"fixture combo did not compose for state={m_state}"
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=T0, e_conditions={"E1": e_condition}, m_maneuvers={"M1": (m1,)},
        combinations=(combo,),
    ), combo


# --------------------------------------------------------------------------- decision-state mapping (no I/O)


def test_watch_for_waiting_state():
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.WAITING_M5_CONFIRMATION.value)
    event = _event()
    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.WATCH.value
    assert decision.strategy_version == STRATEGY_VERSION
    assert decision.simulated_broker_stop is None
    assert decision.pending_entry_expiry is None


def test_invalidated_passthrough():
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.INVALIDATED.value)
    event = _event()
    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.INVALIDATED.value


def test_entry_geometry_absent_at_ready_is_blocked_not_fabricated():
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=None)
    event = _event()
    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.BLOCKED.value
    assert "ENTRY_GEOMETRY_ABSENT" in decision.reason_codes


def test_expired_via_half_open_interval_boundary():
    engine = LargeSMCResearchEngine()
    end = T0 + dt.timedelta(hours=8)
    event = _event(intervals=((T0, end),))
    decisions = engine._evaluate_event("EURUSD", end, event, _EMPTY_TIMELINE)  # exactly at end -- not eligible
    assert len(decisions) == 1
    assert decisions[0].state == LargeSMCDecisionState.EXPIRED.value
    assert decisions[0].e_context_eligibility_end == end


def test_no_decision_before_first_eligibility_interval_starts():
    engine = LargeSMCResearchEngine()
    start = T0 + dt.timedelta(hours=1)
    event = _event(intervals=((start, start + dt.timedelta(hours=8)),))
    decisions = engine._evaluate_event("EURUSD", T0, event, _EMPTY_TIMELINE)  # before the interval even opens
    assert decisions == ()


def test_occurrence_id_stable_and_identity_fields_populated():
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.WAITING_M5_CONFIRMATION.value)
    event = _event()
    d1 = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    d2 = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert d1.candidate_occurrence_id is not None
    assert d1.candidate_occurrence_id == d2.candidate_occurrence_id
    assert d1.setup_family_id is not None
    assert d1.eligibility_interval_id is not None


def test_occurrence_id_differs_across_disjoint_intervals():
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.WAITING_M5_CONFIRMATION.value)
    event = _event()
    d1 = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    later_start = T0 + dt.timedelta(days=1)
    d2 = engine._evaluate_combination("EURUSD", later_start, event, combo, analysis, later_start, later_start + dt.timedelta(hours=8))
    assert d1.candidate_occurrence_id != d2.candidate_occurrence_id
    assert d1.setup_family_id == d2.setup_family_id  # same setup family, different occurrence


# --------------------------------------------------------------------------- READY branch: target found -> C10 (now signed)


def _flat_m5_candles(n=ATR_PERIOD + 1, price=1.1000):
    """Zero-true-range M5 candles for ATR14 -- deterministic, ATR == 0.0, so the
    1.5-pip floor always governs the buffer in these engine-level tests (the ATR
    formula itself is exercised in tests/test_c10_stop_policy.py)."""
    return [
        type("Candle", (), {
            "time": T0 - dt.timedelta(minutes=5 * (n - i)), "open": price, "high": price, "low": price, "close": price,
        })()
        for i in range(n)
    ]


def test_ready_with_target_found_and_valid_tick_is_research_qualified(monkeypatch):
    """C10 is now signed (c10_stop_policy.py, AG_LARGE_SMC_V1_C10_STRUCTURAL_
    INVALIDATION_IMPLEMENTATION_AND_PROMOTION_V3): a READY SHORT combination with a
    found target, sufficient closed M5 history for ATR14, and an available bid/ask
    reaches RESEARCH_QUALIFIED with a real simulated_broker_stop, not BLOCKED."""
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000, invalidation_price=1.1050)
    event = _event()

    bid, ask = 1.09990, 1.10010
    monkeypatch.setattr(engine_module, "select_target",
                         lambda *a, **k: TargetSelection(found=True, target_price=1.1200,
                                                          target_tier="PRIMARY_EXTERNAL_LIQUIDITY"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: _flat_m5_candles())
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: type("Tick", (), {"bid": bid, "ask": ask})())
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.RESEARCH_QUALIFIED.value
    assert decision.reason_codes == ()
    assert decision.simulated_broker_stop is not None
    floor_price = MIN_BUFFER_PIPS * PIP_SIZE_EURUSD  # ATR == 0 with flat candles -> floor governs
    spread = ask - bid
    assert combo.direction == "SHORT"
    expected_stop = combo.invalidation_price + floor_price + spread
    assert decision.simulated_broker_stop == pytest.approx(expected_stop)
    assert decision.target_price == 1.1200


def test_ready_missing_atr_history_is_blocked_not_data_error(monkeypatch):
    """C10-A requires closed M5 history for ATR14; insufficient history must fail
    closed to BLOCKED (a C10-specific governance failure), distinct from DATA_ERROR
    (which is reserved for genuine market-data-fetch exceptions)."""
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000, invalidation_price=1.1050)
    event = _event()

    monkeypatch.setattr(engine_module, "select_target",
                         lambda *a, **k: TargetSelection(found=True, target_price=1.1200,
                                                          target_tier="PRIMARY_EXTERNAL_LIQUIDITY"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: _flat_m5_candles(n=3))  # too few
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: type("Tick", (), {"bid": 1.0999, "ask": 1.1001})())
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.BLOCKED.value
    assert decision.reason_codes == (f"{REASON_C10_STOP_MISSING_DATA}:ATR_NOT_READY",)
    assert decision.simulated_broker_stop is None


def test_ready_with_target_found_missing_tick_is_data_error(monkeypatch):
    """C10-B requires a live spread for SHORT; a MarketDataError from get_tick fails
    closed to DATA_ERROR (never fabricates a stop, never silently reverts to BLOCKED)."""
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000, invalidation_price=1.1050)
    event = _event()

    monkeypatch.setattr(engine_module, "select_target",
                         lambda *a, **k: TargetSelection(found=True, target_price=1.1200,
                                                          target_tier="PRIMARY_EXTERNAL_LIQUIDITY"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: _flat_m5_candles())
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: (_ for _ in ()).throw(MarketDataError("NO_TICK", "n/a")))
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.DATA_ERROR.value
    assert decision.simulated_broker_stop is None


def test_ready_long_direction_ignores_missing_tick_and_qualifies(monkeypatch):
    """LONG never needs bid/ask for C10 -- a missing tick (MarketDataError, e.g. from
    _select_target's own tolerant live_bid/live_ask lookup) must not block a LONG
    candidate's C10 computation, unlike SHORT which requires it."""
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, direction="LONG",
                                            entry_price=1.1000, invalidation_price=1.0950)
    event = _event(direction="LONG")

    monkeypatch.setattr(engine_module, "select_target",
                         lambda *a, **k: TargetSelection(found=True, target_price=1.0800,
                                                          target_tier="PRIMARY_EXTERNAL_LIQUIDITY"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: _flat_m5_candles())
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: (_ for _ in ()).throw(MarketDataError("NO_TICK", "n/a")))
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.RESEARCH_QUALIFIED.value
    floor_price = MIN_BUFFER_PIPS * PIP_SIZE_EURUSD
    assert decision.simulated_broker_stop == pytest.approx(combo.invalidation_price - floor_price)


def test_ready_with_inverted_tick_blocks_on_invalid_spread(monkeypatch):
    """A tick with ask < bid (a genuinely invalid market snapshot) must fail closed to
    BLOCKED with a C10_STOP:MISSING_DATA-family reason, never silently produce a
    negative-spread stop."""
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000, invalidation_price=1.1050)
    event = _event()

    monkeypatch.setattr(engine_module, "select_target",
                         lambda *a, **k: TargetSelection(found=True, target_price=1.1200,
                                                          target_tier="PRIMARY_EXTERNAL_LIQUIDITY"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: _flat_m5_candles())
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: type("Tick", (), {"bid": 1.1010, "ask": 1.0990})())
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.BLOCKED.value
    assert decision.reason_codes == (f"{REASON_C10_STOP_MISSING_DATA}:INVALID_SPREAD",)
    assert decision.simulated_broker_stop is None


def test_ready_with_no_target_is_no_trade(monkeypatch):
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000)
    event = _event()

    monkeypatch.setattr(engine_module, "select_target", lambda *a, **k: TargetSelection(found=False, reason="REJECT_NO_TARGET"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: ())
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: (_ for _ in ()).throw(MarketDataError("NO_TICK", "n/a")))
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.NO_TRADE.value
    assert REASON_REJECT_NO_TARGET in decision.reason_codes


def test_ready_with_unavailable_structure_tier_is_data_error_not_no_trade(monkeypatch):
    """A target-model failure caused by unavailable structure/data (e.g.
    market_structure.tiers.analyze_structure_tiers requiring live MT5 symbol metadata
    that historical replay never patches -- a real gap this phase discovered) must
    fail closed to DATA_ERROR, never be silently reported as the legitimate C11
    trading conclusion REJECT_NO_TARGET."""
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000)
    event = _event()

    monkeypatch.setattr(engine_module, "select_target",
                         lambda *a, **k: TargetSelection(found=False, reason="MISSING_DIRECTION_OR_STRUCTURE_TIER"))
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", lambda *a, **k: ())
    monkeypatch.setattr(engine_module.stage2, "get_tick", lambda *a, **k: (_ for _ in ()).throw(MarketDataError("NO_TICK", "n/a")))
    monkeypatch.setattr(engine_module, "analyze_structure_tiers",
                         lambda *a, **k: type("R", (), {"status": "VALID", "external": None})())

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.DATA_ERROR.value
    assert decision.data_quality_state == "DATA_ERROR"
    assert "MISSING_DIRECTION_OR_STRUCTURE_TIER" in decision.reason_codes


def test_ready_target_selection_data_error_fails_closed(monkeypatch):
    engine = LargeSMCResearchEngine()
    analysis, combo = _analysis_with_combo(EntryModelState.READY.value, entry_price=1.1000)
    event = _event()

    def _raise(*a, **k):
        raise MarketDataError("INSUFFICIENT_CANDLES", "not enough M5 history")
    monkeypatch.setattr(engine_module.stage2, "get_latest_candles", _raise)

    decision = engine._evaluate_combination("EURUSD", T0, event, combo, analysis, T0, T0 + dt.timedelta(hours=8))
    assert decision.state == LargeSMCDecisionState.DATA_ERROR.value
    assert decision.data_quality_state == "DATA_ERROR"


# --------------------------------------------------------------------------- evaluate(): universe guard + C18


def test_symbol_outside_frozen_universe_fails_closed():
    engine = LargeSMCResearchEngine()
    dataset = Stage1Dataset(events=(), liquidity_timeline=_EMPTY_TIMELINE, metadata={})
    decisions = engine.evaluate("GBPUSD", T0, dataset)
    assert len(decisions) == 1
    assert decisions[0].state == LargeSMCDecisionState.DATA_ERROR.value
    assert REASON_SYMBOL_NOT_IN_FROZEN_UNIVERSE in decisions[0].reason_codes


def test_evaluate_records_multiple_simultaneous_combinations_independently(monkeypatch):
    """C18: two independently composed combinations at the same evaluation_time must
    both be recorded, each with its own occurrence id -- never silently narrowed to one
    by list order or any other implicit priority."""
    engine = LargeSMCResearchEngine()
    e_condition = EConditionResult(symbol="EURUSD", entry_condition="E1", direction="SHORT",
                                    eligible_for_confirmation=True, reference_type="GAP",
                                    reference_low=1.17, reference_high=1.18)
    m1 = _m1(EntryModelState.WAITING_M5_CONFIRMATION.value, source_id="M1-src")
    m2_result = M2Result(symbol="EURUSD", entry_condition="E1", direction="SHORT",
                          state=EntryModelState.WAITING_M5_CONFIRMATION.value, source_id="M2-src")
    combo1 = compose(e_condition, m1)
    combo2 = compose(e_condition, m2_result)
    assert combo1 is not None and combo2 is not None
    analysis = SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=T0, e_conditions={"E1": e_condition},
        m_maneuvers={"M1": (m1,), "M2": (m2_result,)}, combinations=(combo1, combo2),
    )
    monkeypatch.setattr(engine_module.stage2, "evaluate_entry_stage_canonical_v2",
                         lambda *a, **k: analysis)

    event = _event()
    dataset = Stage1Dataset(events=(event,), liquidity_timeline=_EMPTY_TIMELINE, metadata={})
    decisions = engine.evaluate("EURUSD", T0, dataset)

    assert len(decisions) == 2
    combos_seen = {d.combination for d in decisions}
    assert combos_seen == {"E1M1", "E1M2"}
    occurrence_ids = {d.candidate_occurrence_id for d in decisions}
    assert len(occurrence_ids) == 2  # independent identities, never collapsed


def test_evaluate_maps_market_data_error_to_data_error(monkeypatch):
    engine = LargeSMCResearchEngine()

    def _raise(*a, **k):
        raise MarketDataError("INSUFFICIENT_CANDLES", "not enough M5 history")
    monkeypatch.setattr(engine_module.stage2, "evaluate_entry_stage_canonical_v2", _raise)

    event = _event()
    dataset = Stage1Dataset(events=(event,), liquidity_timeline=_EMPTY_TIMELINE, metadata={})
    decisions = engine.evaluate("EURUSD", T0, dataset)
    assert len(decisions) == 1
    assert decisions[0].state == LargeSMCDecisionState.DATA_ERROR.value
