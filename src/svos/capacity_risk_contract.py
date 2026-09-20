"""Deterministic capacity-risk contract for STRATEGY_CAPACITY_VALIDATION.

This contract is intentionally scoped to virtual capacity accounting only. It does not
assert broker margin, leverage, or MT5 execution parity. Missing broker facts remain
explicitly deferred as DEFERRED_EXECUTION_PARITY, and any required numeric authority
must come from project evidence rather than invented values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


class CapacityRiskError(ValueError):
    pass


CAPACITY_RISK_VERSION = "VD_CAPACITY_RISK_V1"

CAPACITY_RISK_CONTRACT = {
    "schema_version": CAPACITY_RISK_VERSION,
    "purpose": "STRATEGY_CAPACITY_VALIDATION",
    "simulator_version": "SVOS_CAPACITY_RISK_V1",
    "strategy_boundary": "SSC v1.0.1 strategy semantics remain frozen; this contract governs virtual-capacity accounting only",
    "initial_virtual_equity": 0.0,
    "initial_equity_authority": "src/svos/virtual_account.py::VirtualAccount.__init__(starting_engineering_balance=0.0)",
    "risk_per_occurrence": None,
    "risk_authority": "UNSPECIFIED_IN_REPO_AUTHORITY",
    "risk_policy": "fail_closed: a capacity decision requiring a numeric risk-per-occurrence cannot be treated as modeled until project authority is supplied",
    "sizing_rule": "ENGINEERING_NORMALIZED_1",
    "sizing_authority": "src/svos/virtual_account.py::VirtualPosition.quantity_basis == ENGINEERING_NORMALIZED_1",
    "max_concurrent_positions": 1,
    "concurrency_authority": "docs/svos/VD_ACCOUNT_PROFILE_V1_DRAFT.json::max_open_positions = 1",
    "simultaneous_occurrence_ordering": "FIRST_DECISION_TIME_WINS; later simultaneous events are rejected/deduplicated deterministically by canonical decision time and event identity",
    "insufficient_capacity_policy": "reject the later overlapping occurrence and record the rejection deterministically; do not mutate canonical SSC geometry",
    "realized_equity_accounting": "sum closed-position normalized pnl; no broker currency conversion or margin model",
    "unrealized_exposure_policy": "NOT_MODELED",
    "rejected_or_skipped_accounting": "count as deterministic rejections, not executed fills",
    "accounting_status": "ENGINEERING_NORMALIZED_ONLY",
    "deferred_execution_parity": [
        "broker leverage",
        "broker margin formula",
        "broker liquidation behavior",
        "broker-specific account parameters",
        "historical executable spread",
        "commission",
        "slippage",
        "latency",
    ],
    "status": "FROZEN",
    "missing_authority": [
        "risk_per_occurrence_numeric_value",
        "broker_margin_schedule",
        "broker_leverage",
        "commission_distribution",
        "slippage_distribution",
        "latency_profile",
    ],
    "non_modeling": [
        "MT5 execution parity",
        "live margin authority",
        "live broker equity authority",
        "economic campaign",
        "OOS or protected data",
    ],
}


def _canonical_contract_payload() -> dict:
    payload = dict(CAPACITY_RISK_CONTRACT)
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _contract_body_for_hash(contract: Optional[dict]) -> dict:
    payload = dict(contract) if contract is not None else _canonical_contract_payload()
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def compute_capacity_risk_hash(*, contract: Optional[dict] = None) -> str:
    payload = _contract_body_for_hash(contract)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


CAPACITY_RISK_HASH = compute_capacity_risk_hash()
CAPACITY_RISK_CONTRACT["sha256"] = CAPACITY_RISK_HASH


def validate_capacity_risk_contract(*, contract: Optional[dict] = None) -> str:
    payload = dict(contract) if contract is not None else dict(CAPACITY_RISK_CONTRACT)
    expected = payload.get("sha256")
    if expected is None:
        raise CapacityRiskError("CAPACITY_RISK_CONTRACT_MISSING_HASH")
    digest = compute_capacity_risk_hash(contract=payload)
    if digest != expected:
        raise CapacityRiskError("CAPACITY_RISK_CONTRACT_DRIFT")
    # The contract is intentionally fail-closed when the project lacks broker risk authority.
    if payload.get("risk_per_occurrence") is not None:
        if not isinstance(payload["risk_per_occurrence"], (int, float)):
            raise CapacityRiskError("CAPACITY_RISK_CONTRACT_INVALID_NUMERIC_TYPE")
    return digest


@dataclass(frozen=True)
class CapacityRiskContract:
    schema_version: str = CAPACITY_RISK_VERSION
    purpose: str = "STRATEGY_CAPACITY_VALIDATION"
    simulator_version: str = "SVOS_CAPACITY_RISK_V1"
    strategy_boundary: str = (
        "SSC v1.0.1 strategy semantics remain frozen; this contract governs virtual-capacity accounting only"
    )
    status: str = "FROZEN"
    initial_virtual_equity: float = 0.0
    initial_equity_authority: str = (
        "src/svos/virtual_account.py::VirtualAccount.__init__(starting_engineering_balance=0.0)"
    )
    risk_per_occurrence: Optional[float] = None
    risk_authority: str = "UNSPECIFIED_IN_REPO_AUTHORITY"
    risk_policy: str = (
        "fail_closed: a capacity decision requiring a numeric risk-per-occurrence cannot be treated as modeled until project authority is supplied"
    )
    sizing_rule: str = "ENGINEERING_NORMALIZED_1"
    sizing_authority: str = "src/svos/virtual_account.py::VirtualPosition.quantity_basis == ENGINEERING_NORMALIZED_1"
    max_concurrent_positions: int = 1
    concurrency_authority: str = "docs/svos/VD_ACCOUNT_PROFILE_V1_DRAFT.json::max_open_positions = 1"
    simultaneous_occurrence_ordering: str = (
        "FIRST_DECISION_TIME_WINS; later simultaneous events are rejected/deduplicated deterministically by canonical decision time and event identity"
    )
    insufficient_capacity_policy: str = (
        "reject the later overlapping occurrence and record the rejection deterministically; do not mutate canonical SSC geometry"
    )
    realized_equity_accounting: str = "sum closed-position normalized pnl; no broker currency conversion or margin model"
    unrealized_exposure_policy: str = "NOT_MODELED"
    rejected_or_skipped_accounting: str = "count as deterministic rejections, not executed fills"
    accounting_status: str = "ENGINEERING_NORMALIZED_ONLY"
    deferred_execution_parity: Tuple[str, ...] = (
        "broker leverage",
        "broker margin formula",
        "broker liquidation behavior",
        "broker-specific account parameters",
        "historical executable spread",
        "commission",
        "slippage",
        "latency",
    )
    missing_authority: Tuple[str, ...] = (
        "risk_per_occurrence_numeric_value",
        "broker_margin_schedule",
        "broker_leverage",
        "commission_distribution",
        "slippage_distribution",
        "latency_profile",
    )
    non_modeling: Tuple[str, ...] = (
        "MT5 execution parity",
        "live margin authority",
        "live broker equity authority",
        "economic campaign",
        "OOS or protected data",
    )

    def __post_init__(self):
        if self.initial_virtual_equity < 0:
            raise CapacityRiskError("negative engineering balance is unsupported")
        if self.max_concurrent_positions < 1:
            raise CapacityRiskError("max_concurrent_positions must be >= 1")
        if self.risk_per_occurrence is not None and self.risk_per_occurrence <= 0:
            raise CapacityRiskError("risk_per_occurrence must be positive when provided")

    @property
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "purpose": self.purpose,
            "simulator_version": self.simulator_version,
            "strategy_boundary": self.strategy_boundary,
            "initial_virtual_equity": self.initial_virtual_equity,
            "initial_equity_authority": self.initial_equity_authority,
            "risk_per_occurrence": self.risk_per_occurrence,
            "risk_authority": self.risk_authority,
            "risk_policy": self.risk_policy,
            "sizing_rule": self.sizing_rule,
            "sizing_authority": self.sizing_authority,
            "max_concurrent_positions": self.max_concurrent_positions,
            "concurrency_authority": self.concurrency_authority,
            "simultaneous_occurrence_ordering": self.simultaneous_occurrence_ordering,
            "insufficient_capacity_policy": self.insufficient_capacity_policy,
            "realized_equity_accounting": self.realized_equity_accounting,
            "unrealized_exposure_policy": self.unrealized_exposure_policy,
            "rejected_or_skipped_accounting": self.rejected_or_skipped_accounting,
            "accounting_status": self.accounting_status,
            "deferred_execution_parity": list(self.deferred_execution_parity),
            "status": self.status,
            "missing_authority": list(self.missing_authority),
            "non_modeling": list(self.non_modeling),
        }

    @property
    def hash(self) -> str:
        return compute_capacity_risk_hash(contract=self.to_dict)

    def to_virtual_account_kwargs(self) -> dict:
        return {
            "starting_engineering_balance": self.initial_virtual_equity,
            "max_open_positions": self.max_concurrent_positions,
        }


DEFAULT_CAPACITY_RISK_CONTRACT = CapacityRiskContract()
DEFAULT_CAPACITY_RISK_HASH = DEFAULT_CAPACITY_RISK_CONTRACT.hash
