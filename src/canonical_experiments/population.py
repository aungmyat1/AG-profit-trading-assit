"""Write-once JSON population storage and provenance hashes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Sequence

from .models import CanonicalOccurrence, CandleSnapshot


SCHEMA_VERSION = "CANONICAL_POPULATION_V1"


def population_hash(occurrences: Sequence[CanonicalOccurrence]) -> str:
    ids = sorted(item.occurrence_id for item in occurrences)
    return hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode("utf-8")).hexdigest()


def write_population(path: str | Path, occurrences: Iterable[CanonicalOccurrence], *, strategy_id: str, strategy_version: str, exchange: str, symbol: str) -> str:
    target = Path(path)
    if target.exists():
        raise FileExistsError(f"IMMUTABLE_POPULATION_EXISTS: {target}")
    records = tuple(occurrences)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "exchange": exchange,
        "symbol": symbol,
        "occurrence_count": len(records),
        "population_hash": population_hash(records),
        "occurrences": [record.to_dict() for record in records],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(target)


def load_population(path: str | Path) -> tuple[dict, tuple[CanonicalOccurrence, ...]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("UNSUPPORTED_POPULATION_SCHEMA")
    occurrences = tuple(_occurrence_from_dict(item) for item in payload.get("occurrences", ()))
    if payload.get("occurrence_count") != len(occurrences):
        raise ValueError("POPULATION_COUNT_MISMATCH")
    if payload.get("population_hash") != population_hash(occurrences):
        raise ValueError("POPULATION_HASH_MISMATCH")
    return payload, occurrences


def _occurrence_from_dict(value: dict) -> CanonicalOccurrence:
    return CanonicalOccurrence(
        **{**value, "m1_path": tuple(CandleSnapshot(**candle) for candle in value.get("m1_path", ()))},
    )