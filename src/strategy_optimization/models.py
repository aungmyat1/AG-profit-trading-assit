"""Strategy Optimization Program V1 immutable data contracts.

This is a coordination layer over existing authorities, not a second strategy engine or
strategy lifecycle. It reuses SVOS hypothesis preregistration, candidate fingerprints,
external-candidate dataset roles, and the repository performance model. Nothing here
changes a canonical strategy, registry, lifecycle stage, or execution authorization.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from numbers import Real
from typing import Any, Mapping, Optional, Tuple

from external_candidate.models import DatasetRole as LegacyDatasetRole
from performance.models import NOT_EVALUATED, TradeMetrics
from post_asian_pilot.fingerprint import fingerprint
from svos.candidate import CandidateFreeze, FrozenCandidate, freeze_candidate
from svos.hypothesis import HypothesisContract, SearchBudget

SCHEMA_VERSION = "AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class DatasetRole(str, Enum):
    """Program-level role vocabulary; legacy formats are mapped explicitly below.

    The values intentionally distinguish independent replication, OOS, final holdout,
    and future forward shadow. A legacy `VALIDATION` value never erases that distinction
    in a Strategy Optimization Program manifest.
    """

    DEVELOPMENT = "DEVELOPMENT"
    DEVELOPMENT_REUSED = "DEVELOPMENT_REUSED"
    REPLICATION = "REPLICATION"
    OOS = "OOS"
    FINAL_HOLDOUT = "FINAL_HOLDOUT"
    FORWARD_SHADOW = "FORWARD_SHADOW"


class BaselineStatus(str, Enum):
    REPRODUCIBLE = "REPRODUCIBLE"
    NOT_REPRODUCIBLE = "NOT_REPRODUCIBLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class HypothesisStatus(str, Enum):
    DRAFT = "DRAFT"
    PREREGISTERED = "PREREGISTERED"
    NOT_PREREGISTERED = "NOT_PREREGISTERED"


class Arm(str, Enum):
    CONTROL = "CONTROL"
    CANDIDATE = "CANDIDATE"


class MetricStatus(str, Enum):
    EVALUATED = "EVALUATED"
    NOT_EVALUATED = "NOT_EVALUATED"
    BLOCKED = "BLOCKED"


class ComparisonStatus(str, Enum):
    COMPARABLE = "COMPARABLE"
    NOT_EVALUATED = "NOT_EVALUATED"
    BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"


class PromotionDisposition(str, Enum):
    HOLD = "HOLD"
    REJECT = "REJECT"
    ADVANCE_TO_OWNER_REVIEW = "ADVANCE_TO_OWNER_REVIEW"
    OWNER_APPROVED_CANDIDATE_VERSION = "OWNER_APPROVED_CANDIDATE_VERSION"


def _require_sha256(value: Optional[str], field_name: str, *, required: bool = False) -> None:
    if value is None:
        if required:
            raise ValueError(f"{field_name} is required")
        return
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 hex digest")


def _frozen_texts(values: Tuple[str, ...], field_name: str) -> Tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError(f"{field_name} must be a sequence, not one string")
    frozen = tuple(values)
    if any(not isinstance(value, str) or not value for value in frozen):
        raise ValueError(f"{field_name} must contain nonempty strings")
    return frozen


def _frozen_pairs(values: Tuple[Tuple[str, Any], ...], field_name: str) -> Tuple[Tuple[str, Any], ...]:
    pairs = tuple(tuple(pair) for pair in values)
    if any(len(pair) != 2 for pair in pairs):
        raise ValueError(f"{field_name} entries must be key/value pairs")
    if any(not isinstance(key, str) or not key for key, _ in pairs):
        raise ValueError(f"{field_name} keys must be nonempty strings")
    if any(not isinstance(value, (str, int, float, bool, type(None))) for _, value in pairs):
        raise ValueError(f"{field_name} values must be immutable JSON scalars")
    if any(isinstance(value, float) and not math.isfinite(value) for _, value in pairs):
        raise ValueError(f"{field_name} float values must be finite")
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{field_name} contains duplicate keys")
    return tuple(sorted(pairs, key=lambda pair: pair[0]))


def to_jsonable(value: Any) -> Any:
    """Convert immutable contracts to canonical-JSON-compatible primitives."""
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: to_jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "as_posix"):
        return value.as_posix()
    return value


def to_legacy_dataset_role(role: DatasetRole) -> Optional[LegacyDatasetRole]:
    """Explicit compatibility map to existing external-candidate/SVOS vocabulary.

    Only DEVELOPMENT and DEVELOPMENT_REUSED map to the legacy optimizer's permitted
    `OPTIMIZATION` role. REPLICATION and OOS both serialize as legacy `VALIDATION`, but
    the program-level role remains present and authoritative in the manifest. A forward
    stream is not a historical DatasetPartition and has no legacy mapping.
    """
    mapping = {
        DatasetRole.DEVELOPMENT: LegacyDatasetRole.OPTIMIZATION,
        DatasetRole.DEVELOPMENT_REUSED: LegacyDatasetRole.OPTIMIZATION,
        DatasetRole.REPLICATION: LegacyDatasetRole.VALIDATION,
        DatasetRole.OOS: LegacyDatasetRole.VALIDATION,
        DatasetRole.FINAL_HOLDOUT: LegacyDatasetRole.HOLDOUT,
        DatasetRole.FORWARD_SHADOW: None,
    }
    return mapping[DatasetRole(role)]


@dataclass(frozen=True)
class StrategyBaseline:
    """Immutable identity/provenance for one strategy's control baseline.

    `baseline_sha256` identifies the frozen economic baseline manifest, not merely the
    strategy YAML. It is `None` until the original population, dataset, and replay are
    reproduced. Canonical config fingerprints remain available independently.
    """

    strategy_id: str
    strategy_version: str
    canonical_config_ref: str
    canonical_config_sha256: str
    baseline_status: BaselineStatus
    baseline_sha256: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_sha256: Optional[str] = None
    population_hash: Optional[str] = None
    friction_profile_ref: Optional[str] = None
    friction_profile_sha256: Optional[str] = None
    source_refs: Tuple[str, ...] = ()
    blockers: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "baseline_status", BaselineStatus(self.baseline_status))
        object.__setattr__(self, "source_refs", _frozen_texts(self.source_refs, "source_refs"))
        object.__setattr__(self, "blockers", _frozen_texts(self.blockers, "blockers"))
        if not self.strategy_id or not self.strategy_version or not self.canonical_config_ref:
            raise ValueError("baseline strategy identity and config reference are required")
        _require_sha256(self.canonical_config_sha256, "canonical_config_sha256", required=True)
        _require_sha256(self.baseline_sha256, "baseline_sha256")
        _require_sha256(self.dataset_sha256, "dataset_sha256")
        _require_sha256(self.population_hash, "population_hash")
        _require_sha256(self.friction_profile_sha256, "friction_profile_sha256")
        if self.baseline_status is BaselineStatus.REPRODUCIBLE:
            missing = [
                name for name, value in (
                    ("baseline_sha256", self.baseline_sha256),
                    ("dataset_id", self.dataset_id),
                    ("dataset_sha256", self.dataset_sha256),
                    ("population_hash", self.population_hash),
                    ("friction_profile_sha256", self.friction_profile_sha256),
                ) if not value
            ]
            if missing:
                raise ValueError(f"reproducible baseline missing identity: {', '.join(missing)}")


@dataclass(frozen=True)
class ExperimentHypothesis:
    """One causal, strategy-scoped experiment hypothesis.

    The program stores permitted and forbidden deltas explicitly. `to_svos_contract()`
    is available only for an actually preregistered hypothesis; merely constructing this
    record does not preregister it or authorize an optimizer.
    """

    hypothesis_id: str
    strategy_id: str
    parent_version: str
    statement: str
    mechanism: str
    permitted_delta: Tuple[str, ...]
    forbidden_deltas: Tuple[str, ...]
    status: HypothesisStatus = HypothesisStatus.DRAFT
    development_dataset_id: Optional[str] = None
    protected_dataset_ids: Tuple[str, ...] = ()
    evaluation_metric: Optional[str] = None
    acceptance_rule: Tuple[Tuple[str, Any], ...] = ()
    frozen_dimensions: Tuple[Tuple[str, Any], ...] = ()
    max_candidates: Optional[int] = None
    max_search_budget: Optional[int] = None
    preregistration_sha256: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", HypothesisStatus(self.status))
        object.__setattr__(self, "permitted_delta", _frozen_texts(self.permitted_delta, "permitted_delta"))
        object.__setattr__(self, "forbidden_deltas", _frozen_texts(self.forbidden_deltas, "forbidden_deltas"))
        object.__setattr__(self, "protected_dataset_ids", _frozen_texts(self.protected_dataset_ids, "protected_dataset_ids"))
        object.__setattr__(self, "acceptance_rule", _frozen_pairs(self.acceptance_rule, "acceptance_rule"))
        object.__setattr__(self, "frozen_dimensions", _frozen_pairs(self.frozen_dimensions, "frozen_dimensions"))
        if not all((self.hypothesis_id, self.strategy_id, self.parent_version, self.statement, self.mechanism)):
            raise ValueError("hypothesis identity, statement, and mechanism are required")
        if not self.permitted_delta:
            raise ValueError("at least one permitted delta must be specified")
        if self.status is HypothesisStatus.PREREGISTERED:
            if len(self.permitted_delta) != 1:
                raise ValueError("preregistered hypothesis must have one primary permitted delta")
            if not self.development_dataset_id or not self.evaluation_metric:
                raise ValueError("preregistered hypothesis needs development data and a primary metric")
            if not self.protected_dataset_ids:
                raise ValueError("preregistered hypothesis must declare protected dataset IDs")
            if not self.preregistration_sha256:
                raise ValueError("preregistered hypothesis needs its frozen preregistration hash")
            if self.max_candidates is None or self.max_search_budget is None:
                raise ValueError("preregistered hypothesis needs a frozen search budget")
            if any(
                not isinstance(value, int) or isinstance(value, bool) or value <= 0
                for value in (self.max_candidates, self.max_search_budget)
            ):
                raise ValueError("frozen search budgets must be positive integers")
        _require_sha256(self.preregistration_sha256, "preregistration_sha256")

    def to_svos_contract(self) -> HypothesisContract:
        """Adapt this contract to the existing SVOS bounded-optimizer preregistration."""
        if self.status is not HypothesisStatus.PREREGISTERED:
            raise ValueError("HYPOTHESIS_NOT_PREREGISTERED")
        if len(self.permitted_delta) != 1:
            raise ValueError("SVOS_REQUIRES_ONE_SINGLE_PRIMARY_DELTA")
        acceptance = dict(self.acceptance_rule)
        if not acceptance:
            raise ValueError("FROZEN_ACCEPTANCE_RULE_REQUIRED")
        contract = HypothesisContract(
            hypothesis_id=self.hypothesis_id,
            parent_strategy=self.strategy_id,
            parent_version=self.parent_version,
            mechanism=self.mechanism,
            single_primary_delta=self.permitted_delta[0],
            frozen_dimensions={
                **dict(self.frozen_dimensions),
                "forbidden_deltas": list(self.forbidden_deltas),
            },
            development_dataset=self.development_dataset_id or "",
            protected_datasets=tuple(sorted(self.protected_dataset_ids)),
            evaluation_metric=self.evaluation_metric or "",
            acceptance_rule=acceptance,
            search_budget=SearchBudget(
                max_candidates=int(self.max_candidates or 0),
                max_search_budget=int(self.max_search_budget or 0),
            ),
        ).freeze()
        if contract.preregistration_hash != self.preregistration_sha256:
            raise ValueError("SVOS_PREREGISTRATION_HASH_MISMATCH")
        return contract


@dataclass(frozen=True)
class CandidateStrategy:
    """Strategy-scoped candidate identity; never a promotion or authorization record."""

    strategy_id: str
    parent_version: str
    candidate_version: Optional[str]
    candidate_config_sha256: str
    candidate_implementation_sha256: str
    implementation_ref: str
    permitted_delta: Tuple[str, ...]
    forbidden_deltas: Tuple[str, ...]
    version_assignment_status: str = "ASSIGNED"
    source_status: str = "FROZEN"

    def __post_init__(self) -> None:
        object.__setattr__(self, "permitted_delta", _frozen_texts(self.permitted_delta, "permitted_delta"))
        object.__setattr__(self, "forbidden_deltas", _frozen_texts(self.forbidden_deltas, "forbidden_deltas"))
        if not self.strategy_id or not self.parent_version or not self.implementation_ref:
            raise ValueError("candidate strategy identity and implementation reference are required")
        _require_sha256(self.candidate_config_sha256, "candidate_config_sha256", required=True)
        _require_sha256(self.candidate_implementation_sha256, "candidate_implementation_sha256", required=True)
        if self.candidate_version is None and self.version_assignment_status == "ASSIGNED":
            raise ValueError("missing candidate version must not be marked ASSIGNED")
        if not self.permitted_delta:
            raise ValueError("candidate must declare its permitted delta")

    @property
    def candidate_sha256(self) -> str:
        return fingerprint(to_jsonable(self))

    def freeze_with_svos(
        self,
        *,
        dataset_role: DatasetRole,
        parameters: Mapping[str, object],
        friction_contract: str,
        session_contract: str,
        decision_tf: str,
        execution_tf: str,
        risk_contract: str,
    ) -> FrozenCandidate:
        """Delegate the later candidate freeze to canonical `svos.candidate`.

        This is intentionally unavailable until an owner assigns a candidate version.
        The common registry does not invent a parallel frozen-candidate fingerprint.
        """
        if not self.candidate_version or self.version_assignment_status != "ASSIGNED":
            raise ValueError("OWNER_ASSIGNED_CANDIDATE_VERSION_REQUIRED_BEFORE_SVOS_FREEZE")
        code_config_hash = fingerprint({
            "candidate_config_sha256": self.candidate_config_sha256,
            "candidate_implementation_sha256": self.candidate_implementation_sha256,
        })
        freeze = CandidateFreeze(
            strategy_id=self.strategy_id,
            version=self.candidate_version,
            code_config_hash=code_config_hash,
            dataset_role=dataset_role.value,
            parameters=dict(parameters),
            friction_contract=friction_contract,
            session_contract=session_contract,
            decision_tf=decision_tf,
            execution_tf=execution_tf,
            risk_contract=risk_contract,
        )
        return freeze_candidate(freeze)


@dataclass(frozen=True)
class DatasetManifest:
    """Write-once dataset identity/role metadata; the framework never reads bars here."""

    strategy_id: str
    dataset_id: str
    role: DatasetRole
    source_ref: str
    dataset_sha256: Optional[str]
    symbols: Tuple[str, ...] = ()
    utc_start: Optional[str] = None
    utc_end: Optional[str] = None
    reused_from_experiment_id: Optional[str] = None
    reused_from_dataset_id: Optional[str] = None
    description: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", DatasetRole(self.role))
        object.__setattr__(self, "symbols", _frozen_texts(self.symbols, "symbols"))
        if not self.strategy_id or not self.dataset_id or not self.source_ref:
            raise ValueError("dataset strategy, id, and source reference are required")
        _require_sha256(self.dataset_sha256, "dataset_sha256")
        if self.role is DatasetRole.DEVELOPMENT_REUSED and not all((
            self.reused_from_experiment_id, self.reused_from_dataset_id
        )):
            raise ValueError("DEVELOPMENT_REUSED must name the prior experiment and dataset")
        if self.role is not DatasetRole.DEVELOPMENT_REUSED and any((
            self.reused_from_experiment_id, self.reused_from_dataset_id
        )):
            raise ValueError("reuse lineage is only valid for DEVELOPMENT_REUSED")
        if self.role is not DatasetRole.FORWARD_SHADOW and not self.dataset_sha256:
            raise ValueError(f"{self.role.value} requires a pinned dataset SHA-256")
        if self.utc_start and self.utc_end and self.utc_start > self.utc_end:
            raise ValueError("dataset UTC start must not be after UTC end")

    @property
    def manifest_sha256(self) -> str:
        return fingerprint(to_jsonable(self))


@dataclass(frozen=True)
class ExperimentMetrics:
    """Common CONTROL/CANDIDATE result schema with explicit gross/friction/net fields.

    Missing evidence is represented by `None` plus NOT_EVALUATED; it is never coerced to
    zero. Existing `performance.calculator` owns trade-metric arithmetic; this contract
    only normalizes its result and adds experiment-specific funnel/concurrency slots.
    """

    status: MetricStatus = MetricStatus.NOT_EVALUATED
    cost_status: str = NOT_EVALUATED
    sample_size: Optional[int] = None
    setup_count: Optional[int] = None
    taken_count: Optional[int] = None
    blocked_count: Optional[int] = None
    position_guard_blocked_count: Optional[int] = None
    previously_blocked_now_admitted_count: Optional[int] = None
    gross_R: Optional[float] = None
    friction_R: Optional[float] = None
    net_R: Optional[float] = None
    gross_expectancy_R: Optional[float] = None
    net_expectancy_R: Optional[float] = None
    gross_wins: Optional[int] = None
    gross_losses: Optional[int] = None
    gross_breakevens: Optional[int] = None
    gross_win_rate: Optional[float] = None
    gross_profit_factor: Optional[float | str] = None
    gross_max_drawdown_R: Optional[float] = None
    net_max_drawdown_R: Optional[float] = None
    mean_MAE_R: Optional[float] = None
    mean_MFE_R: Optional[float] = None
    max_concurrent_positions: Optional[int] = None
    max_concurrent_positions_per_symbol: Optional[int] = None
    source_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", MetricStatus(self.status))
        object.__setattr__(self, "source_refs", _frozen_texts(self.source_refs, "source_refs"))
        integer_fields = (
            "sample_size", "setup_count", "taken_count", "blocked_count",
            "position_guard_blocked_count", "previously_blocked_now_admitted_count",
            "gross_wins", "gross_losses", "gross_breakevens",
            "max_concurrent_positions", "max_concurrent_positions_per_symbol",
        )
        for name in integer_fields:
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        float_fields = (
            "gross_R", "friction_R", "net_R", "gross_expectancy_R", "net_expectancy_R",
            "gross_win_rate", "gross_max_drawdown_R", "net_max_drawdown_R", "mean_MAE_R", "mean_MFE_R",
        )
        for name in float_fields:
            value = getattr(self, name)
            if value is not None and (not isinstance(value, Real) or isinstance(value, bool) or not math.isfinite(float(value))):
                raise ValueError(f"{name} must be a finite number or None")
        if isinstance(self.gross_profit_factor, Real) and (
            isinstance(self.gross_profit_factor, bool) or not math.isfinite(float(self.gross_profit_factor))
        ):
            raise ValueError("gross_profit_factor must be finite")
        if self.gross_win_rate is not None and not 0.0 <= self.gross_win_rate <= 1.0:
            raise ValueError("gross_win_rate must be between zero and one")
        if self.status is not MetricStatus.EVALUATED:
            numeric_fields = (
                *integer_fields,
                "gross_R", "friction_R", "net_R", "gross_expectancy_R", "net_expectancy_R",
                "gross_win_rate", "gross_profit_factor", "gross_max_drawdown_R",
                "net_max_drawdown_R", "mean_MAE_R", "mean_MFE_R",
            )
            if any(getattr(self, name) is not None for name in numeric_fields):
                raise ValueError("NOT_EVALUATED/BLOCKED metrics must not contain numeric outcomes")
        elif self.sample_size is None:
            raise ValueError("EVALUATED metrics require sample_size")
        elif self.sample_size <= 0:
            raise ValueError("EVALUATED metrics require a positive sample_size")
        if self.status is MetricStatus.EVALUATED and not any(
            getattr(self, name) is not None for name in (
                *integer_fields[1:], "gross_R", "friction_R", "net_R", "gross_expectancy_R",
                "net_expectancy_R", "gross_win_rate", "gross_profit_factor",
                "gross_max_drawdown_R", "net_max_drawdown_R", "mean_MAE_R", "mean_MFE_R",
            )
        ):
            raise ValueError("EVALUATED metrics require at least one observed metric")
        if self.status is MetricStatus.EVALUATED and all(
            value is not None for value in (self.gross_wins, self.gross_losses, self.gross_breakevens)
        ) and self.gross_wins + self.gross_losses + self.gross_breakevens != self.sample_size:
            raise ValueError("gross outcome counts must sum to sample_size")
        if self.cost_status == NOT_EVALUATED and any(
            value is not None for value in (self.friction_R, self.net_R, self.net_expectancy_R, self.net_max_drawdown_R)
        ):
            raise ValueError("unavailable friction must not be represented as zero or net results")
        if self.friction_R is not None and self.friction_R < 0:
            raise ValueError("friction_R must be nonnegative when modeled")
        if self.gross_R is not None and self.friction_R is not None and self.net_R is not None:
            if not math.isclose(self.gross_R - self.friction_R, self.net_R, rel_tol=1e-9, abs_tol=1e-9):
                raise ValueError("gross_R - friction_R must equal net_R")

    @classmethod
    def from_trade_metrics(
        cls,
        metrics: TradeMetrics,
        *,
        friction_R: Optional[float] = None,
        source_refs: Tuple[str, ...] = (),
    ) -> "ExperimentMetrics":
        """Normalize the canonical performance calculator output without recalculating it."""
        if metrics.sample_size == 0:
            return cls(source_refs=source_refs)

        def number_or_none(value: Any) -> Optional[float]:
            if isinstance(value, Real) and not isinstance(value, bool):
                return float(value)
            return None

        normalized_cost_status = metrics.cost_status
        normalized_net_total = number_or_none(metrics.net_total_R)
        if friction_R is not None and normalized_net_total is not None:
            normalized_cost_status = "MODELED"
        elif friction_R is not None:
            normalized_cost_status = "PARTIAL"
        return cls(
            status=MetricStatus.EVALUATED,
            cost_status=normalized_cost_status,
            sample_size=metrics.sample_size,
            gross_R=number_or_none(metrics.gross_total_R),
            friction_R=friction_R,
            net_R=normalized_net_total,
            gross_expectancy_R=number_or_none(metrics.gross_expectancy_R),
            net_expectancy_R=number_or_none(metrics.net_expectancy_R),
            gross_wins=metrics.wins,
            gross_losses=metrics.losses,
            gross_breakevens=metrics.breakevens,
            gross_win_rate=number_or_none(metrics.win_rate),
            gross_profit_factor=(
                float(metrics.profit_factor)
                if isinstance(metrics.profit_factor, Real) and not isinstance(metrics.profit_factor, bool)
                else metrics.profit_factor if isinstance(metrics.profit_factor, str) else None
            ),
            gross_max_drawdown_R=number_or_none(metrics.max_drawdown_R),
            source_refs=source_refs,
        )


@dataclass(frozen=True)
class ExperimentResult:
    """Immutable per-arm result. Control/candidate comparability is checked separately."""

    experiment_id: str
    strategy_id: str
    arm: Arm
    metrics: ExperimentMetrics
    dataset_id: Optional[str] = None
    dataset_sha256: Optional[str] = None
    dataset_role: Optional[DatasetRole] = None
    population_hash: Optional[str] = None
    friction_profile_sha256: Optional[str] = None
    candidate_config_sha256: Optional[str] = None
    run_id: Optional[str] = None
    evidence_refs: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "arm", Arm(self.arm))
        if self.dataset_role is not None:
            object.__setattr__(self, "dataset_role", DatasetRole(self.dataset_role))
        object.__setattr__(self, "evidence_refs", _frozen_texts(self.evidence_refs, "evidence_refs"))
        if not self.experiment_id or not self.strategy_id:
            raise ValueError("experiment result identity is required")
        _require_sha256(self.dataset_sha256, "dataset_sha256")
        _require_sha256(self.population_hash, "population_hash")
        _require_sha256(self.friction_profile_sha256, "friction_profile_sha256")
        _require_sha256(self.candidate_config_sha256, "candidate_config_sha256")
        if self.metrics.status is MetricStatus.EVALUATED and not all((
            self.dataset_id, self.dataset_sha256, self.dataset_role, self.population_hash,
            self.friction_profile_sha256, self.candidate_config_sha256,
        )):
            raise ValueError("evaluated result requires dataset, population, friction, and config identities")

    @property
    def result_sha256(self) -> str:
        return fingerprint(to_jsonable(self))


@dataclass(frozen=True)
class ExperimentManifest:
    """Immutable experiment identity shared across all strategy-specific tracks."""

    experiment_id: str
    strategy_id: str
    baseline: StrategyBaseline
    hypothesis: ExperimentHypothesis
    candidate: CandidateStrategy
    dataset: Optional[DatasetManifest]
    created_at_utc: str
    related_evidence_refs: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "related_evidence_refs", _frozen_texts(self.related_evidence_refs, "related_evidence_refs"))
        object.__setattr__(self, "notes", _frozen_texts(self.notes, "notes"))
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported experiment schema: {self.schema_version}")
        if not self.experiment_id or not self.created_at_utc:
            raise ValueError("experiment id and creation timestamp are required")
        identities = {
            self.strategy_id,
            self.baseline.strategy_id,
            self.hypothesis.strategy_id,
            self.candidate.strategy_id,
        }
        if len(identities) != 1:
            raise ValueError("CROSS_STRATEGY_EXPERIMENT_FORBIDDEN")
        if self.hypothesis.parent_version != self.baseline.strategy_version:
            raise ValueError("HYPOTHESIS_PARENT_VERSION_MISMATCH")
        if self.candidate.parent_version != self.baseline.strategy_version:
            raise ValueError("CANDIDATE_PARENT_VERSION_MISMATCH")
        if self.dataset is not None and self.dataset.strategy_id != self.strategy_id:
            raise ValueError("CROSS_STRATEGY_DATASET_FORBIDDEN")
        if self.baseline.baseline_status is BaselineStatus.REPRODUCIBLE:
            if self.dataset is None:
                raise ValueError("REPRODUCIBLE_EXPERIMENT_REQUIRES_DATASET_ROLE")
            if self.baseline.dataset_id != self.dataset.dataset_id or self.baseline.dataset_sha256 != self.dataset.dataset_sha256:
                raise ValueError("BASELINE_AND_EXPERIMENT_DATASET_IDENTITY_MISMATCH")

    @property
    def baseline_sha256(self) -> Optional[str]:
        return self.baseline.baseline_sha256

    @property
    def candidate_config_sha256(self) -> str:
        return self.candidate.candidate_config_sha256

    @property
    def dataset_role(self) -> Optional[DatasetRole]:
        return self.dataset.role if self.dataset is not None else None

    @property
    def manifest_sha256(self) -> str:
        return fingerprint(to_jsonable(self))


@dataclass(frozen=True)
class PromotionDecision:
    """Auditable human decision record; writing it never edits strategy authority."""

    decision_id: str
    experiment_id: str
    strategy_id: str
    disposition: PromotionDisposition
    rationale: str
    decided_by: str
    decided_at_utc: str
    authority_ref: str
    candidate_version: Optional[str] = None
    execution_authority_changed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "disposition", PromotionDisposition(self.disposition))
        if not all((self.decision_id, self.experiment_id, self.strategy_id, self.rationale,
                    self.decided_by, self.decided_at_utc, self.authority_ref)):
            raise ValueError("promotion decision requires explicit owner, rationale, time, and authority reference")
        if self.execution_authority_changed:
            raise ValueError("OPTIMIZATION_PROGRAM_CANNOT_CHANGE_EXECUTION_AUTHORITY")
        if self.disposition is PromotionDisposition.OWNER_APPROVED_CANDIDATE_VERSION and not self.candidate_version:
            raise ValueError("owner-approved candidate decision must name a candidate version")

    @property
    def decision_sha256(self) -> str:
        return fingerprint(to_jsonable(self))


__all__ = [
    "Arm", "BaselineStatus", "CandidateStrategy", "ComparisonStatus", "DatasetManifest",
    "DatasetRole", "ExperimentHypothesis", "ExperimentManifest", "ExperimentMetrics",
    "ExperimentResult", "HypothesisStatus", "MetricStatus", "PromotionDecision",
    "PromotionDisposition", "SCHEMA_VERSION", "StrategyBaseline", "to_jsonable",
    "to_legacy_dataset_role",
]
