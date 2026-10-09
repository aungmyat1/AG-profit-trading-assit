# Immutable partition manifests

`run_edge_discovery_offline.py` writes a manifest here only after raw Crypto-CFD
provenance, quality, and pre-outcome coverage gates pass. It uses
`UTC_CHRONOLOGICAL_60_20_20_V1`: contiguous common complete UTC days, in chronological
DEV → VALIDATION → HOLDOUT order, with no overlap or shuffle.

The manifest is strategy-blind: its hashes bind only date membership and source-lineage
IDs/SHA-256 values, never OHLC values, signals, trades, or P&L. A path that already
exists must be byte-identical on re-run; any changed content raises
`PARTITION_MANIFEST_IMMUTABILITY_VIOLATION` instead of overwriting the original.

No real Crypto-CFD source files are present in this repository at R2 publication, so no
actual partition manifest is committed.
