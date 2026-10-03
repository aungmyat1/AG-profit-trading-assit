"""Offline, fail-closed ingestion for immutable Crypto-CFD raw M5 exports.

This module deliberately has no MT5, broker, exchange, or network dependency.  It
accepts only local paths plus the exporter-side provenance manifest and never writes to
a raw input path.  Parquet decoding is loaded lazily so provenance-only checks and unit
tests remain portable when the optional Parquet reader is not installed.

Exporter manifest contract (``AG_CRYPTO_CFD_RAW_DATA_PROVENANCE_V1``)::

    {
      "schema_version": "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE_V1",
      "datasets": [{
        "dataset_id": "...", "filename": "BTCUSD_M5_RAW.parquet",
        "sha256": "<64 lowercase hex>", "symbol": "BTCUSD",
        "asset_class": "CRYPTO_CFD", "timeframe": "M5",
        "broker": "VT Markets", "environment": "DEMO",
        "timestamp_normalization": {
          "source_timezone": "UTC", "normalized_timezone": "UTC",
          "timestamp_column": "timestamp", "timestamp_convention": "OPEN_TIME",
          "normalization_complete": true
        },
        "schema": {"columns": ["timestamp", "open", "high", "low", "close"]},
        "row_count": 123, "coverage": {"start_utc": "...Z", "end_utc": "...Z"}
      }]
    }

``broker`` and ``environment`` may be null when unavailable, but their presence is
required so missing provenance cannot silently become an implied claim.  ``time`` is
also accepted as the declared timestamp column for exports that preserve MT5 naming.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence, Tuple

PROVENANCE_SCHEMA_VERSION = "AG_CRYPTO_CFD_RAW_DATA_PROVENANCE_V1"
RAW_TIMEFRAME = "M5"
CFD_ASSET_CLASS = "CRYPTO_CFD"
EXPECTED_RAW_FILENAMES = {
    "BTCUSD": "BTCUSD_M5_RAW.parquet",
    "ETHUSD": "ETHUSD_M5_RAW.parquet",
}
REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close")


class DatasetIngestionError(ValueError):
    """A local dataset violated the immutable ingestion contract."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}{': ' + detail if detail else ''}")


