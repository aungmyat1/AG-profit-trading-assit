# HYP_001_EXIT_CAPTURE -- Preregistration & Freeze (Prospective Confirmation)

Status: **PREREGISTERED, NOT EXECUTED, NOT EXECUTABLE YET.** Committed in writing before
any post-2026-09-14 SSC outcome is inspected. No fresh population generated, no fresh
occurrence generated, no fresh outcome inspected, no parameter searched or modified, no
parent strategy or execution authority modified. This document is the governance repair
called for by `HYP_001_LINEAGE_AUDIT/hyp001_lineage_audit.json` (sha256
`ebc7a99f84646362acb7d73367089146bb6d0ecbc4ea7d6bf9612e0554969ba7`), whose confirmation
readiness classification was `NEEDS_PREREGISTRATION_REPAIR`.

## 1. Identity

```
hypothesis_id       = HYP_001_EXIT_CAPTURE
parent_strategy_id  = ST_SESSION_SWEEP_CONTINUATION_V1
parent_version      = 1.0.0
parent_config_hash  = e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf
parent_raw_sha256   = c92311c3c1789a2ea01495a82a1fbcba1d877a8fb4d9ac46732f39e0b81970a9
parent_source       = strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml @ HEAD (unchanged
                      since its single introducing commit c36bf23; re-verified this
                      session)
candidate_version   = 1.1.0
candidate_source    = artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/
                      V1_1_0_CANDIDATE_SPEC/candidate_spec.yaml
candidate_raw_sha256 = 3c3f232d29228de402730bc2a1d68c4c1262c91fa6f16da497157c88609d0127
candidate_manifest  = artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/
                      V1_1_0_CANDIDATE_SPEC/candidate_manifest.json
lineage_audit       = artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/
                      HYP_001_LINEAGE_AUDIT/hyp001_lineage_audit.json
                      (sha256 ebc7a99f84646362acb7d73367089146bb6d0ecbc4ea7d6bf9612e0554969ba7)
```

## 2. Historical provenance -- stated honestly, not repaired retroactively

HYP_001 was formulated (commit `552bec3`, branch `refactor/architecture-boundary-
hardening-v3`, not reachable from `main`) from a root-cause finding that 0/88 GEN_001+
GEN_002A trades ever reached the frozen 3.0R runner target. A preregistered, no-search
grid `{0.5R, 1.0R, 1.5R, 2.0R, 3.0R}` was subsequently evaluated (`9852c52`, same
branch). The empirically best-performing grid point in the only population showing a
real effect (GEN_002A, GBPUSD) was **0.5R** (`net_expectancy_R = -0.330`), not 1.5R.

`candidate_spec.yaml` freezes **1.5R** as the declared candidate value and cites a
`candidate_manifest.json` and a "P4 structural-compromise rationale" as its
justification. Neither existed anywhere in the repository prior to this mission (see
`HYP_001_LINEAGE_AUDIT` phases 1 and 6). **This preregistration does not fabricate that
missing rationale.** 1.5R must not be described, here or in any downstream artifact, as
a historical optimum, a best-performing target, or the output of any search.

```
classification = LEGACY_DECLARED_CANDIDATE_VALUE_WITH_INCOMPLETE_RATIONALE
```

## 3. Owner prospective freeze decision

```
owner_freeze_status = APPROVED_FOR_PROSPECTIVE_CONFIRMATION
CONTROL   = runner_target_r = 3.0R (frozen parent value)
TREATMENT = runner_target_r = 1.5R (already-declared HYP_001 candidate value)
```

Reasoning: preserving the already-declared 1.5R avoids selecting a NEW target after
observing additional GEN_002 exit/MFE evidence, which would itself constitute post-hoc,
evidence-informed parameter selection. This is a **prospective** governance decision
about what to test going forward. It does not retroactively establish that 1.5R was
historically well-justified (Section 2). No alternative value (0.5R, 1.0R, 2.0R, or any
other) is tested, computed, or compared by this document or this mission.

## 4. Control / Treatment (deterministic)

