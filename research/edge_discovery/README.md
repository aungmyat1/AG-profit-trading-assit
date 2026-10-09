# AG Edge Discovery — Offline Research Factory

**R2 status:** `UNIT_TESTED`, `BLOCKED_DATASET_UNAVAILABLE` for the real C001 run.
This directory is research-only. It provides no proposal, risk, execution, broker, or
market-download authority.

## Local-only flow

```text
immutable raw M5 files
  -> provenance/hash verification
  -> deterministic quality gate
  -> lineaged UTC NORMALIZED_M5 / M15 / H1 / D1 artifacts
  -> strategy-blind chronological partition freeze
  -> DEV-only Candidate Factory C001 fast screen
  -> FAIL / INCONCLUSIVE / PASS_FAST_SCREEN
  -> FROZEN_FOR_VERIFICATION (never EDGE_VERIFIED)
```

Run only after a Local Codex/free exporter has supplied the three input files described
in [OFFLINE_DATASET_INGESTION_CONTRACT.md](OFFLINE_DATASET_INGESTION_CONTRACT.md):

```bash
python scripts/run_edge_discovery_offline.py --input-dir /path/to/export-dir
```

The runner needs local files only; it imports no MT5/broker runtime and makes no live
market call. Missing sources report `BLOCKED_DATASET_UNAVAILABLE` without a fallback.

| Artifact | Meaning |
|---|---|
| `candidates/CRYPTO_CFD_C001.yaml` | Existing frozen C001 manifest; do not edit after results |
| `candidates/CRYPTO_CFD_C001.freeze.json` | Byte-level C001 manifest + strategy-rule identity freeze |
| `candidates/CRYPTO_CFD_C001.friction.freeze.json` | Independent frozen BASE/STRESS/SEVERE friction identity |
| `datasets.yaml` | R1 historical data authority inventory; records the absent CFD history |
| `OFFLINE_DATASET_INGESTION_CONTRACT.md` | Required local exporter manifest/schema/hash contract |
| `partition_manifests/` | Immutable strategy-blind DEV/VALIDATION/HOLDOUT manifests (none committed without real data) |
| `candidate_queue.yaml` | Metadata-only future queue and strict research-lane mapping |
| `dataset_access_ledger.jsonl` | Append-only dataset access record; C001 fast screen is DEV-only |

## Invariants

- Raw Parquet input is never modified. Derived artifacts receive an independent
  `dataset_id`, `parent_dataset_id`, `transform_id`, and SHA-256.
- No price bar is filled automatically. Duplicate, non-monotonic, invalid OHLC, UTC
  alignment, unexpected M5 gap, normalization, and derived-timeframe failures block C001.
- Partitions are chronological, non-overlapping, strategy-blind, and immutable. C001
  may access DEV only; an attempted HOLDOUT access is recorded as a denial.
- `BTCUSD`/`ETHUSD` Crypto-CFD evidence is isolated from FX and Crypto-perpetual lanes.
- `PASS_FAST_SCREEN` only becomes `FROZEN_FOR_VERIFICATION`; `EDGE_VERIFIED` is always
  false at this stage and remains EdgeLab's separate decision.

The currently committed dataset inventory contains no BTCUSD/ETHUSD Crypto-CFD historical
bundle. Therefore there are no fabricated coverage values, no C001 profitability values,
and no partition manifest in this repository at publication.

R1 eligibility/quarantine keeps the raw finding `BLOCKED_UNKNOWN_GAPS` intact while
making a later complete-only population check available. It neither creates a partition
nor runs C001. See [RESEARCH_WINDOW_ELIGIBILITY_CONTRACT.md](RESEARCH_WINDOW_ELIGIBILITY_CONTRACT.md)
and `eligibility_manifests/`.
