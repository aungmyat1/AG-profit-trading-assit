# AG Crypto CFD Research Eligibility + Quarantine R1

**Date:** 2026-10-03 local repository date
**Status:** `UNIT_TESTED` data-dependency quarantine layer; no economic replay executed.

## Authority and lineage

```text
PR32_STATE    = OPEN
PR32_HEAD_SHA = 8570c957fc387c99704ea0d697a6e730296a3ff8
PR31_STATE    = OPEN
PR31_HEAD_SHA = a592c164a0c2e0a2be584622c87eec9b4f42004c
```

The fixed Arena branch includes PR #32's exact read-only dataset-pipeline commits so
eligibility reuses its export/provenance abstraction through
`edge_discovery/pr32_dataset_adapter.py`; it is not an MT5 fetch path. R1 consumes the
R2 `RawDataset`/`DerivedDataset` model and can hand an eligible M5 population to R2's
existing partition freezer. No open PR was merged.

## Preserved raw finding

```text
RAW_DATA_QUALITY = BLOCKED_UNKNOWN_GAPS
```

This is a non-negotiable source-quality result. Eligibility never marks any gap expected,
repairs a source, or reclassifies source quality. It merely records whether a bounded
reference/observation dependency can be proven from raw bars that exist.

The mission-authoritative raw hashes are pinned in code:

```text
BTCUSD = ea0216b3431c8043537fd0a4cba9d57a7cf721f8d21656c2d90bb8a22468d3be
ETHUSD = 1a2bd9429e14d0815210ae7913e130213d7c3b00c1608ec3025c333f06f5f713
```

The raw Parquet files themselves are not present in this checkout, so their bytes were
not opened or changed and data-specific day/window counts were not fabricated.

## Implemented controls

- Typed eligibility/quarantine reasons for exact reference-day and observation-window
  dependencies, including source boundary, duplicate, OHLC, contiguity, and unknown-gap
  outcomes.
- Canonical immutable per-symbol eligibility manifests with source ID/hash, per-day bar
  evidence, gap-dependency flag, and deterministic SHA-256 identity.
- M15/H1/D1 aggregation only from complete 3/12/288-bar valid source groups.
- R2-compatible eligible M5 `DerivedDataset` output, with no partition creation.
- Explicit source-hash verification and PR #32 local-export adapter.
- No C001/replay import, profitability calculation, partition, HOLDOUT strategy access,
  broker operation, risk change, or execution authority.

See
[`research/edge_discovery/RESEARCH_WINDOW_ELIGIBILITY_CONTRACT.md`](../../research/edge_discovery/RESEARCH_WINDOW_ELIGIBILITY_CONTRACT.md).

## Actual source availability

```text
BTCUSD_RAW_FILE = UNAVAILABLE_IN_CHECKOUT
ETHUSD_RAW_FILE = UNAVAILABLE_IN_CHECKOUT
RAW_HASH_MATCH  = NOT_EVALUATED_SOURCE_FILES_UNAVAILABLE
C001_RUN = FALSE
PARTITIONS_CREATED = FALSE
HOLDOUT_ACCESSED_BY_STRATEGY = FALSE
```

The local runner emits `BLOCKED_INSUFFICIENT_CLEAN_DATA` without raw source files. If
both verified source files arrive, it builds only quarantine eligibility artifacts; R2
partitioning remains a separate later action and C001 remains out of scope.

## Verification evidence

```text
new R1 + PR32 pipeline tests = 35 passed
existing non-C001 regression = 904 passed, 4 skipped, 1 warning
compileall = PASS
```

The regression command deliberately excluded the frozen C001/replay test modules because
this mission must stop before C001. No C001 function was invoked in R1 tests. Unit tests
remain offline evidence, not broker/live validation.
