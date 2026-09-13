"""Immutable, research-only experiment primitives."""

from .models import CanonicalOccurrence, CandleSnapshot, ExitDecision, ExperimentResult
from .policies import ControlPolicy, TimeStopPolicy
from .runner import CanonicalExperimentRunner, ExperimentScopeError
from .splits import chronological_split
from .population import load_population, population_hash, write_population

__all__ = [
    "CanonicalOccurrence", "CandleSnapshot", "ExitDecision", "ExperimentResult",
    "ControlPolicy", "TimeStopPolicy", "CanonicalExperimentRunner",
    "ExperimentScopeError", "chronological_split",
    "load_population", "population_hash", "write_population",
]