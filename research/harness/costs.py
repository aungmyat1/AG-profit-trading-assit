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
    swap_rollover3days: int | None = None  # MT5 symbol_info.swap_rollover3days (0=Sun..6=Sat); required


@dataclass(frozen=True)
class CostModel:
    per_symbol: dict = field(default_factory=dict)

    def for_symbol(self, symbol: str) -> SymbolCosts:
        if symbol not in self.per_symbol:
            raise KeyError(f"no cost entry for {symbol}: refusing to assume zero costs")
        c = self.per_symbol[symbol]
        if c.swap_rollover3days not in range(7):
            raise KeyError(f"no swap_rollover3days (0=Sun..6=Sat) for {symbol}: refusing to assume a triple-swap day")
        return c


ROLLOVER_TZ = "America/New_York"
ROLLOVER_LOCAL_HOUR = 17
ROLLOVER_CONVENTION = "17:00 America/New_York (DST-aware), Mon-Fri; triple day from swap_rollover3days"


def rollover_nights(entry, exit_, rollover3days: int) -> int:
    """Count 17:00 New York rollovers crossed in (entry, exit]; the MT5 swap_rollover3days
    weekday (0=Sun..6=Sat, New York local date) counts 3. Weekend dates carry no rollover."""
    triple = (rollover3days - 1) % 7  # MT5 Sunday=0 -> Python Monday=0 convention
    n = 0
    for d in pd.date_range(entry.tz_convert(ROLLOVER_TZ).date() - pd.Timedelta(days=1),
                           exit_.tz_convert(ROLLOVER_TZ).date(), freq="D"):  # naive local dates
        roll = (d + pd.Timedelta(hours=ROLLOVER_LOCAL_HOUR)).tz_localize(ROLLOVER_TZ)
        if d.weekday() < 5 and entry < roll <= exit_:
            n += 3 if d.weekday() == triple else 1
    return n


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
        n = rollover_nights(r.entry_time, r.exit_time, c.swap_rollover3days)
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
