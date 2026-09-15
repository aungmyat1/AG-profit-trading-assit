# HYP_002_SETUP_SELECTIVITY -- Preregistration & Freeze (G1)

Status: **PREREGISTERED, NOT EXECUTED, NOT EXECUTABLE YET.** Committed in writing before
GEN_002 receives any SSC setup detection or outcome inspection. No population generated,
no occurrence generated, no outcome inspected, no parameter optimized, no parent strategy
or execution authority modified. This document resolves the single Stage-1 blocker
recorded in `CURRENT_VALIDATION_STATE.json` (`STOP_OWNER_DECISION_REQUIRED`) using the
owner's direct mechanism definition; nothing here was inferred or invented by the agent.

## 1. Identity

```
hypothesis_id       = HYP_002_SETUP_SELECTIVITY
parent_strategy_id  = ST_SESSION_SWEEP_CONTINUATION_V1
parent_version       = 1.0.0
parent_config_hash   = e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf
parent_raw_sha256    = c92311c3c1789a2ea01495a82a1fbcba1d877a8fb4d9ac46732f39e0b81970a9
parent_source        = strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml @ HEAD ebe8557 (unchanged, verified clean this session)
```

Parent hashes computed with the project's own canonical `compute_config_hash`
(`src/session_sweep_continuation/config.py`) over the parsed YAML, plus a raw-file
SHA-256 for the byte-identical file. Both were recomputed and reconfirmed unchanged in
this session immediately before writing this document.

## 2. Falsifiable claim

Restricting setup admission to S1 (Sweep Reversal) + S2 (Breakout Continuation) only --
excluding S3 (Pullback Continuation) at the admission stage -- produces a genuinely
positive economic improvement over the unrestricted S1+S2+S3 population on the frozen
GEN_002 EURUSD development window, and that improvement is not merely an artifact of a
smaller, lower-variance sample.

Mechanistic rationale (owner-supplied, verbatim intent): test whether requiring a more
immediate session-liquidity/structural confirmation path (S1 sweep reversal or S2
breakout continuation) improves economic quality relative to admitting the broader
S1/S2/S3 setup family. S3 (pullback continuation, the setup class most dependent on a
prior BOS having already occurred earlier in the campaign) is hypothesized to be the
weaker admission path.

This is a **setup-admission change only**. Confirmed unchanged: S1 detector, S2
detector, S3 detector (S3 is not disabled, only excluded from admission), session
definitions, market/regime classification, entry rules, stop geometry, exit rules,
friction model, risk model, occurrence identity scheme, dataset authority, holdout,
execution authority.

## 3. Control / Treatment (deterministic)

```
CONTROL   = S1 + S2 + S3, under the frozen v1.0.0 parent admission rules, unmodified.
TREATMENT = S1 + S2 only. S3 candidates are detected identically (same S3 detector,
            same setups.py logic, setup_model == SetupModel.S3) but REJECTED at the
            admission boundary -- never entered into the TREATMENT occurrence population.
```

CONTROL and TREATMENT are **not independent samples** -- TREATMENT is CONTROL's S1+S2
subset (every TREATMENT occurrence is also a CONTROL occurrence; CONTROL additionally
contains every S3 occurrence). The evaluation in G3/G4 must treat this as a nested
comparison, not two independently-drawn populations. This is recorded now specifically
so it cannot be silently reframed as an independent-sample test later.

Both arms use the identical single frozen population generated once from GEN_002 (see
Section 5) -- CONTROL is the full population; TREATMENT is a deterministic filter
(`setup_model in {S1, S2}`) applied to it. No second detector run, no second admission
pass.

## 4. Population eligibility / development symbol

