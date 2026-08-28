"""Focused tests for DAYTRADING_LIQUIDITY_AFFINITY_V1 (daytrading/liquidity_affinity.py),
spec sections 33-42. Pure/offline -- no MT5 connection, no candle fetch; every input is
hand-built, matching liquidity/hierarchy and liquidity/affinity's own test fixture style."""
from __future__ import annotations

from datetime import datetime, timezone

from daytrading.liquidity_affinity import evaluate_liquidity_affinity
from daytrading.models import (
    AFFINITY_CONFLICTED,
    AFFINITY_INSUFFICIENT_DATA,
    AFFINITY_RESOLVED,
    AFFINITY_UNRESOLVED,
    BIAS_BEARISH,
    BIAS_BULLISH,
    BIAS_UNRESOLVED,
    NarrativeBiasResult,
    PHASE_CORRECTIVE,
    PHASE_IMPULSIVE,
    REL_RETURNING_INTERNAL,
    SESSION_CONTEXT_DETECTED,
    SESSION_CONTEXT_NOT_AVAILABLE,
    SESSION_CONTEXT_RELEVANT,
    TERMINAL_POLICY_UNRESOLVED,
    TERMINAL_UNRESOLVED,
)
from liquidity.hierarchy import SCOPE_EXTERNAL, SCOPE_INTERNAL, ScopedLiquidityLevel, level_id
from liquidity.models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from market_structure.models import STATE_BEARISH, STATE_BULLISH, StructureTier, TieredStructureResult
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from supply_demand.native_zones import dealing_range_zones

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _level(source, side, price, status=LiquidityStatus.UNSWEPT) -> LiquidityLevel:
    return LiquidityLevel(symbol="EURUSD", timeframe="H1", side=side, source=source, price=price,
                           origin_time=NOW, status=status)


def _scoped(source, side, price, scope, status=LiquidityStatus.UNSWEPT) -> ScopedLiquidityLevel:
    lvl = _level(source, side, price, status)
    return ScopedLiquidityLevel(level=lvl, scope=scope, level_id=level_id(lvl))


def _liquidity(*levels, status="LIQUIDITY_OK") -> LiquidityResult:
    nearest_buy = next((l for l in levels if l.side == LiquiditySide.BUY_SIDE), None)
    nearest_sell = next((l for l in levels if l.side == LiquiditySide.SELL_SIDE), None)
    return LiquidityResult(symbol="EURUSD", timeframe="H1", status=status, levels=tuple(levels),
                            nearest_buy_side=nearest_buy, nearest_sell_side=nearest_sell)


def _tier(name, direction, swing_length=50, latest_swing_high=None, latest_swing_low=None) -> StructureTier:
    return StructureTier(tier=name, swing_length=swing_length, direction=direction, swings=(), events=(),
                          latest_swing_high=latest_swing_high, latest_swing_low=latest_swing_low)


def _tiers(external, internal) -> TieredStructureResult:
    return TieredStructureResult(symbol="EURUSD", timeframe="H1", status="VALID", reason_codes=(),
                                  external=external, internal=internal)


def _fvg(direction, low, high, status=ZoneStatus.FRESH) -> ZoneResult:
    return ZoneResult(symbol="EURUSD", timeframe="H1", family=ZoneFamily.FVG,
                       role=ZoneRole.DEMAND if direction == ZoneDirection.BULLISH else ZoneRole.SUPPLY,
                       direction=direction, status=status, source="smc.fvg", low=low, high=high, origin_time=NOW)


_BULLISH = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BULLISH, status="OK")
_BEARISH = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_BEARISH, status="OK")
_UNRESOLVED = NarrativeBiasResult(symbol="EURUSD", reference_timeframe="D1", bias=BIAS_UNRESOLVED, status="OK")


# =========================================================================== section 33: external liquidity

def test_external_bsl_and_ssl_are_labeled_with_status():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL),
        _scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL, status=LiquidityStatus.CONSUMED),
    ]
    liq = _liquidity(scoped[0].level, scoped[1].level)
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped)
    assert any("EXTERNAL_BUY_SIDE@1.19" in l and "UNSWEPT" in l for l in result.external_liquidity)
    assert any("EXTERNAL_SELL_SIDE@1.17" in l and "CONSUMED" in l for l in result.external_liquidity)


def test_external_consumed_vs_remaining_partition():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL, status=LiquidityStatus.CONSUMED),
        _scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL),
    ]
    liq = _liquidity(scoped[0].level, scoped[1].level)
    result = evaluate_liquidity_affinity("EURUSD", _BEARISH, liq, scoped_levels=scoped)
    assert len(result.consumed_liquidity) == 1 and "CONSUMED" in result.consumed_liquidity[0]
    assert len(result.remaining_liquidity) == 1 and "UNSWEPT" in result.remaining_liquidity[0]


