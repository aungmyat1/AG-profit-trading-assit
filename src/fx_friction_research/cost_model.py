"""AG_THREE_STRATEGY_VALIDATION_CONTINUATION_V1 (Session Trade economic validation, P2/P3).
Minimal, explicitly-governed FX friction (spread/commission/slippage) cost model for
ST_ASIAN_SWEEP_5R_V1's resolved forward-shadow outcomes.

Audited before adding: no existing FX-specific cost/friction model was found anywhere in
this repository (searched src/, scripts/; entry_confirmation/spread.py is pre-trade alert
geometry, never a realized-cost model; src/btc_sweep_research/costs.py is BTC-specific
fee/funding, wrong instrument mechanics for FX pip/spread economics but the same
"minimal, explicitly-documented, no live-fetched numbers presented as fetched facts"
convention is deliberately reused here). This is genuinely new.

Why governed SCENARIOS, not a single number: no real per-trade or per-symbol historical
Vantage FX spread/commission/slippage capture exists in this repository (confirmed by
searching docs/status/ -- the one real broker-cost audit found,
docs/status/AG_BTC_VANTAGE_ECONOMIC_RECONCILIATION_V1_STATUS.md, is BTC/BTCUSD-specific
and explicitly states commission was "NOT CAPTURED this pass" even there). Presenting a
single invented number as if it were a measured historical fact would violate the
"never infer missing evidence" rule. Instead, three explicit, sourced scenarios are
offered; BASE/STRESSED/SEVERE are estimates, never presented as exact historical fills.

Real, signed evidence used as anchors (not invented) --
strategies/ST_ASIAN_SWEEP_5R_V1.yaml:
    max_spread_allowed_pips: 2.0   (line 110)
    slippage_limit_points: 10      (line 111)
-- and docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_
STATUS.md's real MT5 symbol_metadata capture for EURUSD/GBPUSD: digits=5, tick_size=1e-05
-- a 5-digit broker, so 1 pip = 10 points (0.0001 = 10 x 0.00001). This is how
slippage_limit_points=10 converts to exactly 1.0 pip below, not an assumed conversion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# 5-digit broker convention (real, captured evidence -- see module docstring): both
# EURUSD and GBPUSD quote to 5 decimals, pip = 10 x tick_size = 0.0001.
PIP_SIZE: Dict[str, float] = {
    "EURUSD": 0.0001,
    "GBPUSD": 0.0001,
}

# Real, signed strategy config (strategies/ST_ASIAN_SWEEP_5R_V1.yaml) -- the strategy's
# own configured maximum spread/slippage it is willing to trade under. Used as the
# STRESSED/SEVERE anchors below rather than invented figures.
STRATEGY_MAX_SPREAD_ALLOWED_PIPS = 2.0  # ST_ASIAN_SWEEP_5R_V1.yaml:110
STRATEGY_SLIPPAGE_LIMIT_PIPS = 1.0  # ST_ASIAN_SWEEP_5R_V1.yaml:111: 10 points / 10 points-per-pip


@dataclass(frozen=True)
class CostScenario:
    """One governed friction scenario. Every field carries its own source -- never
    presented as a measured historical fill. `spread_pips`/`commission_pips`/
    `slippage_pips` are each a ONE-TIME, round-turn-equivalent pip cost applied once per
    trade (see calculate_trade_friction's docstring for the exact arithmetic and its
    documented limitation)."""

    name: str
    spread_pips: float
    commission_pips: float
    slippage_pips: float
    source: str

    @property
    def total_friction_pips(self) -> float:
        return self.spread_pips + self.commission_pips + self.slippage_pips


SCENARIOS: Dict[str, CostScenario] = {
    "BASE": CostScenario(
        name="BASE",
        spread_pips=0.8,
        commission_pips=0.7,
        slippage_pips=0.3,
        source=(
            "Documented industry-typical figures for a retail ECN/STP EURUSD/GBPUSD "
            "account (approx. 0.8 pip average spread, approx. $7/round-turn-per-standard-"
            "lot commission expressed as pip-equivalent, approx. 0.3 pip conservative "
            "market-order slippage) -- NOT a Vantage-specific measured historical fact; "
            "no such capture exists in this repository for FX (the one real broker-cost "
            "audit found, AG_BTC_VANTAGE_ECONOMIC_RECONCILIATION_V1_STATUS.md, is "
            "BTC/BTCUSD-specific and itself could not capture commission)."
        ),
    ),
    "STRESSED": CostScenario(
        name="STRESSED",
        spread_pips=STRATEGY_MAX_SPREAD_ALLOWED_PIPS,
        commission_pips=0.7,
        slippage_pips=STRATEGY_SLIPPAGE_LIMIT_PIPS,
        source=(
            "spread_pips = strategies/ST_ASIAN_SWEEP_5R_V1.yaml:110 max_spread_allowed_pips "
            "(the strategy's own signed maximum-tradable-spread threshold, i.e. the worst "
            "spread this strategy is configured to still enter under); slippage_pips = "
            "strategies/ST_ASIAN_SWEEP_5R_V1.yaml:111 slippage_limit_points=10, converted "
            "at 10 points/pip for this 5-digit-quote symbol (real captured evidence: "
            "docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_"
            "CLOSURE_STATUS.md's EURUSD/GBPUSD symbol_metadata, digits=5/tick_size=1e-05); "
            "commission_pips unchanged from BASE (no independent basis to stress it)."
        ),
    ),
    "SEVERE": CostScenario(
        name="SEVERE",
        spread_pips=2 * STRATEGY_MAX_SPREAD_ALLOWED_PIPS,
        commission_pips=0.7,
        slippage_pips=2 * STRATEGY_SLIPPAGE_LIMIT_PIPS,
        source=(
            "2x the STRESSED spread/slippage anchors -- an explicit, labeled hypothetical "
            "adverse-liquidity-event stress case (e.g. a news spike), not a measured or "
            "observed historical condition; commission_pips unchanged from BASE."
        ),
    ),
}


@dataclass(frozen=True)
class TradeFriction:
    proposal_id: str
    scenario: str
    gross_R: float
    risk_price_distance: float
    pip_size: float
    spread_cost_R: float
    commission_cost_R: float
    slippage_cost_R: float
    total_friction_R: float
    net_R: float


def calculate_trade_friction(
    proposal_id: str,
    symbol: str,
    entry: float,
    stop_loss: float,
    gross_R: float,
    scenario: CostScenario,
) -> TradeFriction:
    """Converts a scenario's fixed pip-cost assumptions into this specific trade's own
    R-denominated cost, using the trade's OWN real risk distance (abs(entry - stop_loss))
    -- so while the pip-cost assumption is scenario-fixed (no per-trade historical spread
    exists to do otherwise, see module docstring), the resulting R-cost is genuinely
    per-trade, not one flat R number copy-pasted across every trade.

    Calculation method (deliberately simple, documented, not a fill-by-fill simulation):
    each of spread/commission/slippage is modeled as a ONE-TIME round-turn-equivalent pip
    cost, converted to a price distance via this symbol's PIP_SIZE, then expressed in R by
    dividing by the trade's own risk_price_distance. total_friction_R is their sum;
    net_R = gross_R - total_friction_R (never the other direction -- gross_R, read
    verbatim from the resolved outcome record, is never modified).

    Documented limitation: this does not separately model a half-spread-on-entry vs
    half-spread-on-exit split, nor a distinct entry-slippage vs exit-slippage split -- it
    is a single lumped round-turn estimate per leg-type, appropriate for a governed
    stress-scenario estimate, not a claim of fill-by-fill precision.

    Fails closed (raises ValueError) rather than silently defaulting to 0 friction if the
    symbol has no known PIP_SIZE or the trade's risk distance is non-positive (a
    malformed record this tool has no basis to interpret)."""
    if symbol not in PIP_SIZE:
        raise ValueError(f"No governed PIP_SIZE for symbol {symbol!r} -- refusing to fabricate a conversion.")
    pip_size = PIP_SIZE[symbol]
    risk = abs(entry - stop_loss)
    if risk <= 0:
        raise ValueError(f"{proposal_id}: non-positive risk distance ({risk}) -- malformed record, refusing to compute friction.")

    spread_cost_R = (scenario.spread_pips * pip_size) / risk
    commission_cost_R = (scenario.commission_pips * pip_size) / risk
    slippage_cost_R = (scenario.slippage_pips * pip_size) / risk
    total_friction_R = spread_cost_R + commission_cost_R + slippage_cost_R

    return TradeFriction(
        proposal_id=proposal_id,
        scenario=scenario.name,
        gross_R=gross_R,
        risk_price_distance=risk,
        pip_size=pip_size,
        spread_cost_R=spread_cost_R,
        commission_cost_R=commission_cost_R,
        slippage_cost_R=slippage_cost_R,
        total_friction_R=total_friction_R,
        net_R=gross_R - total_friction_R,
    )
