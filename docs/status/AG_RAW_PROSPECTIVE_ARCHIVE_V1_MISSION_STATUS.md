# RAW_PROSPECTIVE_ARCHIVE_V1 — Mission Status

Mission: implement the read-only prospective raw market-data archive for
future SSC evidence. Data collection infrastructure only — this mission does
not create DEV_003, assign DEVELOPMENT role, run SSC replay, compute
outcomes, optimize, create hypotheses, evaluate G3, touch CONFIRM_001 /
HOLDOUT / OOS / H2, start VirtualBroker/Forward, or mutate broker state.

## P0 — Preflight / authority (verified against live repository state)

Read from `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/svos_context.json`
(schema_version 1.3, head_sha `1a50d4bb14f258b6669e7371d5246c47818fd808`), cross-checked
against `G2_POPULATION_MANIFEST_V1.json` and `SSC_V1_0_1_DATA_CONSUMPTION_REGISTRY_V1.json`:

| Field | Expected | Actual | Match |
|---|---|---|---|
| strategy | ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 | same | MATCH |
| G2 | POPULATION_FROZEN | `g2_population.status = POPULATION_FROZEN` | MATCH |
| population | SSC_V1_0_1_G2_DEV_002_POPULATION_V1 | same | MATCH |
| N | 22 | `population_n = 22` | MATCH |
| hash | `832e8e13...067ab5e` | `population_hash` / `population_hash_recomputed` identical | MATCH |
| DEV_002 | CONSUMED | registry `status = CONSUMED` | MATCH |
| G3 | NOT_EVALUATED_UNSIGNED_CONTRACT | `g3_verdict` identical | MATCH |
| optimization_eligible | false | `false` | MATCH |

All eight preflight facts confirmed. No mismatch — this mission is NOT blocked
by P0. (Additional context, not part of the claim: `G0`/`G1` are `PARTIAL`,
`furthest_verified_gate: null`, `svos_lifecycle_stage: OFFLINE_RESEARCH`.)

Concurrent writers checked: `git status` shows an unrelated in-progress
live/shadow proposal process (`state/proposal_ledger/proposal_ledger.json`,
`src/mtf_context/__init__.py`) and an unrelated Large-SMC friction campaign
(`strategies/ST_LARGE_SMC_V1.yaml`, `artifacts/validation/ST_LARGE_SMC_V1/.../friction_campaign_wp3a1/sessions/*`,
`journal/reports/btc/2026/2026-09-18.json`, `src/mtf_context/topdown_composer.py`,
`tests/test_topdown_composer*.py`). None of this mission's files touch any of
those paths; all of that foreign WIP is left exactly as found.

## P1 — Lineage audit

Real dataset facts (from `data/research/ssc_fresh_dev/*/dataset_manifest.json`
and the consumption registry):

- **DEV_002** — EURUSD, H1/M15/M1, decision interval 2026-06-21→2026-08-02,
  `parent_dataset: SSC_V1_0_1_G2_DEV_001`, raw file hashes recorded
  (H1 `93d27d8c…`, M15 `cefed970…`, M1 `b760a2a6…`).
- **DEV_001** (parent) — acquired via `scripts/acquire_ssc_v1_0_1_g2_dev_001.py`
  (Vantage-Demo MT5); registry marks it `FROZEN_REPLAY_INSUFFICIENT`
  (zero H1 warmup before its decision window) — superseded, not reused.
- **GEN_002 / HYP_002** — EURUSD+GBPUSD, 2026-08-03→2026-09-14,
  `strategy_version_used: "1.0.0 (pre-remediation)"`,
  `counting_status: PRE_REMEDIATION_NON_COUNTING`.

Classification, using `src/data_archive/lineage_audit.classify_lineage`
(never infers independence from ID difference alone — see
`tests/test_raw_prospective_archive_safety.py`):

| Pair | Classification | Basis |
|---|---|---|
| DEV_002 vs DEV_001 | `DERIVED_FROM_PRIOR_DATA` | `parent_dataset` field |
| DEV_002 vs GEN_002/HYP_002 | `SAME_MARKET_INTERVAL_DIFFERENT_SEMANTICS` | same symbol (EURUSD), immediately adjacent windows (2026-08-02 → 2026-08-03), different `strategy_version_used` (1.0.1 vs "1.0.0 pre-remediation") |

Neither pair is treated as `INDEPENDENT_RAW_SAMPLE`. This mission does not
change any data role based on this classification — it is recorded as
evidence for whoever later evaluates DEV_002/DEV_003 independence, not acted
on here.

## P2 — Archive authority

Reused, unmodified, existing read-only MT5 wrappers rather than building new
ones (`src/mt5/connection.py`, `src/mt5/market_data.py`, `src/mt5/broker_time.py`):
`connect()`/`shutdown()` (initialize/shutdown/terminal_info),
`get_latest_candles()` (copy_rates_from_pos), `get_tick()`
(symbol_info/symbol_info_tick). Two additional direct calls, both already on
the explicit allowlist and not exposed by an existing getter, were added in
`src/data_archive/raw_prospective_archive.py`: `terminal_info()` for
broker/server identity and `symbol_info()` for symbol metadata. No new
allowlist entry was needed or added — nothing required a STOP.

`mt5/market_data.py` also contains `get_candles()`, which uses
`copy_rates_range` (not on the allowlist) — the archive never imports or
calls it; `tests/test_raw_prospective_archive_safety.py` proves this via a
function-scoped (not whole-file) AST reachability check.

