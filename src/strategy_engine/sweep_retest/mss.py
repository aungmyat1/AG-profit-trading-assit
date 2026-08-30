"""MSS (Market Structure Shift) confirmation for the sweep-retest entry.

Swing detection reuses market_structure.smc_adapter.full_swings -- the existing Market
Structure capability -- rather than reimplementing fractal/swing logic (spec: "Do NOT
create duplicate implementations of ... swing detection ... where reusable capability
exists"). This module adds only the strategy-specific MSS CONFIRMATION rule (a subsequent
CLOSED M5 candle closing beyond the located swing) -- that rule is this strategy's own
entry logic, not a market-structure primitive, matching the same division of labor as
strategy_engine.session.setups.entry_2_sweep layering plain candle.close comparisons on
top of reference_box.py's box.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Sequence

from market_structure.config import load_market_structure_config
from market_structure.models import MarketStructureConfig, StructurePointKind
from market_structure.smc_adapter import candles_to_dataframe, full_swings
from strategy_engine.session import Candle

from .sweep import SWEEP_HIGH, SweepEvent

MSS_BEARISH = "MSS_BEARISH"  # after a HIGH sweep -- confirms SHORT
MSS_BULLISH = "MSS_BULLISH"  # after a LOW sweep -- confirms LONG


@dataclass(frozen=True)
class MSSEvent:
    kind: str  # MSS_BEARISH / MSS_BULLISH
    broken_swing_price: float
    broken_swing_time: datetime
    confirming_candle: Candle
    confirmed_at: datetime


def _most_recent_swing(
    candles: Sequence[Candle], want_high: bool, config: Optional[MarketStructureConfig]
) -> Optional[float]:
    if len(candles) < 3:
        return None
    config = config or load_market_structure_config()
    df = candles_to_dataframe(candles)
    swings = full_swings(df, config.swing_length)
    want_kind = StructurePointKind.SWING_HIGH if want_high else StructurePointKind.SWING_LOW
    matching = [p for p in swings if p.kind == want_kind]
    return matching[-1].price if matching else None


def find_mss(
    sweep: SweepEvent,
    candles_up_to_sweep: Sequence[Candle],
    candles_after_sweep: Sequence[Candle],
    config: Optional[MarketStructureConfig] = None,
) -> Optional[MSSEvent]:
    """candles_up_to_sweep: closed M5 candles ending at (and including) the sweep candle
    -- used only to LOCATE the swing that must be broken; the swing search never sees
    candles_after_sweep (no lookahead).

    candles_after_sweep: closed M5 candles strictly after the sweep candle, chronological
    -- only these can CONFIRM the MSS, and only via candle.close beyond the located swing.
    Intrabar penetration (candle.low/.high beyond the swing without a close beyond it) is
    explicitly insufficient -- this function never inspects .high/.low for confirmation.
    """
    if sweep.direction == SWEEP_HIGH:
        swing_low = _most_recent_swing(candles_up_to_sweep, want_high=False, config=config)
        if swing_low is None:
            return None
        for candle in candles_after_sweep:
            if candle.close < swing_low:
                return MSSEvent(MSS_BEARISH, swing_low, candle.time, candle, candle.time)
        return None

    swing_high = _most_recent_swing(candles_up_to_sweep, want_high=True, config=config)
    if swing_high is None:
        return None
    for candle in candles_after_sweep:
        if candle.close > swing_high:
            return MSSEvent(MSS_BULLISH, swing_high, candle.time, candle, candle.time)
    return None
