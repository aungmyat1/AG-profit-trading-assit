"""AG_EXTERNAL_CANDIDATE_PACKAGE -- canonical data model for a frozen external
strategy candidate.

This module defines the shape only. It reuses, rather than re-derives:
  - `post_asian_pilot.fingerprint.fingerprint()` for all hashing (no second hash
    implementation is introduced here -- see that module's own docstring).
  - the `config/historical_datasets/*.yaml` manifest field vocabulary (`dataset_id`,
    `symbol`, timeframe, `utc_start`/`utc_end`, `dataset_fingerprint`) for
    `DatasetPartition`, rather than inventing new field names for the same concept.
  - `performance.models.ResolvedTradeSample`/`TradeMetrics` for every metric this
    package produces or compares (parity/, oos_evaluator.py, walk_forward.py) --
    no competing metric definition is introduced.

No dataclass here grants execution, Demo, or Live authority, and none is itself an
R6 verdict -- see `admission.py` for CANDIDATE_PACKAGE_* outcomes (distinct
vocabulary from R6's EDGE_VALIDATED/EDGE_FAILED/INSUFFICIENT_EVIDENCE, per the
mission's explicit instruction not to overload R6 vocabulary with admission
failures).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

NOT_AVAILABLE = "NOT_AVAILABLE"
SCHEMA_VERSION = "AG_EXTERNAL_CANDIDATE_PACKAGE_V1"

# Required structured-rule categories (mission section 5). A candidate package is
# INCOMPLETE if any of these keys is absent from CandidateRules.rule_sections.
REQUIRED_RULE_SECTIONS: Tuple[str, ...] = (
    "entry_rules",
    "exit_rules",
    "direction_rules",
    "regime_rules",
    "session_rules",
    "filters",
    "sl_logic",
    "tp_logic",
    "trade_management_logic",
    "position_risk_assumptions",
)


class DatasetRole(str, Enum):
    DISCOVERY = "DISCOVERY"
    OPTIMIZATION = "OPTIMIZATION"
    VALIDATION = "VALIDATION"
    HOLDOUT = "HOLDOUT"


@dataclass(frozen=True)
class DatasetPartition:
    """One named dataset slice. Field names deliberately mirror
    `config/historical_datasets/*.yaml` (dataset_id/symbol/timeframe/utc_start/
    utc_end/dataset_fingerprint) so an existing manifest can be referenced/copied
    into a candidate package without renaming anything."""

    role: DatasetRole
    dataset_id: str
    symbol: str
    timeframe: str
    utc_start: str
    utc_end: str
    dataset_fingerprint: str
    source: str = NOT_AVAILABLE
    timezone_status: str = NOT_AVAILABLE
    broker_utc_offset_hours: Optional[float] = None


@dataclass(frozen=True)
class HoldoutDeclaration:
    """Mandatory, non-inferred declarations (mission section 8). Absence of this
    object entirely (as opposed to an explicit False) is itself
    CANDIDATE_PACKAGE_INCOMPLETE -- see admission.py; compliance is never assumed."""

    holdout_dataset_id: str
    holdout_used_for_optimization: bool
    rules_changed_after_holdout: bool


@dataclass(frozen=True)
class FrictionAssumptions:
    """External candidate's own stated friction assumptions. `None` on any field
    means the external package did not state that cost component -- never treated
    as zero. Never silently mapped onto CONTRACT_CEILING; see friction.py for the
    explicit compatibility classification this package requires instead."""

    spread: Optional[float] = None
    spread_unit: Optional[str] = None  # e.g. "pips", "price"
    commission: Optional[float] = None
    commission_unit: Optional[str] = None
    slippage: Optional[float] = None
    slippage_unit: Optional[str] = None
    funding: Optional[float] = None
    other_costs: Mapping[str, float] = field(default_factory=dict)

    def is_stated(self) -> bool:
        return self.spread is not None and self.commission is not None and self.slippage is not None


@dataclass(frozen=True)
class CandidateRules:
    """Exact-rules contract (mission section 5). `strategy_config_ref` points at an
    existing repository strategy config (strategies/<ID>.yaml or equivalent) rather
    than duplicating its parameters in prose -- `rule_sections` carries only the
    candidate-specific structured rule text/deltas the referenced config does not
    already encode, plus the complete parameter map the candidate actually used."""

    strategy_config_ref: str
    rule_sections: Mapping[str, str]
    parameters: Mapping[str, Any]


@dataclass(frozen=True)
class CandidateProvenance:
    candidate_config_hash: str
    dataset_fingerprints: Tuple[str, ...]
    research_source: str
    research_run_id: str
    git_commit: str = NOT_AVAILABLE


@dataclass(frozen=True)
class ExternalTradeRecord:
    """One external-candidate trade/cycle record for parity comparison (mission
    section 13). Any field the external export could not supply must be `None`,
    never fabricated -- see parity/trade_comparator.py's PARTIAL capability
    handling."""

    cycle: Optional[str]
    signal_timestamp: Optional[str]
    direction: Optional[str]
    entry: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    exit_price: Optional[float]
    outcome: Optional[str]
    gross_R: Optional[float]
    cost_R: Optional[float]
    net_R: Optional[float]


@dataclass(frozen=True)
class ExternalCandidatePackage:
    schema_version: str
    candidate_id: str
    strategy_id: str
    candidate_version: str
    parent_strategy_version: Optional[str]

    frozen_at_utc: str
    candidate_frozen: bool

    rules: CandidateRules
    datasets: Tuple[DatasetPartition, ...]
    holdout: Optional[HoldoutDeclaration]
    friction: FrictionAssumptions
    provenance: CandidateProvenance

    external_trades: Tuple[ExternalTradeRecord, ...] = ()
    external_trade_capability: str = "PARTIAL"  # "FULL" only if every field above is populated for every trade


class AdmissionStatus(str, Enum):
    ACCEPTED = "CANDIDATE_PACKAGE_ACCEPTED"
    INCOMPLETE = "CANDIDATE_PACKAGE_INCOMPLETE"
    REJECTED_HOLDOUT_LEAKAGE = "CANDIDATE_REJECTED_HOLDOUT_LEAKAGE"
    REJECTED_NOT_FROZEN = "CANDIDATE_REJECTED_NOT_FROZEN"
    REJECTED_VERSION_CONFLICT = "CANDIDATE_REJECTED_VERSION_CONFLICT"
    REJECTED_VERSION_MUTATION = "CANDIDATE_REJECTED_VERSION_MUTATION"
    REJECTED_AMBIGUOUS_RULES = "CANDIDATE_REJECTED_AMBIGUOUS_RULES"


@dataclass(frozen=True)
class AdmissionResult:
    status: AdmissionStatus
    candidate_id: str
    reasons: Tuple[str, ...]
    details: Mapping[str, Any] = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status is AdmissionStatus.ACCEPTED
