"""C11 target model -- HYBRID_WITH_STRUCTURAL_FALLBACK, exactly as frozen in
strategies/ST_LARGE_SMC_V1.yaml (`target_model:` block, RESOLVED_BY_OWNER,
2026-09-01). Thin adapter only: no new swing/sweep detector, reuses
`liquidity.hierarchy.external_swing_liquidity` (primary tier) and
`market_structure.tiers.StructureTier.swings` + `liquidity.status.compute_status`
(fallback tier, same status function `external_swing_liquidity` itself calls) --
matching the yaml's own `no new swing algorithm, no new detector` requirement.

Direction -> target side (yaml, direction_long/direction_short): a LONG trade's target
is the nearest qualifying BUY_SIDE (resting liquidity ABOVE price) EXTERNAL/UNSWEPT
level strictly above the anchor; SHORT mirrors to SELL_SIDE strictly below.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from liquidity.hierarchy import external_swing_liquidity, level_id
from liquidity.models import LiquidityLevel, LiquiditySide, LiquidityStatus
from liquidity.status import compute_status
from market_structure.models import StructurePointKind, StructureTier
from strategy_engine.session import Candle

TARGET_TIER_PRIMARY = "PRIMARY_EXTERNAL_LIQUIDITY"
TARGET_TIER_FALLBACK = "FALLBACK_M5_SWING"

_SIDE_FOR_DIRECTION = {"LONG": LiquiditySide.BUY_SIDE, "SHORT": LiquiditySide.SELL_SIDE}
_HIGH_KINDS = (StructurePointKind.SWING_HIGH, StructurePointKind.HH, StructurePointKind.LH)
_LOW_KINDS = (StructurePointKind.SWING_LOW, StructurePointKind.HL, StructurePointKind.LL)


@dataclass(frozen=True)
class TargetSelection:
    found: bool
    target_price: Optional[float] = None
    target_tier: Optional[str] = None
    target_type: Optional[str] = None
    target_source: Optional[str] = None
    target_source_id: Optional[str] = None
    target_side: Optional[str] = None
    target_status_at_selection: Optional[str] = None
    target_evidence_timestamp: Optional[datetime] = None
    reason: str = ""


def _strictly_beyond(side: LiquiditySide, anchor_price: float, candidate_price: float) -> bool:
    return candidate_price > anchor_price if side == LiquiditySide.BUY_SIDE else candidate_price < anchor_price


def _primary_candidate(
    symbol: str, timeframe: str, side: LiquiditySide, external_tier: StructureTier,
    m5_candles: Sequence[Candle], anchor_price: float, live_bid: Optional[float], live_ask: Optional[float],
) -> Optional[LiquidityLevel]:
    levels = external_swing_liquidity(symbol, timeframe, external_tier, m5_candles, live_bid, live_ask)
    for level in levels:
        if (level.side == side and level.status == LiquidityStatus.UNSWEPT
                and _strictly_beyond(side, anchor_price, level.price)):
            return level
    return None


def _fallback_candidates(
    symbol: str, timeframe: str, side: LiquiditySide, external_tier: StructureTier,
    m5_candles: Sequence[Candle], anchor_price: float, exclude_origin_time: Optional[datetime],
) -> Sequence[LiquidityLevel]:
    """All CONFIRMED EXTERNAL-tier M5 swings of the matching side (StructureTier.swings,
    the same chronological list latest_swing_high/low are themselves reduced from),
    excluding whichever swing the primary tier already evaluated (its own
    latest_swing_high/low origin_time), filtered to UNSWEPT + strictly beyond anchor."""
    wanted_kinds = _HIGH_KINDS if side == LiquiditySide.BUY_SIDE else _LOW_KINDS
    out = []
    for point in external_tier.swings:
        if point.kind not in wanted_kinds:
            continue
        if exclude_origin_time is not None and point.time_utc == exclude_origin_time:
            continue
        after = [c for c in m5_candles if c.time > point.time_utc]
        status, sweep_time, reclaim_time, _reasons = compute_status(side, point.price, after)
        if status != LiquidityStatus.UNSWEPT:
            continue
        if not _strictly_beyond(side, anchor_price, point.price):
            continue
        out.append(LiquidityLevel(
            symbol=symbol, timeframe=timeframe, side=side,
            source="EXTERNAL_SWING_HIGH" if side == LiquiditySide.BUY_SIDE else "EXTERNAL_SWING_LOW",
            price=point.price, origin_time=point.time_utc, status=status,
            sweep_time=sweep_time, reclaim_time=reclaim_time,
        ))
    return out


def select_target(
    direction: str, anchor_price: float, symbol: str, timeframe: str,
    external_tier: Optional[StructureTier], m5_candles: Sequence[Candle],
    live_bid: Optional[float] = None, live_ask: Optional[float] = None,
) -> TargetSelection:
    """STATIC mode: called once, at candidate qualification, never retargeted by this
    function's own caller (engine.py calls it exactly once per candidate)."""
    if direction not in _SIDE_FOR_DIRECTION or external_tier is None:
        return TargetSelection(found=False, reason="MISSING_DIRECTION_OR_STRUCTURE_TIER")

    side = _SIDE_FOR_DIRECTION[direction]

    primary = _primary_candidate(symbol, timeframe, side, external_tier, m5_candles, anchor_price, live_bid, live_ask)
    if primary is not None:
        return TargetSelection(
            found=True, target_price=primary.price, target_tier=TARGET_TIER_PRIMARY,
            target_type=primary.source, target_source="liquidity.hierarchy.external_swing_liquidity",
            target_source_id=level_id(primary), target_side=side.value,
            target_status_at_selection=primary.status.value, target_evidence_timestamp=primary.origin_time,
            reason="PRIMARY_TIER_OPPOSING_EXTERNAL_UNSWEPT_LIQUIDITY",
        )

    primary_origin = None
    latest_point = external_tier.latest_swing_high if side == LiquiditySide.BUY_SIDE else external_tier.latest_swing_low
    if latest_point is not None:
        primary_origin = latest_point.time_utc

    candidates = _fallback_candidates(symbol, timeframe, side, external_tier, m5_candles, anchor_price, primary_origin)
    if not candidates:
        return TargetSelection(found=False, reason="REJECT_NO_TARGET")

    # NEAREST_IN_TRADE_DIRECTION, tie_break=MOST_RECENT_ORIGIN_TIME_WINS.
    best = min(candidates, key=lambda lvl: (abs(lvl.price - anchor_price), -lvl.origin_time.timestamp()))
    return TargetSelection(
        found=True, target_price=best.price, target_tier=TARGET_TIER_FALLBACK,
        target_type=best.source, target_source="market_structure.tiers.StructureTier.swings",
        target_source_id=level_id(best), target_side=side.value,
        target_status_at_selection=best.status.value, target_evidence_timestamp=best.origin_time,
        reason="FALLBACK_TIER_CONFIRMED_M5_SWING_EXTREMUM",
    )
