"""Runtime integration tests for SMC_CONDITIONAL_ENTRY_V2 (spec section 26). Exercises
`compose_conditional_entry_analysis` -- the PURE half of the runtime wiring, no MT5
mocking needed (mirrors the discipline every other entry_confirmation test file already
uses: hand-built fixtures, the REAL market_structure/supply_demand/liquidity/
entry_confirmation logic underneath). `build_symbol_conditional_entry_analysis` (the
thin MT5-fetching wrapper) is intentionally NOT unit-tested here, matching
daytrading_runtime/snapshot.py's own existing convention (its build_e1/e2/e3_result
functions have never had direct unit tests either -- MT5 mocking for that thin a layer
would mostly test the mock).
"""
from __future__ import annotations

import datetime as dt

from daytrading_runtime.conditional_entry_snapshot import compose_conditional_entry_analysis
from entry_confirmation.models import CandidateDirection
from liquidity.hierarchy import InducementCandidate
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc

_D1_ORIGIN = dt.datetime(2026, 1, 1, tzinfo=UTC)
_D1_TOUCH_TIME = dt.datetime(2026, 1, 3, tzinfo=UTC)
_D1_REACTION_TIME = dt.datetime(2026, 1, 4, tzinfo=UTC)

_H1_ORIGIN = dt.datetime(2026, 1, 4, 10, 0, tzinfo=UTC)
_H1_TOUCH_TIME = dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC)

_M5_START = dt.datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
_ZONE_FAIL_TIME = _M5_START - dt.timedelta(minutes=5)
_CHOCH_TIME = _M5_START + dt.timedelta(minutes=5 * 8)


def _pt(t, p, eps=0.0002):
    return Candle(time=t, open=p, high=p + eps, low=p - eps, close=p, volume=1.0)


def _displacement_history(base):
    return [Candle(base + dt.timedelta(minutes=5 * i), 1.1000, 1.1002, 1.0999, 1.10005) for i in range(20)]


# --------------------------------------------------------------------------- E1 (bearish, SHORT)


def _d1_gap_zone():
    return ZoneResult(symbol="EURUSD", timeframe="D1", family=ZoneFamily.FVG, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.BEARISH, status=ZoneStatus.TOUCHED, source="test",
                       low=1.0980, high=1.1000, origin_time=_D1_ORIGIN)


def _d1_touch_candle():
    return Candle(_D1_TOUCH_TIME, 1.1005, 1.1010, 1.0985, 1.0990)  # intersects, closes below midpoint -> SHORT


def _d1_reaction_candle():
    return Candle(_D1_REACTION_TIME, 1.0990, 1.0992, 1.0850, 1.0855)  # big bearish, qualifies displacement


# --------------------------------------------------------------------------- E2 (bearish, SHORT)


def _h1_poi_zone():
    return ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.SUPPLY,
                       direction=ZoneDirection.BEARISH, status=ZoneStatus.TOUCHED, source="test",
                       low=1.1005, high=1.1015, origin_time=_H1_ORIGIN)


def _h1_candles_with_touch():
    return [
        Candle(_H1_ORIGIN + dt.timedelta(hours=1), 1.0990, 1.0995, 1.0985, 1.0992),
        Candle(_H1_TOUCH_TIME, 1.1000, 1.1012, 1.0998, 1.1008),  # intersects [1.1005, 1.1015]
    ]


def _e2_reaction_m5_candle():
    return Candle(_H1_TOUCH_TIME + dt.timedelta(minutes=5), 1.1010, 1.1012, 1.0930, 1.0932)  # big bearish


# --------------------------------------------------------------------------- E3 / M1 / M2 / M3 shared M5


def _htf_liquidity_buy(reclaim_time):
    return LiquidityLevel(symbol="EURUSD", timeframe="H1", side=LiquiditySide.BUY_SIDE, source="EXTERNAL_SWING_HIGH",
                           price=1.1060, origin_time=_M5_START, status=LiquidityStatus.RECLAIMED,
                           sweep_time=_M5_START + dt.timedelta(minutes=35), reclaim_time=reclaim_time)


