# AG_MARKET_INTELLIGENCE_V1 release and freeze

`FINAL_CLASSIFICATION = MI_V1_FROZEN`

## Release gate

- Branch: `main`
- HEAD before: `c435dba`
- Required baselines are all ancestors: TD-8E `f4a1045`, Cycle 1 `93586ec`, Cycle 2 `cbb6a43`, Cycle 3 `2597547`, Cycle 4 `c435dba`.
- Canonical SSC remains `ST_SESSION_SWEEP_CONTINUATION_V1@1.0.1`; decision authority remains `session_sweep_continuation.replay.run_replay`.
- Unrelated WIP was untouched.

## Frozen surface and evidence

The release freezes the immutable `MarketIntelligenceSnapshot` and supporting value
objects, deterministic composer, TD-8E event/provenance semantics, VALID/INCOMPLETE
quality behavior, timeframe/source/dataset lineage, and the non-cutover MI-to-SSC
compatibility boundary.

Repository-wide EMA and cross-strategy regime remain `UNAVAILABLE`.

Evidence chain: `f4a1045 → 93586ec → cbb6a43 → 2597547 → c435dba`. Existing Cycle 1–4
evidence is referenced; no economic evidence was regenerated.

## Freeze regression

The accumulated TD-8E, provenance/session, MI, temporal/parity, SSC compatibility, and
canonical SSC regression command passed **117 tests**. No live/replay parity claim is
made because equivalent live inputs were not tested.

## Downstream contract

`SVOS_VIRTUAL_DEMO_ENGINE_V1 → ReplayEvaluationContext → Market Intelligence V1 → MI-to-SSC compatibility → canonical SSC → StrategyDecision`

Virtual Demo is not implemented here. SSC production migration is not performed.

## Authority exclusions and safety

MI has no authority for BUY/SELL decisions, trade proposals, risk sizing, execution,
Demo authorization, or Live authorization. No TD-8E semantics, SSC parameters,
entry/stop/target semantics, optimization, population, DEV_002 economic evidence,
holdout/OOS state, or execution authority changed. No proposal, Demo, or Live order ran.

HEAD after: recorded after the freeze commit.
