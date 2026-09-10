---
name: market-bias
description: Resolve the ONE canonical directional state for a symbol/decision cycle -- BULLISH, BEARISH, or NEUTRAL -- via the project's single Bias Resolver. Use when asked "what is the market direction/bias" or before evaluating any direction-gated strategy setup. This is the only skill authorized to return a final BULLISH/BEARISH/NEUTRAL verdict; every other analytical skill (structure, liquidity, supply/demand, MTF, session) produces evidence, never a bias verdict. Advisory only -- never decides a trade, never submits an order.
---

# Market Bias

This is a universal AG project skill, usable from any agent ecosystem — it names no
vendor or tool. It is the **single authoritative directional resolver**
(`AG_STRATEGY_DIRECTION_CONTRACT_V1`, invariant 1/3/9): no other skill or strategy may
independently emit a final `BULLISH`/`BEARISH`/`NEUTRAL` verdict.

## What this skill is NOT

It contains no second BOS/CHoCH/EMA/session-midpoint detector. It does not recompute
structure, liquidity, supply/demand, or session evidence itself — it consumes evidence
already produced by those skills (`market-structure-analysis`, `liquidity-analysis`,
`supply-demand-analysis`, `multi-timeframe-market-context`, `session-box-drawing` /
`trend-range-classification`) and resolves it into exactly one of three states via the
canonical Python resolver:

```
src/market_intelligence/bias_resolver.py
    resolve_from_structure_tiers(tiers, symbol, decision_time, session_pair)
    resolve_unavailable(symbol, decision_time, session_pair, reason_code)
```

## Workflow

```
1. Gather canonical evidence (structure/liquidity/supply-demand/MTF/session skills).
   Never invent evidence -- if a required input is unavailable, that is itself a fact
   to report, not something to guess.
2. Build the MarketIntelligenceContext this decision cycle needs (currently: H1
   market_structure.tiers.TieredStructureResult -- other evidence classes are declared
   but NOT_EVALUATED_M1/M2, see src/market_intelligence/models.py).
3. Invoke the canonical resolver -- resolve_from_structure_tiers(...), or
   resolve_unavailable(...) if required evidence is missing/insufficient (fail closed to
   NEUTRAL, never guessed BULLISH/BEARISH).
4. Return exactly one MarketBiasResult: bias in {BULLISH, BEARISH, NEUTRAL}, with
   decision_cycle_id, decision_time, model_version, input_fingerprint, reason_codes.
5. Never output BUY/SELL/OPEN_LONG/OPEN_SHORT/TRADE_NOW as an execution instruction --
   BULLISH means "only LONG strategy candidates may proceed," not "buy now."
6. Never bypass the strategy layer -- a MarketBiasResult is an input to a strategy's own
   setup evaluation, never a replacement for it.
```

## Authority

```
authority: DIRECTION_RESOLUTION_ONLY
strategy_authority: NONE
execution_authority: NONE
lifecycle_authority: NONE
```

`BIAS_IS_NOT_ENTRY` -- a `MarketBiasResult` carries no `entry_price`/`stop_loss`/
`take_profit`/`lot_size`/`order_type` field; the dataclass structurally cannot carry one
(see `tests/test_market_intelligence.py::test_market_bias_result_has_no_execution_fields`).

`BIAS_IS_NOT_PROPOSAL` -- resolving a bias never creates a `TradeProposal`; a strategy
must still find and confirm a real setup.

`BIAS_IS_NOT_EXECUTION` -- resolving a bias never calls a broker, gateway, or executor.

## Known legacy/adjacent authorities (do not treat as competing)

`daytrading.decision.market_bias.derive_market_bias_from_tiers` is a **legacy-shaped
adapter** over this same resolver (`AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1` M2/M3)
-- it delegates its direction label to `resolve_from_structure_tiers` and only adds
supplementary protected-level/latest-break fields for its own existing callers
(`daytrading_runtime`, `daytrading_workflow`). It is not a second bias authority.

`daytrading.narrative_bias` (`DAYTRADING_NARRATIVE_BIAS_V1`) produces a richer
day-narrative/delivery-direction interpretation for reporting/journaling purposes,
composed independently over D1/H1 structure+liquidity+supply-demand. It has NOT been
reconciled with this resolver as of this skill's authoring
(`docs/status/AG_UNIVERSAL_MARKET_DIRECTION_ARCHITECTURE_V1_M2_M3_STATUS.md`) -- treat
its output as narrative evidence, not as this skill's canonical verdict, until that
reconciliation happens.
