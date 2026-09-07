# ST_LARGE_SMC_V1 -- Forward-Research Lifecycle Promotion (2026-09-07)

Governance/lifecycle transition only. No strategy version change (remains `1.0.7`), no
strategy semantics change, no execution/proposal authority change.

## Pre-promotion re-verification

Re-ran the canonical `AG_EGSVF_V1` evaluator against the current clean repository state
(`src/validation_framework/adapters/large_smc_adapter.py::build_large_smc_record()`)
immediately before making any change:

```text
strategy_id       = ST_LARGE_SMC_V1
semantic_version  = 1.0.7
transition         = OFFLINE_RESEARCH -> FORWARD_RESEARCH

SPEC_FIDELITY      = PASS
DETERMINISM         = PASS
NO_LOOKAHEAD        = PASS
HISTORICAL_REPLAY   = PASS
C10_STOP_POLICY     = PASS

promotion_eligible  = True
promotion_blockers  = ()
```

Also re-verified the frozen C10 parameters had not drifted since signing:

```text
MIN_BUFFER_PIPS = 1.5     (src/large_smc_research/c10_stop_policy.py)
ATR_TIMEFRAME   = M5
ATR_PERIOD      = 14
ATR_MULTIPLIER  = 0.35
strategies/ST_LARGE_SMC_V1.yaml: min_buffer_pips=1.5, atr_multiplier=0.35,
  missing_anchor_action=FAIL_CLOSED, atr_not_ready_action=FAIL_CLOSED,
  min_stop_violation_action=REJECT
```

All match exactly. No `STRATEGY_FREEZE_MISMATCH`.

## Owner authorization

The owner explicitly authorized the lifecycle governance transition itself --
`OFFLINE_RESEARCH -> FORWARD_RESEARCH` -- and explicitly did NOT authorize any strategy
parameter change, C10 change, ATR/buffer optimization, entry/target/risk-model change,
proposal-generation authorization, or execution authorization. All of those remain
exactly as they were before this promotion.

## What changed

`src/validation_framework/adapters/large_smc_adapter.py`'s `lifecycle_stage` constant:
`LifecycleStage.OFFLINE_RESEARCH -> LifecycleStage.FORWARD_RESEARCH`, and
`next_transition`: `FORWARD_RESEARCH -> OPERATIONAL_SHADOW`.

This is the only change. **`strategies/registry.yaml` has no `lifecycle_stage` or
`version` schema field for any strategy** (only `registered`/`active`/`research`/
`demo_authorized`/`live_authorized` booleans) -- introducing one now would be inventing
new schema rather than using the repository's existing representation. The adapter's
own `lifecycle_stage` constant is the sole persisted record of AG-EGSVF lifecycle stage
in this repository (it was likewise the only place `OFFLINE_RESEARCH` was ever recorded
in the first place, set from evidence when the adapter was originally built). The
registry's free-text `engine`/`note` fields, and `strategies/STRATEGY_LEDGER.md`'s own
narrative history, were updated to describe this transition in prose -- not as new
structured fields.

`proposal_generation_authorized` (`strategies/ST_LARGE_SMC_V1.yaml`) remains `false`.
`execution_authority`/`execution_capability` (adapter-derived) remain `NONE`. No file
under `src/large_smc_research/` was touched.

## Post-promotion evaluator check

Immediately re-ran the evaluator for the strategy's new current stage's next
transition, `FORWARD_RESEARCH -> OPERATIONAL_SHADOW` -- evaluated only, not executed:

```text
required_gates = SPEC_FIDELITY, DETERMINISM, NO_LOOKAHEAD, HISTORICAL_REPLAY,
  SHADOW_ENTRY_EVIDENCE_UNRESOLVED_FOR_STRATEGY
promotion_eligible = False
promotion_blockers = (SHADOW_ENTRY_EVIDENCE_UNRESOLVED_FOR_STRATEGY,)
```

The blocker is the abstract `SHADOW_ENTRY_EVIDENCE` milestone gate (see
`evaluator.ABSTRACT_MILESTONE_GATES`/`MILESTONE_GATE_MAP`), unresolved because no
repository governance yet defines what evidence would let Large-SMC enter
`OPERATIONAL_SHADOW` (unlike FX's `FX_SHADOW_ENTRY_PREFLIGHT_PASS` or BTC's
`NATURAL_CAMPAIGN_ACCRUAL`). This is a genuine, evaluator-derived finding -- no concrete
gate was invented to force this transition past `NOT_APPLICABLE`, and no attempt was
made to satisfy or bypass it.

## Semantic freeze declaration

`ST_LARGE_SMC_V1 v1.0.7`'s C10 parameters are frozen as of this promotion:

```text
FROZEN (no in-place mutation authorized):
  buffer_model     = DYNAMIC_ATR_WITH_HARD_FLOOR
  atr_timeframe    = M5
  atr_period       = 14
  atr_multiplier   = 0.35
  min_buffer_pips  = 1.5
  spread_mode      = SIDE_AWARE
  min_stop_policy  = REJECT
```

Any future change to these parameters (including ATR-multiplier/floor-pip grid search
against forward-research evidence) requires a new strategy version and a separate,
explicitly authorized research/validation process -- never a mutation of `v1.0.7` in
place.

## What this promotion did NOT do

- Did not change any file under `src/large_smc_research/`.
- Did not change C10's signed parameters.
- Did not authorize proposal generation or any execution/demo/live capability.
- Did not execute the next transition (`FORWARD_RESEARCH -> OPERATIONAL_SHADOW`) --
  only evaluated it.
- Did not rewrite any historical evidence.
- Did not touch FX or BTC strategy state.
- Did not bump the application release.
