"""Read-only bridge from PR #32's exported raw Crypto-CFD Parquet format to R2's
``RawDataset`` contract.

This reuses PR #32's strategy-blind parser/validator rather than creating another MT5
or candle-format abstraction.  It does not call the PR #32 client/exporter, MT5, a
broker, or a network service: it accepts only already-exported local paths.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from scripts.research.market_dataset import sha256_file, validate

from .ingestion import DatasetIngestionError, OhlcBar, RawDataset, parse_utc_timestamp
from .research_eligibility import AUTHORITATIVE_RAW_SHA256

PR32_PROVENANCE_SCHEMA = "AG_CRYPTO_CFD_RAW_PROVENANCE_V1"


def _source_marks_synthetic(row: Mapping[str, Any]) -> bool:
    for field in ("synthetic", "is_synthetic", "filled", "is_filled", "interpolated", "is_interpolated"):
        value = row.get(field)
        if isinstance(value, str):
            if value.strip().lower() in {"1", "true", "yes", "y"}:
                return True
        elif bool(value):
            return True
    return False


def load_pr32_raw_dataset(
    raw_path: Path,
    provenance_path: Path,
    symbol: str,
    *,
    expected_hashes: Optional[Mapping[str, str]] = None,
) -> RawDataset:
    """Verify a PR #32 raw export and present it to the R2 eligibility/partition
    boundary. Unknown gaps are preserved in the resulting bars for quarantine; they are
    never blocked, filled, or marked expected here.
    """
    raw_path, provenance_path = Path(raw_path), Path(provenance_path)
    if symbol not in AUTHORITATIVE_RAW_SHA256:
        raise DatasetIngestionError("SYMBOL_NOT_SUPPORTED", symbol)
    if not raw_path.is_file() or not provenance_path.is_file():
        raise DatasetIngestionError("RAW_DATASET_OR_PROVENANCE_MISSING")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetIngestionError("PROVENANCE_MANIFEST_INVALID", str(exc)) from exc
    if provenance.get("schema") != PR32_PROVENANCE_SCHEMA:
        raise DatasetIngestionError("PROVENANCE_SCHEMA_MISMATCH", str(provenance.get("schema")))
    entries = [entry for entry in provenance.get("datasets", [])
               if isinstance(entry, Mapping) and entry.get("canonical_symbol") == symbol]
    if len(entries) != 1:
        raise DatasetIngestionError("PROVENANCE_ENTRY_NOT_UNIQUE", symbol)
    entry = entries[0]
    if entry.get("asset_class") != "CRYPTO_CFD" or entry.get("timeframe") != "M5":
        raise DatasetIngestionError("ASSET_CLASS_OR_TIMEFRAME_MISMATCH")
    declared_path = Path(str(entry.get("file", ""))).name
    if declared_path and declared_path != raw_path.name:
        raise DatasetIngestionError("PROVENANCE_FILENAME_MISMATCH", raw_path.name)
    actual_hash = sha256_file(raw_path)
    if entry.get("sha256") != actual_hash:
        raise DatasetIngestionError("PROVENANCE_HASH_MISMATCH", symbol)
    authoritative = dict(AUTHORITATIVE_RAW_SHA256 if expected_hashes is None else expected_hashes)
    if authoritative.get(symbol) != actual_hash:
        raise DatasetIngestionError("AUTHORITATIVE_RAW_HASH_MISMATCH", symbol)

    try:
        import pandas as pd
        frame = pd.read_parquet(raw_path, engine="pyarrow")
    except ImportError as exc:
        raise DatasetIngestionError("PARQUET_READER_UNAVAILABLE") from exc
    except Exception as exc:
        raise DatasetIngestionError("PARQUET_READ_FAILURE", str(exc)) from exc
    # PR32's validate() is the existing strategy-blind schema/quality abstraction.
    # Its gap result is retained as evidence, not used to relax eligibility.
    qa = validate(frame)
    required = {"timestamp_utc", "open", "high", "low", "close"}
    if not required.issubset(frame.columns):
        raise DatasetIngestionError("SCHEMA_MISMATCH", ",".join(sorted(required - set(frame.columns))))
    if int(entry.get("row_count", -1)) != len(frame):
        raise DatasetIngestionError("ROW_COUNT_MISMATCH")
    bars = tuple(OhlcBar(
        time=parse_utc_timestamp(row["timestamp_utc"]), open=float(row["open"]), high=float(row["high"]),
        low=float(row["low"]), close=float(row["close"]),
        volume=(float(row["tick_volume"]) if "tick_volume" in row and row["tick_volume"] is not None else None),
        synthetic=_source_marks_synthetic(row),
    ) for row in frame.to_dict(orient="records"))
    coverage = {
        "start_utc": entry.get("first_timestamp_utc"), "end_utc": entry.get("last_timestamp_utc"),
    }
    return RawDataset(
        dataset_id=str(entry.get("dataset_id")), source_path=raw_path, sha256=actual_hash,
        symbol=symbol, asset_class="CRYPTO_CFD", timeframe="M5", broker=entry.get("broker"),
        environment=entry.get("environment"), timestamp_normalization={
            "normalized_timezone": "UTC", "normalization_complete": True,
            "timestamp_convention": "OPEN_TIME", "source_timestamp_semantics": entry.get("source_timestamp_semantics"),
        }, schema_columns=tuple(str(column) for column in frame.columns),
        declared_row_count=len(frame), declared_coverage=coverage, bars=bars,
        expected_gap_intervals=(),
    )


__all__ = ["PR32_PROVENANCE_SCHEMA", "load_pr32_raw_dataset"]
