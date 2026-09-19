# SSC_V1_0_1_ONE_YEAR_HISTORICAL_REPLAY_STATUS

ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 — one-year historical replay mission (R0–R17).
Date: 2026-09-19. Environment: local Windows workstation, `.venv`, repository
`D:\ddev\AG profit trading`, branch `main`. Mode: ONE-SHOT / READ-ONLY /
HISTORICAL_RESEARCH_ONLY.

**FINAL_STATUS = `BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT`.** The mission's own R2/R3
timezone-authority gate fires **before** R5 (contract freeze) and therefore before R6
(the single canonical replay). The one-year window cannot be replayed, because the H1
and M15 legs that the coverage audit counts as admissible are not expressed in the same
time base as the M1 leg. **No replay was executed, no population was created, and no
economic metric exists.** No parameter, config or strategy file was modified.

The mission also corrects a real gap in the previous gate: the canonical coverage audit
proves *timestamp-union coverage* only. It does not prove *timezone consistency between
legs*, and it therefore returned `DATA_COVERAGE_COMPLETE` for a window that is not
replayable. That missing check is now implemented as a durable, read-only gate.

---

## R0 — Repository / concurrency preflight

| Item | Value |
| --- | --- |
| Branch | `main` |
| HEAD_BEFORE | `4b365934d1c2be2702a8d34eadb4c6d1fe39c409` |
| Commit `4b36593` present in ancestry | **YES** — it *is* HEAD (`data(ssc): acquire one-year EURUSD M1 leg -> DATA_COVERAGE_COMPLETE`) |
| Overlapping writer on mission output files | **NONE** — no other writer touches `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/` or the new gate script |
| Foreign WIP | **DETECTED and preserved untouched** — modified `state/proposal_ledger/proposal_ledger.json`; untracked `artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-18_WINDOW_{C,D}_*` and `journal/reports/btc/2026/2026-09-18.json`. None staged, none modified. |

`HEAD_AFTER` is recorded in the commit that adds this document, the new gate script and
the `docs/README.md` index entry. Nothing else is staged; nothing is pushed.

---

## R1 — Strategy authority

| Field | Value | Verdict |
| --- | --- | --- |
| `strategy_id` | `ST_SESSION_SWEEP_CONTINUATION_V1` | **PASS** |
| `version` | `1.0.1` (`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml:22`, `src/session_sweep_continuation/__init__.py`) | **PASS** |
| Canonical replay authority | `session_sweep_continuation.replay.run_replay` | **PASS** |
| v1.0.1 exit-semantic remediation | present (`src/session_sweep_continuation/outcome_resolution.py`, owner-adjudicated OPTION_A, `PARTIAL_TARGET_DIRECTION_INVERSION`) | **PASS** |
| Partial target semantic | `OPPOSITE_SESSION_BOUNDARY` — declared field `trade_management.partial_target_mode: NEXT_LIQUIDITY_TARGET`, executable mapping LONG → reference high, SHORT → reference low | **PASS** |
| EMA invariant | regime 20/50 == signal 20/50 | **PASS** (test) |
| H1 bias authority / M15 decision authority / M1 fill-resolution authority | `h1_bias.resolve_h1_market_bias` / `run_replay` M15 step / `run_replay(..., m1_candles=...)` | **PASS** |
| Historical/forward parity | `svos.adapters.ssc.historical_replay_entrypoint() is forward_decision_entrypoint() is run_replay` | **PASS** (test) |

No strategy, config or parameter edit was made.

---

## R2 — Dataset identity and coverage

`ONE_YEAR_COVERAGE_STATUS = DATA_COVERAGE_COMPLETE` — reproduced by running the canonical
audit read-only (`scripts/audit_ssc_v1_0_1_one_year_data_coverage.py`, exit 0).

