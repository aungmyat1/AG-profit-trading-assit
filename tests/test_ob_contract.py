"""Tests for supply_demand.ob_contract: the AG Order Block Validator (AG_ORDER_BLOCK_V1).

Structure/FVG detection themselves were already verified in Phase 2/3 (real
smc.swing_highs_lows/bos_choch/fvg calls against live and synthetic data); these tests
supply pre-built StructurePoint/ZoneResult fixtures directly to validate_order_block()
so the contract logic (family classification, structure/FVG requirements, mitigation,
invalidation) is tested in isolation, deterministically.
"""
from __future__ import annotations

import datetime as dt

import pytest

from market_structure.models import StructurePoint, StructurePointKind
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from supply_demand.ob_config import AGOrderBlockConfig, load_ag_order_block_config
from supply_demand.ob_contract import (
    ORDER_BLOCK_CONTRACT_GAPS,
    OBFamily,
    OBValidationStatus,
    validate_order_block,
)

UTC = dt.timezone.utc


def _t(i, base=dt.datetime(2026, 1, 5, tzinfo=UTC)):
    return base + dt.timedelta(minutes=15 * i)


def _candle(i, o, h, l, c):
    return Candle(time=_t(i), open=o, high=h, low=l, close=c, volume=1.0)


def _ob_candidate(origin_index, low, high, direction=ZoneDirection.BULLISH):
    return ZoneResult(
        symbol="EURUSD", timeframe="M15", family=ZoneFamily.ORDER_BLOCK,
        role=ZoneRole.DEMAND if direction == ZoneDirection.BULLISH else ZoneRole.SUPPLY,
        direction=direction, low=low, high=high, origin_time=_t(origin_index),
        status=ZoneStatus.FRESH, source="smc.ob", raw_strength_metric=40.0,
    )


def _fvg_candidate(origin_index, low, high, direction):
    return ZoneResult(
        symbol="EURUSD", timeframe="M15", family=ZoneFamily.FVG,
        role=ZoneRole.DEMAND if direction == ZoneDirection.BULLISH else ZoneRole.SUPPLY,
        direction=direction, low=low, high=high, origin_time=_t(origin_index),
        status=ZoneStatus.FRESH, source="smc.fvg",
    )


def _break(index, kind):
    return StructurePoint(time_utc=_t(index), price=1.10, kind=kind)


# --------------------------------------------------------------------------- setup helpers

# origin candle at index 2, PIVOT geometry (body-dominant): body 0.0008 / range 0.0015 = 0.53
_PIVOT_BULLISH_ORIGIN = _candle(2, o=1.1000, h=1.1010, l=1.0995, c=1.1008)
_PIVOT_BEARISH_ORIGIN = _candle(2, o=1.1010, h=1.1015, l=1.1000, c=1.1002)

# origin candle at index 2, SHADOW geometry (wick-dominant): body 0.0003 / range 0.0060 = 0.05
_SHADOW_BULLISH_ORIGIN = _candle(2, o=1.1005, h=1.1010, l=1.0950, c=1.1008)


def _no_touch_after(n=6, start=3, level_above=1.1200):
    """Candles that never wick back into a bullish zone below `level_above`."""
    return [_candle(i, level_above, level_above + 0.0010, level_above - 0.0002, level_above) for i in range(start, start + n)]


# --------------------------------------------------------------------------- valid PIVOT + FVG

def test_valid_bullish_pivot_ob_with_matching_fvg():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BULLISH_ORIGIN, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0995, high=1.1010, direction=ZoneDirection.BULLISH)
    fvg = _fvg_candidate(3, low=1.1015, high=1.1025, direction=ZoneDirection.BULLISH)
    breaks = [_break(3, StructurePointKind.BULLISH_BOS)]

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=breaks)

    assert result.family == OBFamily.PIVOT_OB
    assert result.status == OBValidationStatus.VALID
    assert result.reason_codes == ("VALID_OB",)
    assert result.low == pytest.approx(1.0995)
    assert result.high == pytest.approx(1.1010)
    assert result.matching_fvg is fvg
    assert result.structure_event is breaks[0]


def test_valid_bearish_pivot_ob_with_matching_fvg():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BEARISH_ORIGIN,
               *[_candle(i, 1.0900, 1.0902, 1.0890, 1.0895) for i in range(3, 9)]]  # stays below the zone
    candidate = _ob_candidate(2, low=1.1000, high=1.1015, direction=ZoneDirection.BEARISH)
    fvg = _fvg_candidate(3, low=1.0880, high=1.0890, direction=ZoneDirection.BEARISH)
    breaks = [_break(3, StructurePointKind.BEARISH_BOS)]

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=breaks)

    assert result.family == OBFamily.PIVOT_OB
    assert result.status == OBValidationStatus.VALID
    assert result.reason_codes == ("VALID_OB",)


# --------------------------------------------------------------------------- FVG rejections

