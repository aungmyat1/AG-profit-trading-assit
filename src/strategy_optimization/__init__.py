"""AG Strategy Optimization Framework V1.

Common immutable experiment contracts and controls. Per-strategy engines, lifecycles,
execution permissions, and economic evidence remain independent and owner-controlled.
"""
from .dataset_firewall import DatasetAccessDenied, DatasetAccessFirewall, optimizer_role
from .metrics import ExperimentComparison, MetricDelta, compare_control_candidate
from .models import (
    Arm,
    BaselineStatus,
    CandidateStrategy,
    ComparisonStatus,
    DatasetManifest,
    DatasetRole,
    ExperimentHypothesis,
    ExperimentManifest,
    ExperimentMetrics,
    ExperimentResult,
    HypothesisStatus,
    MetricStatus,
    PromotionDecision,
    PromotionDisposition,
    StrategyBaseline,
)
from .registry import ExperimentRegistry, TransitionRejected
from .state_machine import CandidateState, TERMINAL_STATES, validate_transition

__all__ = [
    "Arm", "BaselineStatus", "CandidateState", "CandidateStrategy", "ComparisonStatus",
    "DatasetAccessDenied", "DatasetAccessFirewall", "DatasetManifest", "DatasetRole",
    "ExperimentComparison", "ExperimentHypothesis", "ExperimentManifest", "ExperimentMetrics",
    "ExperimentRegistry", "ExperimentResult", "HypothesisStatus", "MetricDelta", "MetricStatus",
    "PromotionDecision", "PromotionDisposition", "StrategyBaseline", "TERMINAL_STATES",
    "TransitionRejected", "compare_control_candidate", "optimizer_role", "validate_transition",
]