| Field | Value |
| --- | --- |
| `WINDOW` | `2025-09-15T00:00:00Z` → `2026-09-14T23:59:59Z` (primary) |
| `primary_common_covered_days` | `365.0` |
| `primary_blocking_missing_intervals` | `{}` |
| `primary_warmup_pass` | `true` |
| `alternate_window_status` | `BLOCKED_INCOMPLETE_ONE_YEAR_DATA` |
| M1 authority dataset | `SSC_V1_0_1_HIST_1Y_M1_001` |
| `M1_SHA256` | `50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a` (**verified from bytes**) |
| raw source `SHA256` | `3fdd97cfba62c37251f401c9e357833da4df3da48729d8edf9363ef2a6fe7fdd` (**verified from bytes**) |
| M1 rows / range | 373 421 / `2025-09-14T21:02:00Z` → `2026-09-15T21:00:00Z` |
| M1 quality | `PASS` — 0 duplicates, 0 non-monotonic, 0 invalid OHLC |
| M1 parity vs canonical DEV_002 M1 | `PASS_EXACT`, 43 292 / 43 292 bars, 0 missing |
| Config hash (canonical, from audit artifact) | `6281b6407c748990d3b68188dafc2b6fec5aa5534dc4ce5fc82abcf53568b1fc` |

All H1/M15/M1 hashes were re-verified from bytes before any replay work; every admissible
source reports `quality_status = PASS`; no candle was interpolated or manufactured.

**However — R2 coverage is necessary but not sufficient.** See R3.

---

## R3 — Timezone / DST authority — **THE GATE THAT FIRES**

The established broker-time interpretation is preserved: `BROKER_SERVER_TIME` is
UTC+2 / UTC+3 seasonally. No fixed +3-hour conversion is applied anywhere; the repo's own
per-week reopen authority (`historical_replay.mt5_export_loader._offset_segments`) remains
the only timezone model used, and the M1 leg's own acquisition detected the real seasonal
change (`[UTC+2, UTC+3]`, 53 weekly segments).

**New check performed (the previous mission never did this).** Timestamp-union coverage
does not establish that the H1 (bias), M15 (decision) and M1 (fill) legs share a time
base. Each admissible H1/M15 source was therefore arbitrated against the finest-
granularity canonical leg — the M1 fill-resolution authority — by aggregating M1 into H1
and M15 buckets (exact OHLC bucketing, no interpolation) and running a −3h…+3h whole-hour
shift scan. Alignment is judged per DST season as well as globally, so a file that is
exactly aligned in winter and summer at *different* shifts is reported as internally
DST-inconsistent instead of being given a single misleading "best" shift.

Arbiter validity: the M1 leg is `PASS_EXACT` against canonical DEV_002 M1 on 43 292/43 292
bars, and `historical_replay.utc_export_csv_loader.load_utc_export_csv` reproduces the
DEV_002 M1 series exactly — so the UTC loader is correct for the `timestamp_utc` CSV
family and the mismatches below are properties of the **data**, not of the loader.

### H1 sources (exact-match rate against M1-derived H1 buckets)

| Source | Rows | Best shift | Exact rate | DST | Verdict |
| --- | --- | --- | --- | --- | --- |
| `EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv` | 9 817 | **+0h** | **1.000000** | CONSISTENT | **ALIGNED** |
| `SSC_V1_0_1_G2_DEV_001::H1` | 723 | **+0h** | **1.000000** | CONSISTENT | **ALIGNED** |
| `SSC_V1_0_1_G2_DEV_002::H1` | 9 843 | +0h | 0.616499 | **INCONSISTENT** | **MISALIGNED** |
| `SSC_HYP002_H1_WARMUP_CONTEXT::H1` | 1 128 | +3h | 0.776596 | n/a | **MISALIGNED** |
| `SSC_FRESH_DEV_GEN_002::H1` | 744 | +3h | 0.783602 | n/a | **MISALIGNED** |
| `HYP_002_EVALUATION_INPUT::H1` | 1 872 | +3h | 0.779380 | n/a | **MISALIGNED** |