def _m5_candles_zigzag_drop():
    """Zone-fail candle (for M2) then an ascending zigzag then a decisive bearish drop
    -> BEARISH_CHOCH at _CHOCH_TIME (same verified shape as the M2/M3 unit tests),
    strictly after the E2 reaction candle and the H1 touch."""
    zone_fail_candle = Candle(_ZONE_FAIL_TIME, 1.0992, 1.0994, 1.0975, 1.0978)
    prices = [1.1000, 1.1030, 1.1010, 1.1040, 1.1020, 1.1050, 1.1030, 1.1060]
    candles = [zone_fail_candle] + [_pt(_M5_START + dt.timedelta(minutes=5 * i), p) for i, p in enumerate(prices)]
    candles.append(Candle(_CHOCH_TIME, 1.1032, 1.1034, 1.0928, 1.0930))
    # Include the E2 reaction candle too so M5 evaluation covers the same window E2 used.
    return [_e2_reaction_m5_candle()] + candles


def _inducement_candidate_short():
    candidate = LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="SWING_HIGH",
                                price=1.1060, origin_time=_M5_START - dt.timedelta(hours=1), status=LiquidityStatus.UNSWEPT)
    target = LiquidityLevel(symbol="EURUSD", timeframe="M5", side=LiquiditySide.BUY_SIDE, source="EXTERNAL_SWING_HIGH",
                             price=1.1200, origin_time=_M5_START - dt.timedelta(hours=2), status=LiquidityStatus.UNSWEPT)
    return InducementCandidate(candidate_id="c1", candidate=candidate, target_id="t1", target=target,
                                side=LiquiditySide.BUY_SIDE)


def _m2_demand_zone():
    return ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.DEMAND,
                       direction=ZoneDirection.BULLISH, status=ZoneStatus.INVALIDATED, source="test",
                       low=1.0990, high=1.1000, origin_time=_H1_ORIGIN)


def _full_bearish_inputs(**overrides):
    kwargs = dict(
        symbol="EURUSD", evaluation_time=_CHOCH_TIME + dt.timedelta(minutes=5), current_price=1.0900,
        d1_gap_zone=_d1_gap_zone(), d1_touch_candle=_d1_touch_candle(), d1_reaction_candle=_d1_reaction_candle(),
        d1_reaction_history=_displacement_history(_D1_ORIGIN - dt.timedelta(days=25)),
        d1_direction=CandidateDirection.SHORT,
        h1_poi_zone=_h1_poi_zone(), h1_candles=_h1_candles_with_touch(),
        htf_liquidity_buy=_htf_liquidity_buy(_M5_START + dt.timedelta(minutes=36)), htf_liquidity_sell=None,
        # 20 tiny candles well before BOTH the E2 reaction candle (3:05) and the M-model
        # CHoCH/displacement candles (~5:45) -- AG_ENTRY_DISPLACEMENT_V1 requires >= 20
        # prior candles strictly before whichever candle is being qualified.
        m5_candles=_m5_candles_zigzag_drop(), m5_displacement_history=_displacement_history(_H1_TOUCH_TIME - dt.timedelta(hours=3)),
        m5_fvg_zones=(), m5_validated_order_blocks=(),
        inducement_candidates=(_inducement_candidate_short(),), inducement_taken_levels=(),
        m2_candidate_zones=(_m2_demand_zone(),),
    )
    kwargs.update(overrides)
    return kwargs


# --------------------------------------------------------------------------- required scenarios


def test_e1_qualified_and_m2_engaged_produces_e1m2():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs())
    assert analysis.e_conditions["E1"].eligible_for_confirmation is True
    assert analysis.e_conditions["E1"].direction == "SHORT"
    combos = {c.combination for c in analysis.combinations}
    assert "E1M2" in combos


def test_e2_qualified_and_m1_engaged_produces_e2m1():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs())
    assert analysis.e_conditions["E2"].eligible_for_confirmation is True
    assert analysis.e_conditions["E2"].direction == "SHORT"
    combos = {c.combination for c in analysis.combinations}
    assert "E2M1" in combos


def test_e3_qualified_and_m2_engaged_produces_e3m2():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs())
    assert analysis.e_conditions["E3"].eligible_for_confirmation is True
    assert analysis.e_conditions["E3"].direction == "SHORT"
    combos = {c.combination for c in analysis.combinations}
    assert "E3M2" in combos


