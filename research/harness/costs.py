"""Itemized cost model: spread, commission, slippage and swap are separate ledger columns.

All inputs are price units (or price units per night for swap) so the model is venue- and
strategy-independent; each component is converted to R by dividing by the trade's own
risk_price (|entry - stop| from the engine ledger). Costs are signed as deductions (>= 0 for
spread/commission/slippage; swap may be a credit, i.e. negative cost).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from research.harness.ledger import DIRECTIONS

COST_COLUMNS = ("spread_R", "commission_R", "slippage_R", "swap_R")


@dataclass(frozen=True)
class SymbolCosts:
    spread: float = 0.0                 # round-trip bid/ask spread paid once per trade
    commission: float = 0.0             # round-trip commission, price-equivalent
    slippage_per_side: float = 0.0      # applied on entry and on exit
    stop_extra_slippage: float = 0.0    # added on exit when exit_reason == STOP
    swap_long_per_night: float = 0.0    # cost per rollover held (negative = credit)
    swap_short_per_night: float = 0.0
    triple_swap_weekday: int = 2        # Wednesday rollover charged x3 (FX convention)


@dataclass(frozen=True)
class CostModel:
    per_symbol: dict = field(default_factory=dict)
    rollover_hour_utc: int = 21          # conservative fixed UTC rollover; recorded in output

    def for_symbol(self, symbol: str) -> SymbolCosts:
        if symbol not in self.per_symbol:
            raise KeyError(f"no cost entry for {symbol}: refusing to assume zero costs")
        return self.per_symbol[symbol]


def rollover_nights(entry, exit_, hour: int, triple_weekday: int) -> int:
    """Count rollovers crossed in (entry, exit]; the triple-swap weekday counts 3."""
    first = entry.normalize() + pd.Timedelta(hours=hour)
    if first <= entry:
        first += pd.Timedelta(days=1)
    if first > exit_:
        return 0
    rolls = pd.date_range(first, exit_, freq="D")
    return int(sum(3 if r.weekday() == triple_weekday else 1 for r in rolls if r.weekday() < 5))


def apply_costs(ledger: pd.DataFrame, model: CostModel, multiplier: float = 1.0) -> pd.DataFrame:
    """Return ledger with gross_R, the four itemized cost columns (in R), total_cost_R and net_R."""
    out = ledger.copy()
    sign = out["direction"].map(DIRECTIONS)
    out["gross_R"] = (out["exit_price"] - out["entry_price"]) * sign / out["risk_price"]
    rows = {c: [] for c in COST_COLUMNS}
    nights = []
    for r in out.itertuples(index=False):
        c = model.for_symbol(r.symbol)
        slip = 2 * c.slippage_per_side + (c.stop_extra_slippage if r.exit_reason == "STOP" else 0.0)
        n = rollover_nights(r.entry_time, r.exit_time, model.rollover_hour_utc, c.triple_swap_weekday)
        swap = n * (c.swap_long_per_night if r.direction == "LONG" else c.swap_short_per_night)
        nights.append(n)
        for col, v in zip(COST_COLUMNS, (c.spread, c.commission, slip, swap)):
            rows[col].append(multiplier * v / r.risk_price)
    for col in COST_COLUMNS:
        out[col] = rows[col]
    out["swap_nights"] = nights
    out["total_cost_R"] = out[list(COST_COLUMNS)].sum(axis=1)
    out["net_R"] = out["gross_R"] - out["total_cost_R"]
    out["cost_multiplier"] = multiplier
    return out
