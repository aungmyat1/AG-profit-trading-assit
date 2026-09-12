"""Thin Backtesting.py adapter for S2R_BREAKOUT_RETEST_CONTINUATION_V1.

S2R signal DETECTION remains entirely owned by research_external/semantic/s2r.py
(the replay engine must never become the authoritative definition of S2R semantics,
per the mission's own rule). This adapter's only job is TRADE RESOLUTION: given a
signal's entry/stop/target, walk forward through subsequent candles to determine
which is touched first -- exactly the "historical fill simulation" Backtesting.py
already implements, not reimplemented here.

Order timing note: Backtesting.py places orders for execution at the NEXT bar's
open by default (trade_on_close=False, the default used here), not synthetically at
the same bar's close. S2R's own spec says entry = "confirmation_candle_close"; this
adapter's actual fill is therefore one bar later, at the confirmation bar's own next
open -- a strictly MORE conservative timing than the spec's nominal entry (you
cannot transact at a bar's exact closing print in reality), never a lookahead. This
is documented, not silently absorbed.
"""
from __future__ import annotations

from typing import Dict, List, Sequence

import pandas as pd
from backtesting import Backtest, Strategy

from research_external.semantic.s2r import S2RSignal


def to_backtesting_dataframe(candles: Sequence[dict]) -> pd.DataFrame:
    """Backtesting.py requires a DatetimeIndex and capitalized OHLCV columns."""
    frame = pd.DataFrame(candles)
    frame["time"] = pd.to_datetime(frame["time"], utc=True)
    frame = frame.set_index("time")
    frame = frame.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
    frame["Volume"] = frame.get("tick_volume", 0)
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def build_signal_index(candles: Sequence[dict], signals: Sequence[S2RSignal]) -> Dict[str, S2RSignal]:
    """Maps each actionable signal's confirmation timestamp -> S2RSignal, for O(1)
    lookup inside Strategy.next(). Only READY_LONG/READY_SHORT signals are indexed --
    every other reason_code produces no order by construction."""
    from research_external.semantic.s2r import REASON_READY_LONG, REASON_READY_SHORT

    return {
        s.decision_timestamp: s
        for s in signals
        if s.reason_code in (REASON_READY_LONG, REASON_READY_SHORT) and s.decision_timestamp
    }


def make_strategy_class(signal_index: Dict[str, S2RSignal]) -> type:
    """Returns a fresh Strategy subclass closing over `signal_index` -- Backtesting.py
    instantiates the class itself, so the signal map must be captured via closure."""

    class AGS2RStrategy(Strategy):
        def init(self):
            self.rejected_orders: List[str] = []

        def next(self):
            current_time = self.data.index[-1]
            key = current_time.isoformat()
            signal = signal_index.get(key)
            if signal is None:
                return
            if self.position:
                return  # exclusive_orders-equivalent discipline: one open trade at a time
            try:
                if signal.direction == "LONG":
                    self.buy(sl=signal.stop, tp=signal.target, tag=signal.risk_distance)
                elif signal.direction == "SHORT":
                    self.sell(sl=signal.stop, tp=signal.target, tag=signal.risk_distance)
            except ValueError:
                # The pure S2R evaluator guarantees stop < entry < target (or the
                # reverse for shorts) using an UNADJUSTED close price. Backtesting.py
                # additionally requires the SPREAD-ADJUSTED execution price to still
                # sit strictly between stop and target. On rare very-low-ATR signals
                # (risk_distance comparable to modeled spread) that bracket can
                # invert once spread is applied -- a real, honest friction rejection
                # (the spread genuinely consumes the whole risk/reward geometry at
                # that moment), not a bug to paper over. Recorded, not silently
                # dropped -- see rejected_orders on the strategy instance.
                self.rejected_orders.append(key)

    return AGS2RStrategy


def run_baseline(
    candles: Sequence[dict], signals: Sequence[S2RSignal], *,
    cash: float = 10_000.0, spread: float = 0.0, commission: float = 0.0,
) -> "tuple[pd.Series, pd.DataFrame]":
    """Runs exactly one baseline configuration (no optimization -- Backtest.optimize()
    is never called anywhere in this module or imported)."""
    data = to_backtesting_dataframe(candles)
    signal_index = build_signal_index(candles, signals)
    strategy_cls = make_strategy_class(signal_index)
    bt = Backtest(data, strategy_cls, cash=cash, spread=spread, commission=commission, exclusive_orders=True)
    stats = bt.run()
    trades = stats._trades.copy()
    return stats, trades


def rejected_order_count(stats) -> int:
    strategy_instance = stats.get("_strategy")
    return len(getattr(strategy_instance, "rejected_orders", []))
