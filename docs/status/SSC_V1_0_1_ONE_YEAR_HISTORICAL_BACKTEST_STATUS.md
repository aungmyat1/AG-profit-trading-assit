# SSC_V1_0_1_ONE_YEAR_HISTORICAL_BACKTEST_STATUS

ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 — one-year historical research backtest
preflight and admissibility verdict. Date: 2026-09-19. Environment: local Windows
workstation, `.venv`, repository `D:\ddev\AG profit trading`, branch `main`.

**FINAL_STATUS = `BLOCKED_INCOMPLETE_ONE_YEAR_DATA`.** No economic replay was run. The
mission's own P1 gate ("if complete canonical-quality H1/M15/M1 coverage cannot be
established … STOP before replay") fires, because the canonical M1
`FILL_RESOLUTION_INPUT` leg does not exist for roughly the first eight months of any
one-year window in the reachable EURUSD history.

---

## P0 — Preflight

| Item | Value |
| --- | --- |
| Branch | `main` |
| HEAD_BEFORE | `83630b0ba92bd823d2e5ca4b423f47afc4cd87de` |
| Commit `83630b0` present | **YES** — it *is* HEAD (`fix(tests): scope Large-SMC frozen-core freeze away from svos_context_export.py`) |
| Concurrent writer | **DETECTED** (see below) — foreign WIP preserved, nothing of it staged |

Authority re-verified (unchanged, not modified by this mission):

- `strategy_id = ST_SESSION_SWEEP_CONTINUATION_V1`, `version = 1.0.1`
  (`src/session_sweep_continuation/__init__.py`, `config/governance/strategy_lifecycle.yaml`
  → `lifecycle_stage: OFFLINE_RESEARCH`).
- Canonical replay authority = `session_sweep_continuation.replay.run_replay`
  (`src/svos/adapters/ssc.py::SSC_HISTORICAL_REPLAY_ENTRYPOINT`); historical/forward
  entrypoint parity asserted by test.
- Canonical partial-target semantic = `OPPOSITE_SESSION_BOUNDARY`
  (`trade_management.partial_target_mode: NEXT_LIQUIDITY_TARGET` is the declared field
  name; the executable mapping is LONG → reference high, SHORT → reference low).

**Concurrent-writer detection (foreign WIP, preserved untouched):** modified
`src/historical_replay/__init__.py`, `src/historical_replay/candle_store.py`,
`src/mtf_context/{__init__,topdown_composer,topdown_contracts}.py`,
`state/proposal_ledger/proposal_ledger.json`, `tests/test_topdown_composer*.py`;
untracked `src/historical_replay/dataset_identity.py`,
`tests/test_historical_replay_dataset_identity.py`,
`tests/test_topdown_composer_replay.py`, `tests/test_topdown_contracts_composition_mode.py`,
`docs/status/TD8_REPLAY_TEMPORAL_PARITY_STATUS.md`, and
`artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/…`.
None of these belong to this mission and none were staged or modified. Large-SMC
remediation was not touched.

HEAD also moved during this mission's own session (`d656a18` → `83630b0`), independently
confirming an active second writer.

---

## P1 — One-year window definition and data coverage

**Window selection rule (outcome-independent).** The primary window is anchored to the
protected prospective CONFIRM_001 calendar boundary — the single fixed calendar fact
available — and is "the one complete year ending immediately before it". No date was
chosen, moved, or shortened on the basis of any strategy result; no result exists yet
for this window.

| | Primary | Alternate (robustness) |
| --- | --- | --- |
| Window | `2025-09-15T00:00:00Z` → `2026-09-14T23:59:59Z` | `2025-09-19T00:00:00Z` → `2026-09-18T23:59:59Z` |
| Rationale | ends immediately before CONFIRM_001 (`2026-09-15T00:00:00Z`) | same length, shifted 4 days, proves the verdict is not boundary-dependent |
| Verdict | `BLOCKED_INCOMPLETE_ONE_YEAR_DATA` | `BLOCKED_INCOMPLETE_ONE_YEAR_DATA` |