```
CONTROL   = trade_management.runner_target_r = 3.0 (FIXED_R), all other semantics as
            frozen in strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml v1.0.0.
TREATMENT = trade_management.runner_target_r = 1.5 (FIXED_R). Every other field
            (entry, setup, regime, stop, risk, friction, partial_target_pct,
            runner_pct, runner_target_mode) is byte-identical to CONTROL -- verified
            by direct diff, not merely asserted (see Section 9, single_mechanism).
```

CONTROL and TREATMENT are **not independent samples** -- they are two exit policies
applied to the SAME frozen occurrence population (Section 8). This is a nested,
nested-by-construction comparison, not two independently-drawn populations.

## 5. Population contract / counterfactual-dependency check (P11)

```
same_occurrence_population = REQUIRED. Exactly ONE canonical fresh occurrence
    population is generated using the frozen v1.0.0 entry/stop/setup/regime/friction
    semantics (runner_target_r is irrelevant to occurrence detection, entry price,
    initial stop, or setup classification -- see stop_engine.py / setups.py, unchanged
    between parent and candidate). CONTROL and TREATMENT are then derived from that
    SAME population by applying two different exit policies to each occurrence's own
    resolution window -- exactly the method already established and precedented by
    this repository's own HYP_001 P6 diagnostic (exit_capture_diagnostic.json,
    "first-touch-order replay of each trade's own actual window") and by HYP_002's own
    Stage-2 evaluation (CONTROL/TREATMENT both derived from one frozen population).
```

Counterfactual-dependency audit (required by mission P11 before authorizing this
contract): does resolving an entry under TREATMENT's earlier 1.5R target (vs
CONTROL's 3.0R) change whether or when a LATER entry in the same campaign is admitted?
Traced through `src/session_sweep_continuation/campaign.py::allocate_risk` and
`state_machine.py`:

- Entry admission is gated by `entries_permitted(campaign.state)`,
  `campaign.entry_count >= max_entries`, per-setup caps, and (if enabled)
  `block_new_entries_after_realized_r_enabled` -- the last of which is `false` in
  **both** the frozen parent and the candidate spec (byte-identical field, verified).
- The only outcome-triggered state transition that could invalidate a campaign
  (`HARD_LOSS_STOP -> CAMPAIGN_INVALIDATED`) is driven by the STOP being hit, which is
  unchanged between CONTROL and TREATMENT (same initial_stop). It is also not wired
  into the actual replay path (`replay.py` only fires `SESSION_WINDOW_EXPIRED`,
  a time-based event independent of exit-target policy).
- Entry timing/admission within a campaign is therefore invariant to the
  `runner_target_r` value.

```
counterfactual_dependency = NONE_FOUND
status = VALID -- same-population counterfactual evaluation is semantically valid for
    this specific parameter (an exit-target change with block_new_entries_after_
    realized_r_enabled=false). This finding is specific to runner_target_r; it does not
    generalize to a hypothesis that changes entry/stop/risk-gating semantics.
```

No `COUNTERFACTUAL_DEPENDENCY_BLOCKER` is raised.

## 6. Fresh-data scope / freshness boundary

```
latest_consumed_decision_timestamp = 2026-09-14T23:59:59Z
earliest_permitted_fresh_start     = 2026-09-15T00:00:00Z
primary_development_symbol         = EURUSD
GBPUSD                              = OUT OF SCOPE for this confirmatory test (Section
                                       13). Reserved for later external replication
                                       only, under a separate preregistration.
```

GEN_001, GEN_002A, and GEN_002 (all three) are `HYPOTHESIS_GENERATION` evidence only
and may not be reused, re-inspected, or cited as confirmatory evidence for this test.
Historical bars before 2026-09-15T00:00:00Z may be used as `WARMUP_CONTEXT_ONLY`
(indicator lookback, e.g. EMA50/ATR14 seeding) with zero economic contribution -- no
occurrence, MFE/MAE value, or expectancy figure from before this boundary may be
attributed to this confirmatory run.

## 7. Fresh-data extension / checkpoint policy (P10)

