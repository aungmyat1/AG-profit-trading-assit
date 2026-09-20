"""Deterministic research execution model for SSC historical edge validation.

This contract intentionally separates historical edge testing from broker execution
parity. It is a research-only model for post-cost assessment of strategy edge under
reasonable execution assumptions. It does not claim exact broker economics, demo
execution authority, or live execution authority.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


class EdgeRealityModelError(ValueError):
    pass


EDGE_REALITY_MODEL_VERSION = "EDGE_REALITY_MODEL_V1"
EDGE_REALITY_MODEL_STATUS = "FROZEN"

EDGE_REALITY_MODEL = {
    "schema_version": EDGE_REALITY_MODEL_VERSION,
    "status": EDGE_REALITY_MODEL_STATUS,
    "purpose": "STRATEGY_EDGE_VALIDATION",
    "strategy_scope": "SSC v1.0.1 strategy-edge validation only",
    "strategy_id": "ST_SESSION_SWEEP_CONTINUATION_V1",
    "strategy_version": "1.0.1",
    "not_broker_execution_parity": True,
    "not_live_execution_authority": True,
    "not_demo_execution_authority": True,
    "not_broker_execution_parity_reason": "Exact Vantage/MT5 spread, commission, slippage, leverage, margin, and latency are intentionally deferred to BROKER_EXECUTION_PARITY",
    "evidence_authority": [
        "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml::friction.default_spread_pips",
        "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml::friction.default_commission_pips",
        "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml::friction.default_slippage_pips",
        "src/svos/friction_contract.py::UNAVAILABLE never converts to zero",
    ],
    "spread_status": "MODELLED",
    "spread_provenance": "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction.default_spread_pips (research defaults, not broker observations)",
    "spread_value_or_model": {"EURUSD": 1.0, "GBPUSD": 1.4},
    "spread_units": {"source_value": "pips", "per_side_or_round_trip": "round_trip_per_trade", "conversion_to_price_or_currency_cost": "spread_pips * pip_size", "conversion_to_R": "(spread_price / risk_distance_price)", "source_classification": "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"},
    "commission_status": "MODELLED",
    "commission_provenance": "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction.default_commission_pips (research defaults, not broker observations)",
    "commission_value_or_model": {"EURUSD": 0.2, "GBPUSD": 0.2},
    "commission_units": {"source_value": "pips", "per_side_or_round_trip": "round_trip_per_trade", "conversion_to_price_or_currency_cost": "commission_pips * pip_size", "conversion_to_R": "(commission_price / risk_distance_price)", "source_classification": "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"},
    "slippage_status": "MODELLED",
    "slippage_provenance": "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction.default_slippage_pips (research defaults, not broker observations)",
    "slippage_value_or_model": {"EURUSD": 0.3, "GBPUSD": 0.4},
    "slippage_units": {"source_value": "pips", "per_side_or_round_trip": "round_trip_per_trade", "conversion_to_price_or_currency_cost": "slippage_pips * pip_size", "conversion_to_R": "(slippage_price / risk_distance_price)", "source_classification": "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"},
    "latency_status": "NOT_MATERIALLY_RESOLVABLE_AT_DATA_RESOLUTION",
    "latency_research_status": "NOT_MATERIALLY_RESOLVABLE_AT_DATA_RESOLUTION",
    "latency_broker_parity_status": "DEFERRED_EXECUTION_PARITY",
    "latency_authority": "Historical M15/M1 bars do not carry a meaningful execution-latency distribution for this strategy/data resolution; defer to broker execution parity",
    "latency_value_or_model": None,
    "scenario_policy": {
        "LOW_PLAUSIBLE": "promote only the lower-bound realistic variation implied by the strategy's own documented defaults",
        "BASE_REPRESENTATIVE": "primary strategy-edge result; use the strategy's own documented defaults as the baseline", 
        "CONSERVATIVE_STRESS": "apply a slightly more punitive but still deterministic friction increase without claiming exact broker values",
        "broker_execution_parity": "deferred; does not block development edge validation",
    },
    "scenarios": {
        "LOW_PLAUSIBLE": {
            "symbol_values": {
                "EURUSD": {"spread_pips": 0.8, "commission_pips": 0.1, "slippage_pips": 0.2},
                "GBPUSD": {"spread_pips": 1.0, "commission_pips": 0.1, "slippage_pips": 0.2},
            },
            "provenance": "derived from lower-bound of the strategy's own documented friction defaults; not broker observed",
            "units": {"spread_pips": "pips", "commission_pips": "pips", "slippage_pips": "pips"},
        },
        "BASE_REPRESENTATIVE": {
            "symbol_values": {
                "EURUSD": {"spread_pips": 1.0, "commission_pips": 0.2, "slippage_pips": 0.3},
                "GBPUSD": {"spread_pips": 1.4, "commission_pips": 0.2, "slippage_pips": 0.4},
            },
            "provenance": "strategy's own documented defaults for the strategy, used as the primary historical edge model",
            "units": {"spread_pips": "pips", "commission_pips": "pips", "slippage_pips": "pips"},
        },
        "CONSERVATIVE_STRESS": {
            "symbol_values": {
                "EURUSD": {"spread_pips": 1.3, "commission_pips": 0.3, "slippage_pips": 0.5},
                "GBPUSD": {"spread_pips": 1.8, "commission_pips": 0.3, "slippage_pips": 0.6},
            },
            "provenance": "conservative deterministic stress test, still research-only and not broker-authoritative",
            "units": {"spread_pips": "pips", "commission_pips": "pips", "slippage_pips": "pips"},
        },
    },
    "units": {
        "spread": "pips",
        "commission": "pips",
        "slippage": "pips",
        "latency": "ms",
        "note": "All spread/commission/slippage figures are modeled in pips and converted to price units using the strategy's pip size before conversion to R.",
    },
    "data_resolution_applicability": "M15 decision timeframe and M1 refinement only; exact execution latency remains outside the representable resolution",
    "symbol_applicability": ["EURUSD", "GBPUSD"],
    "strategy_applicability": ["ST_SESSION_SWEEP_CONTINUATION_V1"],
    "immutable_during_campaign": True,
    "economic_accounting_rule": "NET_R = GROSS_R - spread_cost_R - commission_cost_R - slippage_cost_R - other_cost_R",
    "deferred_execution_parity": [
        "broker leverage",
        "broker margin formula",
        "historical executable spread",
        "commission schedule",
        "slippage distribution",
        "latency profile",
        "order acknowledgement and rejection behavior",
        "restart and reconciliation",
    ],
    "non_modeling": [
        "MT5 execution parity",
        "live broker authority",
        "demo execution authority",
        "OOS or protected data",
    ],
}


def _canonical_contract_payload() -> dict:
    payload = dict(EDGE_REALITY_MODEL)
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _contract_body_for_hash(contract: Optional[dict] = None) -> dict:
    payload = dict(contract) if contract is not None else _canonical_contract_payload()
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def compute_edge_reality_model_hash(*, contract: Optional[dict] = None) -> str:
    payload = _contract_body_for_hash(contract)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


EDGE_REALITY_MODEL_HASH = compute_edge_reality_model_hash()
EDGE_REALITY_MODEL["sha256"] = EDGE_REALITY_MODEL_HASH


def validate_edge_reality_model(*, contract: Optional[dict] = None) -> str:
    payload = dict(contract) if contract is not None else dict(EDGE_REALITY_MODEL)
    expected = payload.get("sha256")
    if expected is None:
        raise EdgeRealityModelError("EDGE_REALITY_MODEL_MISSING_HASH")
    digest = compute_edge_reality_model_hash(contract=payload)
    if digest != expected:
        raise EdgeRealityModelError("EDGE_REALITY_MODEL_DRIFT")
    valid_statuses = {
        "OBSERVED",
        "DOCUMENTED",
        "HISTORICAL_ESTIMATE",
        "MODELLED",
        "CONSERVATIVE_ASSUMPTION",
        "UNAVAILABLE",
        "NOT_MATERIALLY_RESOLVABLE_AT_DATA_RESOLUTION",
    }
    for key in ("spread_status", "commission_status", "slippage_status", "latency_status"):
        status = payload.get(key)
        if status not in valid_statuses:
            raise EdgeRealityModelError(f"EDGE_REALITY_MODEL_INVALID_STATUS:{key}={status!r}")
    return digest


def compute_net_r(*, gross_r: float, spread_r: float = 0.0, commission_r: float = 0.0, slippage_r: float = 0.0, other_cost_r: float = 0.0) -> float:
    """Deterministic additive cost accounting: net = gross - modeled friction."""
    for name, value in {"gross_r": gross_r, "spread_r": spread_r, "commission_r": commission_r, "slippage_r": slippage_r, "other_cost_r": other_cost_r}.items():
        if value < 0:
            raise EdgeRealityModelError(f"EDGE_REALITY_MODEL_NEGATIVE_COST:{name}")
    return float(gross_r) - float(spread_r) - float(commission_r) - float(slippage_r) - float(other_cost_r)


@dataclass(frozen=True)
class EdgeRealityModel:
    schema_version: str = EDGE_REALITY_MODEL_VERSION
    status: str = EDGE_REALITY_MODEL_STATUS
    purpose: str = "STRATEGY_EDGE_VALIDATION"
    strategy_scope: str = "SSC v1.0.1 strategy-edge validation only"
    strategy_id: str = "ST_SESSION_SWEEP_CONTINUATION_V1"
    strategy_version: str = "1.0.1"
    not_broker_execution_parity: bool = True
    not_live_execution_authority: bool = True
    not_demo_execution_authority: bool = True
    spread_status: str = "MODELLED"
    spread_provenance: str = "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction.default_spread_pips (research defaults, not broker observations)"
    spread_value_or_model: Dict[str, float] = field(default_factory=lambda: {"EURUSD": 1.0, "GBPUSD": 1.4})
    spread_units: Dict[str, str] = field(default_factory=lambda: {"source_value": "pips", "per_side_or_round_trip": "round_trip_per_trade", "conversion_to_price_or_currency_cost": "spread_pips * pip_size", "conversion_to_R": "(spread_price / risk_distance_price)", "source_classification": "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"})
    commission_status: str = "MODELLED"
    commission_provenance: str = "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction.default_commission_pips (research defaults, not broker observations)"
    commission_value_or_model: Dict[str, float] = field(default_factory=lambda: {"EURUSD": 0.2, "GBPUSD": 0.2})
    commission_units: Dict[str, str] = field(default_factory=lambda: {"source_value": "pips", "per_side_or_round_trip": "round_trip_per_trade", "conversion_to_price_or_currency_cost": "commission_pips * pip_size", "conversion_to_R": "(commission_price / risk_distance_price)", "source_classification": "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"})
    slippage_status: str = "MODELLED"
    slippage_provenance: str = "strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml friction.default_slippage_pips (research defaults, not broker observations)"
    slippage_value_or_model: Dict[str, float] = field(default_factory=lambda: {"EURUSD": 0.3, "GBPUSD": 0.4})
    slippage_units: Dict[str, str] = field(default_factory=lambda: {"source_value": "pips", "per_side_or_round_trip": "round_trip_per_trade", "conversion_to_price_or_currency_cost": "slippage_pips * pip_size", "conversion_to_R": "(slippage_price / risk_distance_price)", "source_classification": "EXPLICIT_CONSERVATIVE_RESEARCH_ASSUMPTION"})
    latency_status: str = "NOT_MATERIALLY_RESOLVABLE_AT_DATA_RESOLUTION"
    latency_research_status: str = "NOT_MATERIALLY_RESOLVABLE_AT_DATA_RESOLUTION"
    latency_broker_parity_status: str = "DEFERRED_EXECUTION_PARITY"
    latency_authority: str = "Historical M15/M1 bars do not carry a meaningful execution-latency distribution for this strategy/data resolution; defer to broker execution parity"
    latency_value_or_model: Optional[float] = None
    immutable_during_campaign: bool = True
    deferred_execution_parity: Tuple[str, ...] = (
        "broker leverage",
        "broker margin formula",
        "historical executable spread",
        "commission schedule",
        "slippage distribution",
        "latency profile",
        "order acknowledgement and rejection behavior",
        "restart and reconciliation",
    )
    non_modeling: Tuple[str, ...] = (
        "MT5 execution parity",
        "live broker authority",
        "demo execution authority",
        "OOS or protected data",
    )

    def __post_init__(self) -> None:
        valid_statuses = {
            "OBSERVED",
            "DOCUMENTED",
            "HISTORICAL_ESTIMATE",
            "MODELLED",
            "CONSERVATIVE_ASSUMPTION",
            "UNAVAILABLE",
            "NOT_MATERIALLY_RESOLVABLE_AT_DATA_RESOLUTION",
        }
        for key in ("spread_status", "commission_status", "slippage_status", "latency_status"):
            value = getattr(self, key)
            if value not in valid_statuses:
                raise EdgeRealityModelError(f"invalid status for {key}: {value!r}")
        if self.not_broker_execution_parity is not True:
            raise EdgeRealityModelError("broker parity must remain deferred for this research model")

    @property
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "purpose": self.purpose,
            "strategy_scope": self.strategy_scope,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "not_broker_execution_parity": self.not_broker_execution_parity,
            "not_live_execution_authority": self.not_live_execution_authority,
            "not_demo_execution_authority": self.not_demo_execution_authority,
            "spread_status": self.spread_status,
            "spread_provenance": self.spread_provenance,
            "spread_value_or_model": self.spread_value_or_model,
            "spread_units": self.spread_units,
            "commission_status": self.commission_status,
            "commission_provenance": self.commission_provenance,
            "commission_value_or_model": self.commission_value_or_model,
            "commission_units": self.commission_units,
            "slippage_status": self.slippage_status,
            "slippage_provenance": self.slippage_provenance,
            "slippage_value_or_model": self.slippage_value_or_model,
            "slippage_units": self.slippage_units,
            "latency_status": self.latency_status,
            "latency_research_status": self.latency_research_status,
            "latency_broker_parity_status": self.latency_broker_parity_status,
            "latency_authority": self.latency_authority,
            "latency_value_or_model": self.latency_value_or_model,
            "immutable_during_campaign": self.immutable_during_campaign,
            "deferred_execution_parity": list(self.deferred_execution_parity),
            "non_modeling": list(self.non_modeling),
        }

    @property
    def hash(self) -> str:
        return compute_edge_reality_model_hash(contract=self.to_dict)


DEFAULT_EDGE_REALITY_MODEL = EdgeRealityModel()
DEFAULT_EDGE_REALITY_MODEL_HASH = DEFAULT_EDGE_REALITY_MODEL.hash
