"""Market Swing Structure orchestration (P4/P17/P23) -- the only place in this package
that calls the canonical engines. This module DISCOVERS, REUSES, and NORMALIZES; it
never computes a swing, a BOS/CHoCH, a liquidity level, or a zone itself.

Reused engines (never reimplemented):
  - market_structure.analyze_structure()      -- swings, BOS/CHoCH, structure_state
  - supply_demand.dealing_range_zones()        -- premium/equilibrium/discount arithmetic
                                                   (via .dealing_range's swing-pair selection)
  - liquidity.liquidity_result()               -- EQH/EQL, PDH/PDL, session levels, sweeps
  - supply_demand.fair_value_gaps_for()         -- FVG detection + mitigation state

This module never imports execution/, authorization/, or any lifecycle/promotion
module -- see tests/test_market_swing_structure.py::test_orchestrator_imports_no_execution_or_authority_modules.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence, Tuple

from liquidity import liquidity_result
from market_structure.analyzer import analyze_structure
from market_structure.models import StructureResult
from mt5.market_data import MarketDataError, get_tick
from supply_demand import fair_value_gaps_for

from . import confirmation
from .alignment import compute_mtf_alignment
from .dealing_range import active_dealing_range_from_structure
from .models import (
    AUTHORITY,
    SCHEMA_VERSION,
    MarketSwingStructureResult,
    StructureEvent,
    TimeframeStructureSnapshot,
)

SKILL_VERSION = "1.0.0"

_STRUCTURE_EVENT_KIND_LABEL = {
    "BULLISH_BOS": "BOS_BULLISH",
    "BEARISH_BOS": "BOS_BEARISH",
    "BULLISH_CHOCH": "CHOCH_BULLISH",
    "BEARISH_CHOCH": "CHOCH_BEARISH",
}


def _event(point, timeframe: str) -> Optional[StructureEvent]:
    if point is None:
        return None
    label = _STRUCTURE_EVENT_KIND_LABEL.get(point.kind.value)
    if label is None:
        return None
    return StructureEvent(event_type=label, price=point.price, confirmed_time_utc=point.time_utc, timeframe=timeframe)


def _snapshot_for_timeframe(structure_result: StructureResult) -> TimeframeStructureSnapshot:
    swing_length = structure_result.config.swing_length if structure_result.config else None
    high_swing = low_swing = None
    if structure_result.status == "VALID" and swing_length is not None:
        high_swing = confirmation.normalize_swing_point(
            structure_result.latest_swing_high, structure_result.timeframe, swing_length
        ) if structure_result.latest_swing_high is not None else None
        low_swing = confirmation.normalize_swing_point(
            structure_result.latest_swing_low, structure_result.timeframe, swing_length
        ) if structure_result.latest_swing_low is not None else None

    return TimeframeStructureSnapshot(
        timeframe=structure_result.timeframe,
        status=structure_result.status,
        structure_state=structure_result.state,
        last_confirmed_swing_high=high_swing,
        last_confirmed_swing_low=low_swing,
        last_bos=_event(structure_result.latest_bos, structure_result.timeframe),
        last_choch=_event(structure_result.latest_choch, structure_result.timeframe),
        reason_codes=structure_result.reason_codes,
    )


def analyze(
    symbol: str,
    timeframes: Sequence[str],
    evaluation_time: Optional[datetime] = None,
    count: Optional[int] = None,
) -> MarketSwingStructureResult:
    """`timeframes` must be ordered HTF-first, LTF-last -- e.g. ("H4", "H1", "M15"). The
    LAST (most granular / LTF) timeframe is used for dealing-range, liquidity_context,
    and imbalance_context (documented choice, not a hidden default) -- these are
    setup-level concepts, and the LTF role is what a strategy's setup timeframe
    typically is."""
    if not timeframes:
        raise ValueError("timeframes must be a non-empty, HTF-first-ordered sequence")

    analysis_time = evaluation_time or datetime.now(timezone.utc)

    per_tf_results = {tf: analyze_structure(symbol, tf, count=count) for tf in timeframes}
    snapshots = tuple((tf, _snapshot_for_timeframe(per_tf_results[tf])) for tf in timeframes)

    structure_events = tuple(
        event
        for tf in timeframes
        for raw_point in (per_tf_results[tf].latest_bos, per_tf_results[tf].latest_choch)
        for event in (_event(raw_point, tf),)
        if event is not None
    )

    ltf = timeframes[-1]
    ltf_result = per_tf_results[ltf]

    current_price = None
    try:
        current_price = get_tick(symbol).bid
    except MarketDataError:
        current_price = None

    active_range = None
    if ltf_result.status == "VALID":
        active_range = active_dealing_range_from_structure(ltf_result, current_price)

    liquidity_ctx: Tuple = ()
    liquidity_res = liquidity_result(symbol, ltf)
    if liquidity_res.status == "LIQUIDITY_OK":
        liquidity_ctx = liquidity_res.levels

    imbalance_ctx: Tuple = ()
    fvg_res = fair_value_gaps_for(symbol, ltf)
    if fvg_res.status == "OK":
        imbalance_ctx = fvg_res.zones

    alignment_input = tuple((tf, per_tf_results[tf].state) for tf in timeframes)
    mtf_alignment = compute_mtf_alignment(alignment_input)

    overall_status = "OK" if all(r.status == "VALID" for r in per_tf_results.values()) else "PARTIAL"
    reason_codes = tuple(
        code for r in per_tf_results.values() if r.status != "VALID" for code in (r.status,)
    )

    return MarketSwingStructureResult(
        schema_version=SCHEMA_VERSION,
        symbol=symbol,
        analysis_time_utc=analysis_time,
        authority=AUTHORITY,
        timeframes=snapshots,
        active_dealing_range=active_range,
        liquidity_context=liquidity_ctx,
        imbalance_context=imbalance_ctx,
        structure_events=structure_events,
        mtf_alignment=mtf_alignment,
        provenance={
            "skill_version": SKILL_VERSION,
            "schema_version": SCHEMA_VERSION,
            "timeframes_requested": list(timeframes),
            "dealing_range_defining_timeframe": ltf,
            "liquidity_imbalance_defining_timeframe": ltf,
        },
        status=overall_status,
        reason_codes=reason_codes,
    )
