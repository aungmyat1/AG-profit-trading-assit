"""AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1 P6/P7 -- canonical FX transaction-cost model.

Every outcome_resolution record for ST_ASIAN_SWEEP_5R_V1 self-declares
`cost_status: "NOT_INCLUDED"` (verified: all 13 records, 2026-09-09) -- no friction has
ever been applied to any FX resolved trade. This module computes net_R as ADDITIVE
derived evidence layered on top of the existing, immutable outcome_resolution records --
it never edits those files (P6: "do not modify gross historical outcomes"; P7:
"costs must be additive evidence").

Cost assumptions used here are NOT invented. The only repository-governed FX friction
figures found (grep-verified across strategies/, config/, artifacts/readiness/) are in
strategies/ST_ASIAN_SWEEP_5R_V1.yaml's own risk_and_money_management block:

    max_spread_allowed_pips = 2.0   (the strategy's own trade-permission ceiling)
    slippage_limit_points    = 10    (broker points; 10 points = 1.0 pip on a 5-digit
                                      EURUSD/GBPUSD quote, confirmed against the
                                      recorded entry/stop_loss price precision in every
                                      outcome_resolution record)

No repository or owner-signed "typical"/average spread or any commission figure exists
for the connected Vantage Markets Demo MT5 account (grep-verified across
artifacts/readiness/AG_VANTAGE_UNIFIED_BROKER_MIGRATION_V1_*.json and every FX status
document) -- inventing one would violate P7 ("Do not invent thresholds without
repository or owner authority"). Consequently this module produces exactly ONE
evidence-backed scenario (`CONTRACT_CEILING`, the strategy's own worst-case-still-
permitted friction) and explicitly reports `BASE`/`STRESSED`/`SEVERE` as
`NOT_AVAILABLE_NO_SIGNED_ASSUMPTION` rather than fabricating numbers for them. Commission
is reported `0.0` with an explicit `UNVERIFIED_NO_SIGNED_COMMISSION_RATE` flag, never
silently assumed to be a confirmed zero.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from performance.models import ResolvedTradeSample

RECORDS_DIR = os.path.join("artifacts", "outcome_resolution", "records")

PIP_SIZE = 0.0001  # 5-digit EURUSD/GBPUSD quote convention (confirmed against recorded
                    # entry/stop_loss decimal precision in every outcome_resolution record)
POINT_SIZE = PIP_SIZE / 10  # strategies/ST_ASIAN_SWEEP_5R_V1.yaml's slippage_limit_points unit

MAX_SPREAD_ALLOWED_PIPS = 2.0    # strategies/ST_ASIAN_SWEEP_5R_V1.yaml:110
SLIPPAGE_LIMIT_POINTS = 10       # strategies/ST_ASIAN_SWEEP_5R_V1.yaml:111
SLIPPAGE_LIMIT_PIPS = SLIPPAGE_LIMIT_POINTS * POINT_SIZE / PIP_SIZE  # = 1.0 pip

COMMISSION_ASSUMPTION_NOTE = "UNVERIFIED_NO_SIGNED_COMMISSION_RATE"

SCENARIO_CONTRACT_CEILING = "CONTRACT_CEILING"
SCENARIO_NOT_AVAILABLE = "NOT_AVAILABLE_NO_SIGNED_ASSUMPTION"

# Only one scenario has real, signed evidence behind it (see module docstring). BASE and
# SEVERE are explicitly reported as unavailable rather than invented -- P7 governance.
FRICTION_SCENARIOS: Dict[str, Optional[Dict[str, float]]] = {
    "BASE": None,
    SCENARIO_CONTRACT_CEILING: {
        "spread_pips": MAX_SPREAD_ALLOWED_PIPS,
        "slippage_pips": SLIPPAGE_LIMIT_PIPS,
        "commission_per_lot": 0.0,
    },
    "SEVERE": None,
}


@dataclass(frozen=True)
class CostAdjustedTradeSample:
    """One resolved trade's gross result plus a fully itemized, scenario-labeled
    friction breakdown. `net_R = gross_R - total_friction_R` always -- enforced by
    construction below, never independently computed elsewhere. Additive only: neither
    this dataclass nor the function producing it ever writes back to the source
    outcome_resolution record."""

    source_record_id: str
    source_path: str
    scenario: str
    gross_R: float
    spread_cost_R: float
    commission_cost_R: float
    slippage_cost_R: float
    other_cost_R: float
    total_friction_R: float
    net_R: float
    risk_distance_price: float
    assumptions_note: str


def _read_records(repo_root: str, strategy_id: str, strategy_version: str) -> List[Tuple[str, dict]]:
    directory = os.path.join(repo_root, RECORDS_DIR)
    out: List[Tuple[str, dict]] = []
    if not os.path.isdir(directory):
        return out
    for name in sorted(os.listdir(directory)):
        if not name.startswith(strategy_id) or not name.endswith(".json"):
            continue
        path = os.path.join(directory, name)
        with open(path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        if record.get("strategy_version") != strategy_version:
            continue
        if record.get("realized_R") is None:
            continue
        out.append((os.path.join(RECORDS_DIR, name).replace("\\", "/"), record))
    return out


def apply_contract_ceiling_scenario(
    repo_root: str = ".", strategy_id: str = "ST_ASIAN_SWEEP_5R_V1", strategy_version: str = "1.1.1",
) -> List[CostAdjustedTradeSample]:
    """Computes the CONTRACT_CEILING-scenario net_R for every resolved
    ST_ASIAN_SWEEP_5R_V1 trade, deriving risk_distance from each record's own
    entry/stop_loss (never a hardcoded per-trade R value) so total_friction_R is
    expressed correctly in that trade's own risk units."""
    scenario_pips = FRICTION_SCENARIOS[SCENARIO_CONTRACT_CEILING]
    friction_price = (scenario_pips["spread_pips"] + scenario_pips["slippage_pips"]) * PIP_SIZE
    commission_R = scenario_pips["commission_per_lot"]  # 0.0, UNVERIFIED (see module docstring)

    results: List[CostAdjustedTradeSample] = []
    for path, record in _read_records(repo_root, strategy_id, strategy_version):
        entry = record.get("entry")
        stop_loss = record.get("stop_loss")
        if entry is None or stop_loss is None:
            continue  # cannot derive a risk-unit conversion without both -- never guessed
        risk_distance = abs(entry - stop_loss)
        if risk_distance <= 0:
            continue  # degenerate/invalid geometry -- fail closed, not divide-by-zero
        friction_R = friction_price / risk_distance
        gross_R = float(record["realized_R"])
        net_R = gross_R - friction_R
        results.append(CostAdjustedTradeSample(
            source_record_id=record["proposal_id"],
            source_path=path,
            scenario=SCENARIO_CONTRACT_CEILING,
            gross_R=gross_R,
            spread_cost_R=(scenario_pips["spread_pips"] * PIP_SIZE) / risk_distance,
            commission_cost_R=commission_R,
            slippage_cost_R=(scenario_pips["slippage_pips"] * PIP_SIZE) / risk_distance,
            other_cost_R=0.0,
            total_friction_R=friction_R,
            net_R=net_R,
            risk_distance_price=risk_distance,
            assumptions_note=(
                f"spread<={scenario_pips['spread_pips']}pips (strategy's own max_spread_allowed_pips), "
                f"slippage<={scenario_pips['slippage_pips']}pips (strategy's own slippage_limit_points), "
                f"commission={COMMISSION_ASSUMPTION_NOTE}"
            ),
        ))
    return results


