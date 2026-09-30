"""VT Markets cost model for ledger re-costing (research only).

PLACEHOLDER: VT Markets MT5 symbol spreads are not captured/audited in this repository
(`config/mt5.yaml` symbol_map fails closed for VTMARKETS; no VT spread history exists).
The table below is an owner-replaceable placeholder, NOT a measured broker cost. Every
ledger row costed with it carries `cost_model_status = PLACEHOLDER_NOT_BROKER_MEASURED`.
Swap in a measured table (same shape) and set MEASURED=True once MT5 spreads exist.
"""
from __future__ import annotations

from typing import Optional

COST_MODEL_ID = "VT_MARKETS_STANDARD_PLACEHOLDER_V1"
MEASURED = False
COST_MODEL_STATUS = "MEASURED_BROKER_SPREAD" if MEASURED else "PLACEHOLDER_NOT_BROKER_MEASURED"

# Round-turn pips: spread paid once per fill, commission + slippage per round turn.
VT_MARKETS_PIPS = {
    "EURUSD": {"spread": 1.2, "commission": 0.0, "slippage": 0.3},
    "GBPUSD": {"spread": 1.6, "commission": 0.0, "slippage": 0.4},
}


def cost_r(symbol: str, stop_distance_price: float, pip_size: float) -> Optional[float]:
    """Total round-turn cost in R units of this entry's own stop distance; None when
    the symbol has no row or the stop distance is not positive (never guessed)."""
    row = VT_MARKETS_PIPS.get(symbol)
    if row is None or not stop_distance_price or stop_distance_price <= 0:
        return None
    return sum(row.values()) * pip_size / stop_distance_price
