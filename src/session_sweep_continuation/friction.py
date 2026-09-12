"""Transaction friction model: spread + commission + slippage, expressed in
price/pips/cash/R, with an explicit cost_status per computation.

No existing friction/cost model was found reusable in this worktree -- project memory
names src/performance/cost_model.py and src/fx_friction_research/ as recently added,
but this worktree is a fresh checkout of committed HEAD (5ca5854) and neither exists
here (verified: os.path checks below / repo listing). This module is therefore a new,
narrowly-scoped implementation. If those modules land on this branch later, they should
be evaluated for consolidation -- recorded as a known gap.

cost_status contract (spec-required): KNOWN (broker-quoted live values supplied),
MODELED (this strategy's own documented config defaults used), UNAVAILABLE (no spread/
commission data at all). Only KNOWN or MODELED may be treated as "friction computed";
UNAVAILABLE must make the stop engine fail closed (REJECT_SETUP), never silently treat
cost as zero -- see stop_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FrictionEstimate:
    symbol: str
    spread_pips: Optional[float]
    commission_pips: Optional[float]
    slippage_pips: Optional[float]
    total_pips: Optional[float]
    total_price: Optional[float]     # in quote-currency price units (pip_size * total_pips)
    total_cash: Optional[float]      # for `lots` lot size, using pip_value_per_lot
    total_r: Optional[float]         # total_price / stop_distance_price, if stop provided
    cost_status: str                 # KNOWN | MODELED | UNAVAILABLE


def estimate_friction(
    symbol: str,
    config: dict,
    pip_size: float,
    pip_value_per_lot: float,
    lots: float = 1.0,
    stop_distance_price: Optional[float] = None,
    live_spread_pips: Optional[float] = None,
    live_commission_pips: Optional[float] = None,
    live_slippage_pips: Optional[float] = None,
) -> FrictionEstimate:
    friction_cfg = config.get("friction", {})

    spread = live_spread_pips
    commission = live_commission_pips
    slippage = live_slippage_pips
    used_live = spread is not None and commission is not None and slippage is not None

    if not used_live:
        default_spread = friction_cfg.get("default_spread_pips", {}).get(symbol)
        default_commission = friction_cfg.get("default_commission_pips", {}).get(symbol)
        default_slippage = friction_cfg.get("default_slippage_pips", {}).get(symbol)
        if default_spread is None or default_commission is None or default_slippage is None:
            return FrictionEstimate(
                symbol=symbol, spread_pips=None, commission_pips=None, slippage_pips=None,
                total_pips=None, total_price=None, total_cash=None, total_r=None,
                cost_status="UNAVAILABLE",
            )
        spread = spread if spread is not None else default_spread
        commission = commission if commission is not None else default_commission
        slippage = slippage if slippage is not None else default_slippage
        cost_status = "MODELED"
    else:
        cost_status = "KNOWN"

    total_pips = spread + commission + slippage
    total_price = total_pips * pip_size
    total_cash = total_pips * pip_value_per_lot * lots
    total_r = (total_price / stop_distance_price) if stop_distance_price else None

    return FrictionEstimate(
        symbol=symbol, spread_pips=spread, commission_pips=commission, slippage_pips=slippage,
        total_pips=total_pips, total_price=total_price, total_cash=total_cash, total_r=total_r,
        cost_status=cost_status,
    )
