# HYP_001_EXIT_CAPTURE — Post-v1.0.1 Preregistration Reassessment

```
mission          = SSC_HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT_V1
mission_type     = GOVERNANCE_REASSESSMENT_NOT_ECONOMIC_EVALUATION
strategy_id      = ST_SESSION_SWEEP_CONTINUATION_V1
generated        = 2026-09-17 (date-only; content reproducible, no mutable timestamp)
head_at_analysis = 6b11726 (main)
```

**Safety confirmation (all read-only, verified by what this document does, not just claims):**

```
HYP_001_executed              = false (unchanged; still fresh_confirmation_runs=0)
new_population_generated      = false
holdout_or_OOS_accessed       = false
parameters_optimized          = false
economic_replay_run           = false
strategy_semantics_changed    = false
demo_authorized / live_authorized = false / false (unchanged)
```

This document reads only already-committed, already-frozen artifacts (the preregistration,
the lineage audit, the remediation manifest, the exit-capture diagnostic on the
`refactor/architecture-boundary-hardening-v3` branch, and the production
`outcome_resolution.py` source as it exists today) and reasons about them. It generates
no data, runs no script, and calls no economic-evaluation function.

---

## 1. Original HYP_001 thesis

Source: `HYP_001_LINEAGE_AUDIT/hyp001_lineage_audit.json`,
`exit_capture_diagnostic.json` (refactor branch, commits `552bec3`/`9852c52`/`5101a51`),
`HYP_001_EXIT_CAPTURE_PREREGISTRATION.md`.

- **Root-cause finding**: 0/88 combined GEN_001 (EURUSD, N=31) + GEN_002A (GBPUSD, N=57)
  trades ever resolved via the 3.0R `runner_target_r` leg.
- **P5 MFE survival profile**: favorable excursion is common at small magnitude (40–63%
  of trades reach 0.25–0.5R) but decays sharply above ~1R (only 3–4% ever reach 3R).
- **P6 preregistered grid** ({0.5, 1.0, 1.5, 2.0, 3.0}R, no search): `UNSTABLE_PATTERN`
  in GEN_001 (flat/noisy, ~0.03R spread), `MONOTONIC_PATTERN` in GEN_002A (both gross and
  net expectancy improve monotonically as target decreases; best point 0.5R, net
  −0.330R — still net-negative). Overall verdict: `WEAKLY_SUPPORTED`.
- **Candidate freeze**: `runner_target_r`: 3.0 → 1.5 (single field; entry/setup/regime/
  stop/risk/friction byte-identical). 1.5R is one of the five preregistered grid points —
  explicitly **not** the empirical best (0.5R) and not the output of a search.
- **Known pre-existing gap** (from the lineage audit, unrelated to v1.0.1): the document
  cited as 1.5R's specific rationale (`candidate_manifest.json`, "P4 structural-
  compromise rationale") does not exist anywhere in the repository. Classification:
  `DEVELOPMENT_TUNED_BUT_TRACEABLE`, `PARAMETER_FREEZE_STATUS = UNRESOLVED`. This gap is
  independent of the v1.0.1 fix and is **not** resolved or worsened by this reassessment.

## 2. Assumptions inherited from v1.0.0

1. **Stated and verified in the preregistration (Section 5, P11 counterfactual-
   dependency audit)**: `runner_target_r` is irrelevant to occurrence detection, entry
   price, initial stop, or setup classification; CONTROL/TREATMENT entry-admission timing
   is invariant to the exit target. — Traced through `campaign.py`/`state_machine.py`;
   holds regardless of the partial-target defect (entry admission never consults the
   partial-target price). **Still valid.**
2. **Implicit, not separately stated anywhere in the preregistration or the lineage
   audit**: that the production trade-management state machine
   (`outcome_resolution.py::resolve_campaign_entry`) correctly implements the strategy's
   declared 50%-partial / 50%-runner-with-breakeven sequence for the CONTROL arm (3.0R),
   and that GEN_001/GEN_002A/GEN_002's recorded "actual" economics and the P6 diagnostic's
   window boundaries reflect that intended lifecycle. **This assumption was never true
   under v1.0.0 — see Section 3.**

## 3. Corrected v1.0.1 exit lifecycle (read directly from
`src/session_sweep_continuation/outcome_resolution.py`, current HEAD)

`resolve_campaign_entry()` computes a partial-target price, then applies a fail-closed
guard: for a LONG, if `partial_target_price <= entry_price` (target behind/at entry), or
for a SHORT if `partial_target_price >= entry_price`, the target is nulled to `None`. If
`partial_target_price is None`, the entry is routed entirely to
`_resolve_full_position_only()` — a function that checks **only** stop-loss vs.
session-exit-at-close. **It never evaluates `runner_target_r` at all.** The
partial→BE-armed-runner→`runner_target_r` path (`Phase 2` in the same function, the only
code path that ever checks the 3R/1.5R target) is reached **exclusively** when a valid
partial target exists and is hit.

