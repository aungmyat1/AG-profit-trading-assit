"""Stable records for entry-population and exit-policy experiments."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Tuple


@dataclass(frozen=True)
class CandleSnapshot:
    timestamp: str
    open: float
    high: float
    low: float
    close: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CanonicalOccurrence:
    occurrence_id: str
    strategy_id: str
    strategy_version: str
    exchange: str
    symbol: str
    side: str
    entry_timestamp: str
    entry_price: float
    initial_sl: float
    initial_tp: float
    m1_path: Tuple[CandleSnapshot, ...]
    cost_context: Dict[str, Any] = field(default_factory=dict)
    market_metadata: Dict[str, Any] = field(default_factory=dict)
    data_hash: str = ""
    strategy_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["m1_path"] = [candle.to_dict() for candle in self.m1_path]
        return value

    def canonical_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ExitDecision:
    policy_id: str
    exit_timestamp: str
    exit_price: float
    exit_reason: str
    holding_minutes: int


@dataclass(frozen=True)
class ExperimentResult:
    policy_id: str
    occurrence_ids: Tuple[str, ...]
    outcomes: Tuple[Dict[str, Any], ...]
    population_hash: str

    @property
    def sample_size(self) -> int:
        return len(self.outcomes)

    @property
    def net_expectancy_R(self) -> float:
        if not self.outcomes:
            return 0.0
        return sum(float(row["net_R"]) for row in self.outcomes) / len(self.outcomes)