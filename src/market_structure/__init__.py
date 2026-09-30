"""Market Structure capability (Phase 2): swing highs/lows, BOS, CHoCH, previous
high/low, general trend/range state -- via smartmoneyconcepts, wrapped behind
project-owned interfaces (see PROJECT_STATUS.md 'Authority order' and smc_adapter.py's
docstring for why the third-party package never becomes project authority directly).

Advisory only: this package explains what structure looks like. It has no execution
authority and must never be treated as a TradeSignal -- see strategy_engine/ for that.
"""
from .analyzer import analyze_structure, structural_breaks_for_candles
from .config import load_market_structure_config
from .models import (
    STATE_BEARISH,
    STATE_BULLISH,
    STATE_UNDEFINED,
    MarketStructureConfig,
    StructurePoint,
    StructurePointKind,
    StructureResult,
)

__all__ = [
    "analyze_structure", "structural_breaks_for_candles", "load_market_structure_config",
    "StructureResult", "StructurePoint", "StructurePointKind", "MarketStructureConfig",
    "STATE_BULLISH", "STATE_BEARISH", "STATE_UNDEFINED",
]
