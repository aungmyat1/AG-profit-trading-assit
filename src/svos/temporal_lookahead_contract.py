"""Deterministic temporal-lookahead contract for SSC/VD validation gates.

This contract encodes the canonical invariant required by the validation system:
for a decision time T, only closed bars with `bar_close_time <= T` may influence
visible strategy inputs, indicators, market structure, setup qualification,
occurrence identity, entries, stops, targets, and decision status.

Future candles may exist in the dataset, but they must not change any of the above
when the system is evaluated as-of T.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional, Tuple


class TemporalLookaheadError(ValueError):
    pass


TEMPORAL_LOOKAHEAD_VERSION = "VD_TEMPORAL_LOOKAHEAD_V1"
TEMPORAL_LOOKAHEAD_STATUS = "FROZEN"

TEMPORAL_LOOKAHEAD_CONTRACT = {
    "schema_version": TEMPORAL_LOOKAHEAD_VERSION,
    "status": TEMPORAL_LOOKAHEAD_STATUS,
    "purpose": "SSC_VD_TEMPORAL_INTEGRITY_VALIDATION",
    "policy": "At decision time T, the visible closed-bar prefix is computed solely from bars whose close_time <= T; future bars are ignored for all visible strategy inputs at T.",
    "applies_to": [
        "indicators",
        "market_structure",
        "MTF_context",
        "setup_qualification",
        "occurrence_identity",
        "entry",
        "stop_loss",
        "targets",
        "decision_status",
    ],
    "test_pattern": "A: dataset truncated at T; B: dataset contains future continuation beyond T but evaluation remains as-of T; C: same prefix through T with different future continuation; A and B must yield identical semantic inputs and decisions at T.",
    "same_prefix_requirements": [
        "closed bar set through T",
        "indicator values at T",
        "market structure at T",
        "MTF context at T",
        "setup qualification at T",
        "direction at T",
        "occurrence identity at T",
        "entry, SL, target, and status at T",
    ],
    "future_data_behavior": "Future continuation is allowed in the dataset for replay provenance but must never affect semantic outputs at T.",
    "governance": "No strategy or simulator component may substitute future-aware data while evaluating historical as-of decisions.",
    "strategy_semantics_changed": False,
    "campaign_run": False,
    "demo_authority": False,
    "live_authority": False,
    "determinism_status": "PASS",
}


def _canonical_contract_payload() -> dict:
    payload = dict(TEMPORAL_LOOKAHEAD_CONTRACT)
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _contract_body_for_hash(contract: Optional[dict] = None) -> dict:
    payload = dict(contract) if contract is not None else _canonical_contract_payload()
    payload.pop("sha256", None)
    return json.loads(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def compute_temporal_lookahead_hash(*, contract: Optional[dict] = None) -> str:
    payload = _contract_body_for_hash(contract)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(body).hexdigest()


TEMPORAL_LOOKAHEAD_HASH = compute_temporal_lookahead_hash()
TEMPORAL_LOOKAHEAD_CONTRACT["sha256"] = TEMPORAL_LOOKAHEAD_HASH


def validate_temporal_lookahead_contract(*, contract: Optional[dict] = None) -> str:
    payload = dict(contract) if contract is not None else dict(TEMPORAL_LOOKAHEAD_CONTRACT)
    expected = payload.get("sha256")
    if expected is None:
        raise TemporalLookaheadError("TEMPORAL_LOOKAHEAD_CONTRACT_MISSING_HASH")
    digest = compute_temporal_lookahead_hash(contract=payload)
    if digest != expected:
        raise TemporalLookaheadError("TEMPORAL_LOOKAHEAD_CONTRACT_DRIFT")
    return digest


@dataclass(frozen=True)
class TemporalLookaheadContract:
    schema_version: str = TEMPORAL_LOOKAHEAD_VERSION
    status: str = TEMPORAL_LOOKAHEAD_STATUS
    purpose: str = "SSC_VD_TEMPORAL_INTEGRITY_VALIDATION"
    policy: str = (
        "At decision time T, the visible closed-bar prefix is computed solely from bars whose close_time <= T; future bars are ignored for all visible strategy inputs at T."
    )
    applies_to: Tuple[str, ...] = (
        "indicators",
        "market_structure",
        "MTF_context",
        "setup_qualification",
        "occurrence_identity",
        "entry",
        "stop_loss",
        "targets",
        "decision_status",
    )
    same_prefix_requirements: Tuple[str, ...] = (
        "closed bar set through T",
        "indicator values at T",
        "market structure at T",
        "MTF context at T",
        "setup qualification at T",
        "direction at T",
        "occurrence identity at T",
        "entry, SL, target, and status at T",
    )
    future_data_behavior: str = "Future continuation is allowed in the dataset for replay provenance but must never affect semantic outputs at T."
    governance: str = "No strategy or simulator component may substitute future-aware data while evaluating historical as-of decisions."
    strategy_semantics_changed: bool = False
    campaign_run: bool = False
    demo_authority: bool = False
    live_authority: bool = False

    @property
    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "purpose": self.purpose,
            "policy": self.policy,
            "applies_to": list(self.applies_to),
            "same_prefix_requirements": list(self.same_prefix_requirements),
            "future_data_behavior": self.future_data_behavior,
            "governance": self.governance,
            "strategy_semantics_changed": self.strategy_semantics_changed,
            "campaign_run": self.campaign_run,
            "demo_authority": self.demo_authority,
            "live_authority": self.live_authority,
        }

    @property
    def hash(self) -> str:
        return compute_temporal_lookahead_hash(contract=self.to_dict)


DEFAULT_TEMPORAL_LOOKAHEAD_CONTRACT = TemporalLookaheadContract()
DEFAULT_TEMPORAL_LOOKAHEAD_HASH = DEFAULT_TEMPORAL_LOOKAHEAD_CONTRACT.hash
