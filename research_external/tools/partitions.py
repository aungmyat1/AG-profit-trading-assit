"""Chronological TRAIN/VALIDATION/FINAL_HOLDOUT partitioning + the holdout-access
guard (mission sections 15-16). Partitions are computed once, frozen (recorded to
disk with a hash), and never reshuffled -- no randomness anywhere in this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

from post_asian_pilot.fingerprint import fingerprint

ROLE_TRAIN = "TRAIN"
ROLE_VALIDATION = "VALIDATION"
ROLE_FINAL_HOLDOUT = "FINAL_HOLDOUT"


class HoldoutAccessDeniedError(RuntimeError):
    """Raised whenever baseline/research code attempts to read a partition whose
    role is FINAL_HOLDOUT. Fail-closed by construction -- there is no bypass
    parameter."""


@dataclass(frozen=True)
class Partition:
    partition_id: str
    role: str
    parent_dataset_sha256: str
    start: str
    end: str
    rows: int
    partition_sha256: str
    locked: bool
    candles: tuple  # kept off the frozen dataclass's hash/repr concerns intentionally simple


def _partition_sha256(role: str, start: str, end: str, candles: Sequence[dict]) -> str:
    return fingerprint({
        "role": role, "start": start, "end": end,
        "row_count": len(candles),
        "first": candles[0]["time"] if candles else None,
        "last": candles[-1]["time"] if candles else None,
    })


def freeze_partitions(
    candles: Sequence[dict], parent_dataset_sha256: str, boundaries: Dict[str, "tuple[str, str]"],
) -> Dict[str, Partition]:
    """`boundaries` maps role -> (start_inclusive_date, end_exclusive_date) as
    'YYYY-MM-DD' strings. Partitions are built by simple chronological date-string
    comparison against each candle's own UTC date prefix -- never shuffled."""
    partitions: Dict[str, Partition] = {}
    for role, (start, end) in boundaries.items():
        rows = [c for c in candles if start <= str(c["time"])[:10] < end]
        partitions[role] = Partition(
            partition_id=f"{role}_{start}_{end}",
            role=role,
            parent_dataset_sha256=parent_dataset_sha256,
            start=start, end=end, rows=len(rows),
            partition_sha256=_partition_sha256(role, start, end, rows),
            locked=(role == ROLE_FINAL_HOLDOUT),
            candles=tuple(rows),
        )
    return partitions


def require_not_holdout(partition: Partition) -> List[dict]:
    """The one and only way baseline/research code may read a partition's candles.
    Raises HoldoutAccessDeniedError for FINAL_HOLDOUT, unconditionally -- no override
    flag exists anywhere in this function's signature."""
    if partition.role == ROLE_FINAL_HOLDOUT or partition.locked:
        raise HoldoutAccessDeniedError(
            f"HOLDOUT_ACCESS_DENIED: partition {partition.partition_id!r} is locked "
            "and may not be read by this task."
        )
    return list(partition.candles)