Coverage (primary window; every source owner-authorized — in-repo frozen packages or
the owner-authorized 2026-09-10 `D:\` Vantage/MT5 export family; no provider was mixed
silently):

| Field | Result |
| --- | --- |
| `AVAILABLE_H1` | `2025-09-15T00:00:00Z` → `2026-09-14T23:59:59Z` (full window) |
| `AVAILABLE_M15` | `2025-09-15T00:00:00Z` → `2026-09-14T23:59:59Z` (full window) |
| `AVAILABLE_M1` | `2026-05-18T06:46:00Z` → `2026-08-03T00:00:00Z` and `2026-08-03T00:01:00Z` → `2026-09-14T23:58:00Z` (i.e. from **2026-05-18** onward only) |
| `COMMON_INTERVAL` (H1 ∩ M15 ∩ M1) | `2026-05-18T06:46:00Z` → `2026-09-14T23:58:00Z`; **119.716 covered days (3.93 months)** |
| `WARMUP_AVAILABLE` | **PASS** — 4 473 closed H1 bars before the first ASIAN_LONDON reference end and 4 478 before LONDON_NEWYORK (requirement 1 000); merged H1 series 10 614 bars, warmup satisfiable from `2025-02-28T12:00:00Z` |
| `MISSING_INTERVALS` | **M1: `2025-09-15T00:00:00Z` → `2026-05-18T06:46:00Z` — 245.282 days, 176 FX weekdays**; M1 micro-gaps `2026-08-03T00:00:00Z`→`00:01:00Z` and `2026-09-14T23:58:00Z`→`23:59:59Z` (source-splice boundaries, 1 minute each). H1 and M15 have **no** missing interval inside the primary window. |

Supporting facts:

- The canonical requirement is three legs — H1 (`MARKET_BIAS_INPUT` + structure
  warmup), M15 (`STRATEGY_DECISION_INPUT`), M1 (`FILL_RESOLUTION_INPUT`). Only the
  intersection supports a replay that honours every leg's no-lookahead/closed-bar
  guarantee, so "H1 and M15 are present" is not sufficient.
- Broker-served M1 history does not reach back before ~2026-05-18, exactly as the
  repository already recorded (`SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_STATUS.md`:
  *"Broker-served M1 history does not extend before ~2026-06-09"*; the audit finds the
  true earliest M1 leg at `2026-05-18T06:46:00Z`).
- The older in-repo packages confirm this independently: `SSC1D_WP1_OOS_EURUSD_2024Q1`
  records `skipped_timeframes.M1 = "NO_DATA -- broker M1 history retention exhausted
  for this window"` for 2024Q1.
- Alternatives were explicitly rejected rather than substituted: **M5 was not used in
  place of M1**, no M1 was **manufactured** from the 228 MB `EURUSD_202606182200_202608241902.csv`
  raw bid/ask tick export, nothing was **interpolated**, and no second provider was
  introduced.

Sources measured (all `quality_status = PASS`; each hash is the SHA-256 of the exact
file used):

| Timeframe | Source | Rows | UTC range | Timezone authority |
| --- | --- | --- | --- | --- |
| H1 | `SSC_V1_0_1_G2_DEV_002::H1` | 9 843 | 2025-01-01T21:00Z → 2026-08-02T23:00Z | UTC (native `copy_rates_range`) |
| H1 | `EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv` | 9 817 | 2025-01-01T21:00Z → 2026-07-30T21:00Z | `BROKER_OFFSET_CONFIRMED` (+3 h) |
| H1 | `SSC_HYP002_H1_WARMUP_CONTEXT_…::H1` | 1 128 | 2026-05-27T18:00Z → 2026-07-31T17:00Z | UTC |
| H1 | `SSC_V1_0_1_G2_DEV_001::H1` | 723 | 2026-06-21T21:00Z → 2026-08-02T23:00Z | UTC |
| H1 | `HYP_002_EVALUATION_INPUT::H1` (derived) | 1 872 | 2026-05-27T18:00Z → 2026-09-14T23:00Z | UTC |
| H1 | `SSC_FRESH_DEV_GEN_002_…::H1` | 744 | 2026-08-03T00:00Z → 2026-09-14T23:00Z | UTC |
| M15 | `EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202607310000.csv` | 39 265 | 2025-01-01T21:00Z → 2026-07-30T21:00Z | `BROKER_OFFSET_CONFIRMED` |
| M15 | `EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202606192345.csv` | 36 480 | 2025-01-01T21:00Z → 2026-06-19T20:45Z | `BROKER_OFFSET_CONFIRMED` |
| M15 | `SSC_V1_0_1_G2_DEV_00{1,2}::M15` (byte-identical) | 2 892 | 2026-06-21T21:00Z → 2026-08-02T23:45Z | UTC |
| M15 | `SSC_FRESH_DEV_GEN_002_…::M15` | 2 976 | 2026-08-03T00:00Z → 2026-09-14T23:45Z | UTC |
| M1 | `EXTERNAL_D_ROOT::EURUSD_M1_202605180946_202607312356.csv` | 78 444 | **2026-05-18T06:46Z** → 2026-07-31T20:56Z | `BROKER_OFFSET_CONFIRMED` |
| M1 | `EXTERNAL_D_ROOT::EURUSD_M1_*` (5 further overlapping candidates) | 32 788 – 75 901 | 2026-05-19T01:15Z earliest start | `BROKER_OFFSET_CONFIRMED` |
| M1 | `SSC_V1_0_1_G2_DEV_00{1,2}::M1` (byte-identical) | 43 292 | 2026-06-21T21:02Z → 2026-08-02T23:59Z | UTC |
| M1 | `SSC_FRESH_DEV_GEN_002_…::M1` | 44 546 | 2026-08-03T00:01Z → 2026-09-14T23:57Z | UTC |

Duplicate timestamps, non-monotonic timestamps, invalid-OHLC rows and
zero/negative-price rows were checked per source and are zero everywhere (the in-repo
loader fails closed on all four, so a successful load *is* the quality verdict;
the external family was measured by the pre-existing
`market_data_readiness.scanner`). All gaps are classified closure gaps (weekend /
daily-rollover), except the two H1 splice gaps inside the derived DEV_002 H1 file, which
are documented attributes of that file and are immaterial here because the external H1
and GEN_002 H1 legs separately cover the same wall-clock intervals.

---

## P2 — Data lineage / contamination map

Classification: **`HISTORICAL_RESEARCH_ONLY`**. Repository governance is **not** read
as supporting a stronger role; this is not a new G2 validation population, not untouched
OOS, not holdout, not CONFIRM_001, not DEV_003, not prospective confirmation, and not
DEMO-eligibility evidence.

Cross-referenced against `SSC_V1_0_1_DATA_CONSUMPTION_REGISTRY_V1.json`
(head `101488f7…`, `generated_at_utc 2026-09-19`):

| Campaign | Overlap with the one-year window | Effect |
| --- | --- | --- |
| GEN_001 | 2026-05-18 → 2026-06-19 inside window | already consumed — re-inspected, **not** fresh |
| GEN_002 | 2026-08-03 → 2026-09-14 inside window | already consumed (`PRE_REMEDIATION_NON_COUNTING`) |
| GEN_002A (GBPUSD) | inside window | already consumed; out of scope (EURUSD mission) |
| DEV_001 | 2026-06-21 → 2026-08-02 inside window | already consumed |
| **DEV_002** | 2026-06-21 → 2026-08-02 inside window | **already consumed (G2 POPULATION_V1 frozen, N=22)** |
| Route B | 2026-05-18 → 2026-07-30 inside window | already consumed (HYP_001 falsified) |
| HYP_001 / HYP_002 | hypothesis lanes over the above | closed/terminal; not reopened |
| CONFIRM_001 | calendar 2026-09-15 → 2026-10-12 begins where the window ends | **PROTECTED — untouched** |
| HOLDOUT / OOS | sealed | **PROTECTED — untouched** (`access_count` remains 0) |
| H2 | 2026-09-21 → 2026-09-25, not yet collected | not consumed, not substituted for historical spread |

- **OVERLAP_WARNING:** DEV_002's interval (and DEV_001 / GEN_001 / GEN_002 / Route B)
  lies wholly inside the one-year window. A one-year population must **never** be added
  to DEV_002's `N = 22` as though independent — those occurrences are a subset of the
  window, not additional sample.
- **Protected-data firewall:** `SSC1D_WP1_OOS_EURUSD_2024Q1` was enumerated
  metadata-only (`access_count = 0` read, raw bytes never opened); HOLDOUT/OOS/CONFIRM_001
  were not accessed; no sealed evidence was touched to create this campaign.
- Dataset-identity notes: DEV_002's M15/M1 are byte-identical to DEV_001's (one
  lineage, not two samples); the registry's "M15 gap 2026-06-20 → 2026-08-02
  (NOT_ACQUIRED)" candidate is in fact already covered by owner-authorized external M15
  exports, so no acquisition is required or implied.

---

## P3 — Semantic authority verification

Verified unchanged and passing (no parameter or YAML edit):

| Check | Status |
| --- | --- |
| v1.0.1 `OPPOSITE_SESSION_BOUNDARY` semantics | PASS (test) |
| Historical/forward replay entrypoint parity | PASS (test) |
| Replay determinism (identical inputs → identical result) | PASS (test) |
| Symbol-metadata manifest binding (`tick_size = 0.00001`, `OWNER_APPROVED_DATASET_MANIFEST`) | PASS (test + config) |
| Timezone authority | PASS — all sources UTC or `BROKER_OFFSET_CONFIRMED` |
| Session definitions (UTC, `HH:MM`, no DST offset applied) | PASS (unchanged) |
| H1 bias / M15 decision / M1 execution resolution | PASS (existing tests) |
| Friction model `cost_status` stamping | PASS (existing tests); status **MODELED** (see P9) |
| EMA invariant (regime 20/50 == signal 20/50) | PASS (test) |
| `STRUCTURE_WARMUP_H1_BARS = 1000` | PASS — satisfied with a 4.4× margin |

---

## P4–P10 — Not evaluated (blocked)

The P1 gate stops the mission before the dataset freeze (P4) and therefore before the
single canonical replay (P5) and every downstream economic, decomposition, excursion,
friction and comparison stage. No replay was executed, so:

| Field | Value |
| --- | --- |
| `DATASET_ID` | `SSC_V1_0_1_HIST_1Y_001` — **NOT_FROZEN** (coverage audit only) |
| `DATA_ROLE` | `HISTORICAL_RESEARCH_ONLY` |
| `WINDOW` | `2025-09-15T00:00:00Z` → `2026-09-14T23:59:59Z` (primary) |
| `TRADING_DAYS` | `NOT_EVALUATED` (window not admissible) |
| `H1_HASH` / `M15_HASH` / `M1_HASH` | `NOT_FROZEN` — per-source hashes recorded in the audit artifact instead |
| `DATASET_FINGERPRINT` | `NOT_FROZEN` |
| `POPULATION_ID` / `POPULATION_HASH` | `NOT_CREATED` |
| `N`, `WINS`, `LOSSES`, `BREAKEVEN`, `WIN_RATE` | `NOT_EVALUATED` |
| `GROSS_R`, `NET_R`, `GROSS_EXPECTANCY_R`, `NET_EXPECTANCY_R`, `GROSS_PF`, `NET_PF`, `MAX_DRAWDOWN_R` | `NOT_EVALUATED` |
| `STDDEV_R`, `STANDARD_ERROR_R`, `CI90`, `CI95` | `NOT_EVALUATED` |
| `S1_RESULT`, `S2_RESULT`, `S3_RESULT` | `NOT_EVALUATED` |
| `LONG_RESULT`, `SHORT_RESULT` | `NOT_EVALUATED` |
| `ASIAN_LONDON_RESULT`, `LONDON_NEWYORK_RESULT` | `NOT_EVALUATED` |
| `MONTHLY_RESULT`, `QUARTERLY_RESULT`, `DST_RESULT` | `NOT_EVALUATED` |
| `MFE_MAE_RESULT` | `NOT_EVALUATED` |
| `FRICTION_CONTRIBUTION` | `NOT_EVALUATED` — `FRICTION_STATUS = MODELED` (no broker-evidenced historical spread exists; H2 is uncollected and explicitly not substituted) |
| `DEV002_OVERLAP` | **100 %** of DEV_002's interval lies inside the window (see P2) |
| `DEV002_COMPARISON` | `INSUFFICIENT_COMPARABILITY` — no one-year population exists to compare |

DEV_002 reference (frozen, unchanged, quoted for the record only): `N = 22`,
gross expectancy ≈ **-0.245R**, net expectancy ≈ **-0.469R**, gross PF ≈ **0.563**
(failure classification `PRIMARY_ALPHA_DEFICIT` + `SECONDARY_FRICTION_AMPLIFICATION`).

**Shortening the window instead of stopping was considered and rejected as a
substitute:** the longest canonically replayable span available is 119.7 days
(`2026-05-18T06:46Z` → `2026-09-14T23:58Z`, under 4 months, not one year), and that span
is almost entirely already-consumed evidence (DEV_001/DEV_002/GEN_002/Route B, plus the
HYP_001/HYP_002 lanes). A run over it would be re-analysis of consumed data — it could
not supply independent evidence and is not performed here.

---

## P11 — Optimization firewall

`OPTIMIZATION_RUN = false` · `PARAMETER_SEARCH = false` · `NEW_CANDIDATE = false`.
`HYP_001` and `HYP_002` were **not** reopened. No parameter, session, EMA, stop, target
or setup-enablement value was changed; `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`
is byte-unchanged. No structural mechanism emerged (there are no outcomes to inspect),
so **no** `HYPOTHESIS_CANDIDATE_FOR_LATER_GOVERNANCE` is registered.

## P12 — Validation interpretation

- `historical_research_result`: **none produced** — the gate fired before any replay.
- `sample_precision`: `NOT_EVALUATED`.
- `regime_coverage`: `NOT_EVALUATED`; the only thing established is that a one-year
  window would have spanned both DST and standard time, which cannot be measured here.
- `independence_limitations`: the only canonically replayable span is 100 % contained in
  consumed evidence, so **no** one-year result obtained from this data could ever be
  independent confirmation.
- `validation_role`: `HISTORICAL_RESEARCH_ONLY`; explicitly not DEMO-eligibility
  evidence. The distinction between "this population performed X" and "the strategy
  has/lacks general market capacity" is preserved — neither statement is made.

## P13 — Safety

```
STRATEGY_CHANGED=false            PARAMETERS_CHANGED=false
EXECUTION_AUTHORITY_CHANGED=false OPTIMIZATION_RUN=false
PROTECTED_DATA_ACCESSED=false     CONFIRMATION_ACCESSED=false
HOLDOUT_ACCESSED=false            OOS_ACCESSED=false
BROKER_MUTATION=false             DEMO_ORDER=false
LIVE_ORDER=false                  VIRTUAL_BROKER_STARTED=false
```

No order was placed, no broker/gateway call was made, no demo/live authorization was
touched, no lifecycle or registry file was edited.

## P14 — Tests, evidence, commit

Test command (run 2026-09-19, `.venv`, local):

```
python -m pytest -q --tb=short \
  tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py \
  tests/test_session_sweep_continuation_replay_determinism.py \
  tests/test_svos_ssc_adapter.py tests/test_symbol_metadata_manifest.py \
  tests/test_svos_mt5_isolation.py tests/test_ssc_g2_dev002_warmup_remediation.py \
  tests/test_session_sweep_continuation_ema_invariant.py
→ 52 passed in 48.95s
```

Skipped deliberately: `tests/test_historical_replay_dataset_identity.py` and the
`test_topdown_*` files, which belong to the concurrent writer's uncommitted WIP and are
not mission evidence.

Evidence artifacts produced:

- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/DATA_COVERAGE_AUDIT_V1.json`
  (P1 source inventory + dual-window coverage verdict)
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/LINEAGE_CONTAMINATION_MAP_V1.json`
  (P2 campaign cross-reference)
- `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` (read-only, deterministic
  regenerator for both artifacts; never calls `run_replay`)

`HEAD_AFTER`: recorded in the commit that adds these three files plus this document and
the `docs/README.md` index entry. Nothing else was staged; the concurrent writer's WIP
was left untouched; nothing was pushed.

## FINAL_STATUS

`BLOCKED_INCOMPLETE_ONE_YEAR_DATA` — canonical M1 `FILL_RESOLUTION_INPUT` coverage is
absent for 245.282 days (176 FX weekdays) of any one-year EURUSD window; H1, M15 and the
1 000-bar H1 warmup are all satisfied; the call was made at the P1 gate and no replay,
no population and no economic metric exist.

## NEXT_SINGLE_ACTION

Obtain an owner-authorized EURUSD **M1** source (or an owner decision that explicitly
authorizes a non-M1 fill-resolution proxy) covering `2025-09-15T00:00:00Z` →
`2026-05-18T06:46:00Z`, then re-run
`python scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` — the mission may proceed to
P4 only when that audit returns `DATA_COVERAGE_COMPLETE` for the same window. If no such
M1 source can be authorized, the correct next action is to abandon the one-year framing
and decide at governance level whether a shorter, consumed-evidence-only historical
re-analysis is worth running at all (it can never be independent evidence).
