"""Tests for chart_renderer.render_annotations: consumes a visual_explanation.Annotation
list directly (BOX/LINE/MARKER/LABEL), draws exactly what it's given (artist-count
assertions), performs no SMC detection of its own, and produces a real PNG file.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from chart_renderer import render_annotations
from entry_confirmation.entry_models_v1 import EConditionResult, SMCConditionalEntryAnalysis, SMCEntryCombinationResult
from entry_confirmation.m1_character_change_inducement import M1Result
from strategy_engine.session import Candle
from visual_explanation import build_visual_explanation

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _candles(n=20):
    out = []
    price = 1.1000
    for i in range(n):
        price += 0.0002 if i % 2 == 0 else -0.0001
        out.append(Candle(time=START + timedelta(hours=i), open=price, high=price + 0.0003,
                           low=price - 0.0003, close=price + 0.0001, volume=1.0))
    return out


def _ready_e2m1_analysis():
    e2 = EConditionResult(entry_condition="E2", symbol="EURUSD", direction="SHORT",
                           reference_timeframe="H1", reference_type="BEARISH_OB",
                           reference_low=1.0990, reference_high=1.1010, eligible_for_confirmation=True)
    m1 = M1Result(symbol="EURUSD", entry_condition="E2", direction="SHORT", state="READY",
                   entry_array_low=1.0980, entry_array_high=1.0995, entry_array_type="FVG",
                   invalidation_price=1.1060, invalidation_source_type="INDUCEMENT_LEVEL")
    combo = SMCEntryCombinationResult(combination="E2M1", entry_condition="E2", maneuver="M1", symbol="EURUSD",
                                       direction="SHORT", confirmation_timeframe="H1", state="READY",
                                       invalidation_price=1.1060, invalidation_source_type="INDUCEMENT_LEVEL")
    return SMCConditionalEntryAnalysis(
        symbol="EURUSD", snapshot_time=START + timedelta(hours=15),
        e_conditions={"E2": e2}, m_maneuvers={"M1": (m1,)}, combinations=(combo,),
    )


def test_render_annotations_from_visual_explanation_produces_file(tmp_path):
    analysis = _ready_e2m1_analysis()
    visual = build_visual_explanation(analysis, "E2M1")
    out_path = str(tmp_path / "e2m1.png")

    result = render_annotations(_candles(20), visual.annotations, out_path, title="E2M1 SHORT")

    assert result.candle_count == 20
    box_count = sum(1 for a in visual.annotations if a.type == "BOX")
    line_count = sum(1 for a in visual.annotations if a.type == "LINE")
    assert result.zone_rect_count == box_count
    assert result.liquidity_line_count == line_count
    assert os.path.exists(out_path) and os.path.getsize(out_path) > 0


def test_render_annotations_draws_exactly_what_it_is_given_no_detection(tmp_path):
    """Feeding zero annotations must draw zero boxes/lines/markers -- the renderer
    never invents its own zones/liquidity/structure from the candles."""
    out_path = str(tmp_path / "empty.png")
    result = render_annotations(_candles(10), (), out_path)
    assert result.candle_count == 10
    assert result.zone_rect_count == 0 and result.liquidity_line_count == 0
    assert result.swing_label_count == 0 and result.event_marker_count == 0


def test_render_annotations_supports_timeframe_filtered_views(tmp_path):
    """Spec section 33: separate HTF/H1/M5 views -- caller filters annotations by
    `.timeframe` before calling, once per view."""
    analysis = _ready_e2m1_analysis()
    visual = build_visual_explanation(analysis, "E2M1")
    h1_only = tuple(a for a in visual.annotations if a.timeframe == "H1")
    assert h1_only  # the fixture's reference annotation is H1-scoped

    out_path = str(tmp_path / "h1_view.png")
    result = render_annotations(_candles(20), h1_only, out_path, title="H1 view")
    assert os.path.exists(out_path) and os.path.getsize(out_path) > 0
