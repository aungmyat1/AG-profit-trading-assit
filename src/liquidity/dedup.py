"""Cross-source deduplication for liquidity levels (AG_LIQUIDITY_V1, see contract.py).

Before this module existed, liquidity_result() emitted one LiquidityLevel per source
unconditionally -- an Asian High and a Swing High at the same real price showed up as
two unrelated levels. This is a minimal, deterministic merge: levels on the SAME side
within `tolerance_price` of each other (adjacent-difference chaining, the same method
equal_levels.py already uses for its own raw-extreme clustering) are combined into one
LiquidityLevel that records every contributing source.

Representative price: the most conservative (furthest) extreme in the cluster -- max
for BUY_SIDE, min for SELL_SIDE. Status/sweep/reclaim/origin/reason_codes are taken from
whichever contributing level has that representative price (first match if tied), never
recomputed independently -- this module does not re-run the sweep/reclaim state machine.
"""
from __future__ import annotations

from typing import List, Sequence

from .models import LiquidityLevel, LiquiditySide


def merge_duplicate_levels(levels: Sequence[LiquidityLevel], tolerance_price: float) -> List[LiquidityLevel]:
    if tolerance_price <= 0:
        return [_with_sources(l) for l in levels]

    out: List[LiquidityLevel] = []
    for side in (LiquiditySide.BUY_SIDE, LiquiditySide.SELL_SIDE):
        side_levels = [l for l in levels if l.side == side]
        out.extend(_merge_side(side_levels, side, tolerance_price))
    return out


def _merge_side(side_levels: List[LiquidityLevel], side: LiquiditySide, tolerance_price: float) -> List[LiquidityLevel]:
    if not side_levels:
        return []
    ordered = sorted(side_levels, key=lambda l: l.price)

    clusters: List[List[LiquidityLevel]] = [[ordered[0]]]
    for level in ordered[1:]:
        if level.price - clusters[-1][-1].price <= tolerance_price:
            clusters[-1].append(level)
        else:
            clusters.append([level])

    pick = max if side == LiquiditySide.BUY_SIDE else min
    merged: List[LiquidityLevel] = []
    for cluster in clusters:
        if len(cluster) == 1:
            merged.append(_with_sources(cluster[0]))
            continue
        rep_price = pick(l.price for l in cluster)
        rep = next(l for l in cluster if l.price == rep_price)
        all_sources = tuple(l.source for l in cluster)
        merged.append(_with_sources(rep, all_sources))
    return merged


def _with_sources(level: LiquidityLevel, sources: tuple | None = None) -> LiquidityLevel:
    from dataclasses import replace
    return replace(level, sources=sources or (level.source,))
