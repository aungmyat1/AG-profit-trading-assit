"""External-candidate vs. canonical-repository-replay SIGNAL parity (mission
section 14). Compares decision-level facts (direction/state/geometry), not yet
resolved trade outcomes -- see trade_comparator.py for that.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from ._common import PRICE_TOLERANCE, ComparisonResult, compare_records

SIGNAL_COMPARE_FIELDS = (
    "setup_type", "direction", "entry", "stop_loss", "take_profit", "expiry", "state",
)
SIGNAL_NUMERIC_FIELDS = ("entry", "stop_loss", "take_profit")


def compare_signals(
    external_signals: Sequence[Mapping[str, Any]],
    repo_signals: Sequence[Mapping[str, Any]],
    *,
    key_field: str = "cycle",
    candidate_fingerprint: str,
    dataset_fingerprint: str,
) -> ComparisonResult:
    return compare_records(
        external_signals, repo_signals,
        key_field=key_field,
        compare_fields=SIGNAL_COMPARE_FIELDS,
        numeric_fields=SIGNAL_NUMERIC_FIELDS,
        candidate_fingerprint=candidate_fingerprint,
        dataset_fingerprint=dataset_fingerprint,
    )
