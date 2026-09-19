# SSC_ONE_YEAR_CROSS_LEG_AUTHORITY_REMEDIATION_STATUS

ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1 — one-year H1/M15 authority remediation
(A0–A9). Date: 2026-09-20. Environment: local Windows workstation, `.venv`, repository
`D:\ddev\AG profit trading`, branch `main`. Mode: DATA-INTEGRITY REMEDIATION ONLY — no SSC
replay, no optimization, no strategy change.

**FINAL_STATUS = `CROSS_LEG_TIMEZONE_BLOCKER_RESOLVED`.** The blocker is resolved by
deriving H1 and M15 deterministically from the already-frozen native MT5 M1 authority, so
all three legs share one time base by construction. The derivation is admitted on exact
reference parity (rate **1.000000**, zero mismatches, zero unreproduced reference bars),
and the companion cross-leg gate now returns `CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW`
at **zero shift** over **365.999 days**.

No SSC replay was executed. No strategy, parameter or config was changed. No optimization
ran. Pre-existing DEV_002 / GEN_002 / HYP_002 evidence was **not** rewritten.

---

## A0 — Preflight

| Item | Value |
| --- | --- |
| Branch | `main` |
| HEAD_BEFORE | `a88f023165bf3349c53dfa11d036ce8e11c46a28` |
| Commit `a88f023` present in ancestry | **YES** — it *is* HEAD |
| Foreign WIP | **DETECTED and preserved untouched** — modified `src/historical_replay/__init__.py`, `src/historical_replay/candle_store.py`, `state/proposal_ledger/proposal_ledger.json`; untracked `src/historical_replay/evaluation_context.py`, `src/replay_evaluation/`, `tests/test_td8e_evaluation_context.py`, Large-SMC friction-campaign sessions, `journal/reports/btc/2026/2026-09-18.json`. None staged, none modified. |
| SSC replay executed | **false** |

Sources read (not modified): the one-year M1 acquisition evidence
(`SSC_V1_0_1_HIST_1Y_M1_001/acquisition_provenance.json`), `DATA_COVERAGE_AUDIT_V1.json`,
`LINEAGE_CONTAMINATION_MAP_V1.json`, the cross-leg consistency gate, the SSC v1.0.1
strategy authority (`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`,
`src/session_sweep_continuation/`), and the existing historical-dataset derivation
conventions (`src/historical_replay/resampler.py`,
`docs/specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md`,
`docs/status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md`).

---

## A1 — Derivation legitimacy: **ADJUDICATED AUTHORIZED**

The mission's own STOP condition (`OWNER_DERIVED_HIGHER_TIMEFRAME_AUTHORIZATION_REQUIRED`)
did **not** fire. The repository already permits deterministic lower→higher timeframe
aggregation for historical analysis, and the authority chain
`NATIVE MT5 M1 → deterministic M15 → deterministic H1` uses that existing convention
rather than inventing one.

Evidence:

| Source | Statement |
| --- | --- |
| `src/historical_replay/resampler.py` | module docstring: *"Deterministic single-feed resampling … derive M15/H1/H4/D1 from one base feed (M5, **or M1 when available**) rather than independently loading separate per-timeframe files. A derived bar is included ONLY when every one of its constituent base bars is present … never fabricated"*; `resample()` is the implementation, with UTC-boundary-aligned buckets. |
| `docs/specs/SMC_3X3_HISTORICAL_VALIDATION_V1_SPEC.md:134` | *"`src/historical_replay/resampler.py` — `resample`: derives M15/H1/H4/D1 from the one [base feed]"*; `:147` — *"CLI wrapper: load → derive timeframes → replay"*. |
| `docs/status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md:92-94` | *"RESAMPLING = src/historical_replay/resampler.py::resample — single base feed (M5) -> M15/H1/H4/D1, UTC-boundary-aligned …, INCOMPLETE windows dropped, never fabricated"*; `:73` — *"M1 preferred by spec IF 'sufficiently long'"*. M1 is now the longest-reaching leg in the repository (373 421 bars over 365 days), so the spec's own preference condition is satisfied. |
| `docs/status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md:179-181` | H1 parity precedent: comparing `resample(..., "H1")` against the native H1 export gave *"**zero** [mismatches]"*, and *"whole-hour offsets preserve hour boundaries, so plain UTC bucketing is correct for H1 (and M15)"*. |
| `tests/test_resampler.py`, `tests/test_resampler_broker_aligned.py` | 16 passing tests (verified in this mission). |
| `src/historical_replay/candle_store.py` | `TIMEFRAME_MINUTES` includes `"M1": 1`, so M1 is a supported base timeframe. |

