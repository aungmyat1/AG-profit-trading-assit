# SSC v1.0.1 SVOS G2 Failure Decomposition — Status (2026-09-19)

## Summary

Read-only, evidence-first failure decomposition of the frozen G2 population
`SSC_V1_0_1_G2_DEV_002_POPULATION_V1` (22 occurrences, population hash
`832e8e13c74a5401684a401cdbe4c42aa95e95661928fe596804068e7067ab5e`, identity
re-verified). No replay rerun, no occurrence regeneration, no parameter change, no
protected-data access. Terminal state: `DIAGNOSIS_COMPLETE_NO_HYPOTHESIS_JUSTIFIED`.

## Headline findings

| Item | Value | Classification |
| --- | --- | --- |
| Gross expectancy | -0.245R | `PRIMARY_ALPHA_DEFICIT` |
| Gross profit factor | 0.563 | — |
| Net expectancy | -0.469R | — |
| Friction (total / mean / share of net loss) | 4.92R / 0.224R / 47.7% | `SECONDARY_AMPLIFIER` |
| Stop-first rate | 50% (11/22) | — |
| Mean favorable excursion before stop (SL trades) | 0.324R | `NO_POST_ENTRY_EDGE` |
| Mean MFE (all trades) | 1.312R | — |
| Mean partial target (reference boundary) | 1.927R | `EXIT_CAPTURE_WEAKNESS` |
| Partial activation rate | 22.7% | — |
| Winner capture efficiency | 52.3% | — |

## Failure hierarchy (evidence-derived)

1. **WEAK_GROSS_EDGE** (HIGH) — gross negative before friction; N=22.
2. **NO_POST_ENTRY_EDGE (stopped entries)** (MEDIUM) — 50% stop-first, 0.32R pre-stop
   favorable excursion. Cannot separate tight stop vs poor timing without an experiment.
3. **EXIT_CAPTURE_WEAKNESS (partial-target reachability)** (MEDIUM) — target 1.93R vs
   typical MFE 1.31R; partial activation 22.7%.
4. **SESSION_SPECIFIC_WEAKNESS** (LOW) — LONDON_NEWYORK gross -0.551 vs ASIAN_LONDON
   +0.010; N=10 and confounded by setup distribution (S2 only in LONDON_NEWYORK).
5. **FRICTION_AMPLIFICATION** (HIGH as secondary) — 47.7% of net loss; cannot explain
   the negative gross edge.

Subgroup guards: LONG (N=4) and S2 (N=2) are `INSUFFICIENT_SUBGROUP_SAMPLE`; S3 (N=7)
is `LOW_SAMPLE_EXPLORATORY`. The SHORT=18/LONG=4 concentration mirrors the frozen H1
bias distribution (BEARISH 61 vs BULLISH 23 cycles) via the bias gate — not a
demonstrated direction-alignment defect.

## Closed-hypothesis collision check

- **HYP_001_EXIT_CAPTURE** (HYPOTHESIS_NOT_SUPPORTED, Route B, paired_n=88,
  delta_net_R=-2.227): the observed partial-target-reachability signal is
  `PARTIAL_OVERLAP` (partial target ≠ the runner target HYP_001 tested). Not recreated.
- **HYP_002_SETUP_SELECTIVITY** (VALIDATED_NEGATIVE): disabling any setup would be
  `DUPLICATE_OF_HYP_002`. Not recreated.

## Hypothesis admission

**None recommended.** No mechanism has adequate sample support (N=22 < proposed 30)
combined with an independently-testable *structural* change. Every candidate reduces
to numeric stop/target tuning, a closed-hypothesis duplicate, or session subgroup
cherry-picking — all excluded.

## Governance (read-only)

- `economic_gate_contract.yaml`: `AG_R6_ECONOMIC_GATE_CONTRACT_V1`, `PROPOSED`,
  unsigned, inactive → G3 `NOT_EVALUATED_UNSIGNED_CONTRACT`.
- `optimization_admission_contract.yaml`: `AG_OPTIMIZATION_ADMISSION_CONTRACT_V1`,
  `PROPOSED`, unsigned, inactive → `OPTIMIZATION_ELIGIBLE=false`.

## Safety

No strategy/parameter/population change, no G2 rerun, no optimization, no candidate,
no protected-data access, no H2 consumption/modification, no forward, no broker/demo/
live order, no execution-authority change.

## Evidence

- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_FAILURE_DECOMPOSITION_V1.json`
  (derived metrics, decompositions, excursion/path facts)
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_FAILURE_DECOMPOSITION_REPORT_V1.json`
  (hierarchy, closed-hypothesis check, hypothesis admission, governance, safety)
- Driver: `scripts/analyze_ssc_v1_0_1_g2_dev002_failure.py` (read-only, deterministic)
