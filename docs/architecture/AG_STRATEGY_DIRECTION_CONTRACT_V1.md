# AG_STRATEGY_DIRECTION_CONTRACT_V1 -- Governance Contract

Status: **M1 (canonical contract) IMPLEMENTED**. M2-M6 (skill consolidation, Session
Trade migration, fill-safe pipeline, canonical economic replay, Large-SMC/Crypto
migration) are **NOT YET DONE** -- see
`docs/status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M0_M1_STATUS.md` for the full
audit and staged plan. This document defines the contract itself, not a claim that every
strategy already follows it.

## The three layers

```
LAYER 1  MARKET INTELLIGENCE   "What is the market direction?"   -> MarketBiasResult
LAYER 2  STRATEGY ENGINE       "Given that, is my setup valid?"  -> TradeProposal
LAYER 3  EXECUTION/GOVERNANCE  "Is this safe and authorized?"    -> Risk/Lifecycle/Auth
```

## Canonical interface

`src/market_intelligence/models.py::MarketBiasResult` -- frozen dataclass, exactly three
`bias` states (`BULLISH` / `BEARISH` / `NEUTRAL`), carries `decision_cycle_id`,
`decision_time` (must be timezone-aware), `model_version`, `input_fingerprint`,
`reason_codes`. Structurally excludes any entry/execution field (no `entry_price`,
`stop_loss`, `take_profit`, `lot_size`, `order_type` field exists on the dataclass --
enforced by `tests/test_market_intelligence.py::test_market_bias_result_has_no_execution_fields`).

`src/market_intelligence/bias_resolver.py` -- the sole resolver. M1 implementation
**adapts** `daytrading.decision.market_bias.derive_market_bias_from_tiers` (the most
complete existing evidence-backed bias source found in this repository, itself a pure
derivation over `market_structure.tiers.TieredStructureResult`) rather than
reimplementing structure/liquidity detection. `INDETERMINATE` (missing/invalid tiers
evidence) and any unrecognized label both fail closed to `NEUTRAL` -- never guessed as
`BULLISH`/`BEARISH`.

## Invariants (enforced, not aspirational)

1. Market Intelligence determines directional bias -- `bias_resolver.py` is the only
   module in `market_intelligence/` that outputs a `Bias` value.
2. Exactly three states -- `MarketBiasResult.__post_init__` raises `InvalidBiasStateError`
   otherwise.
6. `NEUTRAL` routes to `NO_TRADE` -- **not yet wired into any strategy this milestone**
   (M3+); the contract supports it, no strategy consumes it yet.
11/12. Bias is never an entry signal and cannot submit an order -- structurally true (no
   such field exists on `MarketBiasResult`).
14/15. `DEMO_ELIGIBLE` != `DEMO_AUTHORIZED`; no refactor grants execution authority --
   this milestone touches no `strategies/registry.yaml` field, no lifecycle stage, no
   execution module.

Invariants 4/5/7-10/13 (strategies consuming bias, permitting only aligned-direction
candidates, decision-cycle identity in a strategy's own evaluation, setup/entry
separation, risk/governance bypass prevention) are **contract requirements strategies
must satisfy once migrated**. At the time `M0_M1_STATUS.md`'s
`CURRENT_DIRECTION_AUTHORITY_MAP` audit was written (2026-09-10), no strategy had
migrated. `ST_SESSION_SWEEP_CONTINUATION_V1` (package added 2026-09-12, commit
`c36bf23`) adopted this contract from its initial implementation --
`src/session_sweep_continuation/bias_gate.py` enforces `MarketBiasResult`-derived
same-direction eligibility for every S1/S2/S3 setup, satisfying invariants 4/5/7-10/13
for that strategy. `strategy_engine.session`'s own
`entry_1_trend`/`entry_2_sweep`/`entry_3_range` and every other strategy audited in
M0_M1_STATUS.md still compute their own direction internally, unchanged by this
milestone.

## Default strategy policy (P15/P16, not yet enforced by code)

```yaml
market_bias:
  source: UNIVERSAL   # default; STRATEGY_SPECIFIC requires explicit governance registration
```

No `strategies/*.yaml` file has been updated to declare this yet -- recorded here as the
target convention for the M3+ migration, not retroactively applied.
