"""Two-tier external/internal structure -- additive to Phase 2's frozen single-tier
analyze_structure()/StructureResult (market_structure/analyzer.py), which this module
does not modify or call.

Frozen this session (SMC foundational skills mission): internal = swing_length 5
(identical to the existing frozen config/market_structure.yaml value -- same detector,
same numbers), external = swing_length 50. This matches the LuxAlgo "Smart Money
Concepts" reference indicator's own internal/swing-structure defaults -- the
smartmoneyconcepts library is a port of that indicator -- rather than an arbitrary
choice invented for this project.

HH/HL/LH/LL tie rule: reuses config/liquidity.yaml's equal_level_tolerance_points
(converted to a price distance via the symbol's own tick_size, same convention as
execution/risk.py) instead of inventing a second tolerance concept. A swing within
tolerance of the previous same-type swing labels toward continuation (HH for highs, LL
for lows). The first swing of each type in the fetched window has no prior to compare
against and stays unclassified (kind remains SWING_HIGH/SWING_LOW).
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import List, Optional

import yaml

from mt5.market_data import MarketDataError, get_latest_candles
from mt5.symbol_resolver import SymbolMetaError, get_symbol_meta

from .config import load_market_structure_config
from .models import (
    STATE_BEARISH,
    STATE_BULLISH,
    STATE_UNDEFINED,
    StructurePoint,
    StructurePointKind,
    StructureTier,
    TieredStructureResult,
)
from .smc_adapter import (
    StructureLibraryError,
    StructureOutputInvalid,
    all_breaks,
    candles_to_dataframe,
    full_swings,
)

EXTERNAL_SWING_LENGTH = 50  # frozen 2026-08-27 -- see module docstring
_LIQUIDITY_CONFIG_PATH = "config/liquidity.yaml"


def _smc_version() -> Optional[str]:
    try:
        return _pkg_version("smartmoneyconcepts")
    except PackageNotFoundError:
        return None


def _equal_level_tolerance_points() -> int:
    with open(_LIQUIDITY_CONFIG_PATH, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return int(raw["equal_level_tolerance_points"])


def label_swings(swings: List[StructurePoint], tolerance_price: float) -> List[StructurePoint]:
    """Classifies each swing as HH/HL/LH/LL by comparing it to the previous swing of the
    SAME kind. Non-swing points (BOS/CHOCH) pass through unchanged -- this function is
    only ever called with a pure swing list in practice, but stays defensive."""
    labeled: List[StructurePoint] = []
    last_high: Optional[StructurePoint] = None
    last_low: Optional[StructurePoint] = None

    for point in swings:
        if point.kind == StructurePointKind.SWING_HIGH:
            if last_high is None:
                labeled.append(point)
            else:
                kind = StructurePointKind.LH if point.price < last_high.price - tolerance_price else StructurePointKind.HH
                labeled.append(StructurePoint(time_utc=point.time_utc, price=point.price, kind=kind))
            last_high = point
        elif point.kind == StructurePointKind.SWING_LOW:
            if last_low is None:
                labeled.append(point)
            else:
                kind = StructurePointKind.HL if point.price > last_low.price + tolerance_price else StructurePointKind.LL
                labeled.append(StructurePoint(time_utc=point.time_utc, price=point.price, kind=kind))
            last_low = point
        else:
            labeled.append(point)

    return labeled


def _tier_direction(latest_bos: Optional[StructurePoint], latest_choch: Optional[StructurePoint]) -> str:
    """Mirrors analyzer.py's _structure_state() rule exactly (same definition). Kept as
    an independent copy here rather than importing that private helper across modules or
    touching the frozen analyzer.py."""
    candidates = [p for p in (latest_bos, latest_choch) if p is not None]
    if not candidates:
        return STATE_UNDEFINED
    latest = max(candidates, key=lambda p: p.time_utc)
    return STATE_BULLISH if "BULLISH" in latest.kind.value else STATE_BEARISH


def _build_tier(df, tier_name: str, swing_length: int, close_break: bool, tolerance_price: float) -> StructureTier:
    raw_swings = full_swings(df, swing_length)
    labeled_swings = label_swings(raw_swings, tolerance_price)
    events = all_breaks(df, swing_length, close_break)

    high_kinds = (StructurePointKind.SWING_HIGH, StructurePointKind.HH, StructurePointKind.LH)
    low_kinds = (StructurePointKind.SWING_LOW, StructurePointKind.HL, StructurePointKind.LL)
    latest_swing_high = next((p for p in reversed(labeled_swings) if p.kind in high_kinds), None)
    latest_swing_low = next((p for p in reversed(labeled_swings) if p.kind in low_kinds), None)
    latest_bos = next((p for p in reversed(events) if "BOS" in p.kind.value), None)
    latest_choch = next((p for p in reversed(events) if "CHOCH" in p.kind.value), None)

    return StructureTier(
        tier=tier_name, swing_length=swing_length, direction=_tier_direction(latest_bos, latest_choch),
        swings=tuple(labeled_swings), events=tuple(events),
        latest_swing_high=latest_swing_high, latest_swing_low=latest_swing_low,
        latest_bos=latest_bos, latest_choch=latest_choch,
    )


def analyze_structure_tiers(symbol: str, timeframe: str, count: Optional[int] = None) -> TieredStructureResult:
    """Independent two-tier read: EXTERNAL (swing_length=50) and INTERNAL
    (swing_length=5, identical to analyze_structure()'s frozen config) computed from the
    same closed-candle window. Does not call or depend on analyze_structure()."""
    base_config = load_market_structure_config()
    count = count or base_config.default_analysis_count

    warmup_bars = max(EXTERNAL_SWING_LENGTH * 20, 100)  # external's larger swing_length needs more warm-up than internal's
    fetch_count = count + warmup_bars

    try:
        candles = get_latest_candles(symbol, timeframe, fetch_count)
    except MarketDataError as exc:
        return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="MARKET_DATA_INVALID",
                                      reason_codes=(exc.reason_code,))

    if len(candles) < warmup_bars:
        return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="INSUFFICIENT_STRUCTURE_HISTORY",
                                      reason_codes=("INSUFFICIENT_STRUCTURE_HISTORY",), closed_candle_count=len(candles))

    df = candles_to_dataframe(candles)

    try:
        tolerance_price = _equal_level_tolerance_points() * get_symbol_meta(symbol).tick_size
    except (SymbolMetaError, OSError, KeyError) as exc:
        return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="SYMBOL_METADATA_MISSING",
                                      reason_codes=(str(exc),), closed_candle_count=len(candles))

    try:
        internal_tier = _build_tier(df, "INTERNAL", base_config.swing_length, base_config.close_break, tolerance_price)
        external_tier = _build_tier(df, "EXTERNAL", EXTERNAL_SWING_LENGTH, base_config.close_break, tolerance_price)
    except (StructureLibraryError, StructureOutputInvalid) as exc:
        return TieredStructureResult(symbol=symbol, timeframe=timeframe, status="STRUCTURE_LIBRARY_ERROR",
                                      reason_codes=(str(exc),), closed_candle_count=len(candles))

    return TieredStructureResult(
        symbol=symbol, timeframe=timeframe, status="VALID", reason_codes=(),
        external=external_tier, internal=internal_tier,
        data_start_utc=candles[0].time, data_end_utc=candles[-1].time,
        closed_candle_count=len(candles), smc_version=_smc_version(),
    )
