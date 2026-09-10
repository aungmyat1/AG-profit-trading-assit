"""Forward-shadow statistical gate (spec section 33-35). Owner-specified research
thresholds; the validator only ever reports GATE_PASS/GATE_FAIL/INSUFFICIENT_EVIDENCE.
It never mutates lifecycle -- governance stays external (spec section 33, 42).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ag_scheduler_v2.config_loader import load_config

GATE_PASS = "GATE_PASS"
GATE_FAIL = "GATE_FAIL"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"

ECONOMIC_GATE_NOT_EVALUABLE = "NOT_EVALUABLE"
ECONOMIC_GATE_EVALUATED = "EVALUATED"


@dataclass(frozen=True)
class ValidationGateThresholds:
    shadow_sample_threshold: int
    net_expectancy_threshold_r: float
    missed_observation_cycle_rate_threshold: float

    @classmethod
    def from_config(cls, path: Optional[str] = None) -> "ValidationGateThresholds":
        raw = load_config(path).get("validation_gate") or {}
        for key in ("shadow_sample_threshold", "net_expectancy_threshold_r", "missed_observation_cycle_rate_threshold"):
            if key not in raw:
                raise ValueError(f"SCHEDULER_CONFIG_CONFLICT: validation_gate.{key} is required")
        return cls(
            shadow_sample_threshold=int(raw["shadow_sample_threshold"]),
            net_expectancy_threshold_r=float(raw["net_expectancy_threshold_r"]),
            missed_observation_cycle_rate_threshold=float(raw["missed_observation_cycle_rate_threshold"]),
        )


@dataclass(frozen=True)
class GateEvaluation:
    verdict: str  # GATE_PASS | GATE_FAIL | INSUFFICIENT_EVIDENCE
    economic_gate_status: str  # ECONOMIC_GATE_EVALUATED | ECONOMIC_GATE_NOT_EVALUABLE
    qualified_shadow_setups: int
    net_expectancy_r: Optional[float]
    missed_observation_cycle_rate: Optional[float]


def evaluate_gate(
    *,
    qualified_shadow_setups: int,
    net_expectancy_r: Optional[float],
    costs_complete: bool,
    missed_observation_cycle_rate: Optional[float],
    thresholds: ValidationGateThresholds,
) -> GateEvaluation:
    """`net_expectancy_r=None` or `costs_complete=False` forces the economic gate to
    NOT_EVALUABLE rather than passing on gross R (spec section 35) -- a NOT_EVALUABLE
    economic gate alone is enough to make the overall verdict INSUFFICIENT_EVIDENCE."""
    economic_status = ECONOMIC_GATE_EVALUATED if (costs_complete and net_expectancy_r is not None) else ECONOMIC_GATE_NOT_EVALUABLE

    if qualified_shadow_setups < thresholds.shadow_sample_threshold:
        verdict = INSUFFICIENT_EVIDENCE
    elif missed_observation_cycle_rate is None or economic_status == ECONOMIC_GATE_NOT_EVALUABLE:
        verdict = INSUFFICIENT_EVIDENCE
    elif (
        net_expectancy_r >= thresholds.net_expectancy_threshold_r
        and missed_observation_cycle_rate < thresholds.missed_observation_cycle_rate_threshold
    ):
        verdict = GATE_PASS
    else:
        verdict = GATE_FAIL

    return GateEvaluation(
        verdict=verdict,
        economic_gate_status=economic_status,
        qualified_shadow_setups=qualified_shadow_setups,
        net_expectancy_r=net_expectancy_r,
        missed_observation_cycle_rate=missed_observation_cycle_rate,
    )