Ten scripts already consume `resampler.resample` (`run_historical_replay.py`,
`run_discovery_backtest.py`, `run_large_smc_discovery.py`, `run_session_sweep_continuation_replay.py`, …).

**Not performed, and explicitly prohibited by the contract:** interpolating missing M1;
deriving M1 from M5/M15; altering prices; synthesizing intra-minute paths; applying any
shift correction.

---

## A2 — Derivation contract (frozen and hashed BEFORE any output)

`DERIVATION_CONTRACT_HASH = 4a0ccd05070359cb3558e9ce06297eb480722f3a3bbcaa283c3e144d0c1b0b88`

| Field | Value |
| --- | --- |
| `SOURCE_DATASET` | `SSC_V1_0_1_HIST_1Y_M1_001` |
| `SOURCE_SHA256` | `50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a` (**re-verified from bytes**) |
| `DERIVED_TIMEFRAMES` | `M15`, `H1` |
| `TIME_AUTHORITY` | normalized UTC from canonical M1 (measured, per-week reopen) |
| `BUCKET_AUTHORITY` | exact UTC floor — M15 → 15-minute boundary, H1 → 1-hour boundary; broker wall-clock buckets used = **false** |
| `OPEN` | first M1 open by M1 timestamp |
| `HIGH` | max M1 high |
| `LOW` | min M1 low |
| `CLOSE` | last M1 close by M1 timestamp |
| `VOLUME` | sum of M1 volumes present; `None` when no member carries a volume |
| `INCOMPLETE_BUCKET_POLICY` | **`NATIVE_FAITHFUL_INCLUSIVE`** (defined below, before generation) |

### Incomplete-bucket policy — defined before output, adjudicated by measurement

The policy was frozen before any dataset was generated, and it is the **only** deliberate
departure from `resampler.resample`'s default rule. That default drops any bucket not
holding every expected base bar ("incomplete windows dropped"). Applied to M1 it silently
deletes **418 real H1 bars and 452 real M15 bars** of the window, because a bucket at a
weekly open, a daily rollover break, or a holiday is legitimately short — and MT5's own
native candles are short there too.

`NATIVE_FAITHFUL_INCLUSIVE`: a bucket is emitted when it holds at least one M1 bar, and
its OHLC is aggregated from exactly the M1 bars present.

The choice was made by measurement against the broker's own native candles, **not** by
preference and **not** after seeing any strategy result:

| Reference (native MT5 / frozen package) | Policy A (strict) | Policy B (**adopted**) |
| --- | --- | --- |
| `EXTERNAL_D_ROOT` H1 | mismatch 0 but **366 native bars unreproduced** | mismatch **0**, reference-only **0** |
| `DEV_001::H1` | mismatch 0 but **48 native bars unreproduced** | mismatch **0**, reference-only **0** |
| `EXTERNAL_D_ROOT` M15 | mismatch 0 but **400 native bars unreproduced** | mismatch **0**, reference-only **0** |
| `DEV_001::M15` / `DEV_002::M15` | mismatch 0 but **49 native bars unreproduced** each | mismatch **0**, reference-only **0** |

This is not fabrication: no bar is invented (a bucket exists only where the M1 authority
has bars), no price is altered or synthesized, no missing M1 is filled, and a genuinely
closed market produces no bucket because it has no M1 bars.

---

## A3 — Derived without strategy access

`src/historical_replay/m1_derivation.py` imports only `datetime`, `collections` and
`strategy_engine.session.candles.Candle`. It does **not** import SSC setup logic, bias
logic, the outcome resolver, any economic evaluator, or optimization code — asserted by a
dedicated unit test (`test_derivation_module_imports_no_strategy_or_optimization_code`).
No strategy outcome influenced dataset construction.

---

## A4 — Validation against trusted overlap

References are the sources the cross-leg gate independently found exactly aligned (0h) with
the canonical M1 authority. They were used **for comparison only**, never as inputs.
Requirement: timestamp / open / high / low / close equality on common complete buckets.

| Timeframe | Reference | N compared | Missing buckets | OHLC mismatches | Exact-match rate |
| --- | --- | --- | --- | --- | --- |
| M15 | `EXTERNAL_D_ROOT::EURUSD_M15_202501020000_202607310000.csv` | 21 792 | **0** | **0** | **1.000000** |
| M15 | `SSC_V1_0_1_G2_DEV_001::M15` | 2 892 | **0** | **0** | **1.000000** |
| M15 | `SSC_V1_0_1_G2_DEV_002::M15` | 2 892 | **0** | **0** | **1.000000** |
| H1 | `EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv` | 5 448 | **0** | **0** | **1.000000** |
| H1 | `SSC_V1_0_1_G2_DEV_001::H1` | 723 | **0** | **0** | **1.000000** |

