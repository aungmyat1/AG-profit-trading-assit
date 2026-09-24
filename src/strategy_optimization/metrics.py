"""Common arm identity and gross/friction/net comparison contracts; no replay engine."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from post_asian_pilot.fingerprint import fingerprint
from .models import (
    Arm,
    ComparisonStatus,
    ExperimentResult,
    MetricStatus,
    StrategyBaseline,
    BaselineStatus,
    to_jsonable,
)


@dataclass(frozen=True)
class MetricDelta:
    gross_R: Optional[float] = None
    friction_R: Optional[float] = None
    net_R: Optional[float] = None
    gross_expectancy_R: Optional[float] = None
    net_expectancy_R: Optional[float] = None
    gross_wins: Optional[int] = None
    gross_losses: Optional[int] = None
    gross_breakevens: Optional[int] = None
    taken_count: Optional[int] = None
    blocked_count: Optional[int] = None
    position_guard_blocked_count: Optional[int] = None
    gross_max_drawdown_R: Optional[float] = None
    net_max_drawdown_R: Optional[float] = None


@dataclass(frozen=True)
class ExperimentComparison:
    experiment_id: str
    strategy_id: str
    status: ComparisonStatus
    blockers: Tuple[str, ...]
    control_result_sha256: str
    candidate_result_sha256: str
    paired_sample_size: Optional[int]
    deltas: MetricDelta
    population_hash: Optional[str]
    dataset_sha256: Optional[str]
    friction_profile_sha256: Optional[str]

    @property
    def comparison_sha256(self) -> str:
        return fingerprint(to_jsonable(self))


def _difference(candidate: Optional[float], control: Optional[float]) -> Optional[float]:
    if candidate is None or control is None:
        return None
    return float(candidate) - float(control)


def compare_control_candidate(
    control: ExperimentResult,
    candidate: ExperimentResult,
    *,
    baseline: StrategyBaseline,
) -> ExperimentComparison:
    """Compare arms only after the frozen control baseline is reproducible.

    This function does not evaluate economic acceptance thresholds. It refuses to create
    numeric deltas when either arm is missing, when results are not evaluated, when the
    baseline lacks reproduced dataset/population/friction identity, or when any paired
    identity differs.
    """
    if control.arm is not Arm.CONTROL or candidate.arm is not Arm.CANDIDATE:
        raise ValueError("results must be passed in CONTROL, CANDIDATE order")
    if control.experiment_id != candidate.experiment_id or control.strategy_id != candidate.strategy_id:
        blockers = ("CROSS_EXPERIMENT_OR_STRATEGY_PAIR_FORBIDDEN",)
        return ExperimentComparison(
            experiment_id=control.experiment_id,
            strategy_id=control.strategy_id,
            status=ComparisonStatus.BLOCKED_IDENTITY_MISMATCH,
            blockers=blockers,
            control_result_sha256=control.result_sha256,
            candidate_result_sha256=candidate.result_sha256,
            paired_sample_size=None,
            deltas=MetricDelta(),
            population_hash=None,
            dataset_sha256=None,
            friction_profile_sha256=None,
        )

    if control.metrics.status is not MetricStatus.EVALUATED or candidate.metrics.status is not MetricStatus.EVALUATED:
        return ExperimentComparison(
            experiment_id=control.experiment_id,
            strategy_id=control.strategy_id,
            status=ComparisonStatus.NOT_EVALUATED,
            blockers=("CONTROL_OR_CANDIDATE_METRICS_NOT_EVALUATED",),
            control_result_sha256=control.result_sha256,
            candidate_result_sha256=candidate.result_sha256,
            paired_sample_size=None,
            deltas=MetricDelta(),
            population_hash=None,
            dataset_sha256=None,
            friction_profile_sha256=None,
        )

    baseline_blockers = []
    if not isinstance(baseline, StrategyBaseline):
        baseline_blockers.append("BASELINE_RECORD_REQUIRED")
    else:
        if baseline.baseline_status is not BaselineStatus.REPRODUCIBLE:
            baseline_blockers.append("BASELINE_NOT_REPRODUCIBLE")
        for name, left, right in (
            ("BASELINE_STRATEGY_ID", baseline.strategy_id, control.strategy_id),
            ("BASELINE_CONTROL_CONFIG", baseline.canonical_config_sha256, control.candidate_config_sha256),
            ("BASELINE_DATASET_ID", baseline.dataset_id, control.dataset_id),
            ("BASELINE_DATASET_SHA256", baseline.dataset_sha256, control.dataset_sha256),
            ("BASELINE_POPULATION_HASH", baseline.population_hash, control.population_hash),
            ("BASELINE_FRICTION_PROFILE", baseline.friction_profile_sha256, control.friction_profile_sha256),
        ):
            if left is None or right is None:
                baseline_blockers.append(f"{name}_MISSING")
            elif left != right:
                baseline_blockers.append(f"{name}_MISMATCH")
    if baseline_blockers:
        return ExperimentComparison(
            experiment_id=control.experiment_id,
            strategy_id=control.strategy_id,
            status=ComparisonStatus.BLOCKED_IDENTITY_MISMATCH,
            blockers=tuple(baseline_blockers),
            control_result_sha256=control.result_sha256,
            candidate_result_sha256=candidate.result_sha256,
            paired_sample_size=None,
            deltas=MetricDelta(),
            population_hash=None,
            dataset_sha256=None,
            friction_profile_sha256=None,
        )

    blockers_list = []
    identity_pairs = (
        ("dataset_id", control.dataset_id, candidate.dataset_id),
        ("dataset_sha256", control.dataset_sha256, candidate.dataset_sha256),
        ("dataset_role", control.dataset_role, candidate.dataset_role),
        ("population_hash", control.population_hash, candidate.population_hash),
        ("friction_profile_sha256", control.friction_profile_sha256, candidate.friction_profile_sha256),
        ("sample_size", control.metrics.sample_size, candidate.metrics.sample_size),
    )
    for name, left, right in identity_pairs:
        if left is None or right is None:
            blockers_list.append(f"{name.upper()}_MISSING")
        elif left != right:
            blockers_list.append(f"{name.upper()}_MISMATCH")
    blockers = tuple(blockers_list)
    if blockers:
        return ExperimentComparison(
            experiment_id=control.experiment_id,
            strategy_id=control.strategy_id,
            status=ComparisonStatus.BLOCKED_IDENTITY_MISMATCH,
            blockers=blockers,
            control_result_sha256=control.result_sha256,
            candidate_result_sha256=candidate.result_sha256,
            paired_sample_size=None,
            deltas=MetricDelta(),
            population_hash=None,
            dataset_sha256=None,
            friction_profile_sha256=None,
        )

    left = control.metrics
    right = candidate.metrics
    deltas = MetricDelta(
        gross_R=_difference(right.gross_R, left.gross_R),
        friction_R=_difference(right.friction_R, left.friction_R),
        net_R=_difference(right.net_R, left.net_R),
        gross_expectancy_R=_difference(right.gross_expectancy_R, left.gross_expectancy_R),
        net_expectancy_R=_difference(right.net_expectancy_R, left.net_expectancy_R),
        gross_wins=(right.gross_wins - left.gross_wins)
        if right.gross_wins is not None and left.gross_wins is not None else None,
        gross_losses=(right.gross_losses - left.gross_losses)
        if right.gross_losses is not None and left.gross_losses is not None else None,
        gross_breakevens=(right.gross_breakevens - left.gross_breakevens)
        if right.gross_breakevens is not None and left.gross_breakevens is not None else None,
        taken_count=(right.taken_count - left.taken_count)
        if right.taken_count is not None and left.taken_count is not None else None,
        blocked_count=(right.blocked_count - left.blocked_count)
        if right.blocked_count is not None and left.blocked_count is not None else None,
        position_guard_blocked_count=(right.position_guard_blocked_count - left.position_guard_blocked_count)
        if right.position_guard_blocked_count is not None and left.position_guard_blocked_count is not None else None,
        gross_max_drawdown_R=_difference(right.gross_max_drawdown_R, left.gross_max_drawdown_R),
        net_max_drawdown_R=_difference(right.net_max_drawdown_R, left.net_max_drawdown_R),
    )
    return ExperimentComparison(
        experiment_id=control.experiment_id,
        strategy_id=control.strategy_id,
        status=ComparisonStatus.COMPARABLE,
        blockers=(),
        control_result_sha256=control.result_sha256,
        candidate_result_sha256=candidate.result_sha256,
        paired_sample_size=left.sample_size,
        deltas=deltas,
        population_hash=control.population_hash,
        dataset_sha256=control.dataset_sha256,
        friction_profile_sha256=control.friction_profile_sha256,
    )


__all__ = ["ExperimentComparison", "MetricDelta", "compare_control_candidate"]
