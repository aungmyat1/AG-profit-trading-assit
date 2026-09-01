# SMC Trap Guard V1 Status (2026-09-01)

Status: **UNIT_TESTED / ADDITIVE SAFETY VALIDATION**.

## Scope

Added a shared semantic-evidence guard for `ST_ASIAN_SWEEP_5R_V1` and
`ST_LARGE_SMC_V1`. The guard does not detect setups or make strategy decisions. It
rejects four cross-layer failure modes:

- future evidence used at an earlier decision time;
- future information retrospectively creating a past qualification;
- observation/context/confirmation evidence claiming a trade decision (directional
  labels remain valid evidence and are not themselves a trade decision);
- a lower or unknown timeframe overriding higher-timeframe context.

Both strategy YAMLs declare `SMC_TRAP_GUARD_V1` invariants. Asian Sweep pins its
already-implemented strict penetration + close-back-inside behavior and ambiguous
dual-side rejection. Large SMC pins its existing E3 sweep-without-reclaim rejection,
D1/H1/M5 authority roles, and `RESEARCH_QUALIFIED` ceiling while its engine remains
unimplemented.

## Authority and behavior

- Strategy versions unchanged: `ST_ASIAN_SWEEP_5R_V1 v1.1.1`,
  `ST_LARGE_SMC_V1 v1.0.4`.
- No entry, stop, target, session, sizing, or execution rule changed.
- No unsigned Large-SMC contract was resolved.
- Proposal, demo, live, risk, portfolio, and execution authority unchanged.
- Default trading and manual-management gates unchanged.

## Verification

Environment: Windows, Python 3.14, local repository checkout.

```text
python -m pytest -q tests/test_smc_trap_guard.py tests/test_strategy_engine.py
tests/test_e3_liquidity_sweep.py tests/test_entry_combination_composer.py
tests/test_market_structure.py tests/test_ob_contract.py tests/test_smc_walkforward.py
tests/test_historical_replay_no_lookahead.py tests/test_large_smc_registration.py
tests/test_dual_workflow_boundaries.py

82 passed, 0 failed, 3901 warnings in 11.59s
```

The focused test covers both YAML declarations, authority leakage, hindsight,
timeframe leakage, Asian penetration without reclaim, and Large-SMC E3 sweep without
reclaim plus the actual Asian engine, E3/composer, market-structure/OB boundaries,
walk-forward/no-lookahead behavior, registration, and cross-strategy authority
boundaries. Warnings are existing Python/pandas deprecations; no warning represented a
test failure.
