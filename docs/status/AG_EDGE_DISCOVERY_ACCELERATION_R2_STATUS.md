# AG Edge Discovery Acceleration R2 — Offline Research Factory

**Date:** 2026-10-02 UTC
**Classification:** `UNIT_TESTED` offline research infrastructure. No broker/runtime,
risk, proposal, or execution authority is added.

## Remote authority / lineage

```text
CURRENT_MAIN_SHA  = eb834dbd6f5eec23a05f2cda8ad6e19d5d32a3ec
CURRENT_MAIN_TREE = 9d435bd9db1b1270eb70f60ddbd759a9afa34249
PR30_STATE        = OPEN
PR30_HEAD_SHA     = 866825a8470cb9292de12834a20e1428c6776b38
PR30_HEAD_TREE    = cca05e86aa7dd33b8dbca8e48dca306a1529749e
PR30_MERGED       = FALSE
```

R2 is deliberately stacked on PR #30's exact fetched head, not merged into it. Arena
pinned this session to `arena/01a0fed0-ag-profit-trading-assit`; the preferred
`research/edge-discovery-acceleration-r2` branch was therefore not used. R2 must be
reviewed with PR #30's Crypto-CFD contract/Candidate Factory lineage first.

## Implemented offline gates

| Gate | Implementation | Fail-closed behavior |
|---|---|---|
| Local ingestion + provenance | `src/edge_discovery/ingestion.py` | Requires local file, SHA-256, manifest identity/schema/row-count/coverage, timestamp metadata, broker/environment field; no live fetch |
| Instrument/lane isolation | `ingestion.py`, `lanes.py` | Exact BTCUSD/ETHUSD `CRYPTO_CFD` only; near-symbol/perpetual/FX lane substitutions are rejected |
| Quality | `quality.py` | Duplicate/non-monotonic timestamps, invalid OHLC, unexpected M5 gaps, incomplete normalization, UTC-grid failures, and incomplete derived bars block C001; no fill/repair |
| UTC lineage | `quality.py` | Raw M5 → NORMALIZED_M5 → M15/H1/D1 each has `dataset_id`, parent ID, transform ID, and independent SHA-256 |
| Research sufficiency | `research_sufficiency.py` | Reports per-symbol coverage, UTC days/weeks/months, usable M5/D1 context before replay; requires only the existing C001 two-complete-day reference prerequisite, not an invented profitability sample |
| Partition freeze | `partitions.py` | Strategy-blind common complete UTC-day index, chronological 60/20/20 DEV/VALIDATION/HOLDOUT, no overlap, per-partition hash, immutable file |
| Holdout firewall | `dataset_ledger.py`, `replay_c001.py` | C001 fast screen is hard DEV-only even with a mutated manifest/governance ID; every request is ledgered; HOLDOUT grant invariant is false |
| C001 integration | `offline_pipeline.py` | Checks all preceding gates plus original C001/friction freeze identities before DEV replay; reports BASE/STRESS/SEVERE metrics with frozen costs only |

The input format and local invocation are specified in
[`research/edge_discovery/OFFLINE_DATASET_INGESTION_CONTRACT.md`](../../research/edge_discovery/OFFLINE_DATASET_INGESTION_CONTRACT.md).

## Candidate semantics and lanes

The queue now records required metadata (`source_type`, `source_reference`,
`asset_class`, `rule_family`, `contract_status`, `preregistered`,
`data_compatible`, `fast_screen_status`, `verification_status`) for future candidates
without inventing C002–C010 rules. It declares independent `LANE_FX`, `LANE_CRYPTO_CFD`,
and `LANE_CRYPTO_PERP` paths. External source performance claims are discovery metadata,
not AG edge evidence.

C001 rules, stop-buffer policy, friction scenarios, promotion policy, Scanner V1,
Checklist V1.1, Message Router V1, risk authority, and execution authority were not
changed. C001's existing contract file hashes are verified before replay; its frozen
friction identity is verified separately. A mismatch blocks C001 with a C002+/version
bump requirement.

## Actual dataset result at publication

No `BTCUSD_M5_RAW.parquet`, `ETHUSD_M5_RAW.parquet`, or matching provenance manifest is
present in this repository. Consequently no C001 outcomes, coverage, partition manifest,
or profitability results were fabricated.

```text
DATASET_INGESTION = BLOCKED_DATASET_UNAVAILABLE
PROVENANCE_GATE = NOT_EVALUATED
QUALITY_GATE = NOT_EVALUATED
RESEARCH_SUFFICIENCY = NOT_EVALUATED
PARTITION_FREEZE = NOT_EVALUATED
HOLDOUT_ACCESSED_BY_C001_FAST_SCREEN = FALSE
C001_RUN = FALSE
FAST_SCREEN_STATUS = NOT_EVALUATED
EDGE_VERIFIED = FALSE
FINAL_VERDICT = BLOCKED_DATASET_UNAVAILABLE
```

When the local immutable bundle arrives, run
`python scripts/run_edge_discovery_offline.py --input-dir <export-dir>`. Only a
`PASS_FAST_SCREEN` survivor is `FROZEN_FOR_VERIFICATION`; no R2 output can emit
`EDGE_VERIFIED`.

## Verification evidence

Focused no-runtime tests: `tests/test_edge_discovery_factory_v0.py` and
`tests/test_edge_discovery_offline_r2.py`; they use only local fixture bytes and injected
rows. Coverage includes provenance hash match/mismatch, symbol/asset substitution
rejection, duplicate/gap/UTC D1 quality, partition chronology/immutability, holdout
denial/ledger recording, pre-gate C001 block, frozen identity, friction identity,
promotion separation, and no fast-screen edge verification.

Linux offline evidence, 2026-10-02:

```text
focused pytest = 39 passed (R1 factory + R2 offline suites)
full pytest    = 939 passed, 4 skipped, 1 warning
compileall     = PASS
static mutation scan (src/edge_discovery) = 0 broker/order/management execution matches
```

Unit tests are not broker/live validation.
