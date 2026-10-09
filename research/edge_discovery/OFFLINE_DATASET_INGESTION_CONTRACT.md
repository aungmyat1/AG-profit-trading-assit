# Offline Crypto-CFD Dataset Ingestion Contract V1

**Status:** implemented, local-only, research-only. This is an input contract for the
Local Codex/free exporter; it is not an MT5 retrieval workflow and does not authorize
broker access, strategy changes, risk changes, or execution.

## Required local input bundle

```text
<export-dir>/BTCUSD_M5_RAW.parquet
<export-dir>/ETHUSD_M5_RAW.parquet
<export-dir>/AG_CRYPTO_CFD_RAW_DATA_PROVENANCE.json
```

Raw Parquet files are immutable source artifacts. The factory opens them only for reads
and checks their byte SHA-256 before decoding. It never fills, sorts, deduplicates, or
rewrites them. A changed capture is a new source artifact, not an in-place update.

## Provenance manifest schema

The top-level schema must be `AG_CRYPTO_CFD_RAW_DATA_PROVENANCE_V1`; it must contain
one and only one `datasets` entry per required filename. Each entry requires:

```json
{
  "dataset_id": "RAW_BTCUSD_<export-id>",
  "filename": "BTCUSD_M5_RAW.parquet",
  "sha256": "64 lowercase hexadecimal characters",
  "symbol": "BTCUSD",
  "asset_class": "CRYPTO_CFD",
  "timeframe": "M5",
  "broker": "VT Markets or null",
  "environment": "DEMO/LIVE/UNKNOWN or null",
  "timestamp_normalization": {
    "source_timezone": "UTC",
    "normalized_timezone": "UTC",
    "timestamp_column": "timestamp",
    "timestamp_convention": "OPEN_TIME",
    "normalization_complete": true
  },
  "schema": {"columns": ["timestamp", "open", "high", "low", "close", "volume"]},
  "row_count": 0,
  "coverage": {"start_utc": "2026-01-01T00:00:00Z", "end_utc": "2026-01-01T00:00:00Z"}
}
```

`time` may replace `timestamp` only if it is declared as `timestamp_column`. All source
timestamps must be timezone-aware; naive timestamps are rejected. `broker` and
environment fields must be present even when unavailable (`null`) so absence cannot be
mistaken for an assertion. The declared schema must exactly match decoded columns and
coverage must exactly match the first/last source bar.

## Hard identity rules

| Expected file | Required identity |
|---|---|
| `BTCUSD_M5_RAW.parquet` | `symbol=BTCUSD`, `asset_class=CRYPTO_CFD`, `timeframe=M5` |
| `ETHUSD_M5_RAW.parquet` | `symbol=ETHUSD`, `asset_class=CRYPTO_CFD`, `timeframe=M5` |

Near symbols and venues do not qualify. In particular, USD-quoted CFD files cannot be
substituted with similarly named perpetual files. The factory reports
`CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN`, `SYMBOL_MISMATCH`, or
`ASSET_CLASS_MISMATCH` and stops; it does not convert or relabel data.

## Derived lineage

Only after provenance and quality pass, the factory creates distinct local artifacts:

```text
RAW_M5 (raw dataset_id, raw file SHA-256)
  -> NORMALIZED_M5 (UTC_NORMALIZATION_V1)
  -> M15 / H1 / D1 (UTC_RESAMPLE_*_V1)
  -> chronological partitions
  -> CANDIDATE_RUN
```

Every derived artifact records a new `dataset_id`, `parent_dataset_id`, `transform_id`,
and independent SHA-256. The portable derived representation is canonical JSON so the
factory remains offline and testable without a broker/runtime. It never changes raw
Parquet bytes.

## Execute locally

```bash
python scripts/run_edge_discovery_offline.py --input-dir /path/to/export-dir
```

Missing files return `BLOCKED_DATASET_UNAVAILABLE`; provenance/hash failures return
`BLOCKED_PROVENANCE`; quality failures return `BLOCKED_DATA_QUALITY`. No live fallback,
market download, or broker request is attempted.
