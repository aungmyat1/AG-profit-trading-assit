# AG_MARKET_INTELLIGENCE_V1 — Cycle 1 design

Status: `MI_V1_DESIGN_READY` (design only; no MI engine implemented).

## Freeze boundary

`HEAD = f4a1045`, and `f4a1045` is the current `main` tip. TD-8E is frozen. Its
`ReplayEvaluationContext`, bound series identity, closed-bar admission, replay adapters,
and R4 SSC completeness behavior are dependencies, not extension points for this cycle.
Existing unrelated WIP remains untouched. No strategy, parameter, validation role,
execution gate, Demo, Live, DEV_002 economic evidence, or holdout/OOS state changes.

## Design shape

MI V1 is a read-only, immutable evidence product built from one caller-supplied event
and one temporal boundary. It is upstream of strategy decisions. It can say evidence is
valid, partial, unavailable, or incomplete; it cannot say BUY/SELL or authorize action.

The implementation sequence is: normalize existing authorities behind adapters, build
one immutable snapshot, validate invariants, then offer opt-in read-only views to SSC,
Large SMC, and sweep/liquidity consumers. SSC migration is explicitly deferred.

See [`MI_AUTHORITY_INVENTORY.json`](MI_AUTHORITY_INVENTORY.json),
[`MI_V1_CONTRACT.md`](MI_V1_CONTRACT.md), [`MI_V1_INVARIANTS.md`](MI_V1_INVARIANTS.md),
and [`MI_V1_MIGRATION_PLAN.md`](MI_V1_MIGRATION_PLAN.md).
