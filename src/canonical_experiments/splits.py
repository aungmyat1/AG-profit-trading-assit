"""Chronological, immutable discovery/holdout split helpers."""
from __future__ import annotations

import hashlib
import json
from typing import Iterable, Mapping, Sequence

from .models import CanonicalOccurrence


def _hash_ids(ids: Sequence[str]) -> str:
    payload = json.dumps(list(ids), separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def chronological_split(
    occurrences: Iterable[CanonicalOccurrence], discovery_fraction: float = 0.70,
) -> Mapping[str, object]:
    if not 0 < discovery_fraction < 1:
        raise ValueError("discovery_fraction must be between 0 and 1")
    ordered = sorted(occurrences, key=lambda item: (item.entry_timestamp, item.occurrence_id))
    cut = int(len(ordered) * discovery_fraction)
    if ordered and cut == 0:
        cut = 1
    if ordered and cut == len(ordered):
        cut = len(ordered) - 1
    discovery_ids = [item.occurrence_id for item in ordered[:cut]]
    holdout_ids = [item.occurrence_id for item in ordered[cut:]]
    return {
        "schema_version": "CANONICAL_SPLIT_V1", "method": "CHRONOLOGICAL",
        "discovery_fraction": discovery_fraction, "discovery_ids": discovery_ids,
        "holdout_ids": holdout_ids, "discovery_hash": _hash_ids(discovery_ids),
        "holdout_hash": _hash_ids(holdout_ids),
    }