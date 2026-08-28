"""Tests for liquidity.hierarchy: external/internal scoping, external_swing_liquidity()
sweep-state reuse, and Inducement Candidate detection (spec sections 5-11, 30-31). Pure/
offline -- no MT5 connection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from liquidity.hierarchy import (
    ROLE_INDUCEMENT_CANDIDATE,
    ROLE_NONE,
    ROLE_TARGET,
    SCOPE_EXTERNAL,
    SCOPE_INTERNAL,
    ScopedLiquidityLevel,
    classify_roles,
    external_swing_liquidity,
    find_inducement_candidates,
    level_id,
    scope_liquidity_levels,
)
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BULLISH, StructurePoint, StructurePointKind, StructureTier
from strategy_engine.session import Candle

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _level(source, side, price, status=LiquidityStatus.UNSWEPT, timeframe="H1") -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe=timeframe, side=side, source=source, price=price,
                           origin_time=NOW, status=status)


def _scoped(source, side, price, scope, status=LiquidityStatus.UNSWEPT) -> ScopedLiquidityLevel:
    lvl = _level(source, side, price, status)
    return ScopedLiquidityLevel(level=lvl, scope=scope, level_id=level_id(lvl))


# --------------------------------------------------------------------------- scoping

def test_scope_liquidity_levels_tags_external_and_internal():
    external = [_level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000)]
    internal = [_level("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400)]
    scoped = scope_liquidity_levels(external, internal)
    assert {s.scope for s in scoped if s.level.source == "EXTERNAL_SWING_HIGH"} == {SCOPE_EXTERNAL}
    assert {s.scope for s in scoped if s.level.source == "EQUAL_HIGHS"} == {SCOPE_INTERNAL}


def test_level_id_deterministic():
    lvl = _level("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400)
    assert level_id(lvl) == level_id(lvl)  # same input -> same id, no hidden state


# --------------------------------------------------------------------------- external_swing_liquidity

def test_external_swing_liquidity_reuses_sweep_state_machine():
    swing_high = StructurePoint(time_utc=NOW, price=1.18000, kind=StructurePointKind.SWING_HIGH)
    swing_low = StructurePoint(time_utc=NOW, price=1.17000, kind=StructurePointKind.SWING_LOW)
    tier = StructureTier(tier="EXTERNAL", swing_length=50, direction=STATE_BULLISH, swings=(swing_high, swing_low),
                          events=(), latest_swing_high=swing_high, latest_swing_low=swing_low)
    candles = [Candle(time=NOW + timedelta(hours=i), open=1.1750, high=1.1750, low=1.1750, close=1.1750, volume=1.0) for i in range(1, 5)]

    levels = external_swing_liquidity("EURUSD", "H1", tier, candles)
    sources = {l.source for l in levels}
    assert sources == {"EXTERNAL_SWING_HIGH", "EXTERNAL_SWING_LOW"}
    assert all(l.status == LiquidityStatus.UNSWEPT for l in levels)  # candles never traded through either level


# --------------------------------------------------------------------------- inducement: Case A (valid)

def test_case_a_valid_bullish_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400, SCOPE_INTERNAL),
    ]
    candidates = find_inducement_candidates(scoped, current_price=1.17000)
    assert len(candidates) == 1
    assert candidates[0].candidate.price == 1.17400 and candidates[0].target.price == 1.18000

    roles = classify_roles(scoped, current_price=1.17000)
    assert roles[level_id(scoped[0].level)] == ROLE_TARGET
    assert roles[level_id(scoped[1].level)] == ROLE_INDUCEMENT_CANDIDATE


def test_case_a_valid_bearish_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.23800, SCOPE_EXTERNAL),
        _scoped("SWING_LOW", LiquiditySide.SELL_SIDE, 1.24600, SCOPE_INTERNAL),
    ]
    candidates = find_inducement_candidates(scoped, current_price=1.25000)
    assert len(candidates) == 1
    assert candidates[0].candidate.price == 1.24600 and candidates[0].target.price == 1.23800


# --------------------------------------------------------------------------- Case B: internal liquidity, no target

def test_case_b_internal_liquidity_without_target_is_none():
    scoped = [_scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400, SCOPE_INTERNAL)]  # no external level at all
    roles = classify_roles(scoped, current_price=1.17000)
    assert roles[level_id(scoped[0].level)] == ROLE_NONE
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


# --------------------------------------------------------------------------- Case C: swept candidate

def test_case_c_swept_candidate_is_not_active_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400, SCOPE_INTERNAL, status=LiquidityStatus.CONSUMED),
    ]
    candidates = find_inducement_candidates(scoped, current_price=1.17000)
    assert candidates == ()
    assert classify_roles(scoped, current_price=1.17000)[level_id(scoped[1].level)] == ROLE_NONE


# --------------------------------------------------------------------------- negative tests (section 31)

def test_target_already_swept_yields_no_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL, status=LiquidityStatus.CONSUMED),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400, SCOPE_INTERNAL),
    ]
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


def test_candidate_beyond_target_is_not_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.19000, SCOPE_INTERNAL),  # beyond the target
    ]
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


def test_candidate_behind_current_price_is_not_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.16000, SCOPE_INTERNAL),  # below current price
    ]
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


def test_candidate_equals_target_is_not_inducement():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_INTERNAL),
    ]
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


def test_no_external_liquidity_yields_no_inducement():
    scoped = [_scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400, SCOPE_INTERNAL)]
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


def test_incompatible_side_does_not_cross_pair():
    # An internal SELL-side level must not be matched against a BUY-side external target.
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_LOWS", LiquiditySide.SELL_SIDE, 1.16500, SCOPE_INTERNAL),
    ]
    assert find_inducement_candidates(scoped, current_price=1.17000) == ()


def test_multiple_valid_candidates_all_returned_without_ranking():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17300, SCOPE_INTERNAL),
        _scoped("SWING_HIGH", LiquiditySide.BUY_SIDE, 1.17600, SCOPE_INTERNAL),
    ]
    candidates = find_inducement_candidates(scoped, current_price=1.17000)
    assert len(candidates) == 2
    assert {c.candidate.source for c in candidates} == {"EQUAL_HIGHS", "SWING_HIGH"}


# --------------------------------------------------------------------------- determinism (section 39)

def test_classification_is_deterministic_across_runs():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.18000, SCOPE_EXTERNAL),
        _scoped("EQUAL_HIGHS", LiquiditySide.BUY_SIDE, 1.17400, SCOPE_INTERNAL),
    ]
    roles_a = classify_roles(scoped, current_price=1.17000)
    roles_b = classify_roles(scoped, current_price=1.17000)
    assert roles_a == roles_b
