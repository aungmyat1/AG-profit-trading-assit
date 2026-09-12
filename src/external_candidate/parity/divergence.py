"""First-divergence diagnostics (mission section 17). Bounded, read-only,
classification-only -- never modifies a candidate's rules or a comparator's input.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

DIVERGENCE_CATEGORIES = (
    "DATA", "TIMEZONE", "SESSION_BOUNDARY", "BAR_CLOSE", "WARMUP", "REGIME",
    "SIGNAL", "ENTRY", "STOP", "TARGET", "FRICTION", "OUTCOME_ORDERING", "UNCLASSIFIED",
)

# Field-name -> category. Deliberately conservative: an unrecognized field name is
# UNCLASSIFIED rather than guessed into the wrong bucket.
_FIELD_CATEGORY = {
    "signal_timestamp": "TIMEZONE",
    "cycle": "SESSION_BOUNDARY",
    "session": "SESSION_BOUNDARY",
    "regime": "REGIME",
    "direction": "SIGNAL",
    "setup_type": "SIGNAL",
    "state": "SIGNAL",
    "entry": "ENTRY",
    "entry_price": "ENTRY",
    "stop_loss": "STOP",
    "sl": "STOP",
    "take_profit": "TARGET",
    "tp": "TARGET",
    "exit_price": "OUTCOME_ORDERING",
    "outcome": "OUTCOME_ORDERING",
    "gross_R": "OUTCOME_ORDERING",
    "cost_R": "FRICTION",
    "net_R": "FRICTION",
}


def classify_field(field_name: str) -> str:
    return _FIELD_CATEGORY.get(field_name, "UNCLASSIFIED")


@dataclass(frozen=True)
class DivergenceReport:
    field_name: str
    category: str
    external_value: Any
    repo_value: Any
    difference: Optional[float]
    candidate_fingerprint: str
    dataset_fingerprint: str
    key: str  # the cycle/trade identity the divergence occurred on


def build_divergence_report(
    field_name: str, external_value: Any, repo_value: Any, *,
    candidate_fingerprint: str, dataset_fingerprint: str, key: str,
) -> DivergenceReport:
    difference: Optional[float] = None
    if isinstance(external_value, (int, float)) and isinstance(repo_value, (int, float)):
        difference = float(external_value) - float(repo_value)
    return DivergenceReport(
        field_name=field_name,
        category=classify_field(field_name),
        external_value=external_value,
        repo_value=repo_value,
        difference=difference,
        candidate_fingerprint=candidate_fingerprint,
        dataset_fingerprint=dataset_fingerprint,
        key=key,
    )
