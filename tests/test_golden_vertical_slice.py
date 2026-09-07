"""AG_TWO_STAGE_GOLDEN_VERTICAL_SLICE_V1: a small, deterministic, production-style
regression lock proving the verified two-stage architecture across the actual
serialization boundary --

    raw historical input -> Stage1 producer -> persisted STAGE1_CONTEXT_V2
    -> process boundary / reload (load_stage1_dataset, the public loader)
    -> Stage2 consumer -> exact setup identity / entry geometry / READY milestone

Expected values are never retyped from memory -- every case in
artifacts/backtests/golden/two_stage_golden_fixture_v1.json carries provenance back
to the row-level original-continuous ledger and the determinism-verified TRUE_STAGE2
oracle (docs/status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md). No E1/E2/E3/M1/M2/M3
semantics are exercised by anything other than the frozen production code path.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from historical_replay import HistoricalCandleStore, load_mt5_export_csv, resample, resample_broker_aligned
from historical_replay.data_source_patch import historical_data_context
from historical_replay.orchestrator import (
    D1_WARMUP_CANDLES, H1_WARMUP_CANDLES, M5_WARMUP_CANDLES, SetupLedger, Stage1Event, _has_enough_history,
)
from historical_replay.stage1 import fingerprint_qualified_e_events, load_stage1_dataset
from historical_replay.stage2 import (
    MissingStage1DirectionalLiquidityContextError,
    evaluate_entry_stage,
    evaluate_entry_stage_canonical_v2,
)

UTC = dt.timezone.utc
GOLDEN_FIXTURE_PATH = "artifacts/backtests/golden/two_stage_golden_fixture_v1.json"
EVENTS_PATH = "artifacts/backtests/stage1/qualified_e_events_2025-08-01_2025-10-01.json"
LIQUIDITY_PATH = "artifacts/backtests/directional_liquidity_timeline.json"
CSV_PATH = r"D:\EURUSD_M5_202504211715_202607310000.csv"


@pytest.fixture(scope="module")
def golden():
    return json.loads(Path(GOLDEN_FIXTURE_PATH).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dataset():
    """The serialization boundary itself: load_stage1_dataset() is the canonical
    public loader -- no manual object reconstruction. Simulates a fresh consumer
    process: nothing here shares memory with whatever produced the artifact."""
    return load_stage1_dataset(EVENTS_PATH, LIQUIDITY_PATH)


@pytest.fixture(scope="module")
def csv_data():
    return load_mt5_export_csv(CSV_PATH, "EURUSD", "M5")


@pytest.fixture(scope="module")
def sorted_m5_times(csv_data):
    candles, _rep = csv_data
    return sorted(c.time for c in candles)


@pytest.fixture(scope="module")
def store(csv_data):
    candles, rep = csv_data
    s = HistoricalCandleStore()
    s.load_series("EURUSD", "M5", candles)
    for tf in ("M15", "H1"):
        s.load_series("EURUSD", tf, resample(candles, "M5", tf))
    for tf in ("H4", "D1"):
        s.load_series("EURUSD", tf, resample_broker_aligned(candles, rep.broker_times, "M5", tf))
    return s


def _event_by_id(dataset, event_id):
    return next(e for e in dataset.events if e.event_id == event_id)


def _to_stage1_event(qe):
    return Stage1Event(entry_condition=qe.entry_condition, reference_key=qe.reference_key,
                        direction=qe.direction, qualification_time=qe.qualification_time,
                        liquidity_reference=qe.htf_liquidity_reference,
                        eligibility_intervals=qe.eligibility_intervals)


# --------------------------------------------------------------------------- fingerprint / reload

def test_fingerprint_matches_golden_fixture(dataset, golden):
    assert golden["fingerprint_algorithm"] == "SHA-256"
    assert fingerprint_qualified_e_events(dataset.events) == golden["fingerprint"]


def test_fingerprint_stable_across_reload():
    a = load_stage1_dataset(EVENTS_PATH, LIQUIDITY_PATH)
    b = load_stage1_dataset(EVENTS_PATH, LIQUIDITY_PATH)
    assert fingerprint_qualified_e_events(a.events) == fingerprint_qualified_e_events(b.events)


def test_reload_produces_18_events_matching_frozen_baseline(dataset):
    from collections import Counter
    counts = Counter(e.entry_condition for e in dataset.events)
    assert len(dataset.events) == 18
    assert counts == {"E1": 3, "E2": 4, "E3": 11}


# --------------------------------------------------------------------------- canonical V2 fail-closed gate

def test_canonical_v2_fails_closed_without_liquidity_timeline(dataset):
    qe = _event_by_id(dataset, "QE-EURUSD-E1-ba85db0c9d68cfbc")
    se = _to_stage1_event(qe)
    with pytest.raises(MissingStage1DirectionalLiquidityContextError):
        evaluate_entry_stage_canonical_v2("EURUSD", se, dt.datetime(2025, 9, 15, 12, 10, tzinfo=UTC),
                                          liquidity_timeline=None)


def test_legacy_fallback_still_permissive(dataset, store):
    """Legacy low-level evaluate_entry_stage() must remain permissive (existing
    unit/API compatibility) -- only the canonical V2 wrapper fails closed. No
    liquidity_timeline given: falls back to event.liquidity_reference (None for this
    E1 event) instead of raising."""
    qe = _event_by_id(dataset, "QE-EURUSD-E1-ba85db0c9d68cfbc")
    se = _to_stage1_event(qe)
    as_of = dt.datetime(2025, 9, 15, 12, 10, tzinfo=UTC)
    with historical_data_context(store, as_of):
        analysis = evaluate_entry_stage("EURUSD", se, as_of, liquidity_timeline=None)
    assert analysis is not None


# --------------------------------------------------------------------------- Stage1-bypass instrumentation

@pytest.fixture()
def bypass_counters():
    import daytrading_runtime.conditional_entry_snapshot as ces
    import entry_confirmation.route as route
    import liquidity.analyzer as la
    import supply_demand.analyzer as sda

    counts = {"D1_or_H1_discovery": 0, "E_evaluator": 0, "build_symbol_conditional_entry_analysis": 0}

    def _wrap(name, real, forbidden_timeframes=None):
        def _wrapped(*args, **kwargs):
            if forbidden_timeframes is not None:
                tf = kwargs.get("timeframe", args[1] if len(args) > 1 else None)
                if tf in forbidden_timeframes:
                    counts["D1_or_H1_discovery"] += 1
            else:
                counts[name] += 1
            return real(*args, **kwargs)
        return _wrapped

    patches = [
        patch.object(sda, "fair_value_gaps_for", _wrap("fvg", sda.fair_value_gaps_for, {"D1"})),
        patch.object(sda, "order_blocks_for", _wrap("ob", sda.order_blocks_for, {"H1"})),
        patch.object(la, "liquidity_result", _wrap("liq", la.liquidity_result, {"H1"})),
        patch.object(ces, "build_symbol_conditional_entry_analysis",
                    _wrap("build_symbol_conditional_entry_analysis", ces.build_symbol_conditional_entry_analysis)),
        patch.object(route, "evaluate_e1", _wrap("E_evaluator", route.evaluate_e1)),
        patch.object(route, "evaluate_e2", _wrap("E_evaluator", route.evaluate_e2)),
        patch.object(route, "evaluate_e3", _wrap("E_evaluator", route.evaluate_e3)),
    ]
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
        yield counts


def _run_case(dataset, store, bypass_counters, case):
    qe = _event_by_id(dataset, case["event_id"])
    se = _to_stage1_event(qe)
    as_of = dt.datetime.fromisoformat(case["evaluation_timestamp"])
    assert qe.is_eligible_at(as_of) == case["expected"]["eligible"]
    with historical_data_context(store, as_of):
        analysis = evaluate_entry_stage_canonical_v2("EURUSD", se, as_of,
                                                      liquidity_timeline=dataset.liquidity_timeline)
    combo = next(c for c in analysis.combinations if c.combination == case["combination"])
    return combo


# --------------------------------------------------------------------------- Case A / B: shared directional liquidity

def test_case_a_e1m3_restored_ready(dataset, store, bypass_counters, golden):
    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_A_E1M3_RESTORED_READY")
    combo = _run_case(dataset, store, bypass_counters, case)
    exp = case["expected"]
    assert combo.state == "READY"
    assert combo.entry_array == exp["entry_array"]["type"]
    assert combo.entry_price == exp["entry_array"]["reference"]
    assert bypass_counters == {"D1_or_H1_discovery": 0, "E_evaluator": 0, "build_symbol_conditional_entry_analysis": 0}


def test_case_b_e3m3_sibling_shares_directional_liquidity(dataset, store, bypass_counters, golden):
    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_B_E3M3_SIBLING_SHARED_LIQUIDITY")
    combo = _run_case(dataset, store, bypass_counters, case)
    exp = case["expected"]
    assert combo.state == "READY"
    assert combo.entry_array == exp["entry_array"]["type"]
    assert combo.entry_price == exp["entry_array"]["reference"]

    # the actual proof: E1M3 and E3M3 resolve to the SAME directional liquidity object
    # at the same (direction, timestamp) -- shared, not E-family-owned
    as_of = dt.datetime.fromisoformat(case["evaluation_timestamp"])
    liq = dataset.liquidity_timeline.lookup("SHORT", as_of)
    assert liq is not None
    assert liq.source == exp["directional_liquidity"]["source"]
    assert liq.price == exp["directional_liquidity"]["price"]
    assert bypass_counters == {"D1_or_H1_discovery": 0, "E_evaluator": 0, "build_symbol_conditional_entry_analysis": 0}


# --------------------------------------------------------------------------- Case C: E1M2 READY (full walk)

def test_case_c_e1m2_ready(dataset, store, sorted_m5_times, bypass_counters, golden):
    """entry_type/entry_low/entry_high/entry_reference are overwritten on every poll
    where an entry array exists (SetupLedger.observe), not only at ready_time -- this
    setup stays non-terminal for days after READY and forms a different array by
    final_time. So this case is verified the same way the oracle itself was produced:
    a full SetupLedger walk of the event across its eligible window, not a
    single-point evaluation at ready_timestamp (see fixture provenance_note_case_c)."""
    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_C_E1M2_READY")
    exp = case["expected"]
    qe = _event_by_id(dataset, case["event_id"])
    se = _to_stage1_event(qe)

    ledger = SetupLedger()
    steps = 0
    for t in sorted_m5_times:
        as_of = t + dt.timedelta(minutes=5)
        if not qe.is_eligible_at(as_of):
            continue
        if not (_has_enough_history(store, "EURUSD", "D1", D1_WARMUP_CANDLES, as_of)
                and _has_enough_history(store, "EURUSD", "H1", H1_WARMUP_CANDLES, as_of)
                and _has_enough_history(store, "EURUSD", "M5", M5_WARMUP_CANDLES, as_of)):
            continue
        steps += 1
        with historical_data_context(store, as_of):
            analysis = evaluate_entry_stage_canonical_v2("EURUSD", se, as_of,
                                                          liquidity_timeline=dataset.liquidity_timeline)
        ledger.observe(analysis, as_of)

    assert steps > 0
    row = ledger.rows[case["setup_id"]]
    assert row.ready_time == dt.datetime.fromisoformat(exp["ready_timestamp"])
    assert row.entry_type == exp["final_entry_array"]["type"]
    assert row.entry_low == exp["final_entry_array"]["low"]
    assert row.entry_high == exp["final_entry_array"]["high"]
    assert row.entry_reference == exp["final_entry_array"]["reference"]
    assert row.final_state == exp["final_state"]
    assert row.final_time == dt.datetime.fromisoformat(exp["final_time"])
    assert bypass_counters == {"D1_or_H1_discovery": 0, "E_evaluator": 0, "build_symbol_conditional_entry_analysis": 0}


# --------------------------------------------------------------------------- Case D: E3M2 expiry regression (negative)

def test_case_d_e3m2_expiry_regression(dataset, golden):
    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_D_E3M2_EXPIRY_REGRESSION")
    qe = _event_by_id(dataset, case["event_id"])
    for iso_ts, expected in case["expected"]["eligible_at"].items():
        ts = dt.datetime.fromisoformat(iso_ts)
        assert qe.is_eligible_at(ts) == expected, f"{iso_ts}: expected eligible={expected}"
    # false Aug-19 READY is IMPOSSIBLE precisely because eligibility gates the M-side
    # evaluation entirely -- an ineligible timestamp is never even passed to Stage 2
    assert not qe.is_eligible_at(dt.datetime(2025, 8, 19, 16, 0, tzinfo=UTC))


# --------------------------------------------------------------------------- Case E: multi-interval eligibility

def test_case_e_multi_interval_eligibility(dataset, golden):
    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_E_MULTI_INTERVAL_ELIGIBILITY")
    qe = _event_by_id(dataset, case["event_id"])
    assert len(qe.eligibility_intervals) == len(case["eligibility_intervals"])
    for iso_ts, expected in case["expected"]["eligible_at"].items():
        ts = dt.datetime.fromisoformat(iso_ts)
        assert qe.is_eligible_at(ts) == expected, f"{iso_ts}: expected eligible={expected}"


# --------------------------------------------------------------------------- determinism
# (AG_EGSVF_V1_CROSS_STRATEGY_DETERMINISM_EVIDENCE_RECONCILIATION)
#
# The stage1/stage2 fingerprint-reload tests above (test_fingerprint_matches_golden_
# fixture, test_fingerprint_stable_across_reload) already prove Stage1 determinism.
# What they do NOT cover is large_smc_research.engine.LargeSMCResearchEngine -- the
# actual top-level entry point that composes Stage2's combinations into
# LargeSMCResearchDecision (occurrence identity, setup_family_id, entry geometry,
# structural-invalidation fields, and C10's always-None simulated_broker_stop). This
# test drives that real engine, reusing the same golden dataset/store/bypass_counters
# fixtures as the cases above -- no new fixture data, no CSV replay of its own.


def test_large_smc_discovery_is_deterministic_for_golden_fixture(dataset, store, bypass_counters, golden):
    """Same golden dataset + same cached historical store + same evaluation_time must
    yield byte-identical LargeSMCResearchDecision tuples across repeated calls to
    LargeSMCResearchEngine.evaluate() -- the actual research-decision output boundary,
    not just Stage1's own fingerprint or one case's combination. C10 remains UNSIGNED
    throughout: simulated_broker_stop must repeat as None, never invented."""
    from large_smc_research.engine import LargeSMCResearchEngine

    case = next(c for c in golden["cases"] if c["case_id"] == "CASE_A_E1M3_RESTORED_READY")
    as_of = dt.datetime.fromisoformat(case["evaluation_timestamp"])
    engine = LargeSMCResearchEngine()

    runs = []
    for _ in range(2):
        with historical_data_context(store, as_of):
            runs.append(engine.evaluate("EURUSD", as_of, dataset))

    baseline = runs[0]
    assert len(baseline) > 0
    for decisions in runs[1:]:
        assert decisions == baseline
    for decision in baseline:
        assert decision.simulated_broker_stop is None  # C10 UNSIGNED -- never invented, repeats identically
    assert bypass_counters == {"D1_or_H1_discovery": 0, "E_evaluator": 0, "build_symbol_conditional_entry_analysis": 0}