```
primary_development_symbol = EURUSD
GBPUSD                     = NOT pooled with EURUSD's primary result under any
                              circumstance. If run, GBPUSD is a separate, optional,
                              non-gating replication cohort (Section 12), reported as
                              REPLICATION_SUPPORTED / REPLICATION_NOT_SUPPORTED only.
dataset_package_id  = SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914
dataset_fingerprint = f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa
admission_status    = FULL_PASS (independently byte/hash-verified; see
                       artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/FRESH_DATA_ADMISSION/)
window              = 2026-08-01T00:00:00Z -> 2026-09-14T23:59:59Z (frozen, verbatim,
                       never to be widened/shortened/shifted after this point)
holdout_overlap     = ZERO (no SSC holdout exists; see Section 13)
```

EURUSD is the default per the mission's own symbol rule: GBPUSD data admission does not
establish GBPUSD strategy/semantic portability, and no existing SSC documentation
establishes it either.

## 5. Occurrence identity, duplicates, missing data

```
occurrence_identity = reuse the existing, unmodified v1.0.0 canonical occurrence/
                       campaign identity scheme already implemented in
                       src/session_sweep_continuation/ (state_machine.py / replay.py /
                       canonical_observations.py). No new identity scheme is defined or
                       invented by this preregistration.
duplicate_policy     = a duplicate occurrence_id appearing within one run is a G2
                       population-integrity failure (STOP_G2_FAIL per the verification
                       plan), not a condition resolved or tolerated here.
missing_data_policy  = GEN_002 admission already verified zero gaps/duplicates/invalid
                       OHLC across the frozen window. If a decision-relevant candle is
                       nonetheless found unavailable at replay time (a causal-computation
                       failure), that occurrence is EXCLUDED from both CONTROL and
                       TREATMENT and logged -- never imputed, never substituted.
```

## 6. Cost / friction model

Unchanged from the frozen parent: `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`
`friction:` block (minimum_stop_multiple 3.0; EURUSD default_spread_pips 1.0,
default_commission_pips 0.2, default_slippage_pips 0.3). Identical friction model
applies to CONTROL and TREATMENT -- only the admission filter differs between arms.

## 7. Primary metric / secondary diagnostics

```
primary_metric = net expectancy R (mean net R per resolved occurrence), matching the
                  convention already used throughout this strategy's prior research
                  (GEN_001, GEN_002A, CANDIDATE_SELECTION_V1) for direct comparability.
primary_comparison = delta_net_expectancy_R = TREATMENT_net_expectancy_R -
                      CONTROL_net_expectancy_R
```

Secondary diagnostics (descriptive only, computed and reported regardless of the
primary result, never used to alter the primary decision): N, accepted/rejected counts,
wins/losses/BE, gross expectancy R, total net R, profit factor, win rate, max drawdown
R, MFE/MAE, S1 vs S2 attribution, long vs short, session-pair split, opportunity
retention (TREATMENT N / CONTROL N).

## 8. Sample adequacy (precommitted, reused from existing governance)

```
rule_source = strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml
              `performance_attribution.min_sample_size: 10` (existing, frozen, parent's
              own precommitted evidentiary floor -- "below this, report
              INSUFFICIENT_EVIDENCE rather than inferring profitability"). Reused
              verbatim, not invented.
minimum_occurrence_requirement = TREATMENT (S1+S2) resolved N >= 10 on EURUSD GEN_002.
                                  This is the binding constraint: since CONTROL is a
                                  superset of TREATMENT, CONTROL N >= TREATMENT N always.
```

This decision is made now, before any setup detection has run on GEN_002 -- no setup
count has been observed.

## 9. Decision rule (mechanical, precommitted)

```
PASS         : TREATMENT_N >= 10
               AND delta_net_expectancy_R > 0
               AND TREATMENT_net_expectancy_R > 0
FAIL         : TREATMENT_N >= 10
               AND (delta_net_expectancy_R <= 0 OR TREATMENT_net_expectancy_R <= 0)
INCONCLUSIVE : TREATMENT_N < 10
```

