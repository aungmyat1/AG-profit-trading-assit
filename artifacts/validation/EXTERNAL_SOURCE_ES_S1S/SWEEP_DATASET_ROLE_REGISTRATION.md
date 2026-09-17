# SWEEP_DATASET_ROLE_REGISTRATION

No bytes altered. No file copied or moved. This is a role annotation only, additive to the SSC1D lineage's own existing role (`EXTERNAL_REFERENCE_REDUCED_PRECISION_RESEARCH` for SSC), not a change to it.

## Candidate artifacts (read-only reference, hashes as previously frozen)

| Artifact | Path | SHA-256 | Existing role (SSC1D lineage, unchanged) | New role for this component |
|---|---|---|---|---|
| Native broker-time M15, EURUSD Oct 2022 | `D:\EURUSD_M15_202210030000_202210212345.csv` | `f010df7dc0f1c30fa1c21c844c8fca79ea8b05a1911d6110c34f77b2f4525fb1` | `TIME_AUTHORITY_STRONGLY_SUPPORTED` source file (SSC1D-EXT-R2A) | `SOURCE_BENCHMARK_REPLICATION` candidate for `SESSION_TRADING_STRATEGY_SOURCE_FAMILY / SWEEP` |
| UTC-normalized M15 (broker_time − 3h) | `.claude/worktrees/ssc1d-ext-r1/artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/EXT_R2B1_M15_REDUCED_PRECISION_PACKAGE/derived/EURUSD_M15_UTC_20221003_20221021_native_normalized.csv` | `b7ae5c458812107fbf3843f5f5e259b0ed14069c1906370d050330a1605af34e` | `EXTERNAL_REFERENCE_REDUCED_PRECISION_RESEARCH` for SSC1D | `SOURCE_BENCHMARK_REPLICATION` candidate for this Sweep component (M15-only, so this is the *complete* data need — no H1 leg required per `SWEEP_TIMEFRAME_CONTRACT.md`) |

## Explicitly NOT used

The derived UTC H1 file from the same package (`EURUSD_H1_UTC_20221003_20221021_derived_from_native_m15.csv`, `sha256:61e8770b...`) is **not referenced or registered here**, per this mission's explicit instruction and because `H1_REQUIRED = false` for this component.

## Data role for this component

`SOURCE_BENCHMARK_REPLICATION` — future use limited to comparing an independently-generated blind Sweep replay against the (still-sealed) 18-event benchmark table. Not `CANONICAL_VALIDATION`, not `OOS`, not `FINAL_HOLDOUT`, not `PROSPECTIVE_VALIDATION`. This registration does not itself authorize or perform any replay.

The 18 benchmark outcomes remain unconsumed by this mission.