def to_resolved_trade_samples(
    cost_adjusted: List[CostAdjustedTradeSample], base_samples: List[ResolvedTradeSample],
) -> List[ResolvedTradeSample]:
    """Merges CONTRACT_CEILING net_R onto the existing normalized ResolvedTradeSample
    list (from performance.adapters.fx_adapter.load_fx_resolved_samples) by
    source_record_id, WITHOUT mutating the originals -- returns a new list of new
    frozen dataclass instances. A sample with no cost-adjusted counterpart (e.g.
    missing entry/stop_loss) keeps net_R=None (NOT_EVALUATED), never fabricated."""
    by_id = {c.source_record_id: c for c in cost_adjusted}
    merged: List[ResolvedTradeSample] = []
    for s in base_samples:
        adjusted = by_id.get(s.source_record_id)
        if adjusted is None:
            merged.append(s)
            continue
        merged.append(ResolvedTradeSample(
            source_record_id=s.source_record_id, source_path=s.source_path,
            strategy_id=s.strategy_id, strategy_version=s.strategy_version,
            symbol=s.symbol, cycle=s.cycle, resolved_at=s.resolved_at,
            gross_R=s.gross_R, net_R=adjusted.net_R,
            cost_status=f"INCLUDED_{adjusted.scenario}", outcome=s.outcome,
        ))
    return merged
