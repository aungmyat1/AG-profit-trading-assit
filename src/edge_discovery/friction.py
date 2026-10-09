"""Phase 7 -- preregistered friction representation for the crypto CFD fast screen.

EPISTEMIC STATUS (frozen BEFORE any candidate profitability has ever been computed for
these instruments -- no BTCUSD/ETHUSD CFD economic result exists anywhere in this
repository at freeze time):

  - The evidence input is a SINGLE live spread observation per symbol
    (OBSERVED_LIVE_SPREAD, VT Markets demo, 2026-10-02, recorded in
    docs/status/AG_CRYPTO_SCANNER_V1_OBSERVATION_STATUS.md). One live snapshot is NOT
    historical spread truth and is never presented as a HISTORICAL_COST_MODEL.
  - Because historical bid/ask is unavailable, the model is a set of clearly labeled
    DETERMINISTIC SCENARIOS (BASE / STRESS / SEVERE multipliers of the observed
    snapshot), not invented precision.
  - Scenario selection discipline: the screening scenario is fixed here, in code,
    before results exist (SCREEN_SCENARIO = BASE, with STRESS and SEVERE always
    reported alongside). Choosing a scenario AFTER seeing which one preserves
    profitability is forbidden.

Cost accounting rule (preregistered): one full scenario spread per unit of notional per
round trip. The partial+runner exit splits the position but total exited notional still
equals entered notional, so cost_R = scenario_spread_price / risk_distance_price.
Units are native broker price units -- never FX pips.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

from .models import FrictionResult

FRICTION_MODEL_ID = "CRYPTO_CFD_SPREAD_SCENARIOS_V1"
EVIDENCE_KIND = "OBSERVED_LIVE_SPREAD_SNAPSHOT_2026_10_02"   # evidence input, not history
HISTORICAL_BID_ASK_AVAILABLE = False

# Raw single live observation per symbol, broker price units (bid/ask capture 2026-10-02).
OBSERVED_SPREAD_PRICE: Mapping[str, float] = MappingProxyType({
    "BTCUSD": 17.02,   # 1702 broker points, ~0.02016267%
    "ETHUSD": 2.50,    # 250 broker points,  ~0.09371790%
})

# Deterministic scenario multipliers -- FROZEN. Not calibrated to any backtest result.
SCENARIOS: Mapping[str, float] = MappingProxyType({
    "BASE": 1.0,
    "STRESS": 2.0,
    "SEVERE": 4.0,
})

# The scenario the fast screen is judged on, fixed before any result exists.
SCREEN_SCENARIO = "BASE"


def friction_for(symbol: str, scenario: str) -> FrictionResult:
    if symbol not in OBSERVED_SPREAD_PRICE:
        raise KeyError(f"no observed spread evidence for {symbol!r}; refusing to invent one")
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown friction scenario {scenario!r}; scenarios are frozen: "
                       f"{sorted(SCENARIOS)}")
    observed = OBSERVED_SPREAD_PRICE[symbol]
    mult = SCENARIOS[scenario]
    return FrictionResult(
        symbol=symbol, scenario=scenario, model_id=FRICTION_MODEL_ID,
        evidence_kind=EVIDENCE_KIND, spread_price=observed * mult,
        observed_spread_price=observed, multiplier=mult,
    )


def cost_r(symbol: str, scenario: str, risk_distance_price: float) -> float:
    """Round-trip cost expressed in R: scenario spread / stop distance (price units)."""
    if risk_distance_price <= 0:
        raise ValueError("risk_distance_price must be strictly positive")
    return friction_for(symbol, scenario).spread_price / risk_distance_price
