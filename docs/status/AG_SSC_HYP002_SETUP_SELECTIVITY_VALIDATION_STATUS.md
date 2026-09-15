# ST_SESSION_SWEEP_CONTINUATION_V1 — HYP_002_SETUP_SELECTIVITY Validation (2026-09-15)

## Summary

`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.0 (`OFFLINE_RESEARCH`) completed its first
fully-preregistered validation hypothesis, `HYP_002_SETUP_SELECTIVITY`, and the result
is **FALSIFIED** (`VALIDATED_NEGATIVE`). This is a terminal research stop: the
hypothesis was formally closed and must not be rerun, reclassified via secondary
diagnostics, or continued through parameter tuning.

This is the first hypothesis in this repository to run the complete frozen validation
pipeline end-to-end — GEN_002 data admission → G1 preregistration freeze → G2
population → G3/G4 economic evaluation → closure — and terminate on a negative result
under its own preregistered decision rule. The pipeline performed fail-closed at every
circuit breaker.

## Identity and lineage

| Field | Value |
| --- | --- |
| Strategy | `ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.0 |
| Lifecycle | `OFFLINE_RESEARCH` (research-only; no proposal/execution authority) |
| Hypothesis | `HYP_002_SETUP_SELECTIVITY` — excluding S3 from the S1+S2+S3 admission set improves net expectancy |
| Dataset | `SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914` (EURUSD H1/M15/M1) |
| Dataset fingerprint | `f8108d37448cae8f9fe2f16a9905abdf8991ac916cf4a497b11eaca2debbf5aa` |
| Preregistration hash | `4e2e4f21c8bf2fe5b461b29ceff670e769445be913d3f193a73e96cc84492fb7` |
| Parent config hash | `e0cf113b2e1e6b82fedee02e744615aa8f30ff7962355c331cbbdfd581fdcfbf` |

Commit lineage: `7c75f89` (freeze preregistration, pushed to `origin/main`) →
`062f1f4` (warmup context + Attempt-2 evidence) → `a06bcea` (closure, failure
decomposition, HYP_003 decline).

## Result

### Attempt 1 — INCONCLUSIVE (preserved)

`INCONCLUSIVE_DATA_CONTEXT_INADEQUATE` — 0 occurrences because the original H1
pre-window warmup was insufficient. The artifact is preserved byte-for-byte and never
edited; Attempt 2 was authorized with an explicit owner decision to add H1 warmup
context.

### Attempt 2 — FAIL (authoritative, terminal)

43 dates, 86 decision cycles, reproducible population (identical hash across two
independent runs).

| Metric | Control (S1+S2+S3) | Treatment (S1+S2 only) |
| --- | --- | --- |
| N | 21 | 11 |
| Wins / win rate | 6 / 28.6% | 3 / 27.3% |
| Gross expectancy | -0.1745R | -0.0942R |
| **Net expectancy (primary)** | **-0.4075R** | **-0.3564R** |
| Profit factor | 0.355 | 0.644 |
| Max drawdown | 4.395R | 2.596R |

Delta net expectancy = **+0.0511R** (positive). Bootstrap delta 90% CI
`[-0.112, +0.234]` (secondary, non-decision).

**Decision:** `FAIL`. The preregistered rule requires `delta > 0 AND TREATMENT_net > 0`;
the treatment improved relative to control ("less unprofitable") but remained
net-negative (`-0.3564R ≤ 0`), so the hypothesis is rejected.

By setup (Attempt 2): S1 N=10 net `-0.3692R`; S2 N=1 net `-0.2291R`; S3 N=10 net
`-0.4638R` (S3 gross `-0.2629R`, PF 0.051 — independently negative, friction-independent).

## Closure and hard constraints

`HYP_002` closed `VALIDATED_NEGATIVE`. Frozen constraints recorded in the closure
artifact:

- Must not be rerun on GEN_002 with modified rules.
- Must not be converted to PASS through secondary diagnostics.
- Must not be continued through parameter tuning.
- GEN_002 Attempt-2 population is retained but downgraded to
  `HYPOTHESIS_GENERATION_ONLY_AFTER_HYP002` — usable for failure analysis / mechanism
  generation only, never for independent confirmation of any HYP_003 idea or parameter
  search.

## Failure decomposition and HYP_003 decision

Three mechanisms were ranked from the failure decomposition:

1. **M1_EXIT_CAPTURE_TARGET_TOO_FAR** — frozen 3.0R target unreachable in-session:
   MFE max 1.35R across all 21 occurrences; 15/21 (71%) exit `RESOLVED_SESSION_EXIT`.
   **Governance overlap:** duplicates the already-preregistered
   `HYP_001_EXIT_CAPTURE` / `V1_1_0_CANDIDATE_SPEC` lineage (runner_target_r 3.0 → 1.5),
   which already carries its own fresh-evidence requirement.
2. **M2_FRICTION_COST_DRAG** — friction 0.233R/trade ≈ 57% of the net loss; S1 gross
   -0.085R vs net -0.369R. Under-decomposed (causal driver not isolated; cost model
   out of scope this mission).
3. **M3_S3_SETUP_QUALITY** — S3 structurally negative, but this is HYP_002's own
   already-adjudicated mechanism.

**HYP_003 decision:** `NOT_JUSTIFIED`. M1 is a duplicate of the governing
`HYP_001_EXIT_CAPTURE` lineage; M2 does not yet clear the preregistration bar; M3 would
substantively continue HYP_002. The existing HYP_001 / V1.1.0 candidate lineage is the
correct vehicle for testing exit/target recalibration on fresh, non-overlapping data.

## Invariants at closure

| Invariant | Value |
| --- | --- |
| `holdout_run_count` | 0 (holdout never consumed) |
| GBPUSD used | false (EURUSD-only development) |
| `demo_eligible` | false |
| `demo_authorized` | false |
| `live_authorized` | false |
| Execution authority changed | false |

## Implementation

- `scripts/run_hyp002_gen002_population.py`, `scripts/run_hyp002_gen002_population_attempt2.py`
- `scripts/acquire_hyp002_h1_warmup_context.py`
- `scripts/run_hyp002_failure_decomposition.py`
- `src/historical_replay/warmup_readiness.py`, `src/historical_replay/utc_export_csv_loader.py`
- State index: `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json`
  (`active_stage=STAGE_2`, `active_gate=TERMINAL_FAIL`, `hyp002_final_status=FALSIFIED_ON_GEN_002_EVIDENCE`)

## Test coverage

- `tests/test_historical_replay_warmup_readiness.py`
- `tests/test_historical_replay_utc_export_csv_loader_readiness_boundary.py`
- Existing `tests/test_validation_framework.py` (validation lifecycle gate coverage)

No strategy rule, parameter, threshold, or authorization flag changed. This milestone
adds research evidence only; it does not register, activate, or authorize any strategy.