`EXACT_MATCH_RATE = 1.0` as expected. The aggregation rules were **not** modified after
seeing this result — the policy was fixed and hashed in A2, and the strict-rule comparison
above was run before adoption specifically to justify the choice.

---

## A5 — Full-year quality

| Field | M15 | H1 |
| --- | --- | --- |
| first timestamp | `2025-09-14T21:00:00Z` | `2025-09-14T21:00:00Z` |
| last timestamp | `2026-09-15T21:00:00Z` | `2026-09-15T21:00:00Z` |
| row count | 24 961 | 6 241 |
| duplicates | 0 | 0 |
| non-monotonic rows | 0 | 0 |
| invalid OHLC | 0 | 0 |
| off-UTC-boundary rows | 0 | 0 |
| incomplete buckets (included by policy) | 452 | 418 |
| complete buckets | 24 509 | 5 823 |
| non-native steps (weekend/rollover closures) | 54 | 54 |
| largest step | 49.25 h | 50.0 h |
| `SHA256` | `c9833427404d8634d8cf57b000017ecea7ad865ab22db4eadedacb80de9b6956` | `4eb522945697773ed34d1b8d47ab928b9e94e99828dade88db18fe186905e288` |
| quality status | **PASS** | **PASS** |

No genuine market closure was filled. The short buckets are distributed across the broker's
own rollover/maintenance hours (`00, 02, 03, 04, 07, 11, 20, 21, 22, 23` UTC) and are the
weekly-open/rollover boundaries — the same places the native references have short candles.

`COMBINED_DATASET_FINGERPRINT = b40c76ae8635070b1cf49c6f11b5aeb29bc28293966167c1528b2695babca605`

Derivation determinism: re-running the driver reproduced **byte-identical** SHA-256 values
for both legs and the combined fingerprint.

---

## A6 — Cross-leg consistency

`python scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` → **exit 0**

```
FINAL_STATUS = CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW
```

| Field | Value |
| --- | --- |
| derived H1 vs M1 arbiter | best shift **+0h**, exact rate **1.000000**, DST_CONSISTENT |
| derived M15 vs M1 arbiter | best shift **+0h**, exact rate **1.000000**, DST_CONSISTENT |
| three-way intersection | `2025-09-14T21:02:00Z` → `2026-09-15T21:01:00Z` |
| coverage | **365.999 days** (was 322.124 days) |
| limiting timeframe | M1 (i.e. no leg truncates the window any more) |
| shift correction applied | **none** — the correct shift is **0** |

The requested window `2025-09-15T00:00:00Z → 2026-09-14T23:59:59Z` is now fully contained
inside a timezone-consistent H1 ∩ M15 ∩ M1 intersection.

**Honesty note (built into the gate).** The derived legs are produced *from* the M1
arbiter, so their alignment with it is guaranteed **by construction** and is *not*
independent corroboration of the arbiter's own alignment. The gate reports them separately
and lists the independent (non-derived) corroboration explicitly:

```
independent corroboration H1 : EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv,
                               SSC_V1_0_1_G2_DEV_001::H1
independent corroboration M15: EXTERNAL_D_ROOT::EURUSD_M15_* (4 files),
                               SSC_V1_0_1_G2_DEV_001::M15, SSC_V1_0_1_G2_DEV_002::M15
```

Those independent legs are exactly what A4 validated the derivation against at rate 1.0 —
so the derivation is corroborated by *independent* sources, not only by itself.

---

## A7 — Lineage

```
NATIVE MT5 M1 BROKER AUTHORITY   (SSC_V1_0_1_HIST_1Y_M1_001, sha256 50beb42a..)
        |
        v
M15 DETERMINISTIC DERIVED DATASET (SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001, sha256 c9833427..)
        |
        v
H1  DETERMINISTIC DERIVED DATASET (SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001, sha256 4eb52294..)
```

| Field | Value |
| --- | --- |
| `DATA_ROLE` | `HISTORICAL_RESEARCH_INPUT_ONLY` |
| `DERIVATION_CLASS` | `AUTHORIZED_DETERMINISTIC_TIMEFRAME_AGGREGATION` |
| `INDEPENDENT_VALIDATION` | `false` |

Previously consumed data was **not** reclassified as fresh. DEV_002 remains consumed and
overlapping the window; GEN_001 / GEN_002 / GEN_002A / Route B / HYP_001 / HYP_002 remain
consumed. Deriving a *new leg of the same consumed period* creates no new evidence period:
the one-year population still cannot be an independent replication population.