```
acquisition_direction = chronological, forward-only, from 2026-09-15T00:00:00Z
checkpoint_1          = first frozen, separately-admitted EURUSD data package covering
                         a contiguous interval from 2026-09-15T00:00:00Z. Evaluate
                         ONLY after that package is admitted (dataset-integrity
                         checked, hashed, frozen) -- never evaluate against a partial
                         or still-accumulating window.
if TREATMENT_N >= 20 at checkpoint_1: apply the Section 9 decision rule. Terminal for
    this checkpoint -- see Section 15 (stopping rule).
if TREATMENT_N < 20 at checkpoint_1: INCONCLUSIVE_INSUFFICIENT_SAMPLE. Do NOT lower N,
    do NOT change 1.5R, do NOT modify setup rules. A later extension may append the
    NEXT contiguous, previously unconsumed chronological interval (i.e. starting
    strictly after checkpoint_1's package end) under this SAME frozen protocol,
    forming checkpoint_2, and so on.
extensions_must_be    = contiguous, prospectively acquired (never backfilled from a
                         date range already available at the time checkpoint_1 was
                         evaluated), non-overlapping, parameter-unchanged.
prohibited             = repeatedly inspecting economics after every small extension;
                         optional/informal stopping; widening or shifting checkpoint_1
                         after it is defined.
```

This repository has no pre-existing SSC-specific checkpoint/extension precedent beyond
HYP_002's "generate once, evaluate once" pattern (HYP_002 never needed an extension --
its single Attempt-2 population reached N=21 >= 10 on the first admitted package). This
document therefore defines the extension policy explicitly here, before any fresh
outcome is observed, rather than inventing one after seeing an insufficient first
sample.

## 8. Occurrence identity, duplicates, missing data

Reuse the existing, unmodified v1.0.0 canonical occurrence/campaign identity scheme
already implemented in `src/session_sweep_continuation/` (`state_machine.py` /
`replay.py` / `canonical_observations.py`). No new identity scheme is defined. Missing
or invalid data at replay time excludes that occurrence from both CONTROL and
TREATMENT and is logged -- never imputed, never substituted (same convention as
HYP_002 Section 5).

## 9. Semantic contract (mechanical, precommitted)

```
entry    = UNCHANGED
setup    = UNCHANGED
regime   = UNCHANGED
stop     = UNCHANGED
risk     = UNCHANGED
friction = UNCHANGED
exit     = CHANGED -- trade_management.runner_target_r: 3.0 -> 1.5 (single field)
single_mechanism = true
```

Independently diff-verified against the frozen parent this session (matches
`HYP_001_LINEAGE_AUDIT` phase5 and `candidate_manifest.json` semantic_delta byte-for-
byte). If any future revision of `candidate_spec.yaml` introduces any other economic
semantic difference, this preregistration is void for that revision and
`NEEDS_CANDIDATE_REFREEZE` must be returned -- it may not be silently repaired.

## 10. Cost / friction model

Unchanged from the frozen parent: `friction:` block (`minimum_stop_multiple` 3.0;
EURUSD `default_spread_pips` 1.0, `default_commission_pips` 0.2,
`default_slippage_pips` 0.3). Identical model applies to CONTROL and TREATMENT. Must
not be altered after fresh outcomes are observed.

## 11. Primary metric / comparison statistic

```
primary_metric      = net_expectancy_R (mean net R per resolved occurrence)
primary_comparison  = delta_net_expectancy_R = TREATMENT_net_expectancy_R -
                       CONTROL_net_expectancy_R
```

## 12. Secondary diagnostics (non-decision, preregistered per mission P8)

Reported regardless of the primary result, never used to alter it and never able to
convert FAIL/INCONCLUSIVE into PASS: gross expectancy R, net R, profit factor, max
drawdown R, win/loss/breakeven rate, median R, R standard deviation, MFE, MAE, MFE
capture ratio, session-exit frequency, bootstrap confidence interval for delta,
chronological half/slice stability, friction contribution. These belong to robustness
interpretation strictly AFTER the primary result is classified.

## 13. Sample adequacy (owner-approved prospective rule)

```
rule_source = owner-approved this mission (not derived from, or reduced to match, any
              observed count -- no fresh count has been observed).
MIN_TREATMENT_N = 20
ADEQUATE   : TREATMENT_N >= 20
INCONCLUSIVE: TREATMENT_N < 20
```