def test_no_structural_context_still_labels_liquidity_but_stays_unresolved():
    result = evaluate_liquidity_affinity("EURUSD", _UNRESOLVED, None)
    assert result.status == AFFINITY_UNRESOLVED
    assert result.external_liquidity == ()


# =========================================================================== section 34: internal liquidity

def test_internal_swing_and_fvg_both_labeled_distinctly():
    scoped = [_scoped("EQUAL_LOWS", LiquiditySide.SELL_SIDE, 1.1750, SCOPE_INTERNAL)]
    fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1760)
    liq = _liquidity(scoped[0].level)
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped, imbalances=(fvg,))
    assert any(l.startswith("INTERNAL_SELL_SIDE@1.175") for l in result.internal_liquidity)
    assert any(l.startswith("INTERNAL_FVG@1.174-1.176") for l in result.internal_liquidity)


def test_no_internal_liquidity_is_empty_not_fabricated():
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, _liquidity())
    assert result.internal_liquidity == ()


# =========================================================================== section 35: external/internal relationship

def test_bullish_external_internal_relationship_maps_to_returning_internal():
    external = _tier("EXTERNAL", STATE_BULLISH)
    internal = _tier("INTERNAL", STATE_BEARISH)  # corrective leg opposing external bias
    tiers = _tiers(external, internal)
    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1770)
    liq = _liquidity(scoped[0].level, _level("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1650))

    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, tiers=tiers, scoped_levels=scoped,
                                          imbalances=(fvg,), current_price=1.1780)

    assert result.status == AFFINITY_RESOLVED
    assert result.market_phase == PHASE_CORRECTIVE
    assert result.external_internal_relationship == REL_RETURNING_INTERNAL
    assert "FVG" in (result.internal_rebalance_target or "")


def test_bearish_external_internal_relationship_mirrors():
    external = _tier("EXTERNAL", STATE_BEARISH)
    internal = _tier("INTERNAL", STATE_BULLISH)
    tiers = _tiers(external, internal)
    scoped = [_scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL)]
    fvg = _fvg(ZoneDirection.BEARISH, 1.1830, 1.1860)
    liq = _liquidity(scoped[0].level, _level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1950))

    result = evaluate_liquidity_affinity("EURUSD", _BEARISH, liq, tiers=tiers, scoped_levels=scoped,
                                          imbalances=(fvg,), current_price=1.1820)

    assert result.status == AFFINITY_RESOLVED
    assert result.external_internal_relationship == REL_RETURNING_INTERNAL


# =========================================================================== section 36: impulse/correction

def test_market_phase_impulsive_when_internal_agrees_with_external():
    external = _tier("EXTERNAL", STATE_BULLISH)
    internal = _tier("INTERNAL", STATE_BULLISH)
    tiers = _tiers(external, internal)
    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    liq = _liquidity(scoped[0].level)
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, tiers=tiers, scoped_levels=scoped,
                                          current_price=1.1780)
    assert result.market_phase == PHASE_IMPULSIVE


def test_market_phase_unresolved_without_tiers():
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, _liquidity(
        _level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900)))
    assert result.market_phase == "UNRESOLVED"


# =========================================================================== section 37: BOS + internal gap (no entry)

def test_bos_and_internal_gap_context_never_produces_an_entry_field():
    external = _tier("EXTERNAL", STATE_BULLISH)
    internal = _tier("INTERNAL", STATE_BEARISH)
    tiers = _tiers(external, internal)
    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    fvg = _fvg(ZoneDirection.BULLISH, 1.1740, 1.1770)
    liq = _liquidity(scoped[0].level, _level("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1650))
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, tiers=tiers, scoped_levels=scoped,
                                          imbalances=(fvg,), current_price=1.1780)
    assert not hasattr(result, "entry_price") and not hasattr(result, "stop_loss")
    assert result.status == AFFINITY_RESOLVED  # context only -- no execution field exists on this result at all


# =========================================================================== section 38: session liquidity

def test_session_sweep_opposing_h1_structure_is_relevant():
    swept_asian_high = _level("ASIAN_HIGH", LiquiditySide.BUY_SIDE, 1.1850, status=LiquidityStatus.RECLAIMED)
    liq = _liquidity(swept_asian_high)
    external = _tier("EXTERNAL", STATE_BEARISH)
    tiers = _tiers(external, _tier("INTERNAL", STATE_BEARISH))
    result = evaluate_liquidity_affinity("EURUSD", _BEARISH, liq, tiers=tiers)
    assert result.session_liquidity is not None
    assert result.session_liquidity.swept_side == "BUY_SIDE"
    assert result.session_liquidity.sweep_opposes_h1_structure is True
    assert result.session_liquidity.status == SESSION_CONTEXT_RELEVANT


def test_session_sweep_aligned_with_h1_structure_is_only_detected():
    swept_asian_low = _level("ASIAN_LOW", LiquiditySide.SELL_SIDE, 1.1650, status=LiquidityStatus.RECLAIMED)
    liq = _liquidity(swept_asian_low)
    external = _tier("EXTERNAL", STATE_BEARISH)
    tiers = _tiers(external, _tier("INTERNAL", STATE_BEARISH))
    result = evaluate_liquidity_affinity("EURUSD", _BEARISH, liq, tiers=tiers)
    assert result.session_liquidity.sweep_opposes_h1_structure is False
    assert result.session_liquidity.status == SESSION_CONTEXT_DETECTED


def test_session_liquidity_not_available_without_session_sources():
    liq = _liquidity(_level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900))
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq)
    assert result.session_liquidity.status == SESSION_CONTEXT_NOT_AVAILABLE