`SSC_V1_0_1_G2_DEV_002::H1` is the sharpest finding: its **winter** bars are exactly
aligned at **−1h** (rate 1.000000 over 1 992 buckets) while its **summer** bars are
exactly aligned at **0h** (rate 1.000000 over 1 584 buckets). One file, two different
offsets, neither of them a constant: the file mixes a DST-shifted segment with an
unshifted one, so no single whole-hour shift can describe it. Its published coverage
interval (`2025-01-01T21:00Z → 2026-08-02T23:00Z`) is therefore not one coherent time
base. The misaligned legs sit consistently at ~+3h (the broker's summer wall clock), which
is the signature of a wall-clock value persisted without the per-week normalization the
repo's own authority performs.

### M15 sources

| Source | Rows | Best shift | Exact rate | Verdict |
| --- | --- | --- | --- | --- |
| `EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202607310000.csv` | 39 265 | **+0h** | **1.000000** | **ALIGNED** |
| `EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202606192345.csv` | 36 480 | **+0h** | **1.000000** | **ALIGNED** |
| `EXTERNAL_D_ROOT::EURUSD_M15_202601020000_202606192345.csv` | 11 616 | **+0h** | **1.000000** | **ALIGNED** |
| `EXTERNAL_D_ROOT::EURUSD_M15_202606220000_202607312345.csv` | 2 880 | **+0h** | **1.000000** | **ALIGNED** |
| `SSC_V1_0_1_G2_DEV_001::M15` | 2 892 | **+0h** | **1.000000** | **ALIGNED** |
| `SSC_V1_0_1_G2_DEV_002::M15` | 2 892 | **+0h** | **1.000000** | **ALIGNED** |
| `SSC_FRESH_DEV_GEN_002::M15` | 2 976 | +3h | 0.778562 | **MISALIGNED** |

### Timezone-consistent three-way intersection (H1 ∩ M15 ∩ M1)

```
2025-09-14T21:02:00Z -> 2026-08-03T00:00:00Z   =  322.124 days
limiting timeframe: H1
```

**Not the requested one year (365 days).** Consequences:

- The window `2025-09-15T00:00:00Z → 2026-09-14T23:59:59Z` **cannot be replayed** with
  mutually consistent legs. `2026-08-03T00:00Z → 2026-09-14T23:59:59Z` (42.998 days) has
  **no timezone-consistent H1 leg at all and no timezone-consistent M15 leg at all**.
- `2026-09-14` — the window's last full day — is covered only by the misaligned
  `SSC_FRESH_DEV_GEN_002` package, whose own internal evidence contradicts its manifest:
  the package is **internally inconsistent**. Its `EURUSD_H1.csv` reproduces its own
  `EURUSD_M1.csv` aggregated to H1 exactly (1.000000) and its `EURUSD_M15.csv` reproduces
  its own M1 aggregated to M15 exactly (1.000000), yet that M1 disagrees with the
  canonical M1 leg (0.795 at −3h). Its manifest declares
  `timezone_status: VERIFIED` / *"timestamps persisted as UTC without transformation"* —
  falsified by its own M1 leg. Its `parity_diagnostic` compares H1-against-H1
  (`ohlc_mismatches: 0` over 744 bars), which is tautological and is why the defect passed
  unnoticed.
- `SSC_V1_0_1_G2_DEV_002::H1`'s last bar `2026-08-02T23:00Z` already lies inside the
  consumed interval, so the 322.124-day aligned span is bounded by the same DST-inconsistent
  file the frozen G2 population used.

Per R3's explicit instruction, DST is **descriptive only**: no trade was selected or
removed on the basis of DST outcomes, and DST was not used as a filter. It is used here
only as the diagnostic that exposes the file-level defect. No fixed +3h conversion was
applied to anything.

---

## R4 — Lineage / contamination map

Reproduced from the frozen `LINEAGE_CONTAMINATION_MAP_V1.json` (registry head
`101488f73fd6cc5b0d5d642beccab81c23141bb0`).

```
DATA_ROLE = HISTORICAL_RESEARCH_ONLY
INDEPENDENT_VALIDATION = false
```

| Field | Value |
| --- | --- |
| `consumed_campaigns_overlapping_primary_window` | `DEV_001, DEV_002, GEN_001, GEN_002, GEN_002A, HYP_001, HYP_002, Route B` |
| `DEV002_OVERLAP` | **100 %** of DEV_002's interval (`2025-09-15 → 2026-08-02`, 322.0 days) lies inside the one-year window |
| Double-counting warning | DEV_002 (N = 22) is a **subset** of the window and must never be pooled with a one-year population as additional sample |
| Dataset-identity conflicts | DEV_002 M15/M1 are byte-identical to DEV_001's (one lineage, not two samples) |
| Protected calendar | CONFIRM_001's reserved calendar opens `2026-09-15T00:00:00Z`, i.e. the window's final days are protected confirmation calendar |
| `PROTECTED_DATA_CLEAR` | **true** |

Protected-data firewall: `CONFIRM_001`, `HOLDOUT` and `OOS` were enumerated from metadata
only and **never opened**; `SSC1D_WP1_OOS_EURUSD_2024Q1` `access_count` remains `0`;
`H2` was **not consumed**. No sealed evidence was touched. The requested replay does not
violate the protected-data firewall — it is blocked by data consistency instead, so R4's
STOP condition (protected-data overlap) did **not** fire; R3's did.

---

## R5 — Replay contract freeze

**NOT FROZEN — the mission stopped at R3 before R5.** No `population_id`, no dataset
fingerprint, no outcome-dependent choice was made. Nothing was frozen after outcomes,
because no outcome was generated. The one-year replay contract remains unfrozen by
design: freezing it against a window that is not replayable would be the failure mode the
gate exists to prevent.

---

## R6–R7 — Replay execution and population identity

**NOT EXECUTED.** `RESEARCH_REPLAY_COUNT = 0`. No `run_replay` call was made for this
mission, no `POPULATION_ID` was created, no occurrence count and no population hash exist,
and no determinism run was performed (there is nothing to reproduce).

---

## R8–R13 — Performance, decomposition, regime, excursion, friction, DEV_002

**`NOT_EVALUATED` — no replay, therefore no metric.** Every field is reported as
`NOT_EVALUATED` rather than zero or blank, so nothing can be mistaken for a measured
value:

| Field group | Value |
| --- | --- |
| `N`, `WINS`, `LOSSES`, `BREAKEVEN`, `WIN_RATE` | `NOT_EVALUATED` |
| `GROSS_R`, `GROSS_EXPECTANCY_R`, `GROSS_PF` | `NOT_EVALUATED` |
| `FRICTION_R`, `NET_R`, `NET_EXPECTANCY_R`, `NET_PF` | `NOT_EVALUATED` |
| `MAX_DRAWDOWN_R`, `STDDEV_R`, `SE_R`, `CI90`, `CI95` | `NOT_EVALUATED` |
| `SETUPS` (S1/S2/S3), `DIRECTIONS` (LONG/SHORT), `SESSIONS` (ASIAN_LONDON/LONDON_NEWYORK) | `NOT_EVALUATED` |
| `MONTHLY`, `QUARTERLY`, `DST_REGIMES` | `NOT_EVALUATED` |
| `MFE_MAE` (MFE_R, MAE_R, stop-first rate, partial/runner activation, efficiency) | `NOT_EVALUATED` |

**R12 friction note (recorded so it is not misread later):** the friction model remains
`MODELED` (`session_sweep_continuation.friction`, `cost_status` MODELED/KNOWN/UNAVAILABLE
only; no broker-evidenced historical spread exists). H2 was **not** consumed early. No
friction figure is quoted, because there is no gross figure to degrade — and per R12,
friction must never be classified as a root cause when gross expectancy is itself
unevaluated.

**R13 DEV_002 comparison.** The frozen DEV_002 baseline is quoted for the record only and
was **not** recomputed: `N = 22`, gross expectancy ≈ −0.245R, net expectancy ≈ −0.469R,
gross PF ≈ 0.563 (`MODELED` friction, 8 wins / 13 losses / 1 breakeven). Because DEV_002
is contained **within** the one-year period, **one-year + DEV_002 must not be pooled as
independent samples**, and the five R13 questions (directional consistency, whether
DEV_002 was unusually weak/strong, persistence across calendar periods, concentration in
one setup/session/direction, DST-regime behaviour change) are **`NOT_EVALUABLE`** — they
all presuppose a one-year population that does not exist.

---

## R14 — Capacity / evidence interpretation

1. **OBSERVED ONE-YEAR PERFORMANCE** — none. No replay ran.
2. **STABILITY** — `NOT_EVALUATED`; no monthly/regime series exists.
3. **GENERALIZATION** — nothing can be inferred. The only canonically replayable
   timezone-consistent span is 322.124 days, and it is ~100 % previously-consumed evidence
   (DEV_001/DEV_002/GEN_001/Route B, plus the HYP_001/HYP_002 lanes), so **no result from
   this data could ever be independent confirmation**, and no claim of universal market
   capacity is made or implied. Sample precision (`SE`/`CI`) is `NOT_EVALUATED` because
   `N = 0`.

---

## R15 — Governance

```
G3 CONTRACT_STATUS  = PROPOSED / UNSIGNED / INACTIVE
CANONICAL_G3_VERDICT = NOT_EVALUATED_UNSIGNED_CONTRACT
OPTIMIZATION_ELIGIBLE = false
OPTIMIZATION_RUN      = false
```

Neither contract was signed; `HYP_003` was not created; `HYP_001` and `HYP_002` were not
reopened; no subgroup result was used to optimize (there are none). No parameter search,
no strategy variant, no threshold tuning, no subgroup exclusion and no repeated run
occurred. No mechanism is promoted to a hypothesis: the R3 findings below are listed as
`RESEARCH_OBSERVATIONS_ONLY` and are **not** hypotheses until separately preregistered.

```
RESEARCH_OBSERVATIONS_ONLY (not hypotheses, not preregistered):
  OBS-1  Two frozen SSC dataset packages carry H1/M15 legs that are ~+3h offset from the
         canonical M1 leg (GEN_002, HYP_002 evaluation input, HYP_002 warmup context).
  OBS-2  SSC_V1_0_1_G2_DEV_002::H1 mixes a DST-shifted winter segment with an unshifted
         summer segment; the boundary is 2026-03-01..2026-05-01.
  OBS-3  The GEN_002 package's manifest timezone claim is contradicted by its own M1 leg,
         and its parity_diagnostic compares a timeframe against itself.
```

---

## R16 — Safety / regression

Narrow tests run 2026-09-19 (`.venv`, local, `main` @ `4b36593`):

```
python -m pytest -q --tb=short \
  tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py \
  tests/test_session_sweep_continuation_replay_determinism.py \
  tests/test_svos_ssc_adapter.py tests/test_symbol_metadata_manifest.py \
  tests/test_svos_mt5_isolation.py tests/test_session_sweep_continuation_ema_invariant.py \
  tests/test_session_sweep_continuation_h1_bias.py tests/test_session_sweep_continuation_sessions.py
→ 52 passed in 76.98s

python -m pytest -q --tb=short \
  tests/test_session_sweep_continuation_gap_remediation.py \
  tests/test_session_sweep_continuation_swing_structure.py \
  tests/test_session_sweep_continuation_regime.py \
  tests/test_session_sweep_continuation_setups.py \
  tests/test_session_sweep_continuation_stop_engine.py \
  tests/test_session_sweep_continuation_bias_gate.py
→ 48 passed in 11.50s
```

Coverage: SSC v1.0.1 exit-semantic remediation, replay determinism, SSC adapter parity,
symbol metadata, EMA invariant, H1 bias, session windows, warmup/gap remediation,
swing structure, regime, setups, stop engine, bias gate, MT5 isolation.

```
STRATEGY_CHANGED=false            PARAMETERS_CHANGED=false
BROKER_MUTATION=false             DEMO_ORDER=false
LIVE_ORDER=false                  OPTIMIZATION_RUN=false
PROTECTED_DATA_ACCESSED=false     EXECUTION_AUTHORITY_CHANGED=false
CONFIRMATION_ACCESSED=false       HOLDOUT_ACCESSED=false
OOS_ACCESSED=false                H2_CONSUMED=false
VIRTUAL_BROKER_STARTED=false      SSC_REPLAY_EXECUTED=false
```

No order was placed; no broker/gateway call was made; no demo/live authorization or
lifecycle/registry file was touched. `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`
is byte-unchanged.

---

## R17 — Output

```
SSC_V1_0_1_ONE_YEAR_HISTORICAL_REPLAY_STATUS

REPOSITORY
  HEAD_BEFORE = 4b365934d1c2be2702a8d34eadb4c6d1fe39c409
  HEAD_AFTER  = recorded in the commit adding this document (nothing pushed)
  COMMIT      = 4b36593

AUTHORITY
  STRATEGY        = ST_SESSION_SWEEP_CONTINUATION_V1
  VERSION         = 1.0.1
  CANONICAL_REPLAY= session_sweep_continuation.replay.run_replay
  SEMANTIC_PARITY = PASS (historical == forward == run_replay; exit semantics OPPOSITE_SESSION_BOUNDARY)

DATASET
  WINDOW              = 2025-09-15T00:00:00Z -> 2026-09-14T23:59:59Z
  H1_HASH             = NOT_FROZEN (per-source hashes in the coverage audit; no single frozen H1 leg exists)
  M15_HASH            = NOT_FROZEN (per-source hashes in the coverage audit)
  M1_HASH             = 50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a
  RAW_SOURCE_HASH     = 3fdd97cfba62c37251f401c9e357833da4df3da48729d8edf9363ef2a6fe7fdd
  DATASET_FINGERPRINT = NOT_FROZEN
  TIMEZONE_AUTHORITY  = BROKER_SERVER_TIME(UTC+2/UTC+3 seasonal, per-week reopen) -- PASS for M1;
                        CROSS_LEG_CONSISTENT = false
  WARMUP              = PASS (4 377 / 4 382 closed H1 bars before the first decision point; required 1 000)

LINEAGE
  DATA_ROLE            = HISTORICAL_RESEARCH_ONLY
  INDEPENDENT_VALIDATION = false
  DEV002_OVERLAP       = 100% of DEV_002's interval inside the window
  PROTECTED_DATA_CLEAR = true

REPLAY
  POPULATION_ID        = NOT_CREATED
  RESEARCH_REPLAY_COUNT= 0
  N                    = NOT_EVALUATED
  POPULATION_HASH      = NOT_CREATED
  DETERMINISM          = NOT_EVALUATED

PERFORMANCE
  WINS/LOSSES/BREAKEVEN/WIN_RATE                        = NOT_EVALUATED
  GROSS_R/GROSS_EXPECTANCY_R/GROSS_PF                   = NOT_EVALUATED
  FRICTION_R/NET_R/NET_EXPECTANCY_R/NET_PF              = NOT_EVALUATED
  MAX_DRAWDOWN_R/STDDEV_R/SE_R/CI90/CI95                = NOT_EVALUATED
  SETUPS/DIRECTIONS/SESSIONS/MONTHLY/QUARTERLY/DST_REGIMES = NOT_EVALUATED
  MFE_MAE                                              = NOT_EVALUATED

DEV002_COMPARISON = INSUFFICIENT_COMPARABILITY (no one-year population exists)

G3
  CONTRACT_STATUS  = PROPOSED / UNSIGNED / INACTIVE
  CANONICAL_VERDICT= NOT_EVALUATED_UNSIGNED_CONTRACT

OPTIMIZATION
  ELIGIBLE = false
  RUN      = false

FORWARD
  STARTED = false

EXECUTION
  BROKER_MUTATION=false  DEMO_ORDER=false  LIVE_ORDER=false

FINAL_STATUS = BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT
NEXT_SINGLE_ACTION = Obtain (or authoritatively re-derive) timezone-consistent EURUSD H1 and
                     M15 legs spanning 2026-08-03T00:00:00Z -> 2026-09-14T23:59:59Z -- the only
                     gap between the current aligned intersection and the requested one-year
                     window -- then re-run
                     `python scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py`
                     and require CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW before the replay
                     mission is attempted again. The G2 DEV_002 H1 DST inconsistency (OBS-2)
                     is a separate, pre-existing evidence-integrity question for owner
                     governance and is NOT adjudicated by this mission.
```

---

## New durable gate (mission deliverable)

`scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` — read-only, deterministic,
no replay, no writes. It closes the gap that let the coverage audit return
`DATA_COVERAGE_COMPLETE` for a non-replayable window: it arbitrates every admissible
H1/M15 source against the M1 fill-resolution authority, judges alignment per DST season,
excludes non-exactly-aligned legs rather than repairing them, and computes the
timezone-consistent three-way intersection. It returns exit 0 only for
`CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW`; here it returns exit 1 with
`BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT` and the aligned span `2025-09-14T21:02:00Z →
2026-08-03T00:00:00Z` (322.124 days). The coverage audit should be read as a
necessary-but-not-sufficient precondition and this gate as its required companion.

## FINAL_STATUS

`BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT` — the requested one-year window is not
replayable: the admissible H1/M15 legs and the canonical M1 leg do not share a time base,
so the timezone-consistent three-way intersection is 322.124 days rather than 365, and the
final 42.998 days of the window have no timezone-consistent H1 or M15 leg at all. The
mission stopped at R3, before the R5 contract freeze and before the single R6 replay. No
population, no performance metric and no economic verdict exist.