---

## A8 — Pre-existing evidence anomalies: recorded, NOT rewritten

`git status` confirms zero modifications under
`data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002`,
`data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914`,
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002`, or
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_POPULATION`.

Recorded as historical provenance findings (no correction performed here):

| Anomaly | Finding | Status |
| --- | --- | --- |
| `DEV_002_ANOMALY` | `SSC_V1_0_1_G2_DEV_002::H1` is internally DST-inconsistent: winter bars exactly aligned at −1h (rate 1.000000 / 1 992 buckets), summer bars exactly aligned at 0h (rate 1.000000 / 1 584 buckets). One file, two offsets. Its published interval `2025-01-01T21:00Z → 2026-08-02T23:00Z` is therefore not one coherent time base. **PRESERVED, not corrected.** | `DEV002_ANOMALY_PRESERVED = true` |
| `GEN_002_ANOMALY` | `SSC_FRESH_DEV_GEN_002::H1/M15` sit ~+3h from the canonical M1 arbiter (rate 0.7836 / 0.7786), contradicting that package's own manifest claim `timezone_status: VERIFIED` / *"persisted as UTC without transformation"*. Its `parity_diagnostic` compares H1-against-H1 (tautological), which is why the defect passed unnoticed. **PRESERVED, not corrected.** | `GEN002_ANOMALY_PRESERVED = true` |
| `HYP_002_ANOMALY` | `HYP_002_EVALUATION_INPUT::H1` and `SSC_HYP002_H1_WARMUP_CONTEXT::H1` sit ~+3h from the canonical M1 arbiter (rate 0.7794 / 0.7766). **PRESERVED, not corrected.** | recorded |

Correcting any of those campaigns requires a **separate governance mission**. This mission
did not adjudicate, reclassify, re-derive or re-attest them, and its derived dataset does
not supersede or replace them — it is an additional, independently-identified leg set with
its own package id and hashes.

---

## A9 — Safety

```
SSC_REPLAY_EXECUTED=false         STRATEGY_CHANGED=false
PARAMETERS_CHANGED=false          OPTIMIZATION_RUN=false
PROTECTED_DATA_ACCESSED=false     H2_CONSUMED=false
BROKER_MUTATION=false             DEMO_ORDER=false
LIVE_ORDER=false                  PRE_EXISTING_EVIDENCE_REWRITTEN=false
```

`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` is byte-unchanged. No order was placed,
no broker/gateway call was made, no demo/live authorization or lifecycle/registry file was
touched. CONFIRM_001 / HOLDOUT / OOS were not accessed; H2 was not consumed.

Tests run 2026-09-20 (`.venv`, local, `main` @ `a88f023`):

```
python -m pytest -q --tb=short tests/test_ssc_m1_derivation.py
→ 25 passed

python -m pytest -q --tb=short \
  tests/test_resampler.py tests/test_resampler_broker_aligned.py tests/test_ssc_m1_derivation.py \
  tests/test_session_sweep_continuation_v1_0_1_exit_semantic_remediation.py \
  tests/test_session_sweep_continuation_replay_determinism.py tests/test_svos_ssc_adapter.py \
  tests/test_symbol_metadata_manifest.py tests/test_svos_mt5_isolation.py \
  tests/test_session_sweep_continuation_ema_invariant.py tests/test_session_sweep_continuation_h1_bias.py \
  tests/test_session_sweep_continuation_sessions.py
→ 93 passed

python -m pytest -q --tb=short \
  tests/test_session_sweep_continuation_gap_remediation.py \
  tests/test_session_sweep_continuation_swing_structure.py tests/test_session_sweep_continuation_regime.py \
  tests/test_session_sweep_continuation_setups.py tests/test_session_sweep_continuation_stop_engine.py \
  tests/test_session_sweep_continuation_bias_gate.py tests/test_historical_replay_dataset_identity.py
→ 65 passed
```

The new 25 tests lock the derivation **contract**: exact UTC bucket boundaries (including an
explicit broker-wall-clock counter-example), first/max/min/last OHLC aggregation, the
inclusive policy, that an absent market produces no fabricated bucket, that no price is
invented, the quality/fail-closed guards, reference-parity accounting, and module isolation
from strategy code.

---

## A — Output

