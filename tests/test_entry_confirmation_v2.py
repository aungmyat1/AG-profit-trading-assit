"""Tests for AG_ENTRY_CONFIRMATION_V2 (entry_confirmation/models_v2.py, gap.py, poi.py,
route.py, spread.py, engine_v2.py). Deterministic-fact tests only -- purely additive to
ENTRY_CONFIRMATION_V1; test_entry_confirmation.py is untouched and still passes.
"""
from __future__ import annotations

import datetime as dt

from entry_confirmation import CandidateDirection, ConfirmationState
from entry_confirmation.engine_v2 import EntryConfirmationV2Request, evaluate_entry_confirmation_v2
from entry_confirmation.gap import evaluate_gap_context, evaluate_inverted_gap_context, gap_midpoint
from entry_confirmation.models import StructureAlignment
from entry_confirmation.poi import evaluate_poi_context
from entry_confirmation.route import classify_route, evaluate_e3
from entry_confirmation.spread import evaluate_spread_context
from liquidity import LiquidityLevel, LiquiditySide, LiquidityStatus
from strategy_engine.session import Candle
from supply_demand import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc


def _candle(o, h, l, c, when):
    return Candle(time=when, open=o, high=h, low=l, close=c, volume=1.0)


def _zone(family=ZoneFamily.FVG, role=ZoneRole.REFERENCE, direction=ZoneDirection.BULLISH,
          status=ZoneStatus.FRESH, low=1.1000, high=1.1010, origin_time=None, timeframe="H1"):
    return ZoneResult(
        symbol="EURUSD", timeframe=timeframe, family=family, role=role, direction=direction,
        status=status, source="test", low=low, high=high, origin_time=origin_time,
    )


def _level(side, status, price=1.0950, sweep_time=None, reclaim_time=None):
    return LiquidityLevel(
        symbol="EURUSD", timeframe="H1", side=side, source="SWING_LOW" if side == LiquiditySide.SELL_SIDE else "SWING_HIGH",
        price=price, origin_time=dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC), status=status,
        sweep_time=sweep_time, reclaim_time=reclaim_time,
    )


# ---------------------------------------------------------------------------
# 50% inverted-gap math (spec rule 69/36)
# ---------------------------------------------------------------------------

def test_gap_midpoint_bullish():
    assert gap_midpoint(1.1000, 1.1020) == 1.1010


def test_gap_midpoint_bearish_same_formula():
    assert gap_midpoint(1.0950, 1.0970) == 1.0960


def test_gap_midpoint_missing_bounds_returns_none():
    assert gap_midpoint(None, 1.1) is None


# ---------------------------------------------------------------------------
# Spread-aware alert (spec rules 55, 56, 71)
# ---------------------------------------------------------------------------

def test_spread_alert_buy_is_price_minus_spread():
    ctx = evaluate_spread_context(1.1050, 0.0002, CandidateDirection.LONG)
    assert ctx.status == "RESOLVED"
    assert round(ctx.spread_adjusted_alert_price, 6) == round(1.1050 - 0.0002, 6)


def test_spread_alert_sell_is_price_plus_spread():
    ctx = evaluate_spread_context(1.1050, 0.0002, CandidateDirection.SHORT)
    assert round(ctx.spread_adjusted_alert_price, 6) == round(1.1050 + 0.0002, 6)


def test_spread_unresolved_when_no_spread_supplied():
    ctx = evaluate_spread_context(1.1050, None, CandidateDirection.LONG)
    assert ctx.status == "UNRESOLVED"
    assert ctx.spread_adjusted_alert_price is None


def test_spread_adjusted_invalidation_directions():
    long_ctx = evaluate_spread_context(1.1050, 0.0002, CandidateDirection.LONG, invalidation_reference_price=1.1020)
    short_ctx = evaluate_spread_context(1.1050, 0.0002, CandidateDirection.SHORT, invalidation_reference_price=1.1080)
    assert round(long_ctx.spread_adjusted_invalidation, 6) == round(1.1020 - 0.0002, 6)
    assert round(short_ctx.spread_adjusted_invalidation, 6) == round(1.1080 + 0.0002, 6)


# ---------------------------------------------------------------------------
# Touch vs reaction (spec rules 20, 50)
# ---------------------------------------------------------------------------

