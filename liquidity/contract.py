"""AG_LIQUIDITY_V1 -- the Phase 4 liquidity contract.

No owner gave a verbatim liquidity spec (unlike AG_ORDER_BLOCK_V1, which was frozen from
a reference image -- see supply_demand/ob_contract.py). This module documents, strictly
from already-implemented behavior, what Phase 4 actually does today. Nothing here invents
new trading theory; it is a record of the existing analyzer.py/status.py/equal_levels.py
behavior so the contract is inspectable in one place instead of implied by code alone.

AG_LIQUIDITY_V1
===============

A LEVEL is a price where resting liquidity is believed to sit. An EVENT is something
that happened to a level (see LiquidityStatus / status.py for the exact sweep/reclaim
state machine -- UNSWEPT/SWEPT/RECLAIMED/CONSUMED/UNKNOWN, unchanged by this pass).

SOURCES (frozen at the set already implemented; see liquidity/analyzer.py):

    SWING_HIGH / SWING_LOW      STRUCTURE-DEPENDENT, IMPLEMENTED
        The single LATEST swing high/low from market_structure.analyze_structure()'s
        StructureResult -- not every historical swing, only the most recent one per
        side. Requires StructureResult.status == "VALID"; otherwise no candidate.

    ASIAN_HIGH / ASIAN_LOW
    LONDON_HIGH / LONDON_LOW
    NEW_YORK_HIGH / NEW_YORK_LOW    SESSION-DEPENDENT, IMPLEMENTED
        From supply_demand.session_zone(), which itself reuses
        assistant.market_data.session_snapshot() against config/canonical_sessions.yaml.
        A session box is only a candidate once session_snapshot() reports "OK" -- i.e.
        the session for that calendar day has fully closed (session_complete()) AND the
        expected M15 bar count was returned. An in-progress or not-yet-started session
        for "today" produces NO candidate for that session, deliberately (see Task 4 of
        the Phase 4 continuation pass: absence is valid, never fabricated). This is
        real, verified behavior, not a hypothesis -- see the deterministic tests added
        in this pass (test_liquidity_session_availability.py).

    PDH / PDL                   IMPLEMENTED, NOT SESSION-DEPENDENT
        Last CLOSED D1 candle's high/low via supply_demand.previous_day_high_low().
        Available whenever a prior D1 candle exists; not tied to intraday session
        completion.

    EQUAL_HIGHS / EQUAL_LOWS     IMPLEMENTED
        Own tolerance-based clustering of raw local candle extremes (liquidity/
        equal_levels.py) -- independent of market_structure's swing detection by
        design. Tolerance: config/liquidity.yaml's equal_level_tolerance_points,
        converted to price via the symbol's own tick_size. Minimum cluster size: 2
        raw extremes (a single unmatched extreme is not "equal" anything).

    FLIP_OB-equivalent liquidity, inducement, SMT divergence, liquidity voids,
    multi-timeframe confluence scoring    NOT IMPLEMENTED, NOT IN SCOPE
        No existing contract or prior implementation requires these. Per the "No
        Theory Expansion" instruction for this pass, they are not added.

DEDUPLICATION / PROVENANCE (added this pass -- see liquidity/dedup.py):
    Multiple sources can identify the same real liquidity pool (e.g. Asian High and a
    Swing High at the same price). Before this pass, liquidity_result() emitted one
    LiquidityLevel per source unconditionally -- no merging existed. This pass adds a
    minimal, deterministic merge: LiquidityLevel objects on the SAME side within the
    same equal-level tolerance price of each other are combined into one level, with
    `sources` recording every contributing source (see LiquidityLevel.sources) and
    `source` kept as the first-detected source for backward compatibility. The
    representative price is the most conservative (furthest) extreme within the
    cluster (max for BUY_SIDE, min for SELL_SIDE) -- the same convention
    equal_levels.py already uses for its own clustering, not a new one invented here.
    Status/sweep/reclaim are taken from whichever contributing level matches that
    representative price. No clustering beyond simple tolerance-chaining is used.

SIGNED / FROZEN / IMPLEMENTED / PARTIAL / UNSIGNED summary:

    IMPLEMENTED : sweep/reclaim state machine (status.py)
                  equal-highs/equal-lows clustering (equal_levels.py)
                  structural (latest swing only), session, PDH/PDL sources
                  cross-source deduplication with provenance (dedup.py, this pass)
    PARTIAL     : SWING_HIGH/SWING_LOW only exposes the LATEST swing per side, not the
                  full swing history market_structure already computes. Not extended in
                  this pass (no owner ask to change SWING semantics); flagged here for
                  visibility, see LIQUIDITY_CONTRACT_GAPS below.
    UNSIGNED    : any ranking/scoring of "which liquidity level matters most" beyond
                  nearest-by-distance (nearest_buy_side/nearest_sell_side already exist
                  and are unchanged). No confidence score exists or is added.
    NOT IN SCOPE: anything under "No Theory Expansion" above.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

CONTRACT_VERSION = "AG_LIQUIDITY_V1"


@dataclass(frozen=True)
class LiquidityContractGap:
    item: str
    question: str


LIQUIDITY_CONTRACT_GAPS: Tuple[LiquidityContractGap, ...] = (
    LiquidityContractGap(
        "SWING_HIGH/SWING_LOW scope",
        "Only the latest structural swing high/low is exposed as a liquidity candidate, "
        "not the full swing history StructureResult already carries. Left unchanged in "
        "this pass -- no owner ask to broaden it. Confirm whether older swings should "
        "also become liquidity candidates.",
    ),
    LiquidityContractGap(
        "Cross-source dedup tolerance",
        "Deduplication (dedup.py) reuses config/liquidity.yaml's "
        "equal_level_tolerance_points as the 'same liquidity pool' distance, rather than "
        "a separately-named tolerance. Confirm this reuse is correct or supply a "
        "dedicated value.",
    ),
)
