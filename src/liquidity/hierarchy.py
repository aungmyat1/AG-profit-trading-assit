"""External/internal liquidity scoping and Inducement Candidate detection.

Consumes market_structure.tiers' StructureTier (EXTERNAL/INTERNAL, already frozen this
session) and liquidity.analyzer.liquidity_result()'s existing levels -- redetects
nothing: no new swing/sweep logic here, only scoping labels and a relational query over
already-computed facts.

Scope freeze (documented, not silently assumed -- spec section 5): EXTERNAL liquidity =
swing levels built from the EXTERNAL structure tier (swing_length=50). INTERNAL
liquidity = every level liquidity.analyzer.liquidity_result() already produces (its
existing swing-sourced levels use analyze_structure()'s swing_length=5, identical to the
INTERNAL tier; EQUAL_HIGHS/EQUAL_LOWS, PDH/PDL, and session H/L are also treated as
internal per the spec's own "EQH/EQL inside the range" / "internal session level"
examples). external_swing_liquidity() below is the one new detector needed: liquidity
never computed EXTERNAL-tier swing levels before this module.

Inducement Candidate (spec section 7-8): a deterministic RELATIONSHIP, never a
standalone label. Rules 1-6 all checked here; Rule 5 ("structure must support the
relationship") is satisfied by construction -- both the candidate and its target are
themselves derived from market_structure/liquidity output, never invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

from market_structure.models import StructureTier

from .models import LiquidityLevel, LiquiditySide
from .status import compute_status

SCOPE_EXTERNAL = "EXTERNAL"
SCOPE_INTERNAL = "INTERNAL"

ROLE_NONE = "NONE"
ROLE_TARGET = "TARGET"
ROLE_INDUCEMENT_CANDIDATE = "INDUCEMENT_CANDIDATE"


def level_id(level: LiquidityLevel) -> str:
    """Deterministic cross-reference id -- same input always produces the same id, no
    counter/state needed (spec section 39's determinism requirement)."""
    return f"{level.symbol}:{level.timeframe}:{level.side.value}:{level.source}:{level.price:.8f}"


def external_swing_liquidity(
    symbol: str, timeframe: str, tier: StructureTier, candles, live_bid: Optional[float] = None,
    live_ask: Optional[float] = None,
) -> Tuple[LiquidityLevel, ...]:
    """The one new detector this module adds: EXTERNAL-tier swing high/low as liquidity
    levels, using the SAME sweep state machine (liquidity.status.compute_status) every
    other liquidity source already uses -- not a second sweep definition."""
    levels = []
    if tier.latest_swing_high is not None:
        point = tier.latest_swing_high
        after = [c for c in candles if c.time > point.time_utc]
        status, sweep_time, reclaim_time, reasons = compute_status(LiquiditySide.BUY_SIDE, point.price, after, live_bid, live_ask)
        levels.append(LiquidityLevel(symbol=symbol, timeframe=timeframe, side=LiquiditySide.BUY_SIDE,
                                      source="EXTERNAL_SWING_HIGH", price=point.price, origin_time=point.time_utc,
                                      status=status, sweep_time=sweep_time, reclaim_time=reclaim_time, reason_codes=reasons))
    if tier.latest_swing_low is not None:
        point = tier.latest_swing_low
        after = [c for c in candles if c.time > point.time_utc]
        status, sweep_time, reclaim_time, reasons = compute_status(LiquiditySide.SELL_SIDE, point.price, after, live_bid, live_ask)
        levels.append(LiquidityLevel(symbol=symbol, timeframe=timeframe, side=LiquiditySide.SELL_SIDE,
                                      source="EXTERNAL_SWING_LOW", price=point.price, origin_time=point.time_utc,
                                      status=status, sweep_time=sweep_time, reclaim_time=reclaim_time, reason_codes=reasons))
    return tuple(levels)


@dataclass(frozen=True)
class ScopedLiquidityLevel:
    level: LiquidityLevel
    scope: str  # SCOPE_EXTERNAL / SCOPE_INTERNAL
    level_id: str


def scope_liquidity_levels(
    external_levels: Sequence[LiquidityLevel], internal_levels: Sequence[LiquidityLevel]
) -> Tuple[ScopedLiquidityLevel, ...]:
    scoped = [ScopedLiquidityLevel(level=l, scope=SCOPE_EXTERNAL, level_id=level_id(l)) for l in external_levels]
    scoped += [ScopedLiquidityLevel(level=l, scope=SCOPE_INTERNAL, level_id=level_id(l)) for l in internal_levels]
    return tuple(scoped)


@dataclass(frozen=True)
class InducementCandidate:
    candidate_id: str
    candidate: LiquidityLevel
    target_id: str
    target: LiquidityLevel
    side: LiquiditySide
    role: str = ROLE_INDUCEMENT_CANDIDATE


def _is_between(side: LiquiditySide, current_price: float, candidate_price: float, target_price: float) -> bool:
    """Rule 3 (ordering) + Rule 6 (candidate nearer than target), spec section 8."""
    if side == LiquiditySide.BUY_SIDE:
        return current_price < candidate_price < target_price
    return current_price > candidate_price > target_price


def find_inducement_candidates(
    scoped_levels: Sequence[ScopedLiquidityLevel], current_price: float
) -> Tuple[InducementCandidate, ...]:
    """Rules 1-6 (spec section 8). Does not rank or pick a single "best" candidate when
    several qualify (spec section 32) -- returns every valid (candidate, target) pair."""
    externals_unswept = {
        side: [s for s in scoped_levels if s.scope == SCOPE_EXTERNAL and s.level.side == side and s.level.status.value == "UNSWEPT"]
        for side in (LiquiditySide.BUY_SIDE, LiquiditySide.SELL_SIDE)
    }

    candidates = []
    for internal in scoped_levels:
        if internal.scope != SCOPE_INTERNAL or internal.level.status.value != "UNSWEPT":
            continue
        for target in externals_unswept[internal.level.side]:
            if _is_between(internal.level.side, current_price, internal.level.price, target.level.price):
                candidates.append(InducementCandidate(
                    candidate_id=internal.level_id, candidate=internal.level,
                    target_id=target.level_id, target=target.level, side=internal.level.side,
                ))
    return tuple(candidates)


def classify_roles(scoped_levels: Sequence[ScopedLiquidityLevel], current_price: float) -> Dict[str, str]:
    """role for every scoped level's id -- TARGET / INDUCEMENT_CANDIDATE / NONE (spec
    section 11: internal liquidity without a valid target stays NONE, never forced into
    INDUCEMENT_CANDIDATE)."""
    candidates = find_inducement_candidates(scoped_levels, current_price)
    candidate_ids = {c.candidate_id for c in candidates}
    target_ids = {c.target_id for c in candidates}
    roles = {}
    for s in scoped_levels:
        if s.level_id in target_ids:
            roles[s.level_id] = ROLE_TARGET
        elif s.level_id in candidate_ids:
            roles[s.level_id] = ROLE_INDUCEMENT_CANDIDATE
        else:
            roles[s.level_id] = ROLE_NONE
    return roles