def test_missing_fvg_is_rejected():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BULLISH_ORIGIN, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0995, high=1.1010)
    breaks = [_break(3, StructurePointKind.BULLISH_BOS)]

    result = validate_order_block(candidate, candles, fvg_candidates=[], breaks=breaks)

    assert result.status == OBValidationStatus.REJECTED
    assert "REQUIRED_FVG_MISSING" in result.reason_codes
    assert "REQUIRED_STRUCTURE_MISSING" not in result.reason_codes


def test_opposite_direction_fvg_is_rejected():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BULLISH_ORIGIN, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0995, high=1.1010, direction=ZoneDirection.BULLISH)
    wrong_fvg = _fvg_candidate(3, low=1.0970, high=1.0980, direction=ZoneDirection.BEARISH)
    breaks = [_break(3, StructurePointKind.BULLISH_BOS)]

    result = validate_order_block(candidate, candles, fvg_candidates=[wrong_fvg], breaks=breaks)

    assert result.status == OBValidationStatus.REJECTED
    assert "FVG_DIRECTION_MISMATCH" in result.reason_codes


def test_fvg_after_more_than_three_candles_is_rejected():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BULLISH_ORIGIN, *_no_touch_after(n=10)]
    candidate = _ob_candidate(2, low=1.0995, high=1.1010, direction=ZoneDirection.BULLISH)
    late_fvg = _fvg_candidate(2 + 4, low=1.1030, high=1.1040, direction=ZoneDirection.BULLISH)  # distance 4 > MAX_CANDLES_TO_FVG (3)
    breaks = [_break(3, StructurePointKind.BULLISH_BOS)]

    result = validate_order_block(candidate, candles, fvg_candidates=[late_fvg], breaks=breaks)

    assert result.status == OBValidationStatus.REJECTED
    assert "FVG_TOO_LATE" in result.reason_codes


def test_required_structure_missing_is_rejected():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BULLISH_ORIGIN, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0995, high=1.1010, direction=ZoneDirection.BULLISH)
    fvg = _fvg_candidate(3, low=1.1015, high=1.1025, direction=ZoneDirection.BULLISH)

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=[])

    assert result.status == OBValidationStatus.REJECTED
    assert "REQUIRED_STRUCTURE_MISSING" in result.reason_codes


# --------------------------------------------------------------------------- Shadow OB geometry

def test_shadow_ob_wick_zone_geometry():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _SHADOW_BULLISH_ORIGIN, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0950, high=1.1010, direction=ZoneDirection.BULLISH)  # smc's own FULL_CANDLE Top/Bottom, ignored for SHADOW

    result = validate_order_block(candidate, candles, fvg_candidates=[], breaks=[])

    assert result.family == OBFamily.SHADOW_OB
    # WICK_TIP_TO_BODY: low = wick tip (candle low), high = body edge (min(open,close))
    assert result.low == pytest.approx(1.0950)
    assert result.high == pytest.approx(1.1005)  # min(open=1.1005, close=1.1008)


# --------------------------------------------------------------------------- PIVOT/SHADOW threshold authority

def test_default_config_threshold_is_0_5():
    config = load_ag_order_block_config()
    assert config.pivot_shadow_body_ratio_threshold == pytest.approx(0.5)


def test_body_ratio_exactly_at_threshold_is_pivot():
    # body 0.01 / range 0.02 = 0.5 exactly (float-exact values) -- boundary is inclusive (>=)
    origin = _candle(2, o=1.10, h=1.12, l=1.10, c=1.11)
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               origin, *_no_touch_after(level_above=1.1300)]
    candidate = _ob_candidate(2, low=1.10, high=1.12, direction=ZoneDirection.BULLISH)

    result = validate_order_block(candidate, candles, fvg_candidates=[], breaks=[])
    assert result.family == OBFamily.PIVOT_OB


def test_body_ratio_just_below_threshold_is_shadow():
    # body 0.0005 / range 0.0011 ~= 0.4545 < 0.5
    origin = _candle(2, o=1.1000, h=1.1007, l=1.0996, c=1.1005)
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               origin, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0996, high=1.1007, direction=ZoneDirection.BULLISH)

    result = validate_order_block(candidate, candles, fvg_candidates=[], breaks=[])
    assert result.family == OBFamily.SHADOW_OB


def test_threshold_is_actually_configurable():
    # Same candle (body_ratio ~0.4545) classifies differently under a lower, explicit threshold.
    origin = _candle(2, o=1.1000, h=1.1007, l=1.0996, c=1.1005)
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               origin, *_no_touch_after()]
    candidate = _ob_candidate(2, low=1.0996, high=1.1007, direction=ZoneDirection.BULLISH)

    default_result = validate_order_block(candidate, candles, fvg_candidates=[], breaks=[])
    assert default_result.family == OBFamily.SHADOW_OB

    lower_threshold = AGOrderBlockConfig(pivot_shadow_body_ratio_threshold=0.4)
    overridden_result = validate_order_block(candidate, candles, fvg_candidates=[], breaks=[], config=lower_threshold)
    assert overridden_result.family == OBFamily.PIVOT_OB


