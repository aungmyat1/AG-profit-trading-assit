"""Retail liquidity proxy (spec section 34) and engineered liquidity candidate (spec
section 33). Both operate on an already-computed `liquidity.analyzer.liquidity_result()`
level list -- no new price/level detection, no MT5 calls.

RETAIL_LIQUIDITY_PROXY is a relabeling view: every LiquidityLevel source this project
already computes (EQUAL_HIGHS/LOWS, SWING_HIGH/LOW, PDH/PDL, session H/L) already *is*
an objective proxy per the spec's own list -- so this is marked VALIDATED, not
research-only.

ENGINEERED_LIQUIDITY_CANDIDATE is genuinely interpretive ("inducement pattern" has no
prior frozen project definition) and is always marked RESEARCH_ONLY. "Internal" here
means a minor reference (EQUAL_HIGHS/EQUAL_LOWS/SWING_HIGH/SWING_LOW); "external" means a
larger objective reference (PDH/PDL or a session high/low) -- substituting for
market_structure's internal/external swing tiers, which liquidity levels aren't wired to
per-source, to keep this self-contained to one liquidity_result() call. Documented
substitution, not a silent one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from .models import LiquidityLevel

MINOR_SOURCES = frozenset({"EQUAL_HIGHS", "EQUAL_LOWS", "SWING_HIGH", "SWING_LOW"})
MAJOR_SOURCES = frozenset({
    "PDH", "PDL", "ASIAN_HIGH", "ASIAN_LOW", "LONDON_HIGH", "LONDON_LOW", "NEW_YORK_HIGH", "NEW_YORK_LOW",
})
_SWEPT_LIKE_STATUSES = frozenset({"SWEPT", "RECLAIMED", "CONSUMED"})


@dataclass(frozen=True)
class RetailLiquidityProxy:
    level: LiquidityLevel
    proxy_source: str
    classification: str = "VALIDATED"


def retail_liquidity_proxies(levels: Sequence[LiquidityLevel]) -> Tuple[RetailLiquidityProxy, ...]:
    """Every level whose source is one of this project's known objective proxies,
    unchanged -- excludes anything else rather than guessing it into this category."""
    return tuple(
        RetailLiquidityProxy(level=lvl, proxy_source=lvl.source)
        for lvl in levels
        if lvl.source in MINOR_SOURCES or lvl.source in MAJOR_SOURCES
    )


@dataclass(frozen=True)
class EngineeredLiquidityCandidate:
    level: LiquidityLevel
    evidence_repeated_internal_levels: bool
    evidence_inducement_pattern: bool
    evidence_external_objective_present: bool
    evidence_score: int  # 0-3
    classification: str = "ENGINEERED_LIQUIDITY_CANDIDATE"
    status: str = "RESEARCH_ONLY"


def engineered_liquidity_candidates(
    levels: Sequence[LiquidityLevel], tolerance_price: float
) -> Tuple[EngineeredLiquidityCandidate, ...]:
    """One candidate per MINOR-source level, each with three independently deterministic
    evidence flags (never a probability -- spec section 46):

    - repeated_internal_levels: >=1 other minor-source level on the same side within
      tolerance_price (a cluster of minor levels).
    - external_objective_present: >=1 MAJOR-source level exists on the same side at all.
    - inducement_pattern: this level's status is SWEPT/RECLAIMED/CONSUMED while at least
      one same-side MAJOR-source level is still UNSWEPT -- the most defensible objective
      proxy available from status data alone for "a minor level was taken while the
      bigger one survived"; not a claim about trader intent.
    """
    minor = [lvl for lvl in levels if lvl.source in MINOR_SOURCES]
    major = [lvl for lvl in levels if lvl.source in MAJOR_SOURCES]

    candidates = []
    for lvl in minor:
        same_side_minor = [l for l in minor if l.side == lvl.side and l is not lvl]
        repeated = any(abs(l.price - lvl.price) <= tolerance_price for l in same_side_minor)

        same_side_major = [l for l in major if l.side == lvl.side]
        external_present = bool(same_side_major)
        inducement = lvl.status.value in _SWEPT_LIKE_STATUSES and any(
            m.status.value == "UNSWEPT" for m in same_side_major
        )

        score = int(repeated) + int(inducement) + int(external_present)
        candidates.append(EngineeredLiquidityCandidate(
            level=lvl, evidence_repeated_internal_levels=repeated, evidence_inducement_pattern=inducement,
            evidence_external_objective_present=external_present, evidence_score=score,
        ))
    return tuple(candidates)
