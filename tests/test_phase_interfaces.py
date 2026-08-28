"""Lightweight cross-layer interface freeze checks (Phase 1-4 stabilization pass,
2026-08-27). These protect the externally-consumed field names each phase hands to the
next -- Phase 5 (and any future consumer) is expected to read these fields rather than
recompute the underlying analysis (see docs/status/PHASE_1_4_FREEZE_STATUS.md's interface section).
Not a test of implementation internals: only that the field a downstream module already
depends on still exists with its documented name.
"""
from __future__ import annotations

import dataclasses

from liquidity.models import LiquidityLevel, LiquidityResult
from market_structure.models import StructureResult
from strategy_engine.session import Candle
from supply_demand.ob_contract import ValidatedOrderBlock


def _field_names(cls) -> set:
    return {f.name for f in dataclasses.fields(cls)}


def test_candle_interface_is_stable():
    assert {"time", "open", "high", "low", "close", "volume"}.issubset(_field_names(Candle))


def test_structure_result_interface_is_stable():
    assert {"symbol", "timeframe", "status", "reason_codes", "state",
            "latest_swing_high", "latest_swing_low", "latest_bos", "latest_choch",
            "previous_high", "previous_low"}.issubset(_field_names(StructureResult))


def test_validated_order_block_interface_is_stable():
    assert {"symbol", "timeframe"}.issubset(_field_names(ValidatedOrderBlock))


def test_liquidity_result_interface_is_stable():
    assert {"symbol", "timeframe", "status", "reason_codes", "levels",
            "nearest_buy_side", "nearest_sell_side"}.issubset(_field_names(LiquidityResult))


def test_liquidity_level_retains_source_and_sources_for_backward_compatibility():
    """`source` (singular, first-detected) predates this pass; `sources` (the full
    provenance tuple) was added by the Phase 4 continuation pass. Both must keep
    working -- a consumer written against the old single-`source` shape must not break."""
    fields = _field_names(LiquidityLevel)
    assert "source" in fields
    assert "sources" in fields