`TREATMENT_net_expectancy_R > 0` is required in addition to `delta > 0` -- per this
project's own established principle (explicit in the HYP_001 fresh-development mission:
"better but still negative = FAIL", e.g. -0.58R -> -0.20R is FAIL, not PASS). A
TREATMENT arm that is merely less unprofitable than CONTROL is not evidence of a
working strategy; it must be genuinely net-positive.

## 10. Zero-occurrence behavior

If TREATMENT_N = 0: classify `INCONCLUSIVE / ZERO_OCCURRENCE`, not FAIL -- the
hypothesis is unobservable on this population, not disconfirmed. Matches the parent
strategy's own fail-closed convention (`regime = UNKNOWN -> NO_TRADE`, never inferred).

## 11. Multiple-comparison policy

Exactly one primary comparison is preregistered: `delta_net_expectancy_R` (TREATMENT vs
CONTROL). No other arm, symbol, session, or threshold variant is compared for the
primary decision. Secondary diagnostics (Section 7) are descriptive only and may never
be used, individually or in combination, to declare PASS on a population that fails the
Section 9 rule, nor to justify a follow-up filter change without its own separate
preregistration -- this mirrors the project's existing GEN_002/H2 precedent ("a
session-only filter may not be adopted as a strategy change on the basis of a subgroup
result alone").

## 12. GBPUSD replication policy

Optional, non-gating. If run: identical frozen CONTROL/TREATMENT/metric/decision rule
applied to GBPUSD GEN_002 data, reported independently as `REPLICATION_SUPPORTED` /
`REPLICATION_NOT_SUPPORTED`. Never pooled with EURUSD's primary `delta_net_expectancy_R`
under any circumstance. Absence of a GBPUSD run does not block or weaken the EURUSD
primary result.

## 13. Holdout policy

No SSC holdout currently exists (`holdout_run_count = 0`, `NONE_DEFINED`, confirmed in
`POST_JULY31_CONSUMPTION_AUDIT/consumption_audit.json`). This preregistration does not
select, define, or reserve a holdout window. A holdout selection procedure must be
separately preregistered before any G7 step in the verification plan; nothing in this
document authorizes or anticipates that selection.

## 14. Robustness policy (deferred to Stage 3, frozen scope only)

If/when Stage 3 (G5) runs, it is limited to the verification plan's own preauthorized
suite: higher friction/slippage, execution delay, temporal stability, regime stability,
S1/S2 stability, direction stability, outlier sensitivity, parameter-neighborhood
stability. Stress testing only -- never parameter reselection, never a second admission
filter search.

## 15. Stopping rule

The frozen population (Section 4 window, Section 3 CONTROL/TREATMENT split) is
generated and evaluated exactly once. No sequential testing, no re-running with an
adjusted admission filter after observing counts or outcomes, no widening/narrowing the
window after generation. A FAIL or INCONCLUSIVE result under Section 9 is terminal for
HYP_002 on this population -- it does not authorize trying a different setup-exclusion
combination (e.g. S1-only, or S2+S3) on the same GEN_002 window.

## 16. Prohibition on post-outcome modification

Once the G2 population is generated and hash-frozen, no field in this document
(CONTROL, TREATMENT, primary metric, sample rule, decision thresholds) may be edited.
Any change after that point requires a new hypothesis ID and a new preregistration from
this same template -- it may never silently amend HYP_002_SETUP_SELECTIVITY in place.

## 17. Explicitly out of scope

No Demo/Live changes. No execution-authority changes. No canonical parent
(`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.0) modification. No holdout access. No
parameter optimization or threshold search. No Track-A/v1.1.0 work. GEN_002 admission
evidence is reused verbatim, not regenerated.

## 18. Verdict

`HYP_002_SETUP_SELECTIVITY_PREREGISTRATION_STATUS: FROZEN.` All fields required by the
verification plan's Stage-1 checklist are committed above, before any setup detection,
population generation, or outcome inspection against GEN_002.
