# TRUE_STAGE2 Oracle Reconciliation Status (2026-09-01)

Scope: reconcile a discrepancy found while preparing the two-stage golden vertical
slice -- the committed `true_stage2_from_stage1_result.json` showed `ready: 2`
(missing `SETUP-EURUSD-E1M3-29ef3d6e78d5f9c2`), contradicting the previously
declared `AG_TWO_STAGE_ARCHITECTURE_V1` baseline of `READY = 3/3 EXACT`. No
Stage1/Stage2 source code changed in this pass.

## 1. Root Cause

The committed oracle was generated in commit `bed28bb` (2026-08-31 19:51:55),
**before** commit `1ebb4f2` (2026-08-31 21:15:40) added
`historical_replay.stage1.DirectionalLiquidityTimeline` -- the fix whose own
docstring cites this exact missing setup as its motivating case. Under the
pre-fix code, E1's event carried no HTF liquidity reference at all (only E3
events were enriched), so `evaluate_entry_stage()` fell back to
`event.liquidity_reference = None` and E1M3 could never form an entry array.
The oracle was never regenerated after the fix landed.

Verified via two independent live reconstructions on current code (isolated
E1M3 replay, and a paired E1-then-E3 sequential-ledger replay mirroring the
production driver) -- both reproduced `SETUP-EURUSD-E1M3-29ef3d6e78d5f9c2`
reaching READY at `2025-09-15T12:10:00Z` (FVG @ 1.17322), matching the original
continuous-replay ledger (`discovery_2mo_aug_sep2025_setup_ledger.parquet`)
exactly.

## 2. Fix Applied

Regenerated `artifacts/backtests/true_stage2_from_stage1_result.json` and
`..._checkpoint.json` by re-running `scripts/run_true_stage2_from_stage1.py`
against the unchanged frozen `qualified_e_events_2025-08-01_2025-10-01.json`
Stage-1 artifact. No Stage1/Stage2 source changed.

## 3. Result

```
events=18, steps=3166, setups=54, arrays=9, ready=3
call_counts: D1_or_H1_discovery=0, E_evaluator=0,
             build_symbol_conditional_entry_analysis=0
```

| setup_id | combination/direction | READY timestamp | entry | entry_reference |
|---|---|---|---|---|
| `SETUP-EURUSD-E1M3-29ef3d6e78d5f9c2` | E1M3 SHORT | 2025-09-15T12:10:00Z | FVG | 1.17322 |
| `SETUP-EURUSD-E3M3-27d758322ae69d05` | E3M3 SHORT | 2025-09-15T12:10:00Z | FVG | 1.17322 |
| `SETUP-EURUSD-E1M2-204f3417f2901979` | E1M2 LONG | 2025-09-23T14:55:00Z | FVG | low 1.16807 / high 1.1684 / ref 1.168235 |

Stage-1-bypass counters are all 0 (no E1/E2/E3 re-evaluation, no D1/H1
rediscovery), confirming the two-stage boundary itself is unaffected.

## 4. Determinism Check

Re-ran `scripts/run_true_stage2_from_stage1.py` a second time against the same
frozen Stage-1 input. The two runs are byte-identical except for the
non-semantic `elapsed_seconds` field.

## 5. Status

```
TRUE_STAGE2 = VERIFIED
AG_TWO_STAGE_ARCHITECTURE_V1 = FROZEN (unchanged)
STAGE1 / STAGE1_CONTEXT_V2 / STAGE2 = FROZEN (unchanged)
```

Setup identities, eligibility semantics, E1/E2/E3, and M1/M2/M3 were not
touched. This pass only regenerated a stale downstream artifact.
