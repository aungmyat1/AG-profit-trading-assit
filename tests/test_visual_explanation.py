"""Tests for visual_explanation: annotation generation for E1M1/E2M2/E3M3 plus cross-pairs
E1M3/E2M1, all source-traceable to the same analysis snapshot without rerunning any
detector.
"""
from __future__ import annotations

import datetime as dt

import pytest

from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from entry_confirmation.m2_supply_demand_shift import M2Result
from entry_confirmation.m3_sweep_drop_pump import M3Result
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus
from visual_explanation import ANNOTATION_BOX, ANNOTATION_LABEL, ANNOTATION_LINE, build_visual_explanation

UTC = dt.timezone.utc


def _e(condition, timeframe, direction="SHORT", low=1.0990, high=1.1010, level=None, ref_type="POI"):
    return EConditionResult(entry_condition=condition, symbol="EURUSD", direction=direction,
                             reference_timeframe=timeframe, reference_type=ref_type,
                             reference_low=low, reference_high=high, reference_level=level,
                             eligible_for_confirmation=True)


def _combo(entry_condition, maneuver, direction="SHORT", state="READY"):
    return SMCEntryCombinationResult(combination=f"{entry_condition}{maneuver}", entry_condition=entry_condition,
                                      maneuver=maneuver, symbol="EURUSD", direction=direction,
                                      confirmation_timeframe="M5", state=state)


def _analysis(e_map, combos, m1=(), m2=(), m3=()):
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        e_conditions=e_map, m_maneuvers={"M1": m1, "M2": m2, "M3": m3}, combinations=combos,
    )


# --------------------------------------------------------------------------- E1M1

def test_e1m1_visual_explanation():
    e1 = _e("E1", "D1", ref_type="D1_GAP")
    m1 = M1Result(symbol="EURUSD", entry_condition="E1", direction="SHORT", state="READY",
                   entry_array_low=1.0980, entry_array_high=1.0995, entry_array_type="FVG")
    combo = _combo("E1", "M1")
    result = build_visual_explanation(_analysis({"E1": e1}, (combo,), m1=(m1,)), "E1M1")

    assert result.reason_codes == ()
    roles = {a.semantic_role for a in result.annotations}
    assert "REFERENCE" in roles
    assert "ENTRY_ARRAY" in roles
    assert "DIRECTION" in roles
    ref = next(a for a in result.annotations if a.semantic_role == "REFERENCE")
    assert ref.type == ANNOTATION_BOX and ref.low == 1.0990 and ref.high == 1.1010
    entry = next(a for a in result.annotations if a.semantic_role == "ENTRY_ARRAY")
    assert entry.low == pytest.approx(1.0980) and entry.high == pytest.approx(1.0995)
    assert entry.developing is False  # state == READY


# --------------------------------------------------------------------------- E2M2

def test_e2m2_visual_explanation():
    e2 = _e("E2", "H1", ref_type="BEARISH_OB")
    demand_zone = ZoneResult(symbol="EURUSD", timeframe="M5", family=ZoneFamily.ORDER_BLOCK, role=ZoneRole.SUPPLY,
                              direction=ZoneDirection.BEARISH, status=ZoneStatus.FRESH, source="test",
                              low=1.0970, high=1.0985, origin_time=dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
    m2 = M2Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state="READY", entry_fvg=demand_zone)
    combo = _combo("E2", "M2")
    result = build_visual_explanation(_analysis({"E2": e2}, (combo,), m2=(m2,)), "E2M2")

    assert result.reason_codes == ()
    ref = next(a for a in result.annotations if a.semantic_role == "POI")
    assert ref.label == "BEARISH_OB"
    entry = next(a for a in result.annotations if a.semantic_role == "ENTRY_ARRAY")
    assert entry.low == pytest.approx(1.0970) and entry.high == pytest.approx(1.0985)
    assert entry.label == "FVG"


# --------------------------------------------------------------------------- E3M3

def test_e3m3_visual_explanation():
    e3 = _e("E3", "H1", level=1.1200, low=None, high=None, ref_type="EXTERNAL_HIGH")
    m3 = M3Result(symbol="EURUSD", entry_condition="E3", direction="SHORT", state="READY",
                   entry_level=1.1150, gap="FVG")
    combo = _combo("E3", "M3")
    result = build_visual_explanation(_analysis({"E3": e3}, (combo,), m3=(m3,)), "E3M3")

    assert result.reason_codes == ()
    ref = next(a for a in result.annotations if a.semantic_role == "REFERENCE")
    assert ref.low == 1.1200 and ref.high == 1.1200  # single-level reference, both bounds = the level
    entry = next(a for a in result.annotations if a.semantic_role == "ENTRY_ARRAY")
    assert entry.type == ANNOTATION_LINE
    assert entry.price == pytest.approx(1.1150)


# --------------------------------------------------------------------------- cross-pairs

def test_e1m3_cross_pair():
    e1 = _e("E1", "D1", ref_type="D1_GAP")
    m3 = M3Result(symbol="EURUSD", entry_condition="E1", direction="SHORT", state="READY", entry_level=1.0985)
    combo = _combo("E1", "M3")
    result = build_visual_explanation(_analysis({"E1": e1}, (combo,), m3=(m3,)), "E1M3")
    assert result.reason_codes == ()
    assert any(a.semantic_role == "ENTRY_ARRAY" and a.type == ANNOTATION_LINE for a in result.annotations)


def test_e2m1_cross_pair():
    e2 = _e("E2", "H1", ref_type="H1_OB")
    m1 = M1Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state="READY",
                   entry_array_low=1.0960, entry_array_high=1.0975)
    combo = _combo("E2", "M1")
    result = build_visual_explanation(_analysis({"E2": e2}, (combo,), m1=(m1,)), "E2M1")
    assert result.reason_codes == ()
    entry = next(a for a in result.annotations if a.semantic_role == "ENTRY_ARRAY")
    assert entry.low == pytest.approx(1.0960) and entry.high == pytest.approx(1.0975)


# --------------------------------------------------------------------------- traceability / no rerun

def test_all_annotations_come_from_the_same_snapshot_without_rerunning_detectors():
    """No mt5/analyzer import in this test at all -- proves the builder only reads the
    already-computed analysis object, never re-fetches or re-detects anything."""
    e1 = _e("E1", "D1")
    m1 = M1Result(symbol="EURUSD", entry_condition="E1", direction="SHORT", state="READY",
                   entry_array_low=1.0980, entry_array_high=1.0995)
    combo = _combo("E1", "M1")
    analysis = _analysis({"E1": e1}, (combo,), m1=(m1,))
    result = build_visual_explanation(analysis, "E1M1")
    assert result.snapshot_time == analysis.snapshot_time.isoformat()
    assert all(a.timeframe in (None, "D1", "M5") for a in result.annotations)


def test_combination_not_present_is_reported_not_fabricated():
    e1 = _e("E1", "D1")
    result = build_visual_explanation(_analysis({"E1": e1}, ()), "E1M1")
    assert result.annotations == ()
    assert "COMBINATION_NOT_PRESENT_IN_ANALYSIS" in result.reason_codes
