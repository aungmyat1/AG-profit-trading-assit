"""Strategy-blind chronological partition freezing for the offline research factory.

Partition membership is derived only from the common, complete UTC-day index and source
lineage identifiers.  It never reads OHLC values, replay outcomes, signals, or P&L.
The result is immutable once written: a different policy, boundary, or source lineage
at the same manifest path is refused rather than silently overwriting a holdout.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Sequence, Tuple

from .ingestion import DerivedDataset, OhlcBar
from .quality import BARS_PER_UTC_DAY, complete_utc_days, utc_iso

PARTITION_POLICY_ID = "UTC_CHRONOLOGICAL_60_20_20_V1"
PARTITION_SCHEMA_VERSION = "AG_EDGE_DISCOVERY_PARTITION_MANIFEST_V1"
PARTITION_ORDER = ("DEV", "VALIDATION", "HOLDOUT")
PARTITION_RATIOS = {"DEV": 0.60, "VALIDATION": 0.20, "HOLDOUT": 0.20}


class PartitionFreezeError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}{': ' + detail if detail else ''}")


@dataclass(frozen=True)
class Partition:
    name: str
    days: Tuple[str, ...]
    start_utc: str
    end_utc: str
    sha256: str


@dataclass(frozen=True)
class PartitionManifest:
    policy_id: str
    cohort_id: str
    source_lineage: Mapping[str, Mapping[str, str]]
    partitions: Mapping[str, Partition]
    manifest_sha256: str
    path: Path | None = None


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _partition_payload(name: str, days: Sequence[str], source_lineage: Mapping[str, Mapping[str, str]]) -> Mapping[str, Any]:
    if not days:
        raise PartitionFreezeError("PARTITION_EMPTY", name)
    start = datetime.fromisoformat(days[0] + "T00:00:00+00:00")
    end = datetime.fromisoformat(days[-1] + "T00:00:00+00:00") + timedelta(days=1)
    identity = {
        "policy_id": PARTITION_POLICY_ID, "partition": name, "days": list(days),
        "source_lineage": source_lineage,
    }
    return {
        "name": name, "days": list(days), "start_utc": utc_iso(start), "end_utc": utc_iso(end),
        "sha256": hashlib.sha256(_canonical(identity)).hexdigest(),
    }


def _allocations(day_count: int) -> Tuple[int, int, int]:
    """Fixed Hamilton-free chronological allocation.  Remaining days belong to the
    future-blind HOLDOUT after fixed DEV and VALIDATION floor allocations."""
    dev = int(day_count * PARTITION_RATIOS["DEV"])
    validation = int(day_count * PARTITION_RATIOS["VALIDATION"])
    holdout = day_count - dev - validation
    return dev, validation, holdout


def build_partition_manifest(
    normalized_datasets: Mapping[str, DerivedDataset],
    cohort_id: str = "CRYPTO_CFD_UTC_COHORT_V1",
) -> PartitionManifest:
    """Create, but do not persist, a deterministic strategy-blind DEV/VALIDATION/
    HOLDOUT partition manifest over common complete days.
    """
    expected_symbols = ("BTCUSD", "ETHUSD")
    if set(normalized_datasets) != set(expected_symbols):
        raise PartitionFreezeError("PARTITION_SYMBOL_SET_MISMATCH", ",".join(sorted(normalized_datasets)))
    for symbol, dataset in normalized_datasets.items():
        if dataset.symbol != symbol or dataset.asset_class != "CRYPTO_CFD" or dataset.timeframe != "M5":
            raise PartitionFreezeError("PARTITION_DATASET_IDENTITY_MISMATCH", symbol)

    complete_by_symbol = {
        symbol: set(complete_utc_days(dataset.bars)) for symbol, dataset in normalized_datasets.items()
    }
    common_days = tuple(sorted(set.intersection(*complete_by_symbol.values())))
    dev_count, validation_count, holdout_count = _allocations(len(common_days))
    if not all((dev_count, validation_count, holdout_count)):
        raise PartitionFreezeError(
            "INSUFFICIENT_COMPLETE_DAYS_FOR_THREE_PARTITIONS",
            f"common_complete_days={len(common_days)} policy={PARTITION_POLICY_ID}",
        )

    source_lineage = {
        symbol: {
            "dataset_id": dataset.dataset_id,
            "parent_dataset_id": dataset.parent_dataset_id,
            "sha256": dataset.sha256,
        }
        for symbol, dataset in sorted(normalized_datasets.items())
    }
    groups = {
        "DEV": common_days[:dev_count],
        "VALIDATION": common_days[dev_count:dev_count + validation_count],
        "HOLDOUT": common_days[dev_count + validation_count:],
    }
    partitions = {
        name: Partition(
            name=name, days=tuple(days),
            start_utc=_partition_payload(name, days, source_lineage)["start_utc"],
            end_utc=_partition_payload(name, days, source_lineage)["end_utc"],
            sha256=_partition_payload(name, days, source_lineage)["sha256"],
        )
        for name, days in groups.items()
    }
    _assert_nonoverlap_and_chronology(partitions)
    doc = _manifest_document(cohort_id, source_lineage, partitions)
    return PartitionManifest(
        policy_id=PARTITION_POLICY_ID, cohort_id=cohort_id, source_lineage=source_lineage,
        partitions=partitions, manifest_sha256=hashlib.sha256(_canonical(doc)).hexdigest(), path=None,
    )


def _assert_nonoverlap_and_chronology(partitions: Mapping[str, Partition]) -> None:
    seen = set()
    prior_end = None
    for name in PARTITION_ORDER:
        part = partitions[name]
        days = set(part.days)
        if len(days) != len(part.days) or seen.intersection(days):
            raise PartitionFreezeError("PARTITION_OVERLAP", name)
        if tuple(sorted(part.days)) != part.days:
            raise PartitionFreezeError("PARTITION_NOT_CHRONOLOGICAL", name)
        if prior_end is not None and part.start_utc < prior_end:
            raise PartitionFreezeError("PARTITION_NOT_CHRONOLOGICAL", name)
        seen.update(days)
        prior_end = part.end_utc


def _manifest_document(
    cohort_id: str,
    source_lineage: Mapping[str, Mapping[str, str]],
    partitions: Mapping[str, Partition],
) -> Mapping[str, Any]:
    return {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "partition_policy_id": PARTITION_POLICY_ID,
        "cohort_id": cohort_id,
        "strategy_blind": True,
        "partition_input": "COMMON_COMPLETE_UTC_DAY_INDEX_AND_SOURCE_LINEAGE_ONLY",
        "source_lineage": source_lineage,
        "partitions": {
            name: {
                "start_utc": partitions[name].start_utc, "end_utc": partitions[name].end_utc,
                "days": list(partitions[name].days), "sha256": partitions[name].sha256,
            }
            for name in PARTITION_ORDER
        },
    }


def freeze_partition_manifest(manifest: PartitionManifest, path: Path) -> PartitionManifest:
    """Persist the partition freeze once.  Repeating an identical construction is safe;
    any byte/content difference at the same path is an immutability violation."""
    path = Path(path)
    document = _manifest_document(manifest.cohort_id, manifest.source_lineage, manifest.partitions)
    encoded = _canonical(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_bytes()
        if existing != encoded:
            raise PartitionFreezeError("PARTITION_MANIFEST_IMMUTABILITY_VIOLATION", str(path))
    else:
        path.write_bytes(encoded)
    return PartitionManifest(
        policy_id=manifest.policy_id, cohort_id=manifest.cohort_id,
        source_lineage=manifest.source_lineage, partitions=manifest.partitions,
        manifest_sha256=hashlib.sha256(encoded).hexdigest(), path=path,
    )


def slice_partition(dataset: DerivedDataset, partition: Partition) -> Tuple[OhlcBar, ...]:
    """Return a read-only-by-convention M5 slice of exactly the frozen UTC days.

    Membership is tested against the frozen *day set*, not against the partition's outer
    time bounds.  The bounds alone are not sufficient: a day can be complete for one symbol
    and gap-declared for the other, so it is excluded from the common-day partition for the
    whole cohort while that symbol's own bars still exist inside the same time range.  A
    range slice would hand those bars to the caller as if they were frozen observations,
    which is exactly the "never silently convert missing data into valid observations" rule.
    """
    frozen_days = frozenset(partition.days)
    if not frozen_days:
        raise PartitionFreezeError("PARTITION_EMPTY", partition.name)
    return tuple(bar for bar in dataset.bars if bar.time.date().isoformat() in frozen_days)


def partition_dataset_id(dataset: DerivedDataset, partition: Partition) -> str:
    """Stable dataset identity carried into the access ledger for a frozen partition."""
    return f"{dataset.dataset_id}:{partition.name}:{partition.sha256[:12]}"


__all__ = [
    "PARTITION_ORDER", "PARTITION_POLICY_ID", "PARTITION_SCHEMA_VERSION", "Partition",
    "PartitionFreezeError", "PartitionManifest", "build_partition_manifest",
    "freeze_partition_manifest", "partition_dataset_id", "slice_partition",
]