```
SSC_ONE_YEAR_CROSS_LEG_AUTHORITY_REMEDIATION_STATUS

SOURCE_M1_ID       = SSC_V1_0_1_HIST_1Y_M1_001
SOURCE_M1_SHA256   = 50beb42ad2f65203f3946301eee0e8a435dd6f2067eb4fc0692ebba451d12f8a

DERIVATION_AUTHORITY     = historical_replay.m1_derivation.aggregate_m1
                           (wraps the existing historical_replay.resampler convention;
                            adjudicated AUTHORIZED in A1 -- no new mechanism invented)
DERIVATION_CONTRACT_HASH = 4a0ccd05070359cb3558e9ce06297eb480722f3a3bbcaa283c3e144d0c1b0b88

M15_ID                    = SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::M15
M15_SHA256                = c9833427404d8634d8cf57b000017ecea7ad865ab22db4eadedacb80de9b6956
M15_ROWS                  = 24961
M15_EXACT_REFERENCE_PARITY= 1.000000 (21792 + 2892 + 2892 compared, 0 mismatches, 0 missing)

H1_ID                     = SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001::H1
H1_SHA256                 = 4eb522945697773ed34d1b8d47ab928b9e94e99828dade88db18fe186905e288
H1_ROWS                   = 6241
H1_EXACT_REFERENCE_PARITY = 1.000000 (5448 + 723 compared, 0 mismatches, 0 missing)

TIMEZONE_AUTHORITY = normalized UTC from canonical M1 (measured, per-week reopen; no fixed offset)
BUCKET_AUTHORITY   = exact UTC floor (M15 -> 15-min, H1 -> 1-hour); broker wall-clock buckets NOT used
BUCKET_POLICY      = NATIVE_FAITHFUL_INCLUSIVE (frozen pre-generation, justified by native parity)

COMBINED_DATASET_FINGERPRINT = b40c76ae8635070b1cf49c6f11b5aeb29bc28293966167c1528b2695babca605

FULL_WINDOW       = 2025-09-15T00:00:00Z -> 2026-09-14T23:59:59Z  (contained; 365.999 days available)
CROSS_LEG_STATUS  = CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW  (gate exit 0)
ZERO_SHIFT_PARITY = true  (best shift +0h, exact rate 1.000000 for both derived legs)

DEV002_ANOMALY_PRESERVED = true
GEN002_ANOMALY_PRESERVED = true
HYP002_ANOMALY_PRESERVED = true (recorded)

DATA_ROLE              = HISTORICAL_RESEARCH_INPUT_ONLY
DERIVATION_CLASS       = AUTHORIZED_DETERMINISTIC_TIMEFRAME_AGGREGATION
INDEPENDENT_VALIDATION = false

SSC_REPLAY_EXECUTED = false
PROTECTED_DATA_CLEAR = true

FINAL_STATUS = CROSS_LEG_TIMEZONE_BLOCKER_RESOLVED
NEXT_SINGLE_ACTION = The one-year SSC replay mission (R5 contract freeze, then the single
                     canonical R6 replay) may now be re-attempted against the derived
                     H1/M15 legs plus canonical M1, with the pre-existing caveats intact:
                     DATA_ROLE=HISTORICAL_RESEARCH_ONLY, INDEPENDENT_VALIDATION=false,
                     DEV_002 fully contained in the window and never poolable as extra
                     sample, and G3 still NOT_EVALUATED_UNSIGNED_CONTRACT. This mission
                     does NOT authorize that replay.
```

---

## Deliverables

| Path | Role |
| --- | --- |
| `src/historical_replay/m1_derivation.py` | the derivation module (contract, aggregation, policy, quality/parity checks); imports no strategy code |
| `scripts/derive_ssc_one_year_h1_m15_from_m1.py` | A0–A7 driver; verifies source bytes, freezes+hashes the contract, derives, validates, writes the derived package + evidence |
| `data/research/ssc_fresh_dev/SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001/` | derived dataset package (`raw/EURUSD_H1.csv`, `raw/EURUSD_M15.csv`, `dataset_manifest.json`) in the repository's canonical `timestamp_utc` schema |
| `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_HIST_1Y_001/H1M15_AUTHORITY_REMEDIATION_EVIDENCE_V1.json` | frozen evidence (hashes, census, quality, parity, lineage, safety) |
| `tests/test_ssc_m1_derivation.py` | 25 contract tests |
| `scripts/audit_ssc_v1_0_1_one_year_cross_leg_consistency.py` | extended: registers the derived legs and reports derived vs independent corroboration separately |

## FINAL_STATUS

`CROSS_LEG_TIMEZONE_BLOCKER_RESOLVED` — authoritative H1 and M15 are deterministically
derivable from the frozen native MT5 M1 authority under an existing, documented and tested
repository convention, with exact parity (1.000000) against independent exactly-aligned
references, and the timezone-consistent three-way intersection now spans the full requested
window at zero shift. No SSC replay was executed and no strategy, parameter, optimization or
pre-existing evidence was changed.