- **Pre-v1.0.1 (defect, `INVERSE_BOUNDARY`)**: LONG → `reference_low`, SHORT →
  `reference_high`.
- **Post-v1.0.1 (`OPPOSITE_SESSION_BOUNDARY`)**: LONG → `reference_high`, SHORT →
  `reference_low`.

ST_SESSION_SWEEP_CONTINUATION_V1 is, by name and design, a **continuation** strategy:
entries follow a sweep of one session boundary and continue away from it. For the
dominant case this means the just-swept boundary sits **behind** the entry in the trade's
own direction (a LONG continuation entry is typically already above `reference_low`; a
SHORT continuation entry is typically already below `reference_high`). Under the
pre-v1.0.1 inverted mapping, the computed partial target (`reference_low` for LONG,
`reference_high` for SHORT) would therefore very likely fail the "ahead of entry" guard
for the large majority of occurrences — routing them to `_resolve_full_position_only`,
which structurally **never checks the 3R runner target at all**, rather than through the
designed partial+BE+runner sequence the strategy YAML declares
(`partial_target_pct=0.50, runner_pct=0.50, runner_target_mode=FIXED_R`).

## 4. Which assumptions remain valid

- Entry, setup, regime, stop, risk, friction: byte-identical parent vs. candidate
  (independently diff-verified) — **unaffected** by the v1.0.1 fix and **unaffected** by
  this reassessment. Valid.
- Entry-admission timing invariance to `runner_target_r` (Section 2, item 1) — **valid**,
  unaffected by the partial-target fix (admission logic never reads the partial target
  either).
- The **mechanism class** (price frequently fails to sustain to a high R multiple) —
  directionally plausible and correctly derived as a preregistered hypothesis from a
  single binary fact (0/88 reaching 3R), not from a value search. Independently
  corroborated by HYP_002's GEN_002 failure decomposition (MFE ≤ 1.35R, 71%
  session-timeout exits) — though see the caveat in Section 5 on that corroboration.
- The raw MFE/MAE **survival-curve shape** (P5) is computed largely from each
  occurrence's own raw price excursion over its window, which is closer to a
  price-action fact than an exit-policy artifact — **directionally likely to remain
  valid**, but see Section 5 for the one qualification (window-boundary dependency).

## 5. Which assumptions were artifacts of the defect

- **The "actual CONTROL" baseline economics** cross-referenced inside
  `exit_capture_diagnostic.json` as a validity cross-check for the simplified P6
  counterfactual (GEN_001 actual CONTROL net −0.1896R; GEN_002A actual CONTROL net
  −0.5766R) were, per Section 3's mechanical analysis, very likely produced by
  `_resolve_full_position_only` — an accidental **all-or-nothing SL-vs-session-exit**
  policy — rather than the strategy-as-specified 50%-partial/50%-runner-with-BE policy
  the CONTROL arm is supposed to represent. These figures do not describe the same
  exit lifecycle the frozen preregistration's CONTROL/TREATMENT contract (Section 4)
  declares.
- By extension, **the literal claim "0/88 trades ever reached the 3R runner leg"**, to
  whatever extent it is sourced from the real engine's terminal states (as opposed to
  the P6 diagnostic's own separate, simplified first-touch-order simulation, which does
  not call `resolve_campaign_entry` and is largely independent of this defect) describes
  a population that mostly never reached Phase 2 (the runner phase) **at all**, for a
  structural/gating reason unrelated to whether price itself could sustain to 3R. This is
  a materially different causal story than "price approaches but falls short of 3R."
- **HYP_002's GEN_002 corroboration** (Section 4) was also generated pre-v1.0.1 and is
  therefore subject to the same caveat: its 71% session-timeout / MFE≤1.35R
  decomposition may itself partly reflect trades that never entered the intended
  partial+runner sequence, not purely a "runner ran but fell short" pattern. This
  weakens (does not eliminate) the strength of that specific corroboration.
- This is a **new, previously unidentified traceability gap**, additive to the
  already-known "`candidate_manifest.json` missing / 1.5R rationale unresolved" gap from
  the lineage audit. It does not resolve or worsen that gap; it is a separate finding.

One structurally important point: **CONFIRM_001's actual future execution is not itself
broken by this.** Per the preregistration (Section 5), CONTROL and TREATMENT for the
fresh confirmatory run will both be derived from the **same freshly-acquired,
post-2026-09-15 occurrence population**, evaluated through the **current** (corrected)
`resolve_campaign_entry`. Both arms of the prospective test will therefore use the
corrected partial-target semantics consistently. The risk is entirely about (a) whether
the **development-era evidence** that justified running this experiment and choosing
1.5R is trustworthy, and (b) whether anyone later compares fresh CONFIRM_001 results
back against stale v1.0.0-era "actual" figures for robustness narrative without a
caveat.

