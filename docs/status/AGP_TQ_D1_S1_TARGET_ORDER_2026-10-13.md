---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AGP-TQ-D1 — S1 canonical target-order safety (2026-10-13)

**Rule:** the frozen `ST_ASIAN_SWEEP_5R_V1@1.1.2` contract says `target_order_rule: FAIL_CLOSED_IF_TP1_BEYOND_TP2` (B-TGT-ORDER). The contract is not modified.

## Trace (before)

| Boundary | Target validation before | After |
|---|---|---|
| Engine → `fx.build_fx_ticket` (TP1 = opposite boundary, TP2 = entry + 5R) | none | unchanged: `fx.py` is part of the v1.1.3 identity |
| `apply_ready_authority` (D6 / owner / scope) | none | unchanged |
| **`actionability.evaluate_actionability`** (READY → WATCH_READY, the canonical boundary) | **none.** Zero risk and missing targets could also reach WATCH_READY. | **BLOCKED** via `v1_tickets.target_geometry` before any WATCH_READY |
| Manual ticket (`logic_gate.R.target_order`) | enforced | unchanged |
| **`demo_execution.admission.evaluate_pre_send_gates`** (execution handoff) | **none** | **refused** with the same validator (defence in depth) |

## Validator (`src/v1_tickets/target_geometry.py`)

- **Ordering required:**
  - LONG: `SL < ENTRY < TP1 <= TP2`
  - SHORT: `SL > ENTRY > TP1 >= TP2`
- **Reasons:**
  - `TARGET_GEOMETRY_INCOMPLETE`: a level is missing, malformed or non-finite.
  - `TARGET_GEOMETRY_DIRECTION_INVALID`
  - `NON_POSITIVE_RISK_DISTANCE`
  - `TP1_NOT_BEYOND_ENTRY`
  - `TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2`
- TP1 == TP2 is allowed. Prices are never swapped or relabelled.

## Reproduction

The USDJPY message 12760 geometry (ENTRY 158.182, SL 158.121, TP1 158.524 = 5.607R, TP2 158.487 = 5.0R)
gives `TARGET_ORDER_INVALID:FAIL_CLOSED_IF_TP1_BEYOND_TP2`. A fresh engine READY ticket with
inverted, missing or zero-risk targets now gives canonical `BLOCKED`, where it used to give WATCH_READY.
Valid geometry still reaches WATCH_READY. Demo admission refuses inverted or missing targets.

## Preserved

- S1 contract identity `d7a8ebe5…`; the account pin …999.
- `ready_authority.yaml`, the owner records, the registry, and the risk limits.
- `enabled: false` and `per_order_confirm_required: true`.
- Demo-execution test fixtures now carry valid targets (before, they had none).

## Tests

- `tests/test_tq_d1_target_geometry.py`: 12 validator cases, legs parsing, WATCH_READY preserved for valid geometry, 3 invalid-geometry cases at the canonical boundary, admission refusal.
- Regression (actionability/canonical, demo execution, S1, D6, canonical FX delivery, manual tickets, G3, report lanes, ticket quality, stale-fix, v1 tickets): **572 passed, 1 skipped**.
- Ran under the R1 lock.
