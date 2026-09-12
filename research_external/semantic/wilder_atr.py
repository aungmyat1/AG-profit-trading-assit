"""Wilder's ATR -- adapted, not rewritten, from a verified owner-owned donor repo.

source:
  repository: aungmyat1/session-smc-trading-bot
  commit: e179fe277d3ab4ac648cfe127e47d987466b2252
  path: strategy/session_liquidity/displacement_detector.py::wilder_atr
  component: Wilder's ATR (SA-05 Displacement Detector)
  license: owner-owned, both repositories confirmed same-owner -- verified 2026-09-12
adaptation:
  destination: research_external/semantic/wilder_atr.py
  changes:
    - none to the algorithm itself (seed = mean(TR[1..period]), recursive Wilder
      smoothing, None for indices 0..period-1) -- copied verbatim
    - renamed the bare `list`/`dict` type hints to explicit typing imports for this
      repo's lint conventions; no behavioral change
    - this docstring/provenance header replaces the donor's own module docstring,
      which described the sibling 'Strategy A' displacement gate this function was
      originally embedded in -- that gate itself is NOT reused here, only the pure
      wilder_atr() function

Note: this is a plain OHLC-based ATR helper with no session/strategy-specific
coupling -- reusable regardless of which S2 specification question (see
research_external/resource_audit/S2_SPEC_CONFLICT.json) is ultimately resolved.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

Candle = Dict[str, float]


def wilder_atr(candles: Sequence[Candle], period: int = 14) -> List[Optional[float]]:
    """Compute Wilder's ATR for every bar in `candles`.

    Args:
        candles: sequence of dicts with float-valued 'high', 'low', 'close'. Must be
                 in chronological order.
        period:  smoothing window. Default 14.

    Returns:
        List of the same length as `candles`.
        Indices 0 .. period-1 -> None  (insufficient history)
        Index  period          -> seed  (mean of TR[1..period])
        Indices period+1 ..    -> recursive Wilder ATR

    Wilder seed note (unchanged from donor): the seed is computed from TR[1..period]
    (candles[1] through candles[period]). TR[0] is intentionally omitted -- it would
    require a "previous close" that does not exist in the supplied data. The first
    valid ATR is therefore at index `period`, not `period - 1`.
    """
    n = len(candles)
    atrs: List[Optional[float]] = [None] * n

    if n <= period:
        return atrs

    trs: List[float] = []
    for i in range(1, n):
        h = candles[i]["high"]
        l = candles[i]["low"]
        pc = candles[i - 1]["close"]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))

    seed = sum(trs[:period]) / period
    atrs[period] = seed

    for i in range(period + 1, n):
        atrs[i] = (atrs[i - 1] * (period - 1) + trs[i - 1]) / period

    return atrs