## 6. Classification

```
CLASSIFICATION = REQUIRES_AMENDMENT
```

Not `UNCHANGED_VALID`: the CONTROL-arm baseline economics and the literal "0/88" claim,
as sourced from the real engine's pre-v1.0.1 terminal states, do not describe the
strategy-as-specified exit lifecycle and must not be silently reused or cited as
comparable to any future v1.0.1-era result without qualification.

Not `INVALIDATED_BY_BASELINE_REMEDIATION`: HYP_001 was never executed under v1.0.0 in a
sense that produced a completed result now falsified by the fix (`fresh_confirmation_runs
= 0` throughout). The underlying mechanism claim is independently supported by raw
MFE/MAE survival data that is largely orthogonal to the partial-routing defect, and the
future CONFIRM_001 execution mechanics are self-consistent (both arms use the corrected
engine). There is nothing here that requires abandoning the hypothesis.

Not `REQUIRES_NEW_HYPOTHESIS`: the mechanism class, the single-mechanism EXIT-only
contract, and every entry/setup/stop/risk/friction assumption remain intact and
verified unchanged. This is a comparability/documentation repair, not a new causal
claim requiring a new hypothesis ID.

## 7. Owner decision packet

**Decision needed**: approve, amend, or decline the following ADDITIVE governance
amendment to `HYP_001_EXIT_CAPTURE_PREREGISTRATION.md`. This follows the same pattern
already established in this repository by `EXTENSION_CHECKPOINT_POLICY.json`
("ADDITIVE governance artifact... does not edit
`HYP_001_EXIT_CAPTURE_PREREGISTRATION.md`'s existing text") — it does not touch Sections
1–21 of the frozen preregistration, does not change `runner_target_r`, `MIN_TREATMENT_N`,
the decision rule, or the extension/checkpoint schedule.

**Proposed amendment content** (for owner approval; not applied by this mission):

1. Record that GEN_001/GEN_002A/GEN_002's "actual" CONTROL-arm economics and the literal
   "0/88 reached 3R" claim were generated under the pre-v1.0.1
   `PARTIAL_TARGET_DIRECTION_INVERSION` defect and do not reliably describe the
   strategy-as-specified partial+BE+runner exit lifecycle.
2. Prohibit citing those v1.0.0-era "actual"/CONTROL figures as a comparability baseline
   for CONFIRM_001's fresh v1.0.1 result (development-era evidence remains
   `HYPOTHESIS_GENERATION` only, as already governed — this simply extends that existing
   firewall to explicitly cover the exit-lifecycle dimension, not just the date-freshness
   dimension already in Section 6 of the preregistration).
3. Leave the mechanism class, the frozen CONTROL=3.0R/TREATMENT=1.5R contract, the
   decision rule, and the checkpoint/extension schedule untouched.

**Separate, independent owner option (not part of this amendment, requires its own
sign-off before being run)**: a read-only re-derivation of the P5/P6 diagnostic over the
*already-frozen* GEN_001/GEN_002A/GEN_002 occurrence populations, replayed through the
corrected v1.0.1 `outcome_resolution.py`, to determine whether the `WEAKLY_SUPPORTED`
verdict and the specific 1.5R choice still hold under corrected exit semantics. This
uses no new data and generates no new population, but it *is* an economic
re-evaluation of historical evidence and must not be inferred as authorized by this
document — it requires its own explicit preregistration and owner approval before
execution, exactly like any other economic evaluation in this project.

## 8. Exact next safe gate

```
NEXT_SAFE_GATE = OWNER_ADJUDICATION_OF_CONTROL_ARM_COMPARABILITY_AMENDMENT
```

Owner reviews and approves/amends/declines the Section 7 additive amendment
(governance-only, no data, no execution). This has no urgency deadline in isolation —
the independent, already-frozen CONFIRM_001 acquisition schedule
(`HYP_001_FRESH_CONFIRM_001/EXTENSION_CHECKPOINT_POLICY.json`) cannot be evaluated
before its own earliest_acquisition_timestamp of **2026-10-13T00:00:00Z** regardless —
but it should be resolved before that date so CONFIRM_001's eventual checkpoint
evaluation is not run against an unaddressed comparability gap.

No other action is authorized by this document. HYP_001 remains
`FROZEN_FOR_FRESH_CONFIRMATION`, `demo_eligible = false`, `demo_authorized = false`,
`live_authorized = false`.
