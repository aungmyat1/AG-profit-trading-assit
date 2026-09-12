# AG_R6_ECONOMIC_GATE_OWNER_REVIEW_V1

Recorded: 2026-09-11
Purpose: present a proposed, unsigned R6 economic-governance contract for owner
decision. This document contains no verdict — it defines the rule, not the answer.

## Current readiness

```
R4 = PASS   (natural READY proven; see docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md)
R5_FX = PASS
R5_PORTFOLIO = PARTIAL (Large-SMC BLOCKED_BY_MISSING_OUTCOME_RESOLVER; BTC INSUFFICIENT_DATA)
R6 = NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS
```

## Current observed economics (OBSERVED, not a formal R6 verdict)

For `ST_ASIAN_SWEEP_5R_V1` v1.1.1, from `artifacts/outcome_resolution/records/`
(13 real, signed-contract-resolved trades, 2026-09-01 to 09-04):

```
samples = 13
wins = 0
losses = 13

gross_expectancy_R = -1.00 R/trade
gross_total_R = -13.0 R

CONTRACT_CEILING cost scenario (the only signed friction assumption)
net_expectancy_R = -3.38 R/trade
net_total_R = -44.00 R
```

This is descriptive fact, not a pass/fail determination — no signed threshold exists to
measure it against. It is reported here exactly as computed; no number below was chosen
after seeing it.

## Limitations

```
- small sample (13 < any reasonable statistical floor)
- BASE friction scenario  = NOT_AVAILABLE_NO_SIGNED_ASSUMPTION
- SEVERE friction scenario = NOT_AVAILABLE_NO_SIGNED_ASSUMPTION
- commission = UNVERIFIED_NO_SIGNED_COMMISSION_RATE (reported as 0.0; not a verified zero)
- portfolio R5 incomplete: Large-SMC has no outcome resolver; BTC has 0/30 campaign days
```

## Proposed economic gate contract

File: `config/governance/economic_gate_contract.yaml`
Status: **PROPOSED — NOT SIGNED** (`identity.signed_by: null`, `identity.signed_at: null`)

| Field | Value | Rationale | Source classification | Effect if signed as-is |
|---|---|---|---|---|
| `sample.minimum_resolved_trades` | 30 | Minimum volume before any economic claim is statistically meaningful | EXISTING_PROJECT_CONVENTION (already used descriptively in `scripts/generate_economic_evidence_report.py`) | A strategy with fewer than 30 resolved trades can never reach `EDGE_VALIDATED` or `EDGE_REJECTED` — only `INSUFFICIENT_EVIDENCE` |
| `sample.minimum_oos_trades` | 15 | A held-out subset large enough to catch a sign flip | STATISTICAL_DESIGN | Requires an out-of-sample split discipline not yet implemented anywhere in this repo |
| `economics.minimum_net_expectancy_R` | 0.10 | Must clear zero with margin, not merely break even | RISK_DERIVED | Net expectancy must exceed +0.10R/trade under the signed cost scenario |
| `economics.minimum_profit_factor` | 1.30 | Conventional minimum-viability figure | EXTERNAL_REFERENCE | Net profit factor must be ≥ 1.30 |
| `economics.maximum_drawdown_R` | 15.0 | Bounded relative to this strategy family's 0.5% risk-per-trade convention | RISK_DERIVED | Max drawdown must stay ≤ 15R |
| `robustness.walk_forward_required` | true | Guards against in-sample-only overfitting | STATISTICAL_DESIGN | Requires a walk-forward evaluation this repo does not yet implement |
| `robustness.minimum_walk_forward_windows` | 3 | — | STATISTICAL_DESIGN | Same as above |
| `robustness.friction_stress_required` | true | Net result must hold under real friction, not an optimistic assumption | RISK_DERIVED | Ties directly to `evidence.accepted_cost_statuses` below |
| `robustness.maximum_friction_degradation_pct` | 50 | Flags strategies too friction-sensitive to be reliably tradeable | RISK_DERIVED | Net expectancy may not fall more than half relative to gross |
| `evidence.required_cost_coverage` | ALL_RESOLVED_TRADES | Every trade must have a cost-adjusted figure, not a partial subset | EXISTING_PROJECT_CONVENTION (mirrors `cost_model.py`'s `friction_evidence_complete`) | Partial cost coverage → `INSUFFICIENT_EVIDENCE` |
| `evidence.accepted_cost_statuses` | `["INCLUDED_CONTRACT_CEILING"]` | Only the one signed friction scenario counts | EXISTING_PROJECT_CONVENTION | Gross-only (`NOT_INCLUDED`) evidence never satisfies this gate |
| `evidence.allowed_market_data_modes` | `["REAL"]` | Only real broker data counts toward promotion | EXISTING_PROJECT_CONVENTION (mirrors `market_snapshot.py`) | REPLAY/SYNTHETIC evidence is research-only |
| `evidence.require_no_lookahead_pass` | true | — | EXISTING_PROJECT_CONVENTION | — |
| `evidence.require_reproducibility_pass` | true | — | EXISTING_PROJECT_CONVENTION | — |
| `promotion.requires_evidence_complete` | true | R5 must independently pass before R6 is even attempted | EXISTING_PROJECT_CONVENTION | — |
| `promotion.requires_economic_gate_pass` | true | — | EXISTING_PROJECT_CONVENTION | — |

Whether `ST_ASIAN_SWEEP_5R_V1`'s current evidence would pass these thresholds is
**deliberately not stated here** — evaluating the real strategy against them is the next,
separate, explicitly-authorized task (`AG_R6_ECONOMIC_EDGE_EVALUATION_V1`), only after
this contract itself is signed.

## Early rejection vs. full promotion (considered, not activated)

The prompt that requested this contract raised whether an `EARLY_REJECTION_GATE`
(stopping evidence collection early under overwhelming negative evidence, before the
full `minimum_resolved_trades` threshold) should exist alongside the full promotion
gate. This was considered and is **not defined or active in this contract** — with 13
real trades already on file for `ST_ASIAN_SWEEP_5R_V1`, adding one now would risk being
(or appearing to be) tuned to that strategy's own results. If the owner wants an
early-rejection rule, it should be proposed and signed as its own separate,
strategy-neutral decision, independent of this contract's review.

## Owner choices

```
APPROVE AS PROPOSED  -- sign config/governance/economic_gate_contract.yaml exactly as written
REVISE                -- request changes to specific thresholds/fields before signing
REJECT                -- discard this proposal; request a different contract design
DEFER                 -- take no action now; R6 remains NOT_EVALUABLE indefinitely
```

No choice has been made. This document does not simulate or assume an answer.

## Next step after a decision

- If **APPROVE** or **REVISE→approve**: set `identity.status: SIGNED`,
  `identity.signed_by`, `identity.signed_at` in `config/governance/economic_gate_contract.yaml`
  (owner action, not automated). Then a separate task, `AG_R6_ECONOMIC_EDGE_EVALUATION_V1`,
  runs the real evidence through `src/validation_framework/economic_gate.py::evaluate_economic_gate()`
  and records the actual verdict.
- If **REJECT** or **DEFER**: no further R6 action; the project remains at
  `R4 PASS / R5 PASS(FX) / R6 NOT_EVALUABLE` until revisited.
