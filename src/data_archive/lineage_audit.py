"""Raw dataset lineage classification -- mission P1.

Deliberately narrow: this module only classifies the RELATIONSHIP between two
already-existing dataset manifests. It never creates a dataset, never assigns
a data role, and never treats two different dataset/population IDs as proof
of independence -- the mission explicitly forbids inferring independence from
ID difference alone, since a derived or overlapping sample can easily be
re-labelled with a new ID.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

INDEPENDENT_RAW_SAMPLE = "INDEPENDENT_RAW_SAMPLE"
OVERLAPPING_RAW_SAMPLE = "OVERLAPPING_RAW_SAMPLE"
DERIVED_FROM_PRIOR_DATA = "DERIVED_FROM_PRIOR_DATA"
SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS = "SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class DatasetLineageRef:
    dataset_id: str
    symbol: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    # timeframe -> sha256 of the raw source file, e.g. {"H1": "93d27d8c..."}
    source_file_hashes: Dict[str, str] = field(default_factory=dict)
    parent_dataset: Optional[str] = None
    strategy_version_used: Optional[str] = None


def _ranges_overlap(a: DatasetLineageRef, b: DatasetLineageRef) -> bool:
    if a.start_date is None or a.end_date is None or b.start_date is None or b.end_date is None:
        return False
    return a.start_date <= b.end_date and b.start_date <= a.end_date


def _shares_any_hash(a: DatasetLineageRef, b: DatasetLineageRef) -> bool:
    return bool(set(a.source_file_hashes.values()) & set(b.source_file_hashes.values()))


# How close two non-overlapping date ranges on the same symbol must be to still
# count as "the same market interval" for SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS
# (e.g. immediately adjacent pre-/post-remediation windows). Anything wider than
# this is a genuinely separate period, not a semantic split of one interval.
_SAME_INTERVAL_MAX_GAP_DAYS = 14


def _ranges_close(a: DatasetLineageRef, b: DatasetLineageRef, max_gap_days: int) -> bool:
    if a.start_date is None or a.end_date is None or b.start_date is None or b.end_date is None:
        return False
    if _ranges_overlap(a, b):
        return True
    gap = (b.start_date - a.end_date).days if a.end_date <= b.start_date else (a.start_date - b.end_date).days
    return 0 <= gap <= max_gap_days


def classify_lineage(a: DatasetLineageRef, b: DatasetLineageRef) -> str:
    """Classify the relationship of `b` to `a`. Symmetric in the sense that
    swapping arguments yields the same classification (parent direction is
    read from whichever side names the other as `parent_dataset`)."""
    if a.parent_dataset == b.dataset_id or b.parent_dataset == a.dataset_id:
        return DERIVED_FROM_PRIOR_DATA

    if _shares_any_hash(a, b):
        return OVERLAPPING_RAW_SAMPLE

    if a.symbol is not None and a.symbol == b.symbol and _ranges_overlap(a, b):
        return OVERLAPPING_RAW_SAMPLE

    if (
        a.symbol is not None
        and a.symbol == b.symbol
        and a.strategy_version_used is not None
        and b.strategy_version_used is not None
        and a.strategy_version_used != b.strategy_version_used
        and _ranges_close(a, b, _SAME_INTERVAL_MAX_GAP_DAYS)
    ):
        return SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS

    if a.symbol is None or b.symbol is None or a.start_date is None or b.start_date is None:
        return UNKNOWN

    return INDEPENDENT_RAW_SAMPLE
