# AG_TWO_STAGE_GOLDEN_VERTICAL_SLICE_V1 Status (2026-09-01)

Scope: a small, deterministic, production-style regression lock proving the
verified `AG_TWO_STAGE_ARCHITECTURE_V1` across the real serialization boundary --
Stage1 producer -> persisted `STAGE1_CONTEXT_V2` -> reload via the public loader ->
Stage2 consumer -> exact setup identity / entry geometry / READY milestone. See
`docs/status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md` for the oracle
reconciliation this slice depends on.

## 1. Freeze Decision

```
AG_TWO_STAGE_ARCHITECTURE_V1 = VERIFIED_FROZEN
STAGE1_CORE                  = FROZEN
STAGE1_CONTEXT_V2            = FROZEN
STAGE2                       = FROZEN
E1/E2/E3                     = FROZEN
M1/M2/M3                     = FROZEN
```

No E1/E2/E3/M1/M2/M3 semantics, setup-ID derivation, or eligibility rules were
touched by this pass. Two small additive-only changes were made:

- `historical_replay.stage1.fingerprint_qualified_e_events()` -- SHA-256 over
  canonical, deterministic event content (excludes wall-clock `created_at`).
- `historical_replay.stage2.evaluate_entry_stage_canonical_v2()` +
  `MissingStage1DirectionalLiquidityContextError` -- a strict wrapper that fails
  closed when a canonical `STAGE1_CONTEXT_V2` replay is attempted without a
  `DirectionalLiquidityTimeline`. The legacy `evaluate_entry_stage()` keeps its
  permissive `event.liquidity_reference` fallback unchanged for existing callers.

## 2. Golden Fixture

`artifacts/backtests/golden/two_stage_golden_fixture_v1.json` -- compact, with
provenance back to the row-level original-continuous ledger
(`discovery_2mo_aug_sep2025_setup_ledger.parquet`) and the determinism-verified
`true_stage2_from_stage1_result.json` oracle. No expected value was retyped from
memory.

```
fingerprint_algorithm = SHA-256
fingerprint            = 81a2bfcadf7da3414528e499c9e764b6dde93ebfa336faf673ff08d38b6586f2
```

## 3. Cases (`tests/test_golden_vertical_slice.py`, all via the public
`load_stage1_dataset()` loader, none via manual object reconstruction)

| Case | Setup | Result |
|---|---|---|
| A | `E1M3-29ef3d6e78d5f9c2` SHORT, 2025-09-15T12:10Z | READY, FVG@1.17322 -- EXACT |
| B | `E3M3-27d758322ae69d05` SHORT sibling, same timestamp | READY, FVG@1.17322, shares the exact directional liquidity object with A -- EXACT |
| C | `E1M2-204f3417f2901979` LONG, 2025-09-23T14:55Z | READY at that timestamp; final ledger geometry (FVG, low 1.16807/high 1.1684/ref 1.168235 at final_time 2025-09-26T20:55Z) matches full-walk reproduction -- EXACT |
| D | `E3M2-4942255764efb736` SHORT, eligibility 2025-08-12T16:00-17:00Z | eligible at 16:00/16:55, NOT eligible at 17:00 or 2025-08-19 -- false READY IMPOSSIBLE |
| E | `E3M3-27d758322ae69d05`'s own 5-interval eligibility timeline | interval/gap/interval/blocked-after all correct |

Stage-1-bypass instrumentation (`D1_or_H1_discovery`, `E_evaluator`,
`build_symbol_conditional_entry_analysis`) is asserted `== 0` for every case that
runs an evaluation.

## 4. Tests

```
golden (tests/test_golden_vertical_slice.py)                   = 10 passed
existing Stage1/Stage2 focused regression                       = 27 passed
broader repository suite (run once)                             = 1130 passed, 0 new failures
```

## 5. Safety

```
strategy_changes      = NONE
risk_changes           = NONE
daily_runtime_changes  = NONE
execution_changes      = NONE
crypto_changes         = NONE
```

## 6. Next Phase

`AG_TWO_STAGE_ARCHITECTURE_V1` is frozen. Replay-architecture development stops
here; do not reopen without a reproduced regression. Next phase:
`AG_POST_ASIAN_DAILY_DECISION_V1` (post-Asian London pilot / release packaging),
tracked and committed separately from this replay-freeze checkpoint.
