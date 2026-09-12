"""Canonical interface for deterministic trading-skill observations.

This module owns no strategy, proposal, risk, lifecycle, authorization, or execution
behavior. Existing deterministic analyzers may adopt this interface through adapters;
they are deliberately not rewritten by this architecture slice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping, Protocol, runtime_checkable


FORBIDDEN_CLASSIFICATIONS = frozenset(
    {"BUY", "SELL", "OPEN_POSITION", "EXECUTE", "PROMOTE", "AUTHORIZE"}
)


def fingerprint_input(value: Any) -> str:
    """Return a stable fingerprint for JSON-compatible skill input."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class MarketObservation:
    """Immutable observation emitted by a deterministic trading skill."""

    skill_id: str
    skill_version: str
    symbol: str
    timeframe: str
    observed_at: datetime
    classification: str
    input_fingerprint: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.classification.strip().upper() in FORBIDDEN_CLASSIFICATIONS:
            raise ValueError(
                "deterministic trading skills may emit observations, not trade or "
                "authority instructions"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_version": self.skill_version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "observed_at": self.observed_at.isoformat(),
            "classification": self.classification,
            "evidence": dict(self.evidence),
            "input_fingerprint": self.input_fingerprint,
        }


@runtime_checkable
class TradingSkill(Protocol):
    """Minimal seam implemented by deterministic market-analysis adapters."""

    skill_id: str
    version: str

    def evaluate(self, context: Mapping[str, Any]) -> MarketObservation: ...