# --------------------------------------------------------------------------- lifecycle: mitigation / invalidation

def _valid_setup(after_candles):
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BULLISH_ORIGIN, *after_candles]
    candidate = _ob_candidate(2, low=1.0995, high=1.1010, direction=ZoneDirection.BULLISH)
    fvg = _fvg_candidate(3, low=1.1015, high=1.1025, direction=ZoneDirection.BULLISH)
    breaks = [_break(3, StructurePointKind.BULLISH_BOS)]
    return candidate, candles, fvg, breaks


def test_mitigation_by_boundary_touch():
    # wick dips back down to touch the zone's high boundary (1.1010) without closing below the zone's low (0.0995)
    after = [_candle(3, 1.1200, 1.1210, 1.1195, 1.1200), _candle(4, 1.1200, 1.1201, 1.1009, 1.1100)]
    candidate, candles, fvg, breaks = _valid_setup(after)

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=breaks)

    assert result.status == OBValidationStatus.MITIGATED
    assert result.reason_codes == ("OB_MITIGATED",)


def test_bullish_close_below_zone_low_is_invalidated():
    after = [_candle(3, 1.1200, 1.1210, 1.1195, 1.1200), _candle(4, 1.1000, 1.1000, 1.0980, 1.0990)]  # closes below 1.0995
    candidate, candles, fvg, breaks = _valid_setup(after)

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=breaks)

    assert result.status == OBValidationStatus.INVALIDATED
    assert result.reason_codes == ("OB_INVALIDATED",)


def test_bearish_close_above_zone_high_is_invalidated():
    candles = [_candle(0, 1.10, 1.1005, 1.0995, 1.10), _candle(1, 1.10, 1.1005, 1.0995, 1.10),
               _PIVOT_BEARISH_ORIGIN,
               _candle(3, 1.0900, 1.0902, 1.0890, 1.0895),
               _candle(4, 1.1000, 1.1030, 1.0990, 1.1020)]  # closes above zone high 1.1015
    candidate = _ob_candidate(2, low=1.1000, high=1.1015, direction=ZoneDirection.BEARISH)
    fvg = _fvg_candidate(3, low=1.0880, high=1.0890, direction=ZoneDirection.BEARISH)
    breaks = [_break(3, StructurePointKind.BEARISH_BOS)]

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=breaks)

    assert result.status == OBValidationStatus.INVALIDATED
    assert result.reason_codes == ("OB_INVALIDATED",)


def test_wick_penetration_without_close_beyond_is_not_invalidated():
    # wick pierces clean through the whole zone (low goes below 0.0995) but CLOSES back inside/above it
    after = [_candle(3, 1.1005, 1.1008, 1.0985, 1.1000)]  # low=1.0985 < zone low 1.0995, close=1.1000 >= 1.0995
    candidate, candles, fvg, breaks = _valid_setup(after)

    result = validate_order_block(candidate, candles, fvg_candidates=[fvg], breaks=breaks)

    assert result.status == OBValidationStatus.MITIGATED  # touched, not invalidated
    assert result.status != OBValidationStatus.INVALIDATED


# --------------------------------------------------------------------------- contract gaps documented

def test_contract_gaps_documents_flip_ob_and_unsigned_items():
    families = {g.family for g in ORDER_BLOCK_CONTRACT_GAPS}
    assert "FLIP_OB" in families
    items = {(g.family, g.item) for g in ORDER_BLOCK_CONTRACT_GAPS}
    assert ("FLIP_OB", "L1_L2") in items
    assert ("FLIP_OB", "inside_bar") in items


# --------------------------------------------------------------------------- live verification

def _mt5_available():
    import MetaTrader5 as mt5
    return mt5.initialize()


@pytest.mark.skipif(not _mt5_available(), reason="requires a running, logged-in MT5 terminal")
def test_validated_order_blocks_live_reach_real_statuses():
    from mt5.connection import connect
    from supply_demand import validated_order_blocks_for

    connect()
    vobs = validated_order_blocks_for("EURUSD", "H1")
    assert len(vobs) > 0
    statuses = {v.status for v in vobs}
    families = {v.family for v in vobs}
    # With AG_ORDER_BLOCK_V1, VALID/MITIGATED/INVALIDATED/REJECTED are all reachable now.
    assert statuses.issubset({OBValidationStatus.VALID, OBValidationStatus.MITIGATED,
                               OBValidationStatus.INVALIDATED, OBValidationStatus.REJECTED})
    assert families.issubset({OBFamily.PIVOT_OB, OBFamily.SHADOW_OB, OBFamily.UNKNOWN_OB})
    assert OBFamily.FLIP_OB not in families  # never assigned -- see ob_contract.py
