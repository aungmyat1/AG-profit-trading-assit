"""Equal-highs / equal-lows: deterministic tolerance-based clustering of raw candle
extremes. Independent of market_structure's smc-based swing detection on purpose --
this is a liquidity-layer-owned method with its own explicit, documented tolerance
(config/liquidity.yaml), not a reuse of the swing_length-tuned structural swing finder.

Method: a candle's high/low is a "raw local extreme" if it's the max/min within a small
window of neighbors (local_extremum_window on each side) -- a much looser filter than a
confirmed structural swing, deliberately, since equal-highs/lows liquidity clusters are
often minor wicks that never qualify as a structural swing point. Local extremes within
`tolerance_price` of each other are chained into one cluster (adjacent-difference
tolerance, not a fixed hard cap across the whole cluster -- documented, not hidden).
"""
from __future__ import annotations

from typing import List, Optional, Sequence

from strategy_engine.session import Candle

from .models import LiquidityLevel, LiquiditySide
from .status import compute_status


def detect_equal_highs(symbol: str, timeframe: str, candles: Sequence[Candle],
                        tolerance_price: float, extremum_window: int,
                        live_bid: Optional[float] = None, live_ask: Optional[float] = None) -> List[LiquidityLevel]:
    points = _local_extremes(candles, extremum_window, want_high=True)
    return _cluster(symbol, timeframe, candles, points, tolerance_price, side=LiquiditySide.BUY_SIDE,
                     source="EQUAL_HIGHS", pick_extreme=max, live_bid=live_bid, live_ask=live_ask)


def detect_equal_lows(symbol: str, timeframe: str, candles: Sequence[Candle],
                       tolerance_price: float, extremum_window: int,
                       live_bid: Optional[float] = None, live_ask: Optional[float] = None) -> List[LiquidityLevel]:
    points = _local_extremes(candles, extremum_window, want_high=False)
    return _cluster(symbol, timeframe, candles, points, tolerance_price, side=LiquiditySide.SELL_SIDE,
                     source="EQUAL_LOWS", pick_extreme=min, live_bid=live_bid, live_ask=live_ask)


def _local_extremes(candles: Sequence[Candle], window: int, want_high: bool):
    n = len(candles)
    out = []
    for i in range(window, n - window):
        neighborhood = candles[i - window: i + window + 1]
        if want_high:
            if candles[i].high == max(c.high for c in neighborhood):
                out.append((candles[i].high, candles[i].time))
        else:
            if candles[i].low == min(c.low for c in neighborhood):
                out.append((candles[i].low, candles[i].time))
    return out


def _cluster(symbol, timeframe, candles, points, tolerance_price, side, source, pick_extreme,
             live_bid, live_ask) -> List[LiquidityLevel]:
    if not points or tolerance_price <= 0:
        return []
    ordered = sorted(points, key=lambda p: p[0])

    clusters = []
    current = [ordered[0]]
    for price, time in ordered[1:]:
        if price - current[-1][0] <= tolerance_price:
            current.append((price, time))
        else:
            clusters.append(current)
            current = [(price, time)]
    clusters.append(current)

    levels = []
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        prices = [p for p, _ in cluster]
        rep_price = pick_extreme(prices)
        latest_time = max(t for _, t in cluster)
        after = [c for c in candles if c.time > latest_time]
        status, sweep_time, reclaim_time, status_reasons = compute_status(side, rep_price, after, live_bid, live_ask)
        levels.append(LiquidityLevel(
            symbol=symbol, timeframe=timeframe, side=side, source=source,
            price=rep_price, origin_time=latest_time, status=status,
            sweep_time=sweep_time, reclaim_time=reclaim_time,
            reason_codes=(f"CLUSTER_SIZE_{len(cluster)}", *status_reasons),
        ))
    return levels
