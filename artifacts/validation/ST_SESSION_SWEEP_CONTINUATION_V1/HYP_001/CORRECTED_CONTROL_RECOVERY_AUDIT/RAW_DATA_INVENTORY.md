# Raw-Data Recovery Audit (P3/P4)

## GEN_001 (EURUSD, 2026-05-18 – 2026-06-19, N=31, population_hash `8e32a7...9166d`)

| Leg | Path | Hash (expected → actual) | Status |
|---|---|---|---|
| M1 | `D:\EURUSD_M1_202605180946_202607312356.csv` | `55422a1c...9f7fd7dd6a23` → **exact match** | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| H1 | `D:\EURUSD_H1_202501020000_202607310000.csv` | `f1b456e4...480a060` → **exact match** (owner-approved manifest `config/historical_datasets/EURUSD_H1_symbol_metadata.yaml`, fully covers 2026-05-18–06-19) | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| M15 | `D:\EURUSD_M15_202501020000_202606192345.csv` | `7f750293...c57fc43a65` → present, fully covers the window | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| Population metadata (`input_manifest.json`, `per_trade_results.csv`, `canonical_lifecycle_population.json`) | `refactor/architecture-boundary-hardening-v3` branch | Read via `git show <branch>:<path>` (no checkout/merge) | `DATA_BYTES_RECOVERABLE_EXACT_FROM_GIT` |

**GEN_001_RECOVERABLE_EXACT = true.** All three raw timeframe legs are hash-verified present on `D:\`; the population's own metadata/manifest is recoverable read-only from the unmerged branch via `git show` (no merge, no checkout, no history rewrite).

## GEN_002A (GBPUSD, N=57, population_hash `2a2fb9...54fd8` — the **true** GEN_002A per the lineage audit; distinct from the unrelated `HYP_001_GBPUSD_REPLICATION_R1` N=15 artifact on `main`, which must not be conflated with it)

| Leg | Path | Hash (expected → actual) | Status |
|---|---|---|---|
| M1 | `D:\GBPUSD_M1_202606080533_202607302357.csv` | `390798de...78c1d705c` → **exact match** | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| H1 | not yet independently confirmed by path in this pass | — | `CONTRACT_AMBIGUOUS` (needs one more lookup before Route B can proceed for GEN_002A specifically) |
| M15 | not yet independently confirmed by path in this pass | — | `CONTRACT_AMBIGUOUS` |
| Population metadata | `refactor/architecture-boundary-hardening-v3` branch, `artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_002A/input_manifest.json` | Read via `git show` | `DATA_BYTES_RECOVERABLE_EXACT_FROM_GIT` |

## GEN_002 (EURUSD, N=21, occurrences 2026-08-06–09-11)

| Leg | Path | Hash (expected → actual) | Status |
|---|---|---|---|
| H1 | `data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914/raw/EURUSD_H1.csv` (**in-repo**) | `76adad8e...657deaa96` → **exact match** | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| M15 | same directory, `EURUSD_M15.csv` | `3f0702eb...c47b76209e8` → **exact match** | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| M1 | same directory, `EURUSD_M1.csv` | `4cc01e2b...3938906f332` → **exact match** | `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` |
| Owner-authorized H1 symbol metadata | `config/historical_datasets/EURUSD_H1_GEN_002_symbol_metadata.yaml` | `authority: OWNER_APPROVED_DATASET_MANIFEST` | present, in-repo |

**GEN_002 is the most completely recoverable population** — all three timeframe legs are version-controlled in-repo (not dependent on `D:\` or any branch), with hashes matching the original `FRESH_DATA_ADMISSION` record exactly.

## Important caveat carried into P6/P7 (not resolved here)

GEN_001/GEN_002A's own population metadata does not indicate whether they were generated under a build of `replay.py` that already enforced the current hard H1-bias-gate invariant (`bias_gate.py`, "a strict narrowing of this function's prior behavior — previously direction-agnostic"). If GEN_001/GEN_002A predate that invariant, a Route B reconstruction using the *current* `replay.py` could behave differently at the bias-gating step than the original generation run did — a `CONTRACT_AMBIGUOUS` item for the future Route B amendment to resolve explicitly, not silently assumed either way here.