def test_wrong_side_liquidity_pool_never_fabricates_m3_readiness():
    # No BUY_SIDE liquidity level available while E1/E2 qualify SHORT -- the runtime's
    # own side-filtering (`liquidity_level = ... if direction == SHORT else ...`) must
    # select None for the SHORT branch. M3 still composes (a qualified E + an engaged-
    # but-waiting M is a valid, explainable "waiting" combination per spec section 26),
    # but its state must honestly stay WAITING_HTF_TOUCH -- never fabricated as READY.
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs(htf_liquidity_buy=None, htf_liquidity_sell=None))
    m3_results = analysis.m_maneuvers["M3"]
    assert all(m.state in ("NOT_APPLICABLE", "WAITING_HTF_TOUCH") for m in m3_results)
    m3_combos = {c.combination: c.state for c in analysis.combinations if c.maneuver == "M3"}
    assert all(state == "WAITING_HTF_TOUCH" for state in m3_combos.values())


def test_two_e_conditions_one_m_confirmation_produces_two_combinations():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs(htf_liquidity_buy=None))  # E3 not eligible
    combos = {c.combination for c in analysis.combinations if c.maneuver == "M2"}
    assert combos == {"E1M2", "E2M2"}


def test_one_e_condition_two_m_confirmations_produces_two_combinations():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs(
        h1_poi_zone=None, htf_liquidity_buy=None,  # only E1 stays eligible
    ))
    combos = {c.combination for c in analysis.combinations if c.entry_condition == "E1"}
    assert "E1M1" in combos and "E1M2" in combos


def test_multiple_e_multiple_m_correct_cross_product():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs())
    combos = {c.combination for c in analysis.combinations}
    # Every combination present must be a genuine (qualified E) x (engaged M) pair --
    # spot-check membership across all three E's for at least M2 (the model most
    # reliably engaged by this fixture's zone-failure evidence).
    assert {"E1M2", "E2M2", "E3M2"}.issubset(combos)


def test_no_e_qualified_produces_no_combinations():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs(
        d1_gap_zone=None, h1_poi_zone=None, htf_liquidity_buy=None, htf_liquidity_sell=None,
    ))
    assert analysis.combinations == ()
    for e in analysis.e_conditions.values():
        assert e.eligible_for_confirmation is False
    for maneuver_results in analysis.m_maneuvers.values():
        assert all(m.state == "NOT_APPLICABLE" for m in maneuver_results)


def test_insufficient_m5_data_reports_unavailable_quality_not_a_crash():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs(m5_candles=(), m5_displacement_history=()))
    assert analysis.data_quality == "UNAVAILABLE"
    # Still fully explainable -- no exception, every E/M still reports a real state.
    assert analysis.e_conditions["E1"].eligible_for_confirmation is True  # E1 doesn't need M5


def test_insufficient_h1_data_e2_stays_dormant_not_fabricated():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs(h1_poi_zone=None, h1_candles=()))
    assert analysis.e_conditions["E2"].eligible_for_confirmation is False
    assert analysis.e_conditions["E2"].touch_status == "WAITING_HTF_TOUCH"


def test_deterministic_repeated_snapshot():
    inputs = _full_bearish_inputs()
    first = compose_conditional_entry_analysis(**inputs)
    second = compose_conditional_entry_analysis(**inputs)
    assert first.combinations == second.combinations
    assert {k: v.eligible_for_confirmation for k, v in first.e_conditions.items()} == \
        {k: v.eligible_for_confirmation for k, v in second.e_conditions.items()}
    assert [m.state for m in first.m_maneuvers["M2"]] == [m.state for m in second.m_maneuvers["M2"]]


def test_selected_combination_is_always_none_no_ranking_layer():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs())
    assert analysis.selected_combination is None
    assert len(analysis.combinations) >= 1  # sanity: this fixture does produce combinations


def test_timeframe_responsibilities_are_explicit():
    analysis = compose_conditional_entry_analysis(**_full_bearish_inputs())
    assert analysis.reference_timeframes["E1"] == "D1"
    assert analysis.reference_timeframes["E2"] == "H1"
    assert analysis.reference_timeframes["E3"] == "H1"  # from the supplied LiquidityLevel.timeframe
    assert analysis.check_timeframe == "H1"
    assert analysis.confirmation_timeframe == "M5"
    assert analysis.execution_timeframe == "M5"
