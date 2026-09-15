# HYP_001_GBPUSD_REPLICATION_R1 -- Preregistration (FROZEN 2026-09-15)

Status: **FROZEN.** Section 8's minimum_N=20 and decision rule were explicitly
approved by the owner (in-session, via AskUserQuestion, 2026-09-15) exactly as
proposed, before any GBPUSD setup detection or outcome inspection occurred. A
GBPUSD H1 symbol-metadata manifest (required for H1 bias resolution) was separately
authorized by the owner in the same session -- see
`config/historical_datasets/GBPUSD_H1_WARMUP_PLUS_R1_symbol_metadata.yaml`. This
document remains a **cross-symbol replication** lane for the already-frozen
HYP_001_EXIT_CAPTURE mechanism -- it does **not** modify, gate, accelerate, or
substitute for HYP_001's own EURUSD `CONFIRM_001` fresh-confirmation track (still
`WAITING_FOR_DATA`, earliest acquisition 2026-10-13T00:00:00Z, entirely untouched by
this document).

Gate 2 (population generation + sample-adequacy check) has since been run against
this frozen protocol: `TREATMENT_N=15 < minimum_N=20` -->
`INCONCLUSIVE_INSUFFICIENT_SAMPLE` (see
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_GBPUSD_REPLICATION_R1/sample_adequacy.json`).
Per Section 8's frozen adequacy gate, no economic evaluation may be performed on this
population, and no field in Sections 1-10 may now be edited (a new lane ID and a new
preregistration would be required for any future attempt on a different window).

## 0. Why this lane exists / evidence-independence check

A repository-wide inventory (this session) found: `SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914`'s
GBPUSD side was admitted (`FULL_PASS`) alongside its EURUSD side, but -- unlike the
EURUSD side, which HYP_002 consumed -- **the GBPUSD side was never drawn into any
occurrence population for any hypothesis.** This was independently re-verified this
session against GEN_002A (`ST_SESSION_SWEEP_CONTINUATION_V1`'s only other GBPUSD
population, `artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_002A/input_manifest.json`,
committed only on `refactor/architecture-boundary-hardening-v3`): its `date_start`/
`date_end` are **2026-06-08 / 2026-07-30** -- entirely before, with zero overlap
against, the 2026-08-03..2026-09-14 window this document proposes to use.

```
candidate_interval        = 2026-08-03T00:00:00Z -> 2026-09-14T23:59:59Z
GEN_002A (GBPUSD, earlier) = 2026-06-08 -> 2026-07-30  -- NO OVERLAP
GEN_002 EURUSD side        = same admission event, EURUSD only consumed by HYP_002
GEN_002 GBPUSD side        = SAME ADMISSION, NEVER CONSUMED  <- this document's target
overlap_with_any_consumed_SSC_evidence = NONE FOUND
```

This is why this lane is the fastest currently executable path: the data is already
downloaded, admitted, hash-verified, and gap-checked (`FRESH_DATA_ADMISSION/
SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914_ADMISSION.json`, `GBPUSD_status.admission
= PASS`) -- no new MT5 acquisition, no waiting for a future calendar boundary.

## 1. Identity

```
lane_id             = HYP_001_GBPUSD_REPLICATION_R1
role                = CROSS_SYMBOL_REPLICATION (never EXTERNAL_GENERALIZATION_EVIDENCE
                      until/unless a PASS result is obtained -- see Section 9)
parent_strategy_id  = ST_SESSION_SWEEP_CONTINUATION_V1
parent_version      = 1.0.0
parent_config_hash  = e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf
candidate_version   = 1.1.0
candidate_manifest  = artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/
                      V1_1_0_CANDIDATE_SPEC/candidate_manifest.json
                      (sha256 03dfed8ae45751bdbe3743e3a7c8ea7587c3a53fa73c6fdd418060f29dc0bb13)
mechanism_inherited_from = HYP_001_EXIT_CAPTURE_PREREGISTRATION.md
                      (sha256 03ed06c68e169893b3172917f4cadf369d52e47f6b8ed5ea2c2f620a13388529)
                      -- CONTROL/TREATMENT values, semantic delta, and provenance
                      limitation are inherited verbatim from that document (Section 2
                      below), not re-derived or re-selected for GBPUSD.
```

## 2. Explicit non-gating declaration

```
gates_HYP_001_EURUSD_status         = false
counts_toward_CONFIRM_001/002/003   = false
counts_toward_minimum_N=20_EURUSD_rule = false
a_PASS_here_means                   = supporting cross-symbol evidence for the exit-
                                       capture MECHANISM only -- never "HYP_001 is
                                       confirmed" and never a substitute for the
                                       EURUSD-specific frozen confirmatory protocol.
a_FAIL_here_means                   = the mechanism does not replicate on GBPUSD in
                                       this window -- does not by itself falsify the
                                       EURUSD track, which remains governed entirely
                                       by its own already-frozen protocol.
```

## 3. Historical provenance -- inherited limitation, restated

Per `HYP_001_EXIT_CAPTURE_PREREGISTRATION.md` Section 2: `runner_target_r=1.5` is
**not** the historical empirical optimum (0.5R was, on the *original* GEN_002A
GBPUSD population, 2026-06-08..07-30) and no committed document explains why 1.5R was
frozen over the empirically better value. This replication lane inherits that same
already-declared candidate value for consistency (testing the SAME frozen treatment
on a new symbol, not re-selecting a value per symbol) -- it does not re-litigate or
repair that limitation, and does not claim 1.5R is optimal for GBPUSD either.

## 4. Control / Treatment (deterministic, inherited)

```
CONTROL   = trade_management.runner_target_r = 3.0 (FIXED_R), all other semantics as
            frozen in strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml v1.0.0.
TREATMENT = trade_management.runner_target_r = 1.5 (FIXED_R). Every other field
            byte-identical to CONTROL (independently diff-verified for the underlying
            spec; the diff itself is symbol-independent since it is a YAML/config
            diff, not a per-symbol computation).
```

Both derived from ONE canonical GBPUSD occurrence population (Section 6), exactly the
same nested, same-population method used for EURUSD HYP_001 and for HYP_002.

## 5. Dataset / symbol

```
symbol              = GBPUSD
dataset_package_id  = SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914 (GBPUSD side only)
window              = 2026-08-03T00:00:00Z -> 2026-09-14T23:59:59Z (frozen, verbatim,
                      never widened/shortened/shifted after this point)
admission_status    = FULL_PASS (already verified; see FRESH_DATA_ADMISSION/
                      SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914_ADMISSION.json)
raw_sha256_H1       = d77f447d8da6c2543874df9c65eeccada3f28cb333b9f783fd9d63b016b0a335
raw_sha256_M15      = 71a67d9d6dd984395e98473d9e265508b6bde32eeeb60c6331d4a6dad8ab3636
raw_sha256_M1       = 41a403a738060131f2be40d16cd048dd5161c934bb1bdc2f2d06f2a46862ef30
holdout_overlap     = ZERO (no SSC holdout exists for any symbol; see
                      POST_JULY31_CONSUMPTION_AUDIT/consumption_audit.json
                      Section "holdout_overlap_status")
instruments_config  = candidate_spec.yaml already lists `instruments: [EURUSD,
                      GBPUSD]` -- GBPUSD requires no strategy-semantic addition.
friction_config     = GBPUSD already present, unchanged, in both v1.0.0 and v1.1.0:
                      default_spread_pips 1.4, default_commission_pips 0.2,
                      default_slippage_pips 0.4.
```

## 6. Population contract (identical method to HYP_001 EURUSD, Section 5 there)

ONE canonical GBPUSD occurrence population generated using the frozen v1.0.0 entry/
stop/setup/regime/friction semantics; CONTROL and TREATMENT derived from it by
applying two exit policies to each occurrence's own resolution window. The P11
counterfactual-dependency audit already performed for EURUSD HYP_001 (traced through
`campaign.py`/`state_machine.py`: `block_new_entries_after_realized_r_enabled=false`
in both versions; no outcome-triggered invalidation wired into the replay path)
applies identically here -- it is a property of the strategy engine, not of the
symbol.

## 7. Warmup

```
requirement  = STRUCTURE_WARMUP_H1_BARS=1000, unchanged.
candidate    = GBPUSD H1 history for GEN_002A's own window (2026-06-08..07-30) or any
               earlier GBPUSD H1 admitted for this strategy family -- reuse preferred
               over new acquisition, exact source TO BE CONFIRMED by whichever
               mission actually generates this population. WARMUP_CONTEXT_ONLY: zero
               occurrence/economic contribution.
```

## 8. Primary metric / decision rule -- OWNER APPROVED 2026-09-15

Approved by the owner in-session (AskUserQuestion, 2026-09-15), exactly as proposed,
before any GBPUSD population was generated:

```
primary_metric  = net_expectancy_R (mean net R per resolved occurrence)
comparison      = delta_net_expectancy_R = TREATMENT_net_expectancy_R
                                            - CONTROL_net_expectancy_R
minimum_N       = TREATMENT_N >= 20
PASS            = TREATMENT_N>=20 AND TREATMENT_net_expectancy_R>0
                   AND delta_net_expectancy_R>0
FAIL            = TREATMENT_N>=20 AND (TREATMENT_net_expectancy_R<=0
                   OR delta_net_expectancy_R<=0)
INCONCLUSIVE    = TREATMENT_N<20  -->  INCONCLUSIVE_INSUFFICIENT_SAMPLE
```

**Actual Gate-2 result (2026-09-15): `TREATMENT_N=15 < 20` --> `INCONCLUSIVE_INSUFFICIENT_SAMPLE`.**
No economic evaluation was performed -- Section 8's own frozen rule required stopping
here.

## 9. Result labelling (mission P4)

```
IF PASS  -> label CROSS_SYMBOL_REPLICATION: SUPPORTED (never "HYP_001 confirmed",
            never promotes GBPUSD to any execution authority)
IF FAIL  -> label CROSS_SYMBOL_REPLICATION: NOT_SUPPORTED (does not, by itself,
            falsify EURUSD HYP_001)
IF INCONCLUSIVE -> label CROSS_SYMBOL_REPLICATION: INSUFFICIENT_SAMPLE
```

A SUPPORTED result may, after separate owner review, be cited as
`EXTERNAL_GENERALIZATION_EVIDENCE` alongside (never instead of) the EURUSD
confirmatory track. It never grants demo/live authority on its own.

## 10. Firewalls (unchanged from HYP_001's own)

```
holdout_run_count required = 0 (no SSC holdout exists to access)
EURUSD CONFIRM_001 track    = untouched by this lane
strategy semantics          = unchanged (verified by diff, Section 4)
demo_eligible/demo_authorized/live_authorized = false, unaffected by this lane
```

## 11. Verdict

`HYP_001_GBPUSD_REPLICATION_R1_PREREGISTRATION_STATUS: FROZEN (2026-09-15).`

`HYP_001_GBPUSD_REPLICATION_R1_RESULT: INCONCLUSIVE_INSUFFICIENT_SAMPLE (Gate 2,
2026-09-15) -- TREATMENT_N=15 < minimum_N=20. Terminal for this population per this
document's own frozen rule. No economic evaluation was, or may now be, performed on
it. GBPUSD raw data used: 2026-08-03..2026-09-14 (already admitted, zero new
consumption of any other symbol/window). EURUSD HYP_001/CONFIRM_001 unaffected.`
