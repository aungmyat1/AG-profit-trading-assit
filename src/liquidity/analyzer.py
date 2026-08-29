"""Public entry point: liquidity_result(). Reuses StructureResult (market_structure),
session_zone() and previous_day_high_low() (supply_demand), and canonical market data
(mt5.market_data) rather than recalculating any of them -- this module only adds the
sweep/reclaim state machine (status.py) and equal-highs/lows clustering (equal_levels.py).
"""
from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

import session_clock as sc
from market_structure import analyze_structure
from mt5.market_data import MarketDataError, get_latest_candles, get_tick
from mt5.symbol_resolver import SymbolMetaError, get_symbol_meta
from supply_demand import previous_day_high_low, previous_week_high_low, session_zone

from .config import load_liquidity_config
from .dedup import merge_duplicate_levels
from .equal_levels import detect_equal_highs, detect_equal_lows
from .models import LiquidityLevel, LiquidityResult, LiquiditySide, LiquidityStatus
from .status import compute_status

_SESSION_DISPLAY = {"asian": "ASIAN", "london_am": "LONDON", "new_york_am": "NEW_YORK"}


def liquidity_result(symbol: str, timeframe: str, count: Optional[int] = None) -> LiquidityResult:
    config = load_liquidity_config()
    count = count or config.lookback_bars

    try:
        candles = get_latest_candles(symbol, timeframe, count)
    except MarketDataError as exc:
        return LiquidityResult(symbol=symbol, timeframe=timeframe, status=exc.reason_code,
                                reason_codes=(exc.reason_code,))

    live_bid = live_ask = None
    try:
        tick = get_tick(symbol)
        live_bid, live_ask = tick.bid, tick.ask
    except MarketDataError:
        pass  # levels still computed from closed-candle history; SWEPT (live) just won't be reachable

    tolerance_price = None
    try:
        meta = get_symbol_meta(symbol)
        tolerance_price = config.equal_level_tolerance_points * meta.tick_size
    except SymbolMetaError:
        pass

    levels: List[LiquidityLevel] = []
    levels += _structural_levels(symbol, timeframe, candles, live_bid, live_ask)
    levels += _session_levels(symbol, timeframe, candles, live_bid, live_ask)
    levels += _previous_day_levels(symbol, timeframe, candles, live_bid, live_ask)
    levels += _previous_week_levels(symbol, timeframe, candles, live_bid, live_ask)
    if tolerance_price is not None:
        levels += detect_equal_highs(symbol, timeframe, candles, tolerance_price,
                                      config.local_extremum_window, live_bid, live_ask)
        levels += detect_equal_lows(symbol, timeframe, candles, tolerance_price,
                                     config.local_extremum_window, live_bid, live_ask)

    levels = merge_duplicate_levels(levels, tolerance_price or 0.0)

    reference_price = live_bid if live_bid is not None else candles[-1].close
    nearest_buy = _nearest(levels, LiquiditySide.BUY_SIDE, reference_price)
    nearest_sell = _nearest(levels, LiquiditySide.SELL_SIDE, reference_price)

    status = "LIQUIDITY_OK" if levels else "NO_LIQUIDITY_LEVELS"
    return LiquidityResult(symbol=symbol, timeframe=timeframe, status=status,
                            levels=tuple(levels), nearest_buy_side=nearest_buy, nearest_sell_side=nearest_sell)


def _structural_levels(symbol, timeframe, candles, live_bid, live_ask) -> List[LiquidityLevel]:
    structure = analyze_structure(symbol, timeframe)
    if structure.status != "VALID":
        return []
    out = []
    if structure.latest_swing_high is not None:
        out.append(_level(symbol, timeframe, LiquiditySide.BUY_SIDE, "SWING_HIGH",
                           structure.latest_swing_high.price, structure.latest_swing_high.time_utc,
                           candles, live_bid, live_ask))
    if structure.latest_swing_low is not None:
        out.append(_level(symbol, timeframe, LiquiditySide.SELL_SIDE, "SWING_LOW",
                           structure.latest_swing_low.price, structure.latest_swing_low.time_utc,
                           candles, live_bid, live_ask))
    return out


def _session_levels(symbol, timeframe, candles, live_bid, live_ask) -> List[LiquidityLevel]:
    out = []
    for canonical_name, display in _SESSION_DISPLAY.items():
        zone = session_zone(symbol, canonical_name)
        if zone.low is None or zone.high is None:
            continue
        try:
            _, end = sc.get_session_bounds(zone.origin_time.date(), canonical_name)
        except Exception:
            continue
        out.append(_level(symbol, timeframe, LiquiditySide.BUY_SIDE, f"{display}_HIGH",
                           zone.high, end, candles, live_bid, live_ask))
        out.append(_level(symbol, timeframe, LiquiditySide.SELL_SIDE, f"{display}_LOW",
                           zone.low, end, candles, live_bid, live_ask))
    return out


def _previous_day_levels(symbol, timeframe, candles, live_bid, live_ask) -> List[LiquidityLevel]:
    zone = previous_day_high_low(symbol)
    if zone.low is None or zone.high is None:
        return []
    origin = zone.origin_time + timedelta(days=1)  # the level is "live" from today onward
    return [
        _level(symbol, timeframe, LiquiditySide.BUY_SIDE, "PDH", zone.high, origin, candles, live_bid, live_ask),
        _level(symbol, timeframe, LiquiditySide.SELL_SIDE, "PDL", zone.low, origin, candles, live_bid, live_ask),
    ]


def _previous_week_levels(symbol, timeframe, candles, live_bid, live_ask) -> List[LiquidityLevel]:
    zone = previous_week_high_low(symbol)
    if zone.low is None or zone.high is None:
        return []
    origin = zone.origin_time + timedelta(days=1)  # the level is "live" from the day after the closed week onward
    return [
        _level(symbol, timeframe, LiquiditySide.BUY_SIDE, "PWH", zone.high, origin, candles, live_bid, live_ask),
        _level(symbol, timeframe, LiquiditySide.SELL_SIDE, "PWL", zone.low, origin, candles, live_bid, live_ask),
    ]


def _level(symbol, timeframe, side, source, price, origin_time, candles, live_bid, live_ask) -> LiquidityLevel:
    after = [c for c in candles if c.time > origin_time]
    status, sweep_time, reclaim_time, reason_codes = compute_status(side, price, after, live_bid, live_ask)
    return LiquidityLevel(symbol=symbol, timeframe=timeframe, side=side, source=source, price=price,
                           origin_time=origin_time, status=status, sweep_time=sweep_time,
                           reclaim_time=reclaim_time, reason_codes=tuple(reason_codes))


def _nearest(levels: List[LiquidityLevel], side: LiquiditySide, reference_price: float) -> Optional[LiquidityLevel]:
    candidates = [l for l in levels if l.side == side and l.status == LiquidityStatus.UNSWEPT]
    if not candidates:
        candidates = [l for l in levels if l.side == side]
    if not candidates:
        return None
    return min(candidates, key=lambda l: abs(l.price - reference_price))
