"""H1 trend filter, reusing the existing Market Structure capability
(market_structure.structural_breaks_for_candles) rather than reimplementing swing/BOS/CHOCH
detection or adding an EMA filter (spec: "Do NOT add an EMA trend filter").

The "whichever of the latest BOS/CHOCH happened most recently sets direction" rule mirrors
market_structure.analyzer._structure_state and market_structure.tiers._tier_direction
exactly. Both of those already keep an independent one-line copy of this same rule rather
than importing a private helper across modules (see tiers.py's own docstring: "Kept as an
independent copy here rather than importing that private helper across modules or
touching the frozen analyzer.py") -- this module follows that same established
project convention instead of modifying analyzer.py to export it.
"""
from __future__ import annotations

from typing import Optional, Sequence

from market_structure import structural_breaks_for_candles
from market_structure.config import load_market_structure_config
from market_structure.models import MarketStructureConfig
from strategy_engine.session import Candle

DIRECTION_LONG_ONLY = "LONG_ONLY"
DIRECTION_SHORT_ONLY = "SHORT_ONLY"
DIRECTION_NO_TRADE = "NO_TRADE_DIRECTION"


def h1_trend_direction(h1_candles: Sequence[Candle], config: Optional[MarketStructureConfig] = None) -> str:
    """h1_candles: closed H1 candles, chronological, up to and including "now" -- never a
    future bar (structural_breaks_for_candles itself only reports CONFIRMED breaks, so no
    additional lookahead guard is needed here beyond "don't pass future candles in").

    Routing (spec): BULLISH -> LOW SWEEP LONG only; BEARISH -> HIGH SWEEP SHORT only;
    no confirmed break (NEUTRAL/INDETERMINATE) -> NO_TRADE_DIRECTION.
    """
    config = config or load_market_structure_config()
    events = structural_breaks_for_candles(h1_candles, config)
    if not events:
        return DIRECTION_NO_TRADE
    latest = max(events, key=lambda p: p.time_utc)
    return DIRECTION_LONG_ONLY if "BULLISH" in latest.kind.value else DIRECTION_SHORT_ONLY
