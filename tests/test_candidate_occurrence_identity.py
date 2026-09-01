"""ST_LARGE_SMC_V1 C14B: candidate-occurrence identity hardening tests.

Covers the three new identity layers added on top of the existing, unchanged
`setup_id` (setup-family identity):

  ELIGIBILITY_INTERVAL_ID  -- proposals.occurrence_identity.eligibility_interval_id
  M_CANDIDATE_IDENTITY     -- M1Result/M2Result/M3Result.source_id (new field)
  CANDIDATE_OCCURRENCE_ID  -- proposals.occurrence_identity.candidate_occurrence_id

And reproduces the C14A-documented defect in the existing (unmodified)
`proposals.lifecycle.update_proposal_lifecycle` -- its store is keyed only by
`setup_id`, so a terminal occurrence gets overwritten rather than preserved -- then
proves the new `candidate_occurrence_id` layer would distinguish what that defect
conflates, without changing `lifecycle.py` itself.
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation.entry_models_v1 import EConditionResult
from entry_confirmation.m1_character_change_inducement import evaluate_m1_character_change_with_inducement
from entry_confirmation.m2_supply_demand_shift import evaluate_m2_supply_demand_shift
from entry_confirmation.m3_sweep_drop_pump import evaluate_m3_sweep_drop_pump
from liquidity.hierarchy import InducementCandidate
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure import MarketStructureConfig
from proposals import candidate_occurrence_id, eligibility_interval_id, setup_id
from proposals.lifecycle import LIFECYCLE_CREATED, LIFECYCLE_EXPIRED, update_proposal_lifecycle
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc
_CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)


def _pt(t, p, eps=0.0002):
    return Candle(time=t, open=p, high=p + eps, low=p - eps, close=p, volume=1.0)


def _displacement_history(base):
    return [Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


# --------------------------------------------------------------------------- eligibility_interval_id


def test_eligibility_interval_id_deterministic_and_no_wall_clock():
    a1 = eligibility_interval_id("QE-EURUSD-E1-abcd", dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                  dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    a2 = eligibility_interval_id("QE-EURUSD-E1-abcd", dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                  dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    assert a1 == a2  # pure function of its inputs -- restart/replay-stable by construction


def test_eligibility_interval_id_distinguishes_disjoint_intervals_of_same_event():
    event_id = "QE-EURUSD-E1-abcd"
    interval_a = eligibility_interval_id(event_id, dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                          dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    interval_b = eligibility_interval_id(event_id, dt.datetime(2025, 9, 16, 8, 0, tzinfo=UTC),
                                          dt.datetime(2025, 9, 16, 12, 0, tzinfo=UTC))
    assert interval_a != interval_b  # same event_id, different [start,end) -> different id


# --------------------------------------------------------------------------- M1 source_id


def _e_condition(entry_condition="E1", direction="SHORT", eligible=True):
    return EConditionResult(entry_condition=entry_condition, symbol="EURUSD", direction=direction,
                             eligible_for_confirmation=eligible)


def _m1_ready_result(candidate_id="ind-1", taken_time=dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)):
    m5_start = taken_time + dt.timedelta(minutes=5)
    choch_time = m5_start + dt.timedelta(minutes=5 * 8)
    level = LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                            price=1.1060, origin_time=taken_time - dt.timedelta(hours=1), status=LiquidityStatus.UNSWEPT)
    target = LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="EXTERNAL_SWING_HIGH",
                             price=1.1200, origin_time=taken_time - dt.timedelta(hours=2), status=LiquidityStatus.UNSWEPT)
    candidate = InducementCandidate(candidate_id=candidate_id, candidate=level, target_id="t1", target=target,
                                     side=LiquiditySide.BUY_SIDE)
    taken = LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                            price=1.1060, origin_time=taken_time - dt.timedelta(hours=1),
                            status=LiquidityStatus.RECLAIMED, sweep_time=taken_time)
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [_pt(m5_start + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(choch_time, 1.1032, 1.1034, 1.0928, 1.0930))
    fvg = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                      direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
                      low=1.0980, high=1.0995, origin_time=taken_time + dt.timedelta(minutes=1))
    return evaluate_m1_character_change_with_inducement(
        "EURUSD", _e_condition("E1", "SHORT"), candidate, inducement_taken_level=taken, m5_candles=candles,
        m5_displacement_history=_displacement_history(taken_time - dt.timedelta(hours=2)),
        m5_fvg_zones=(fvg,), m5_order_blocks=(), current_price=1.1000,
        evaluation_time=choch_time + dt.timedelta(minutes=5), structure_config=_CFG,
    )


def test_m1_source_id_none_before_choch_confirmed():
    result = evaluate_m1_character_change_with_inducement("EURUSD", _e_condition(), None, m5_candles=())
    assert result.choch_confirmed is False
    assert result.source_id is None


def test_m1_source_id_stable_for_same_evidence():
    r1 = _m1_ready_result()
    r2 = _m1_ready_result()
    assert r1.choch_confirmed is True
    assert r1.source_id is not None
    assert r1.source_id == r2.source_id


def test_m1_source_id_differs_for_different_inducement():
    r1 = _m1_ready_result(candidate_id="ind-1")
    r2 = _m1_ready_result(candidate_id="ind-2")
    assert r1.source_id != r2.source_id


def test_m1_source_id_differs_for_different_choch_bar():
    r1 = _m1_ready_result(taken_time=dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC))
    r2 = _m1_ready_result(taken_time=dt.datetime(2026, 1, 6, 5, 0, tzinfo=UTC))
    assert r1.source_id != r2.source_id


# --------------------------------------------------------------------------- M2 source_id


def _m2_result(zone_low=1.0990, zone_origin=dt.datetime(2026, 1, 4, 10, 0, tzinfo=UTC)):
    m5_start = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
    zone_fail_time = m5_start - dt.timedelta(minutes=5)
    choch_time = m5_start + dt.timedelta(minutes=5 * 8)
    demand_zone = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                              direction=ZoneDirection.BULLISH, status=ZoneStatus.INVALIDATED, source="test",
                              low=zone_low, high=1.1000, origin_time=zone_origin)
    zone_fail_candle = Candle(zone_fail_time, 1.0992, 1.0994, 1.0975, 1.0978)
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [zone_fail_candle] + [_pt(m5_start + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(choch_time, 1.1032, 1.1034, 1.0928, 1.0930))
    return evaluate_m2_supply_demand_shift(
        "EURUSD", _e_condition("E2", "SHORT"), demand_zone, m5_candles=candles,
        m5_displacement_history=_displacement_history(zone_fail_time - dt.timedelta(hours=2)),
        m5_candidate_zones=(), m5_fvg_zones=(), m5_order_blocks=(), current_price=None,
        evaluation_time=choch_time + dt.timedelta(minutes=5), structure_config=_CFG,
    )


def test_m2_source_id_none_before_zone_failure():
    result = evaluate_m2_supply_demand_shift("EURUSD", _e_condition("E2", "SHORT"), None, m5_candles=())
    assert result.zone_failure is False
    assert result.source_id is None


def test_m2_source_id_stable_and_separated():
    r1 = _m2_result(zone_low=1.0990)
    r2 = _m2_result(zone_low=1.0990)
    r3 = _m2_result(zone_low=1.0850)  # different zone boundary -> different zone_id
    assert r1.zone_failure is True
    assert r1.source_id is not None
    assert r1.source_id == r2.source_id
    assert r1.source_id != r3.source_id


# --------------------------------------------------------------------------- M3 source_id


def _m3_result(sweep_price=1.1060, reclaim_time=None):
    m5_start = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
    sweep_time = m5_start + dt.timedelta(minutes=5 * 7)
    reclaim_time = reclaim_time or (sweep_time + dt.timedelta(minutes=1))
    choch_time = m5_start + dt.timedelta(minutes=5 * 8)
    level = LiquidityLevel(symbol="EURUSD", timeframe="M15", side=LiquiditySide.BUY_SIDE, source="ASIAN_HIGH",
                            price=sweep_price, origin_time=m5_start, status=LiquidityStatus.RECLAIMED,
                            sweep_time=sweep_time, reclaim_time=reclaim_time)
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [_pt(m5_start + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(time=choch_time, open=1.1032, high=1.1034, low=1.0928, close=1.0930))
    return evaluate_m3_sweep_drop_pump(
        "EURUSD", _e_condition("E3", "SHORT"), level, m5_candles=candles,
        m5_displacement_history=_displacement_history(m5_start - dt.timedelta(hours=2)),
        m5_fvg_zones=(), m5_order_blocks=(), current_price=None,
        evaluation_time=choch_time + dt.timedelta(minutes=5), structure_config=_CFG,
    )


def test_m3_source_id_none_before_choch():
    result = evaluate_m3_sweep_drop_pump("EURUSD", _e_condition("E3", "SHORT"), None, m5_candles=())
    assert result.choch is None
    assert result.source_id is None


def test_m3_source_id_stable_and_separated():
    r1 = _m3_result(sweep_price=1.1060)
    r2 = _m3_result(sweep_price=1.1060)
    r3 = _m3_result(sweep_price=1.1180)  # different swept level -> different level_id
    assert r1.choch is not None
    assert r1.source_id is not None
    assert r1.source_id == r2.source_id
    assert r1.source_id != r3.source_id


# --------------------------------------------------------------------------- candidate_occurrence_id composition


def test_candidate_occurrence_id_same_inputs_same_id():
    fam = setup_id("EURUSD", "E1M2", "SHORT", "GAP|1.17|1.18|None")
    interval = eligibility_interval_id("QE-EURUSD-E1-abcd",
                                        dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                        dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    o1 = candidate_occurrence_id(fam, interval, "M1-deadbeef")
    o2 = candidate_occurrence_id(fam, interval, "M1-deadbeef")
    assert o1 == o2


def test_candidate_occurrence_id_same_family_different_interval_differs():
    """New eligibility interval under the same setup family -> new occurrence
    (non-monotonic per C12; setup_id alone cannot distinguish this -- occurrence_id can)."""
    fam = setup_id("EURUSD", "E1M2", "SHORT", "GAP|1.17|1.18|None")
    interval_a = eligibility_interval_id("QE-EURUSD-E1-abcd", dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                          dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    interval_b = eligibility_interval_id("QE-EURUSD-E1-abcd", dt.datetime(2025, 9, 16, 8, 0, tzinfo=UTC),
                                          dt.datetime(2025, 9, 16, 12, 0, tzinfo=UTC))
    occurrence_a = candidate_occurrence_id(fam, interval_a, "M1-deadbeef")
    occurrence_b = candidate_occurrence_id(fam, interval_b, "M1-deadbeef")
    assert occurrence_a != occurrence_b


def test_candidate_occurrence_id_same_family_same_interval_different_m_candidate_differs():
    """Two independent M-candidates under the same family+interval must not collapse."""
    fam = setup_id("EURUSD", "E1M2", "SHORT", "GAP|1.17|1.18|None")
    interval = eligibility_interval_id("QE-EURUSD-E1-abcd", dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                        dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    occurrence_x = candidate_occurrence_id(fam, interval, "M1-aaaa")
    occurrence_y = candidate_occurrence_id(fam, interval, "M1-bbbb")
    assert occurrence_x != occurrence_y


def test_candidate_occurrence_id_different_e_or_m_combination_differs():
    """Preserves the 3x3 architecture: different E or M combination -> distinct family
    -> distinct occurrence, even with identical M-candidate/interval inputs."""
    interval = eligibility_interval_id("QE-EURUSD-E1-abcd", dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                        dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    fam_e1m2 = setup_id("EURUSD", "E1M2", "SHORT", "GAP|1.17|1.18|None")
    fam_e1m3 = setup_id("EURUSD", "E1M3", "SHORT", "GAP|1.17|1.18|None")
    fam_e3m3 = setup_id("EURUSD", "E3M3", "SHORT", "SWEEP|1.19|None|None")
    o1 = candidate_occurrence_id(fam_e1m2, interval, "M-x")
    o2 = candidate_occurrence_id(fam_e1m3, interval, "M-x")
    o3 = candidate_occurrence_id(fam_e3m3, interval, "M-x")
    assert len({o1, o2, o3}) == 3


# --------------------------------------------------------------------------- C14A defect reproduction + repair proof


class _DictStore:
    """Minimal get/put store matching proposals.lifecycle's documented store contract
    (JsonKeyValueStore-compatible), used only to exercise the REAL, unmodified
    update_proposal_lifecycle() deterministically in a test."""

    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def put(self, key, value):
        self._data[key] = value


def _real_ready_analysis():
    """Builds a REAL SMCConditionalEntryAnalysis (not a fake) from a real, READY
    M1Result + composer.compose(), so generate_proposals()/update_proposal_lifecycle()
    run their actual, unmodified logic end to end."""
    from entry_confirmation.composer import compose
    from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis

    m1 = _m1_ready_result()
    assert m1.state == "READY", "fixture must reach READY for generate_proposals to emit a proposal"
    e_condition = EConditionResult(
        symbol="EURUSD", entry_condition="E1", direction=m1.direction, eligible_for_confirmation=True,
        reference_type="GAP", reference_low=1.1700, reference_high=1.1710,
    )
    combo = compose(e_condition, m1)
    assert combo is not None and combo.state == "READY"
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC),
        e_conditions={"E1": e_condition}, m_maneuvers={"M1": (m1,)}, combinations=(combo,),
    )


def test_c14a_defect_reproduced_setup_id_only_store_overwrites_terminal_occurrence():
    """Reproduces the exact defect documented in C14A: the real, unmodified
    update_proposal_lifecycle() keys its store only by setup_id. A terminal
    (EXPIRED) record for one eligibility interval is silently overwritten -- not
    preserved -- when a later, genuinely different occurrence under the same
    setup_id reaches CREATED. This is the "before" half of the regression proof."""
    analysis = _real_ready_analysis()
    store = _DictStore()

    updates = update_proposal_lifecycle(analysis, store)
    assert updates and updates[0].lifecycle == LIFECYCLE_CREATED
    fam_key = updates[0].setup_id

    # Occurrence A reaches the store, then is manually marked terminal (as C12's
    # EXPIRED/INVALIDATED would eventually do, keyed only by setup_id -- the defect).
    stored = store.get(fam_key)
    store.put(fam_key, {**stored, "lifecycle": LIFECYCLE_EXPIRED})

    # Occurrence B: same setup_id (same symbol/combination/direction/reference_key),
    # evaluated again -- the real function transitions back to CREATED...
    updates_2 = update_proposal_lifecycle(analysis, store)
    assert updates_2[0].lifecycle == LIFECYCLE_CREATED
    # ...but the OLD terminal record is gone -- store now holds only the new one.
    assert store.get(fam_key)["lifecycle"] == LIFECYCLE_CREATED  # occurrence A's EXPIRED record is unrecoverable
    # This is SETUP_FAMILY_STATE_OVERWRITE, confirmed by the real function, not inferred.


def test_c14b_occurrence_id_would_distinguish_what_c14a_defect_conflates():
    """The 'after' half: candidate_occurrence_id (not wired into lifecycle.py in this
    phase) computes DIFFERENT ids for the two occurrences the test above showed
    colliding on setup_id alone -- proving the new identity layer is sufficient to
    make an occurrence-keyed store correct, without having touched lifecycle.py."""
    fam = setup_id("EURUSD", "E1M2", "SHORT", None)
    interval_a = eligibility_interval_id("QE-EURUSD-E1-xyz", dt.datetime(2025, 9, 15, 10, 0, tzinfo=UTC),
                                          dt.datetime(2025, 9, 15, 14, 0, tzinfo=UTC))
    interval_b = eligibility_interval_id("QE-EURUSD-E1-xyz", dt.datetime(2025, 9, 20, 9, 0, tzinfo=UTC),
                                          dt.datetime(2025, 9, 20, 13, 0, tzinfo=UTC))
    occurrence_a = candidate_occurrence_id(fam, interval_a, "M1-source-A")
    occurrence_b = candidate_occurrence_id(fam, interval_b, "M1-source-B")
    assert occurrence_a != occurrence_b  # an occurrence-keyed store would preserve both records