@dataclass(frozen=True)
class OhlcBar:
    """One source M5 bar. ``time`` is always a timezone-aware UTC open timestamp."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    # Raw exporter flags are retained only to quarantine a source-marked synthetic,
    # filled, or interpolated bar. They never alter any price or timestamp.
    synthetic: bool = False


@dataclass(frozen=True)
class RawDataset:
    """Verified immutable source artifact.  ``source_path`` is never opened for write."""

    dataset_id: str
    source_path: Path
    sha256: str
    symbol: str
    asset_class: str
    timeframe: str
    broker: Any
    environment: Any
    timestamp_normalization: Mapping[str, Any]
    schema_columns: Tuple[str, ...]
    declared_row_count: int
    declared_coverage: Mapping[str, Any]
    bars: Tuple[OhlcBar, ...]
    expected_gap_intervals: Tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class DerivedDataset:
    """A derived artifact with independent lineage and an immutable content SHA-256."""

    dataset_id: str
    parent_dataset_id: str
    transform_id: str
    sha256: str
    symbol: str
    asset_class: str
    timeframe: str
    bars: Tuple[OhlcBar, ...]
    artifact_path: Optional[Path] = None


def sha256_of_file(path: Path) -> str:
    """Hash bytes directly from disk; no in-memory or metadata shortcut is accepted."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _hex64(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _utc_string(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc_timestamp(value: Any) -> datetime:
    """Accept an aware datetime/ISO timestamp and normalize it to UTC, never guessing a
    timezone for a naive timestamp."""
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise DatasetIngestionError("TIMESTAMP_PARSE_FAILURE", repr(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DatasetIngestionError("TIMESTAMP_NOT_TIMEZONE_AWARE", repr(value))
    return parsed.astimezone(timezone.utc)


def _load_manifest(path: Path) -> Mapping[str, Any]:
    if not path.is_file():
        raise DatasetIngestionError("PROVENANCE_MANIFEST_MISSING", str(path))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetIngestionError("PROVENANCE_MANIFEST_INVALID", str(exc)) from exc
    if doc.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        raise DatasetIngestionError("PROVENANCE_SCHEMA_MISMATCH", str(doc.get("schema_version")))
    if not isinstance(doc.get("datasets"), list):
        raise DatasetIngestionError("PROVENANCE_DATASETS_MISSING")
    return doc


def _entry_for_path(manifest: Mapping[str, Any], raw_path: Path) -> Mapping[str, Any]:
    matches = [entry for entry in manifest["datasets"]
               if isinstance(entry, Mapping) and entry.get("filename") == raw_path.name]
    if len(matches) != 1:
        raise DatasetIngestionError("PROVENANCE_ENTRY_NOT_UNIQUE", raw_path.name)
    return matches[0]


def _validate_entry(entry: Mapping[str, Any], raw_path: Path, expected_symbol: str) -> None:
    required = ("dataset_id", "filename", "sha256", "symbol", "asset_class", "timeframe",
                "broker", "environment", "timestamp_normalization", "schema", "row_count",
                "coverage")
    missing = [key for key in required if key not in entry]
    if missing:
        raise DatasetIngestionError("PROVENANCE_FIELD_MISSING", ",".join(missing))
    if not isinstance(entry["dataset_id"], str) or not entry["dataset_id"].strip():
        raise DatasetIngestionError("DATASET_ID_INVALID")
    if not _hex64(entry["sha256"]):
        raise DatasetIngestionError("PROVENANCE_SHA256_INVALID")
    if entry["symbol"] != expected_symbol:
        if str(entry["symbol"]).endswith("USDT"):
            raise DatasetIngestionError("CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN",
                                        f"{entry['symbol']} != {expected_symbol}")
        raise DatasetIngestionError("SYMBOL_MISMATCH", f"{entry['symbol']} != {expected_symbol}")
    if entry["asset_class"] != CFD_ASSET_CLASS:
        raise DatasetIngestionError("ASSET_CLASS_MISMATCH",
                                    f"{entry['asset_class']} != {CFD_ASSET_CLASS}")
    if entry["timeframe"] != RAW_TIMEFRAME:
        raise DatasetIngestionError("TIMEFRAME_MISMATCH", str(entry["timeframe"]))
    metadata = entry["timestamp_normalization"]
    if not isinstance(metadata, Mapping):
        raise DatasetIngestionError("TIMESTAMP_NORMALIZATION_METADATA_MISSING")
    required_metadata = ("source_timezone", "normalized_timezone", "timestamp_column",
                         "timestamp_convention", "normalization_complete")
    absent = [key for key in required_metadata if key not in metadata]
    if absent:
        raise DatasetIngestionError("TIMESTAMP_NORMALIZATION_FIELD_MISSING", ",".join(absent))
    if metadata["normalized_timezone"] != "UTC" or not metadata["normalization_complete"]:
        raise DatasetIngestionError("TIMESTAMP_NORMALIZATION_INCOMPLETE")
    if metadata["timestamp_column"] not in ("timestamp", "time"):
        raise DatasetIngestionError("TIMESTAMP_COLUMN_UNSUPPORTED", str(metadata["timestamp_column"]))
    if metadata["timestamp_convention"] != "OPEN_TIME":
        raise DatasetIngestionError("TIMESTAMP_CONVENTION_MISMATCH",
                                    str(metadata["timestamp_convention"]))
    if not isinstance(entry["row_count"], int) or entry["row_count"] < 0:
        raise DatasetIngestionError("PROVENANCE_ROW_COUNT_INVALID")
    coverage = entry["coverage"]
    if not isinstance(coverage, Mapping) or set(("start_utc", "end_utc")) - set(coverage):
        raise DatasetIngestionError("PROVENANCE_COVERAGE_INVALID")
    # Validate formatting and awareness now rather than relying on textual equality later.
    parse_utc_timestamp(coverage["start_utc"])
    parse_utc_timestamp(coverage["end_utc"])


def _schema_columns(schema: Any) -> Tuple[str, ...]:
    columns = schema.get("columns") if isinstance(schema, Mapping) else schema
    if not isinstance(columns, list) or not all(isinstance(c, str) for c in columns):
        raise DatasetIngestionError("PROVENANCE_SCHEMA_INVALID")
    if len(columns) != len(set(columns)):
        raise DatasetIngestionError("PROVENANCE_SCHEMA_DUPLICATE_COLUMN")
    return tuple(columns)


def _default_parquet_loader(path: Path) -> Sequence[Mapping[str, Any]]:
    """Optional local-only Parquet reader.  No external data or runtime integration is
    attempted if pandas/pyarrow is absent."""
    try:
        import pandas as pd  # type: ignore[import-not-found]
    except ImportError as exc:
        raise DatasetIngestionError("PARQUET_READER_UNAVAILABLE", "install pandas + pyarrow") from exc
    try:
        frame = pd.read_parquet(path, engine="pyarrow")
    except Exception as exc:  # parser failures must block rather than become partial data
        raise DatasetIngestionError("PARQUET_READ_FAILURE", str(exc)) from exc
    return tuple(frame.to_dict(orient="records"))


def _as_number(value: Any, field: str, row_number: int) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DatasetIngestionError("SCHEMA_VALUE_INVALID", f"row={row_number} field={field}") from exc
    if not math.isfinite(number):
        raise DatasetIngestionError("SCHEMA_VALUE_NONFINITE", f"row={row_number} field={field}")
    return number


def _source_marks_synthetic(row: Mapping[str, Any]) -> bool:
    """Preserve a source-side synthetic/fill/interpolation marker if one exists.
    Missing markers do not manufacture a flag; true values are always quarantined."""
    for field in ("synthetic", "is_synthetic", "filled", "is_filled", "interpolated", "is_interpolated"):
        value = row.get(field)
        if isinstance(value, str):
            if value.strip().lower() in {"1", "true", "yes", "y"}:
                return True
        elif bool(value):
            return True
    return False


def ingest_raw_m5(
    raw_path: Path,
    provenance_path: Path,
    expected_symbol: str,
    frame_loader: Optional[Callable[[Path], Sequence[Mapping[str, Any]]]] = None,
) -> RawDataset:
    """Verify and load exactly one immutable BTCUSD/ETHUSD CFD M5 source artifact.

    ``frame_loader`` is a test seam for local deterministic fixtures.  Production calls
    leave it unset and use the local Parquet reader above.  The raw path is only read;
    this function never normalizes or repairs the source in place.
    """
    raw_path = Path(raw_path)
    provenance_path = Path(provenance_path)
    if expected_symbol not in EXPECTED_RAW_FILENAMES:
        raise DatasetIngestionError("SYMBOL_NOT_SUPPORTED", expected_symbol)
    if raw_path.name != EXPECTED_RAW_FILENAMES[expected_symbol]:
        raise DatasetIngestionError("RAW_FILENAME_IDENTITY_MISMATCH",
                                    f"expected {EXPECTED_RAW_FILENAMES[expected_symbol]}, got {raw_path.name}")
    if not raw_path.is_file():
        raise DatasetIngestionError("RAW_DATASET_MISSING", str(raw_path))

    manifest = _load_manifest(provenance_path)
    entry = _entry_for_path(manifest, raw_path)
    _validate_entry(entry, raw_path, expected_symbol)
    actual_sha = sha256_of_file(raw_path)
    if actual_sha != entry["sha256"]:
        raise DatasetIngestionError("PROVENANCE_HASH_MISMATCH",
                                    f"expected={entry['sha256']} actual={actual_sha}")

    columns = _schema_columns(entry["schema"])
    timestamp_column = entry["timestamp_normalization"]["timestamp_column"]
    required_columns = {timestamp_column, *REQUIRED_PRICE_COLUMNS}
    if not required_columns.issubset(columns):
        raise DatasetIngestionError("PROVENANCE_SCHEMA_REQUIRED_COLUMN_MISSING",
                                    ",".join(sorted(required_columns - set(columns))))

    rows = tuple((frame_loader or _default_parquet_loader)(raw_path))
    if len(rows) != entry["row_count"]:
        raise DatasetIngestionError("ROW_COUNT_MISMATCH", f"manifest={entry['row_count']} actual={len(rows)}")
    actual_columns = set().union(*(set(row) for row in rows)) if rows else set(columns)
    if actual_columns != set(columns):
        raise DatasetIngestionError("SCHEMA_MISMATCH",
                                    f"manifest={sorted(columns)} actual={sorted(actual_columns)}")

    bars = []
    for row_number, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise DatasetIngestionError("SCHEMA_ROW_NOT_MAPPING", str(row_number))
        try:
            at = parse_utc_timestamp(row[timestamp_column])
        except KeyError as exc:
            raise DatasetIngestionError("SCHEMA_TIMESTAMP_MISSING", str(row_number)) from exc
        bars.append(OhlcBar(
            time=at,
            open=_as_number(row.get("open"), "open", row_number),
            high=_as_number(row.get("high"), "high", row_number),
            low=_as_number(row.get("low"), "low", row_number),
            close=_as_number(row.get("close"), "close", row_number),
            volume=(None if "volume" not in row or row["volume"] is None
                    else _as_number(row["volume"], "volume", row_number)),
            synthetic=_source_marks_synthetic(row),
        ))

    if bars:
        declared_start = parse_utc_timestamp(entry["coverage"]["start_utc"])
        declared_end = parse_utc_timestamp(entry["coverage"]["end_utc"])
        if bars[0].time != declared_start or bars[-1].time != declared_end:
            raise DatasetIngestionError("COVERAGE_MISMATCH",
                                        f"manifest={_utc_string(declared_start)}..{_utc_string(declared_end)} "
                                        f"actual={_utc_string(bars[0].time)}..{_utc_string(bars[-1].time)}")
    elif entry["coverage"]["start_utc"] != entry["coverage"]["end_utc"]:
        raise DatasetIngestionError("EMPTY_DATASET_COVERAGE_MISMATCH")

    expected_gaps = entry.get("expected_gap_intervals", ())
    if not isinstance(expected_gaps, (list, tuple)):
        raise DatasetIngestionError("EXPECTED_GAP_INTERVALS_INVALID")
    return RawDataset(
        dataset_id=entry["dataset_id"], source_path=raw_path, sha256=actual_sha,
        symbol=expected_symbol, asset_class=entry["asset_class"], timeframe=entry["timeframe"],
        broker=entry["broker"], environment=entry["environment"],
        timestamp_normalization=dict(entry["timestamp_normalization"]), schema_columns=columns,
        declared_row_count=entry["row_count"], declared_coverage=dict(entry["coverage"]),
        bars=tuple(bars), expected_gap_intervals=tuple(dict(x) for x in expected_gaps),
    )


def _bar_payload(bar: OhlcBar) -> Mapping[str, Any]:
    return {
        "timestamp": _utc_string(bar.time), "open": bar.open, "high": bar.high,
        "low": bar.low, "close": bar.close, "volume": bar.volume,
        "synthetic": bar.synthetic,
    }


def build_derived_dataset(
    parent: RawDataset | DerivedDataset,
    transform_id: str,
    timeframe: str,
    bars: Iterable[OhlcBar],
    artifact_root: Optional[Path] = None,
) -> DerivedDataset:
    """Build a separate immutable derived artifact.  Its payload is a canonical JSON
    file when an artifact root is supplied, keeping the layer portable even in an
    offline environment without a Parquet engine.  The raw Parquet remains untouched.
    """
    frozen_bars = tuple(bars)
    identity_seed = _canonical_json({
        "parent_dataset_id": parent.dataset_id, "parent_sha256": parent.sha256,
        "transform_id": transform_id, "timeframe": timeframe,
    })
    dataset_id = f"{timeframe}_{hashlib.sha256(identity_seed).hexdigest()[:16]}"
    payload = {
        "schema_version": "AG_EDGE_DISCOVERY_DERIVED_DATASET_V1",
        "dataset_id": dataset_id, "parent_dataset_id": parent.dataset_id,
        "transform_id": transform_id, "symbol": parent.symbol,
        "asset_class": parent.asset_class, "timeframe": timeframe,
        "bars": [_bar_payload(bar) for bar in frozen_bars],
    }
    encoded = _canonical_json(payload)
    artifact_path: Optional[Path] = None
    if artifact_root is not None:
        artifact_path = Path(artifact_root) / f"{dataset_id}.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        # An existing artifact must be byte-identical; never rewrite a derived record.
        if artifact_path.exists() and artifact_path.read_bytes() != encoded:
            raise DatasetIngestionError("DERIVED_ARTIFACT_IMMUTABILITY_VIOLATION", str(artifact_path))
        if not artifact_path.exists():
            artifact_path.write_bytes(encoded)
        digest = sha256_of_file(artifact_path)
    else:
        digest = hashlib.sha256(encoded).hexdigest()
    return DerivedDataset(
        dataset_id=dataset_id, parent_dataset_id=parent.dataset_id, transform_id=transform_id,
        sha256=digest, symbol=parent.symbol, asset_class=parent.asset_class,
        timeframe=timeframe, bars=frozen_bars, artifact_path=artifact_path,
    )


__all__ = [
    "CFD_ASSET_CLASS", "DerivedDataset", "DatasetIngestionError", "EXPECTED_RAW_FILENAMES",
    "OhlcBar", "PROVENANCE_SCHEMA_VERSION", "RAW_TIMEFRAME", "RawDataset",
    "build_derived_dataset", "ingest_raw_m5", "parse_utc_timestamp", "sha256_of_file",
]
