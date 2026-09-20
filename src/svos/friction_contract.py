"""Deterministic friction contract for SSC/VD validation gates.

This contract is intentionally fail-closed. Any friction component without signed
project authority remains UNAVAILABLE and is never silently replaced with zero or a
proxy. The rule is the same as in svos.friction_profile: UNAVAILABLE never converts
into a cost total.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple


class FrictionContractError(ValueError):
    pass


FRICTION_STATUS = "FROZEN"
FRICTION_VERSION = "VD_FRICTION_V1"

FRICTION_CONTRACT = {
    "schema_version": FRICTION_VERSION,
    "status": FRICTION_STATUS,
    "purpose": "SSC_VD_FRICTION_VALIDATION",
    "strategy_scope": "SSC validation only; friction is economic accounting only and cannot change SSC qualification, occurrence identity, geometry, or direction",
    "symbol_scope": "No broker-specific or cross-strategy friction model is reused; no symbol-specific inference is allowed without signed authority",
    "evidence_authority": [
        "src/svos/friction_profile.py::FrictionProfile -> UNAVAILABLE never converts to zero",
        "src/performance/cost_model.py::CONTRACT_CEILING is the only signed scenario for a different strategy and is not reused here",
        "docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_STATUS.md::spread and P&L are engineering proxies only; commission, slippage, latency, and margin remain unavailable",
        "docs/svos/VD_EXECUTION_PROFILE_V1_DRAFT.json::explicitly marks slippage as UNAVAILABLE_DISTRIBUTION and does not authorize a silent zero",
        "docs/status/AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_WP3A_STATUS.md::Large-SMC friction evidence is not signed for SSC reuse",
    ],
    "spread_status": "UNAVAILABLE",
    "spread_authority": "UNAVAILABLE: no signed broker-evidenced spread distribution or executable spread coverage for the SSC validation scope",
    "spread_value_or_model": None,
    "commission_status": "UNAVAILABLE",
    "commission_authority": "UNAVAILABLE: no signed commission schedule or distribution for the SSC validation scope",
    "commission_value_or_model": None,
    "slippage_status": "UNAVAILABLE",
    "slippage_authority": "UNAVAILABLE: no signed slippage distribution exists; an observed favorable fill is not a distribution",
    "slippage_value_or_model": None,
    "latency_status": "UNAVAILABLE",
    "latency_authority": "UNAVAILABLE: no millisecond execution dataset or broker timing authority exists for the virtual model",
    "latency_value_or_model": None,
    "preregistered_dev_assumptions": [],
    "unavailable_components": ["spread", "commission", "slippage", "latency"],
    "friction_application_policy": {
        "entry_spread_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "exit_spread_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "stop_execution_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "target_execution_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "commission_application": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "slippage_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "conversion_to_price_pips_R": "NOT_PERFORMED; unavailable components never convert to zero or to a proxy; they remain unknown until signed authority exists",
        "long_short_symmetry": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "partial_exit_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "unresolved_occurrence_treatment": "DO_NOT_COST; record as unresolved in economic accounting and keep SSC geometry unchanged",
    },
    "r_conversion_policy": "No price/pips/R conversion occurs for unavailable components. R conversion is permitted only after a component is explicitly classified as KNOWN or PREREGISTERED_DEV_ASSUMPTION and has a signed numeric value.",
    "large_smc_friction_reused": False,
    "reuse_authority": "Large-SMC EURUSD friction evidence is not reused for SSC because it is strategy-scoped and does not satisfy the SSC validation contract; no owner sign-off is present here",
    "deferred_execution_parity": [
        "broker leverage",
        "broker margin formula",
        "historical executable spread",
        "commission distribution",
        "slippage distribution",
        "latency profile",
        "volume and account-specific fee schedule",
    ],
    "capacity_contract_dependency": "src/svos/capacity_risk_contract.py::CAPACITY_RISK_VERSION == VD_CAPACITY_RISK_V1",
    "determinism_status": "PASS",
    "strategy_semantics_changed": False,
    "campaign_run": False,
    "campaign_results_inspected": False,
    "demo_authority": False,
    "live_authority": False,
    "non_modeling": [
        "MT5 execution parity",
        "live margin authority",
        "live broker economics",
        "OOS or protected data",
        "economic campaign",
    ],
    "notes": "This is a frozen validation contract only; no thresholds, costs, or campaign results are inferred from missing broker evidence.",
}


def _canonical_contract_payload() -> dict:
    payload = dict(FRICTION_CONTRACT)
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _contract_body_for_hash(contract: Optional[dict]) -> dict:
    payload = dict(contract) if contract is not None else _canonical_contract_payload()
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def compute_friction_hash(*, contract: Optional[dict] = None) -> str:
    payload = _contract_body_for_hash(contract)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


FRICTION_HASH = compute_friction_hash()
FRICTION_CONTRACT["sha256"] = FRICTION_HASH


def validate_friction_contract(*, contract: Optional[dict] = None) -> str:
    payload = dict(contract) if contract is not None else dict(FRICTION_CONTRACT)
    expected = payload.get("sha256")
    if expected is None:
        raise FrictionContractError("FRICTION_CONTRACT_MISSING_HASH")
    digest = compute_friction_hash(contract=payload)
    if digest != expected:
        raise FrictionContractError("FRICTION_CONTRACT_DRIFT")
    for component in ("spread", "commission", "slippage", "latency"):
        status = payload.get(f"{component}_status")
        if status not in ("KNOWN", "UNAVAILABLE", "PREREGISTERED_DEV_ASSUMPTION"):
            raise FrictionContractError(f"FRICTION_CONTRACT_INVALID_COMPONENT_STATUS:{component}")
    return digest


@dataclass(frozen=True)
class FrictionContract:
    schema_version: str = FRICTION_VERSION
    status: str = FRICTION_STATUS
    purpose: str = "SSC_VD_FRICTION_VALIDATION"
    strategy_scope: str = (
        "SSC validation only; friction is economic accounting only and cannot change SSC qualification, occurrence identity, geometry, or direction"
    )
    symbol_scope: str = (
        "No broker-specific or cross-strategy friction model is reused; no symbol-specific inference is allowed without signed authority"
    )
    evidence_authority: Tuple[str, ...] = (
        "src/svos/friction_profile.py::FrictionProfile -> UNAVAILABLE never converts to zero",
        "src/performance/cost_model.py::CONTRACT_CEILING is the only signed scenario for a different strategy and is not reused here",
        "docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_STATUS.md::spread and P&L are engineering proxies only; commission, slippage, latency, and margin remain unavailable",
        "docs/svos/VD_EXECUTION_PROFILE_V1_DRAFT.json::explicitly marks slippage as UNAVAILABLE_DISTRIBUTION and does not authorize a silent zero",
        "docs/status/AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_WP3A_STATUS.md::Large-SMC friction evidence is not signed for SSC reuse",
    )
    spread_status: str = "UNAVAILABLE"
    spread_authority: str = (
        "UNAVAILABLE: no signed broker-evidenced spread distribution or executable spread coverage for the SSC validation scope"
    )
    spread_value_or_model: Optional[float] = None
    spread_value: Optional[float] = None
    commission_status: str = "UNAVAILABLE"
    commission_authority: str = (
        "UNAVAILABLE: no signed commission schedule or distribution for the SSC validation scope"
    )
    commission_value_or_model: Optional[float] = None
    commission_value: Optional[float] = None
    slippage_status: str = "UNAVAILABLE"
    slippage_authority: str = (
        "UNAVAILABLE: no signed slippage distribution exists; an observed favorable fill is not a distribution"
    )
    slippage_value_or_model: Optional[float] = None
    slippage_value: Optional[float] = None
    latency_status: str = "UNAVAILABLE"
    latency_authority: str = (
        "UNAVAILABLE: no millisecond execution dataset or broker timing authority exists for the virtual model"
    )
    latency_value_or_model: Optional[float] = None
    latency_value: Optional[float] = None
    preregistered_dev_assumptions: Tuple[str, ...] = ()
    unavailable_components: Tuple[str, ...] = ("spread", "commission", "slippage", "latency")
    friction_application_policy: dict = field(default_factory=lambda: {
        "entry_spread_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "exit_spread_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "stop_execution_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "target_execution_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "commission_application": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "slippage_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "conversion_to_price_pips_R": "NOT_PERFORMED; unavailable components never convert to zero or to a proxy; they remain unknown until signed authority exists",
        "long_short_symmetry": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "partial_exit_treatment": "UNAVAILABLE_COMPONENT_FAIL_CLOSED",
        "unresolved_occurrence_treatment": "DO_NOT_COST; record as unresolved in economic accounting and keep SSC geometry unchanged",
    })
    r_conversion_policy: str = (
        "No price/pips/R conversion occurs for unavailable components. R conversion is permitted only after a component is explicitly classified as KNOWN or PREREGISTERED_DEV_ASSUMPTION and has a signed numeric value."
    )
    large_smc_friction_reused: bool = False
    reuse_authority: str = (
        "Large-SMC EURUSD friction evidence is not reused for SSC because it is strategy-scoped and does not satisfy the SSC validation contract; no owner sign-off is present here"
    )
    deferred_execution_parity: Tuple[str, ...] = (
        "broker leverage",
        "broker margin formula",
        "historical executable spread",
        "commission distribution",
        "slippage distribution",
        "latency profile",
        "volume and account-specific fee schedule",
    )
    capacity_contract_dependency: str = "src/svos/capacity_risk_contract.py::CAPACITY_RISK_VERSION == VD_CAPACITY_RISK_V1"
    determinism_status: str = "PASS"
    strategy_semantics_changed: bool = False
    campaign_run: bool = False
    campaign_results_inspected: bool = False
    demo_authority: bool = False
    live_authority: bool = False
    notes: str = "This is a frozen validation contract only; no thresholds, costs, or campaign results are inferred from missing broker evidence."

    def __post_init__(self) -> None:
        for component, status, value in (
            ("spread", self.spread_status, self.spread_value_or_model),
            ("commission", self.commission_status, self.commission_value_or_model),
            ("slippage", self.slippage_status, self.slippage_value_or_model),
            ("latency", self.latency_status, self.latency_value_or_model),
        ):
            if status not in {"KNOWN", "UNAVAILABLE", "PREREGISTERED_DEV_ASSUMPTION"}:
                raise FrictionContractError(f"invalid status for {component}: {status!r}")
            if status == "KNOWN":
                if value is None or value <= 0:
                    raise FrictionContractError(f"known friction component {component} requires a positive numeric value")
            if status == "UNAVAILABLE" and value is not None and value != 0:
                raise FrictionContractError(f"unavailable friction component {component} must not store a non-zero proxy")
            if status == "PREREGISTERED_DEV_ASSUMPTION" and value is not None and value <= 0:
                raise FrictionContractError(f"preregistered friction component {component} requires a positive numeric value")

    @property
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "purpose": self.purpose,
            "strategy_scope": self.strategy_scope,
            "symbol_scope": self.symbol_scope,
            "evidence_authority": list(self.evidence_authority),
            "spread_status": self.spread_status,
            "spread_authority": self.spread_authority,
            "spread_value_or_model": self.spread_value_or_model,
            "commission_status": self.commission_status,
            "commission_authority": self.commission_authority,
            "commission_value_or_model": self.commission_value_or_model,
            "slippage_status": self.slippage_status,
            "slippage_authority": self.slippage_authority,
            "slippage_value_or_model": self.slippage_value_or_model,
            "latency_status": self.latency_status,
            "latency_authority": self.latency_authority,
            "latency_value_or_model": self.latency_value_or_model,
            "preregistered_dev_assumptions": list(self.preregistered_dev_assumptions),
            "unavailable_components": list(self.unavailable_components),
            "friction_application_policy": self.friction_application_policy,
            "r_conversion_policy": self.r_conversion_policy,
            "large_smc_friction_reused": self.large_smc_friction_reused,
            "reuse_authority": self.reuse_authority,
            "deferred_execution_parity": list(self.deferred_execution_parity),
            "capacity_contract_dependency": self.capacity_contract_dependency,
            "determinism_status": self.determinism_status,
            "strategy_semantics_changed": self.strategy_semantics_changed,
            "campaign_run": self.campaign_run,
            "campaign_results_inspected": self.campaign_results_inspected,
            "demo_authority": self.demo_authority,
            "live_authority": self.live_authority,
            "non_modeling": ["MT5 execution parity", "live margin authority", "live broker economics", "OOS or protected data", "economic campaign"],
            "notes": self.notes,
        }

    @property
    def hash(self) -> str:
        return compute_friction_hash(contract=self.to_dict)


DEFAULT_FRICTION_CONTRACT = FrictionContract()
DEFAULT_FRICTION_HASH = DEFAULT_FRICTION_CONTRACT.hash