Because CONTROL and TREATMENT are alternate exit policies applied to the identical
occurrence population (Section 5), `CONTROL_N == TREATMENT_N` is expected by
construction -- the exit-policy choice cannot itself create or destroy an occurrence.
Any observed inequality would indicate a population-integrity defect (e.g. an
occurrence excluded from one arm's evaluation by a data gap) and must be investigated,
not silently accepted. N is never reduced after observing fresh outcomes.

## 14. Decision rule (mechanical, precommitted, owner-approved)

```
PASS         : TREATMENT_N >= 20
               AND TREATMENT_net_expectancy_R > 0
               AND delta_net_expectancy_R > 0
FAIL         : TREATMENT_N >= 20
               AND (TREATMENT_net_expectancy_R <= 0 OR delta_net_expectancy_R <= 0)
INCONCLUSIVE : TREATMENT_N < 20
```

No significance test, profit factor, drawdown, MFE, or win-rate condition is added to
this primary rule (mission P7). `TREATMENT_net_expectancy_R > 0` is required in
addition to `delta > 0`, matching this project's own established principle from the
HYP_002 closure ("better but still negative = FAIL", e.g. delta +0.051R but
TREATMENT -0.356R was correctly classified FAIL, not PASS).

## 15. Stopping rule

Each checkpoint (Section 7) is generated and evaluated exactly once under this frozen
protocol. No sequential re-testing of the same checkpoint after observing its own
outcome, no re-running with an adjusted target after observing counts or outcomes, no
widening/narrowing a checkpoint's window after it is admitted. A FAIL result is
terminal for HYP_001 on this population (Section 17, mission P18) -- it does not
authorize trying a different target value on the same or an overlapping window.

## 16. Prohibition on post-outcome modification

Once a checkpoint's population is generated and hash-frozen, no field in this document
(CONTROL, TREATMENT, primary metric, sample rule, decision thresholds, extension
policy) may be edited. Any change after that point requires a new hypothesis ID and a
new preregistration from this same template.

## 17. Termination rules (mission P18)

```
PASS         -> proceed to a robustness mission (out of scope here). HYP_001 remains
                NOT validated, NOT demo-eligible, NOT demo-authorized until robustness
                and any further governance-required steps also pass.
FAIL         -> HYP_001 = VALIDATED_NEGATIVE. STOP HYP_001 permanently on this
                mechanism. Do not change the target and rerun.
INCONCLUSIVE -> follow ONLY the Section 7 frozen extension/checkpoint policy. Do not
                tune. Do not reinterpret. Do not lower MIN_TREATMENT_N.
```

## 18. Holdout firewall

```
holdout_run_count = 0
```

No SSC holdout currently exists for this strategy (confirmed in
`POST_JULY31_CONSUMPTION_AUDIT/consumption_audit.json`). This preregistration does not
select, define, or reserve a holdout window. Fresh confirmation under this document is
DEVELOPMENT/CONFIRMATORY evidence, not final holdout. Any holdout access remains
reserved until: HYP_001 fresh confirmation PASS -> robustness PASS -> candidate
freeze/qualification -> external replication as required, in that order, with holdout
access itself separately preregistered before it is invoked.

## 19. GBPUSD firewall

GBPUSD must not contribute to N, target selection, confirmation, or any part of this
preregistration's repair. It is reserved for later external replication only, under a
separate preregistration, after (not instead of) an EURUSD primary result.

## 20. Explicitly out of scope

No Demo/Live changes. No execution-authority changes. No canonical parent (v1.0.0)
modification. No holdout access. No parameter optimization or threshold search beyond
the single frozen 1.5R value. No fresh EURUSD data acquisition or population
generation (that is a separate, subsequent mission gated on this document existing).
M2_FRICTION_COST_DRAG remains `RESEARCH_BACKLOG` and is not part of HYP_001.

## 21. Verdict

`HYP_001_EXIT_CAPTURE_PREREGISTRATION_STATUS: FROZEN.` All fields required by the
lineage audit's `NEEDS_PREREGISTRATION_REPAIR` finding are committed above, before any
post-2026-09-14 EURUSD outcome is inspected.

```
HYP_001_STATUS = FROZEN_FOR_FRESH_CONFIRMATION
fresh_confirmation_runs = 0
holdout_run_count = 0
demo_eligible = false
demo_authorized = false
live_authorized = false
```