Explicit deny confirmed unreachable: `order_send`, `order_check`,
`positions_get`/`positions()`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_SLTP`, and
imports of `execution.mt5_gateway`, `mt5.management_gateway`, `mt5.account`,
`state.proposal_ledger`, `proposal_envelope`, `validation_orchestrator`,
`historical_replay` — all statically proven absent from
`src/data_archive/*` and from the specific reused functions.

## P3 — Raw data

`collect_daily_partition()` in `src/data_archive/raw_prospective_archive.py`
archives EURUSD H1/M15/M1 candles per UTC calendar day, plus (when available)
a bid/ask/spread tick snapshot, broker server name/company, and symbol
metadata (digits, point, contract size, currencies, spread). No field is
fabricated: candle fetch failure raises `ArchiveDataError`; tick-fetch
failure degrades to `None` fields rather than inventing a quote.

## P4 — Storage isolation

Namespace: `artifacts/raw_prospective_archive/RAW_PROSPECTIVE_ARCHIVE_V1/<SYMBOL>/<TIMEFRAME>/<date>.{jsonl,manifest.json}`
— physically separate from `state/proposal_ledger/`, any
`artifacts/validation/**` population/confirmation directory, and
`data/research/ssc_fresh_dev/`. Every manifest carries
`data_role: RAW_PROSPECTIVE_OBSERVATION`; no code path writes any other
role, and no code path grants DEVELOPMENT authority.

## P5 — Immutability / daily QA

Each partition manifest records: SHA-256 of the exact raw JSONL bytes, row
count, first/last UTC timestamp, gap list (bar-to-bar delta beyond the
timeframe's expected seconds), duplicate-timestamp count, strict
monotonicity, OHLC validity, `timezone_authority: "UTC"`, broker
server/company, and symbol metadata. `collect_daily_partition()` raises
`ArchiveImmutabilityError` instead of overwriting any partition already
`status: COMPLETE` — proven in
`tests/test_raw_prospective_archive_partitions.py`.

## P6 — Regime descriptors

`_regime_descriptors()` records only calendar date, weekday, H1 day
high/low/range, and a single spread snapshot — outcome-independent metadata,
never a trade result. It is not consulted anywhere to pick a favorable
window; there is no DEV_003 selection code in this mission at all.

## P7 — Protected window

`EXTENSION_CHECKPOINT_POLICY.json`'s `maximum_horizon.blocks[2]` (`CONFIRM_003`)
ends `2026-12-07`, with `earliest_acquisition_timestamp: 2026-12-08T00:00:00Z`
and an explicit `CONFIRM_004_prohibition`. Verified — repository authority
agrees with the mission's assumed date.

**EARLIEST_POSSIBLE_DEV003_START = 2026-12-08**, independent of whether
HYP_001 resolves early. Raw archival collection under this mission may run
during the protected period; every partition it writes is `RAW_PROSPECTIVE_OBSERVATION`
under `RAW_PROSPECTIVE_ARCHIVE_V1`, never reclassified to any DEVELOPMENT
role by this mission's code.

## P8 — Frozen-core expected failures

Ran `tests/_lsmc_frozen_core.py`, `tests/test_lsmc_frozen_core_scope.py`,
`tests/test_svos_context_authority.py`, `tests/test_ssc_svos_post_g2_authority_sync.py`
before and after this mission's changes: **25/25 passed both times** — this
mission touched none of those files, and there are no pre-existing failures
to record. No frozen-core module was edited.

## P9 — Tests

New files, all passing (23 tests):
- `tests/test_raw_prospective_archive_safety.py` — items 1-6, 10, 11 (static
  AST reachability: only-allowlisted MT5 calls, no forbidden identifiers, no
  forbidden imports, no proposal-ledger reference, lineage classifier proofs).
- `tests/test_raw_prospective_archive_partitions.py` — items 7, 8, 9
  (hash-bound partitions, gap/duplicate detection, immutability, no
  fabrication on missing data) — pure unit tests with injected fake
  connect/candle/tick functions, no live terminal required.

Relevant SSC/SVOS/Large-SMC regressions re-run (see P8): all pass, no
regression introduced.

## P10 — Safety

```
STRATEGY_CHANGED=false
PARAMETERS_CHANGED=false
DEV002_CHANGED=false
DEV003_CREATED=false
REPLAY_EXECUTED=false
OPTIMIZATION_RUN=false
HYPOTHESIS_CREATED=false
G3_EVALUATED=false
CONFIRMATION_ACCESSED_FOR_OUTCOMES=false
HOLDOUT_ACCESSED=false
OOS_ACCESSED=false
H2_CONSUMED=false
FORWARD_STARTED=false
VIRTUAL_BROKER_STARTED=false
BROKER_MUTATION=false
DEMO_ORDER=false
LIVE_ORDER=false
EXECUTION_AUTHORITY_CHANGED=false
```

Files added by this mission: `src/data_archive/__init__.py`,
`src/data_archive/raw_prospective_archive.py`,
`src/data_archive/lineage_audit.py`,
`tests/test_raw_prospective_archive_safety.py`,
`tests/test_raw_prospective_archive_partitions.py`, this status doc.
No other file was modified. Nothing was pushed.

## FINAL_STATUS

**READY_FOR_PROSPECTIVE_RAW_COLLECTION**

## NEXT_SINGLE_ACTION

Independent audit of this archive contract before scheduled collection
begins (e.g. a second reviewer or agent re-runs
`tests/test_raw_prospective_archive_safety.py` and re-derives the P0/P1
tables above from repository state directly, rather than trusting this
document).
