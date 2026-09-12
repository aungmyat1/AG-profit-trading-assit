"""AG_R6_ECONOMIC_GATE_CONTRACT evaluator -- deterministic, fail-closed consumer of a
SIGNED config/governance/economic_gate_contract.yaml.

This module is NOT a new validation authority: it reads a signed contract (governance
truth) and a performance.models.TradeMetrics (performance truth, already computed by
src/performance/calculator.py) and returns one explicit verdict. It never computes
metrics itself, never mutates the contract file, never touches strategy files, never
submits or authorizes anything.

Fail-closed rules (each has a dedicated test in tests/test_economic_gate_evaluator.py):
  - contract missing / status != SIGNED         -> NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS
  - SIGNED contract missing a required field     -> NOT_EVALUABLE_INCOMPLETE_CONTRACT (fail
                                                     closed, never substitutes a default)
  - evidence_complete is not True                -> INSUFFICIENT_EVIDENCE (never
                                                     EDGE_VALIDATED regardless of metrics)
  - sample_size below the contract's own minimum -> INSUFFICIENT_EVIDENCE
  - metrics fail any economics/robustness bound  -> EDGE_REJECTED
  - metrics clear every bound                    -> EDGE_VALIDATED

Same (contract, metrics, evidence_complete) always yields the same verdict -- no
wall-clock, no randomness, no hidden state.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import yaml

from performance.models import NOT_EVALUATED, TradeMetrics

VERDICT_EDGE_VALIDATED = "EDGE_VALIDATED"
VERDICT_EDGE_REJECTED = "EDGE_REJECTED"
VERDICT_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS = "NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS"
VERDICT_NOT_EVALUABLE_INCOMPLETE_CONTRACT = "NOT_EVALUABLE_INCOMPLETE_CONTRACT"

DEFAULT_CONTRACT_PATH = os.path.join("config", "governance", "economic_gate_contract.yaml")

_REQUIRED_FIELDS = (
    ("sample", "minimum_resolved_trades"),
    ("economics", "minimum_net_expectancy_R"),
    ("economics", "minimum_profit_factor"),
    ("economics", "maximum_drawdown_R"),
    ("evidence", "accepted_cost_statuses"),
)


@dataclass(frozen=True)
class EconomicGateVerdict:
    strategy_id: str
    strategy_version: str
    verdict: str
    reason: str
    contract_id: Optional[str] = None
    contract_version: Optional[str] = None


def load_contract(path: str = DEFAULT_CONTRACT_PATH) -> Optional[Dict[str, Any]]:
    """Read-only. Returns None if the file does not exist -- never fabricates a
    contract. Raises on malformed YAML rather than silently treating it as absent."""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _contract_is_signed(contract: Optional[Dict[str, Any]]) -> bool:
    if not contract:
        return False
    identity = contract.get("identity") or {}
    return identity.get("status") == "SIGNED"


def _missing_required_fields(contract: Dict[str, Any]) -> list:
    missing = []
    for section, field_name in _REQUIRED_FIELDS:
        section_dict = contract.get(section)
        if not isinstance(section_dict, dict) or field_name not in section_dict or section_dict[field_name] is None:
            missing.append(f"{section}.{field_name}")
    return missing


def evaluate_economic_gate(
    strategy_id: str,
    strategy_version: str,
    metrics: Optional[TradeMetrics],
    evidence_complete: bool,
    contract: Optional[Dict[str, Any]],
) -> EconomicGateVerdict:
    if not _contract_is_signed(contract):
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS,
            "no contract, or identity.status != SIGNED -- proposed thresholds are never evaluated against",
        )

    contract_identity = contract["identity"]
    contract_id = contract_identity.get("contract_id")
    contract_version = contract_identity.get("version")

    missing = _missing_required_fields(contract)
    if missing:
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_NOT_EVALUABLE_INCOMPLETE_CONTRACT,
            f"SIGNED contract missing required field(s): {', '.join(missing)}",
            contract_id, contract_version,
        )

    if not evidence_complete:
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_INSUFFICIENT_EVIDENCE,
            "evidence_complete is not True",
            contract_id, contract_version,
        )

    if metrics is None:
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_INSUFFICIENT_EVIDENCE,
            "no performance metrics available", contract_id, contract_version,
        )

    min_sample = contract["sample"]["minimum_resolved_trades"]
    if metrics.sample_size < min_sample:
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_INSUFFICIENT_EVIDENCE,
            f"sample_size {metrics.sample_size} < minimum_resolved_trades {min_sample}",
            contract_id, contract_version,
        )

    if metrics.cost_status not in contract["evidence"]["accepted_cost_statuses"]:
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_INSUFFICIENT_EVIDENCE,
            f"cost_status {metrics.cost_status!r} not in accepted_cost_statuses "
            f"{contract['evidence']['accepted_cost_statuses']}",
            contract_id, contract_version,
        )

    net_expectancy = metrics.net_expectancy_R
    if net_expectancy == NOT_EVALUATED or not isinstance(net_expectancy, (int, float)):
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_INSUFFICIENT_EVIDENCE,
            "net_expectancy_R is NOT_EVALUATED", contract_id, contract_version,
        )

    min_net_expectancy = contract["economics"]["minimum_net_expectancy_R"]
    min_profit_factor = contract["economics"]["minimum_profit_factor"]
    max_drawdown = contract["economics"]["maximum_drawdown_R"]

    failures = []
    if net_expectancy < min_net_expectancy:
        failures.append(f"net_expectancy_R {net_expectancy} < minimum {min_net_expectancy}")

    profit_factor = metrics.profit_factor
    if isinstance(profit_factor, (int, float)):
        if profit_factor < min_profit_factor:
            failures.append(f"profit_factor {profit_factor} < minimum {min_profit_factor}")
    else:
        failures.append(f"profit_factor is {profit_factor!r}, cannot verify >= {min_profit_factor}")

    max_dd = metrics.max_drawdown_R
    if isinstance(max_dd, (int, float)):
        if max_dd > max_drawdown:
            failures.append(f"max_drawdown_R {max_dd} > maximum {max_drawdown}")
    else:
        failures.append(f"max_drawdown_R is {max_dd!r}, cannot verify <= {max_drawdown}")

    if failures:
        return EconomicGateVerdict(
            strategy_id, strategy_version, VERDICT_EDGE_REJECTED,
            "; ".join(failures), contract_id, contract_version,
        )

    return EconomicGateVerdict(
        strategy_id, strategy_version, VERDICT_EDGE_VALIDATED,
        "all signed economic/robustness bounds satisfied", contract_id, contract_version,
    )
