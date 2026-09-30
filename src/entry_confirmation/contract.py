"""ENTRY_CONFIRMATION_V1 -- the Phase 5 entry-confirmation contract.

Full audit backing this contract: docs/specs/ENTRY_CONFIRMATION_V1_SPEC.md. Summary of what was
found before writing any code (searched market_structure/, supply_demand/, liquidity/,
strategy_engine/, execution/, trade_management/, config/*.yaml, and every SKILL.md):

    No generic (capability-level, symbol/timeframe-neutral) signed threshold exists
    anywhere in this repo for "this candle qualifies as displacement" or "this candle
    qualifies as a rejection/reversal candle." The only body-ratio threshold found,
    `pivot_shadow_body_ratio_threshold` in config/ag_order_block_v1.yaml, is signed for
    a different question -- classifying an Order Block origin candle as PIVOT vs.
    SHADOW inside AG_ORDER_BLOCK_V1 (supply_demand/ob_contract.py) -- not for judging
    whether a candle constitutes valid entry confirmation. Reusing it here would silently
    globalize a supply-demand-specific number into a different capability's authority,
    which this contract does not do.

    strategy_engine/session/reference_box.py has its own `displacement` (session-level,
    `abs(close - open)` over an entire frozen session) and `efficiency_ratio` --
    ER_ONLY_V2, signed for ST_ASIAN_SWEEP_5R_V1 only, operating on a session window, not
    a single candle. Not reusable here without inventing a new candle-level
    interpretation the owner never signed.

    strategy_engine/session/setups.py's `upper_rejection`/`lower_rejection` are signed,
    but for ST_ASIAN_SWEEP_5R_V1's own range-boundary rejection setup (close vs. a
    specific session box boundary) -- strategy-specific, not a generic candle qualifier.

Given that, ENTRY_CONFIRMATION_V1 implements the MEASUREMENT layer for displacement and
rejection/reversal candles (objective, always computable) and explicitly withholds
QUALIFICATION (`ConfirmationState.UNSIGNED_RULE`) until an owner signs a generic
threshold. structure_shift and liquidity_reclaim require no new threshold at all --
they only check alignment of an already-decided event (from market_structure /
liquidity) against a caller-supplied candidate direction.

CONTRACT_VERSION -- SIGNED / UNSIGNED summary:

    SIGNED, IMPLEMENTED : structure_shift alignment (consumes market_structure's own
                           signed StructureResult.latest_choch verbatim)
                          liquidity_reclaim alignment (consumes liquidity's own signed
                           LiquidityResult verbatim)
                          candle measurements for displacement and rejection (body,
                           range, wicks, ratios, close_location -- pure arithmetic, no
                           threshold involved)
    UNSIGNED            : displacement QUALIFICATION (what body_ratio/range counts as
                           "displaced")
                          rejection QUALIFICATION (what wick_ratio/body_ratio counts as
                           a "rejection candle")
    NOT IN SCOPE (V1)   : FVG retest, order-block reaction, breaker/mitigation-block
                           confirmation, multi-timeframe confluence scoring, any
                           numeric confirmation "score" -- per the mission's explicit
                           "do not create a universal SMC entry formula" instruction.

Market-data reuse: this package never calls MT5 or re-derives candles/structure/
liquidity itself. `EntryConfirmationRequest.candidate_candle` /
`.structure_result` / `.liquidity_result` are supplied by the caller, already computed
by `market-data` / `market-structure` / `liquidity` -- see
entry_confirmation/engine.py's module docstring.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

CONTRACT_VERSION = "ENTRY_CONFIRMATION_V1"


@dataclass(frozen=True)
class EntryConfirmationContractGap:
    item: str
    question: str


ENTRY_CONFIRMATION_CONTRACT_GAPS: Tuple[EntryConfirmationContractGap, ...] = (
    EntryConfirmationContractGap(
        "Displacement qualification threshold",
        "No owner-signed generic body_ratio/range threshold exists for 'this candle is "
        "displacement.' config/ag_order_block_v1.yaml's pivot_shadow_body_ratio_threshold "
        "is signed for OB family classification, a different question -- not reused here. "
        "Measurement is fully implemented; qualification returns UNSIGNED_RULE until an "
        "owner signs a generic threshold (or explicitly authorizes reusing an existing one).",
    ),
    EntryConfirmationContractGap(
        "Rejection/reversal candle qualification threshold",
        "Same gap as above, for wick-dominance-based rejection candles. Measurement "
        "(wicks, ratios, close_location) is fully implemented; qualification returns "
        "UNSIGNED_RULE.",
    ),
    EntryConfirmationContractGap(
        "FVG retest / order-block reaction / breaker confirmation",
        "Not implemented in V1 -- no existing signed definition was found, and the "
        "mission scoped V1 to four primitives only. supply_demand's zone/OB/FVG facts "
        "remain available for a future primitive without requiring them for V1.",
    ),
)