def test_session_sweep_without_narrative_or_h1_context_stays_unresolved():
    # spec section 53: session liquidity is not a holy grail -- a sweep alone, with
    # narrative UNRESOLVED, must never resolve a trade context.
    swept = _level("ASIAN_HIGH", LiquiditySide.BUY_SIDE, 1.1850, status=LiquidityStatus.RECLAIMED)
    liq = _liquidity(swept)
    result = evaluate_liquidity_affinity("EURUSD", _UNRESOLVED, liq)
    assert result.status == AFFINITY_UNRESOLVED
    assert result.session_liquidity is not None  # still detected/mapped...
    assert result.primary_draw is None            # ...but never turned into a directional draw


# =========================================================================== section 39: entry-side vs target-side

def test_bullish_entry_and_target_side_distinction():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL),
        _scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL),
    ]
    liq = _liquidity(scoped[0].level, scoped[1].level)
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped)
    assert result.entry_side_liquidity == "SELL_SIDE"
    assert result.target_side_liquidity == "BUY_SIDE"
    assert result.primary_target_price == 1.1900


def test_bearish_entry_and_target_side_distinction():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL),
        _scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL),
    ]
    liq = _liquidity(scoped[0].level, scoped[1].level)
    result = evaluate_liquidity_affinity("EURUSD", _BEARISH, liq, scoped_levels=scoped)
    assert result.entry_side_liquidity == "BUY_SIDE"
    assert result.target_side_liquidity == "SELL_SIDE"


# =========================================================================== section 40: consumed target

def test_consumed_target_never_blindly_reused():
    liq = _liquidity(_level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, status=LiquidityStatus.CONSUMED))
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq)
    assert result.status == AFFINITY_UNRESOLVED
    assert result.target_side_liquidity is None or result.primary_draw is None


# =========================================================================== section 41: sweep != direction

def test_entry_side_sweep_does_not_flip_target_direction():
    scoped = [
        _scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL),  # target, unswept
        _scoped("EXTERNAL_SWING_LOW", LiquiditySide.SELL_SIDE, 1.1700, SCOPE_EXTERNAL, status=LiquidityStatus.CONSUMED),
    ]
    liq = _liquidity(scoped[0].level, scoped[1].level)
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped)
    # SSL (entry-side) already swept -- continuation bullish target must still stand.
    assert result.target_side_liquidity == "BUY_SIDE"
    assert result.primary_draw == "BUY_SIDE"


# =========================================================================== section 28/29: conflicts

def test_h1_structure_conflicting_with_narrative_is_conflicted_not_forced():
    external = _tier("EXTERNAL", STATE_BEARISH)  # disagrees with bullish narrative
    tiers = _tiers(external, _tier("INTERNAL", STATE_BEARISH))
    liq = _liquidity(_level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900))
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, tiers=tiers)
    assert result.status == AFFINITY_CONFLICTED
    assert result.primary_draw is None
    assert result.contradictions


# =========================================================================== section 30: affinity never overrides narrative

def test_unresolved_narrative_with_clear_liquidity_stays_unresolved():
    liq = _liquidity(_level("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900))
    result = evaluate_liquidity_affinity("EURUSD", _UNRESOLVED, liq)
    assert result.status == AFFINITY_UNRESOLVED
    assert result.primary_draw is None


# =========================================================================== section 31: zero look-ahead / determinism

def test_identical_inputs_always_produce_identical_result():
    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    liq = _liquidity(scoped[0].level)
    r1 = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped)
    r2 = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped)
    assert r1 == r2


# =========================================================================== section 42: engineered terminal liquidity

def test_terminal_liquidity_always_reports_policy_unresolved():
    scoped = [_scoped("EXTERNAL_SWING_HIGH", LiquiditySide.BUY_SIDE, 1.1900, SCOPE_EXTERNAL)]
    liq = _liquidity(scoped[0].level)
    result = evaluate_liquidity_affinity("EURUSD", _BULLISH, liq, scoped_levels=scoped)
    assert result.terminal_liquidity_pattern == TERMINAL_UNRESOLVED
    assert result.terminal_liquidity_policy == TERMINAL_POLICY_UNRESOLVED
