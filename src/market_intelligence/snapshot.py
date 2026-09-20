"""Immutable, strategy-neutral Market Intelligence V1 evidence contract."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Tuple

SCHEMA_VERSION = "AG_MARKET_INTELLIGENCE_SNAPSHOT_V1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("MI timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class MIIdentity:
    symbol: str
    as_of: datetime
    event_id: str
    evaluation_mode: str
    decision_cycle: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "as_of", _utc(self.as_of))
        if not self.symbol or not self.event_id or not self.evaluation_mode:
            raise ValueError("MI identity requires symbol, event_id, and evaluation_mode")


@dataclass(frozen=True)
class MIProvenance:
    event_id: str
    visibility_rule_version: str
    dataset_identities: Tuple[Tuple[str, str], ...]
    source_labels: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class MIQuality:
    overall_status: str
    reason_codes: Tuple[str, ...] = ()
    missing_components: Tuple[str, ...] = ()
    completeness: str = "COMPLETE"

    def __post_init__(self):
        if self.overall_status not in {"VALID", "INCOMPLETE", "INVALID"}:
            raise ValueError("unsupported MI quality status")


@dataclass(frozen=True)
class MIComponent:
    """A typed observation bundle; values are supplied by an existing authority."""
    status: str
    source_classification: str
    feature_version: str
    value: Any = None
    reason_codes: Tuple[str, ...] = ()

    def __post_init__(self):
        if self.source_classification not in {"AUTHORITATIVE", "ADAPTED_AUTHORITATIVE", "UNAVAILABLE"}:
            raise ValueError("invalid MI authority classification")
        if self.status not in {"AVAILABLE", "UNAVAILABLE", "INCOMPLETE"}:
            raise ValueError("invalid MI component status")


@dataclass(frozen=True)
class MIExecutionLineage:
    timeframe: str
    participating_series: Tuple[str, ...]
    last_closed_bar: Optional[datetime]
    confirmation_cutoffs: Tuple[Tuple[str, datetime], ...]
    m1_used: bool

    def __post_init__(self):
        if self.last_closed_bar is not None:
            object.__setattr__(self, "last_closed_bar", _utc(self.last_closed_bar))
        object.__setattr__(self, "confirmation_cutoffs", tuple(
            (name, _utc(value)) for name, value in self.confirmation_cutoffs
        ))


@dataclass(frozen=True)
class MarketIntelligenceSnapshot:
    schema_version: str
    snapshot_id: str
    identity: MIIdentity
    provenance: MIProvenance
    quality: MIQuality
    sessions: MIComponent
    higher_timeframe_context: MIComponent
    structure: MIComponent
    liquidity: MIComponent
    regime: MIComponent
    volatility: MIComponent
    execution_timeframe_lineage: MIExecutionLineage

    def __post_init__(self):
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported MI schema version")
        if self.identity.event_id != self.provenance.event_id:
            raise ValueError("identity/provenance event IDs must match")

    def semantic_payload(self) -> Mapping[str, Any]:
        return {
            "schema_version": self.schema_version,
            "identity": self.identity,
            "provenance": self.provenance,
            "quality": self.quality,
            "sessions": self.sessions,
            "higher_timeframe_context": self.higher_timeframe_context,
            "structure": self.structure,
            "liquidity": self.liquidity,
            "regime": self.regime,
            "volatility": self.volatility,
            "execution_timeframe_lineage": self.execution_timeframe_lineage,
        }

    def to_dict(self) -> dict:
        def convert(value):
            if isinstance(value, datetime): return _utc(value).isoformat()
            if hasattr(value, "__dataclass_fields__"):
                return {k: convert(getattr(value, k)) for k in value.__dataclass_fields__}
            if isinstance(value, tuple): return [convert(v) for v in value]
            if isinstance(value, dict): return {str(k): convert(v) for k, v in value.items()}
            return value
        return convert(self.semantic_payload())


def build_snapshot_id(payload: Mapping[str, Any]) -> str:
    def default(value):
        if hasattr(value, "__dataclass_fields__"):
            return {k: getattr(value, k) for k in value.__dataclass_fields__}
        if isinstance(value, datetime): return _utc(value).isoformat()
        if isinstance(value, tuple): return list(value)
        raise TypeError(type(value).__name__)
    blob = json.dumps(payload, default=default, sort_keys=True, separators=(",", ":"))
    return "MI-" + hashlib.sha256(blob.encode()).hexdigest()