def test_gap_touch_without_reaction_is_not_gap_reacted():
    zone = _zone(status=ZoneStatus.FRESH, low=1.1000, high=1.1010)
    touch = _candle(1.1005, 1.1012, 1.0998, 1.1004, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    ctx = evaluate_gap_context(zone, touch_candle=touch, candidate_direction=CandidateDirection.LONG)
    assert ctx.status in ("GAP_TOUCHED", "GAP_FILLED")
    assert ctx.status != "GAP_REACTED"


def test_gap_reacted_requires_qualifying_displacement():
    zone = _zone(status=ZoneStatus.FRESH, low=1.1000, high=1.1010)
    touch = _candle(1.1005, 1.1012, 1.0998, 1.1004, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    # 20 flat prior candles -> tiny median body, so this displacement candle qualifies easily.
    history = tuple(
        _candle(1.1000, 1.1002, 1.0999, 1.10005, dt.datetime(2026, 1, 5, 9, m, tzinfo=UTC))
        for m in range(20)
    )
    reaction = _candle(1.1004, 1.1060, 1.1003, 1.1058, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC))
    ctx = evaluate_gap_context(zone, touch, reaction, history, CandidateDirection.LONG)
    assert ctx.status == "GAP_REACTED"
    assert ctx.reaction_time is not None


def test_untouched_gap_stays_untouched():
    zone = _zone(status=ZoneStatus.FRESH, low=1.2000, high=1.2010)
    touch = _candle(1.1005, 1.1012, 1.0998, 1.1004, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    ctx = evaluate_gap_context(zone, touch_candle=touch, candidate_direction=CandidateDirection.LONG)
    assert ctx.status == "UNTOUCHED"


def test_poi_touched_reports_poi_reached_not_confirmed():
    zone = _zone(family=ZoneFamily.ORDER_BLOCK, status=ZoneStatus.TOUCHED)
    ctx = evaluate_poi_context(zone)
    assert ctx.status == "POI_REACHED"
    assert ctx.status != "CONFIRMED"


# ---------------------------------------------------------------------------
# POI + liquidity association (spec rules 13, 59, 60)
# ---------------------------------------------------------------------------

def test_poi_liquidity_association_preserved_when_supplied():
    zone = _zone(family=ZoneFamily.ORDER_BLOCK, status=ZoneStatus.TOUCHED)
    level = _level(LiquiditySide.SELL_SIDE, LiquidityStatus.UNSWEPT)
    ctx = evaluate_poi_context(zone, liquidity_level=level, liquidity_side="BELOW")
    assert ctx.liquidity_association == "ORDER_BLOCK_WITH_LIQUIDITY_BELOW"


def test_poi_liquidity_association_not_fabricated_without_context():
    zone = _zone(family=ZoneFamily.ORDER_BLOCK, status=ZoneStatus.TOUCHED)
    ctx = evaluate_poi_context(zone)
    assert ctx.liquidity_association == "NONE"


def test_filled_ob_waits_for_sweep_when_liquidity_unswept():
    zone = _zone(family=ZoneFamily.ORDER_BLOCK, status=ZoneStatus.MITIGATED)
    level = _level(LiquiditySide.SELL_SIDE, LiquidityStatus.UNSWEPT)
    ctx = evaluate_poi_context(zone, liquidity_level=level, liquidity_side="BELOW")
    assert ctx.status == "WAITING_LIQUIDITY_EVENT"


def test_filled_ob_without_required_sweep_context_waits_for_confirmation_not_confirmed():
    zone = _zone(family=ZoneFamily.ORDER_BLOCK, status=ZoneStatus.MITIGATED)
    ctx = evaluate_poi_context(zone)
    assert ctx.status == "WAITING_CONFIRMATION"
    assert ctx.status != "CONFIRMED"


# ---------------------------------------------------------------------------
# Route classification (spec rules 40, 72, 73)
# ---------------------------------------------------------------------------

def test_route_none_when_nothing_qualifies():
    result = classify_route()
    assert result.route == "NONE"
    assert result.matching_routes == ()


def test_route_single_daily_gap_reaction():
    gap_ctx = evaluate_gap_context(
        _zone(status=ZoneStatus.FRESH), touch_candle=_candle(1.1005, 1.1012, 1.0998, 1.1004, dt.datetime(2026, 1, 5, 10, tzinfo=UTC)),
    )
    # Force GAP_REACTED via direct construction is not allowed (no fabrication) -- build
    # via the real evaluator instead, matching test_gap_reacted_requires_qualifying_displacement.
    zone = _zone(status=ZoneStatus.FRESH, low=1.1000, high=1.1010)
    touch = _candle(1.1005, 1.1012, 1.0998, 1.1004, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    history = tuple(
        _candle(1.1000, 1.1002, 1.0999, 1.10005, dt.datetime(2026, 1, 5, 9, m, tzinfo=UTC))
        for m in range(20)
    )
    reaction = _candle(1.1004, 1.1060, 1.1003, 1.1058, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC))
    reacted_ctx = evaluate_gap_context(zone, touch, reaction, history, CandidateDirection.LONG)
    result = classify_route(gap_context=reacted_ctx)
    assert result.route == "DAILY_GAP_REACTION"


def test_route_multiple_when_gap_and_sweep_both_qualify():
    zone = _zone(status=ZoneStatus.FRESH, low=1.1000, high=1.1010)
    touch = _candle(1.1005, 1.1012, 1.0998, 1.1004, dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC))
    history = tuple(
        _candle(1.1000, 1.1002, 1.0999, 1.10005, dt.datetime(2026, 1, 5, 9, m, tzinfo=UTC))
        for m in range(20)
    )
    reaction = _candle(1.1004, 1.1060, 1.1003, 1.1058, dt.datetime(2026, 1, 5, 11, 0, tzinfo=UTC))
    reacted_ctx = evaluate_gap_context(zone, touch, reaction, history, CandidateDirection.LONG)
    sweep = _level(LiquiditySide.SELL_SIDE, LiquidityStatus.SWEPT, sweep_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    result = classify_route(gap_context=reacted_ctx, sweep_level=sweep)
    assert result.route == "MULTIPLE"
    assert set(result.matching_routes) == {"DAILY_GAP_REACTION", "LIQUIDITY_SWEEP"}


def test_no_ltf_scan_before_condition_is_dormant():
    request = EntryConfirmationV2Request(symbol="EURUSD", timeframe="M5", candidate_direction=CandidateDirection.LONG)
    result = evaluate_entry_confirmation_v2(request)
    assert result.route.route == "NONE"
    assert result.status == "DORMANT"
    assert result.confirmation_model == "NONE"


# ---------------------------------------------------------------------------
# E3 -- sweep is not entry; 50% inverted-gap entry geometry (rules 31-37, 51, 66-69)
# ---------------------------------------------------------------------------

def test_e3_sweep_only_no_displacement_no_gap_is_not_confirmed():
    sweep = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.SWEPT, price=1.1100,
                    sweep_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    events, geometry, model, status = evaluate_e3(
        sweep, ConfirmationState.INSUFFICIENT_DATA, None, None, None, None,
    )
    assert status == "PARTIAL"
    assert geometry.entry_reference is None


def test_e3_positive_sequence_waiting_entry_price_until_midpoint_traded():
    sweep = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.SWEPT, price=1.1100,
                    sweep_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    drop_pump_time = dt.datetime(2026, 1, 5, 9, 5, tzinfo=UTC)
    gap_origin = dt.datetime(2026, 1, 5, 9, 10, tzinfo=UTC)
    events, geometry, model, status = evaluate_e3(
        sweep, ConfirmationState.PASS, drop_pump_time, 1.1040, 1.1060, gap_origin,
        current_price=None,
    )
    assert model == "SWEEP_DROP_PUMP"
    assert geometry.entry_method == "FIFTY_PERCENT_INVERTED_GAP"
    assert geometry.entry_reference == 1.1050
    assert geometry.status == "WAITING_ENTRY_PRICE"
    assert status == "WAITING_ENTRY_PRICE"
    assert geometry.structural_invalidation_type == "LIQUIDITY_SWEEP_WICK"
    assert geometry.structural_invalidation_reference == 1.1100


def test_e3_entry_reference_available_once_midpoint_traded_but_not_marked_filled():
    sweep = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.SWEPT, price=1.1100,
                    sweep_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    drop_pump_time = dt.datetime(2026, 1, 5, 9, 5, tzinfo=UTC)
    gap_origin = dt.datetime(2026, 1, 5, 9, 10, tzinfo=UTC)
    events, geometry, model, status = evaluate_e3(
        sweep, ConfirmationState.PASS, drop_pump_time, 1.1040, 1.1060, gap_origin,
        current_price=1.1045,
    )
    assert geometry.status == "ENTRY_REFERENCE_AVAILABLE"
    assert status == "CONFIRMED"
    # never claims a fill -- no "FILLED" state exists anywhere in this contract
    assert "FILLED" not in (geometry.status, status)


def test_e3_future_inverted_gap_does_not_leak_backwards():
    sweep = _level(LiquiditySide.BUY_SIDE, LiquidityStatus.SWEPT, price=1.1100,
                    sweep_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    drop_pump_time = dt.datetime(2026, 1, 5, 9, 5, tzinfo=UTC)
    gap_origin = dt.datetime(2026, 1, 5, 9, 30, tzinfo=UTC)  # after evaluation_time
    evaluation_time = dt.datetime(2026, 1, 5, 9, 15, tzinfo=UTC)
    events, geometry, model, status = evaluate_e3(
        sweep, ConfirmationState.PASS, drop_pump_time, 1.1040, 1.1060, gap_origin,
        evaluation_time=evaluation_time,
    )
    assert status == "WAITING_CONFIRMATION"
    assert geometry.entry_reference is None


# ---------------------------------------------------------------------------
# Structural invalidation selection per route (spec rules 24, 30, 37, 70)
# ---------------------------------------------------------------------------

def test_structural_invalidation_type_differs_by_route():
    sweep = _level(LiquiditySide.SELL_SIDE, LiquidityStatus.SWEPT, price=1.0900,
                    sweep_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    drop_pump_time = dt.datetime(2026, 1, 5, 9, 5, tzinfo=UTC)
    gap_origin = dt.datetime(2026, 1, 5, 9, 10, tzinfo=UTC)
    _, e3_geometry, _, _ = evaluate_e3(sweep, ConfirmationState.PASS, drop_pump_time, 1.0910, 1.0930, gap_origin)
    assert e3_geometry.structural_invalidation_type == "LIQUIDITY_SWEEP_WICK"

    structure_shift = StructureAlignment(status=ConfirmationState.PASS, event_price=1.0850,
                                          event_time=dt.datetime(2026, 1, 5, 8, 0, tzinfo=UTC))
    gap_ctx = evaluate_gap_context(_zone(low=1.1000, high=1.1010), candidate_direction=CandidateDirection.LONG)
    from entry_confirmation.route import evaluate_e1
    _, e1_geometry, _, _ = evaluate_e1(gap_ctx, None, structure_shift)
    # inducement missing -> INDETERMINATE, geometry default (UNRESOLVED) -- confirms no
    # invented invalidation reference when inducement evidence is absent.
    assert e1_geometry.structural_invalidation_type == "UNRESOLVED"


# ---------------------------------------------------------------------------
# No DayTrading dependency (spec rule 75) -- SMC entry_confirmation must be independently usable
# ---------------------------------------------------------------------------

def test_entry_confirmation_v2_package_has_no_daytrading_imports():
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "entry_confirmation"
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for n in names:
                assert n is None or not n.startswith("daytrading"), f"{path.name} imports {n}"


def test_entry_confirmation_v2_still_has_no_execution_imports():
    import ast
    import pathlib

    pkg_dir = pathlib.Path(__file__).resolve().parents[1] / "src" / "entry_confirmation"
    for path in pkg_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                continue
            for n in names:
                assert n is None or not (n.startswith("execution") or n.startswith("mt5")), \
                    f"{path.name} imports {n}"


def test_htf_context_default_is_unresolved_not_fabricated():
    request = EntryConfirmationV2Request(symbol="EURUSD", timeframe="M5")
    result = evaluate_entry_confirmation_v2(request)
    assert result.directional_context.status == "UNRESOLVED"
    assert result.directional_context.htf_direction is None
