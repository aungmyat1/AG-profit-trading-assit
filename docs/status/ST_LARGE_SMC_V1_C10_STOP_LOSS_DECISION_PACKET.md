# ST_LARGE_SMC_V1 — C10 Broker Stop-Loss Distance: Decision Packet

Status: **UNSIGNED — OWNER DECISION REQUIRED**. Date: 2026-09-02.
Phase: `ST_LARGE_SMC_V1_RESEARCH_ONLY_FUNNEL_V1`.

This is a decision packet, not a decision. No formula below is selected, adopted, or
implemented. `src/large_smc_research/engine.py` returns `BLOCKED`
(`reason_code=UNSIGNED_CONTRACT:C10_BROKER_STOP`) for every candidate that reaches its
entry-available (READY-equivalent) state rather than computing a stop from any of the
options here. Fill/invalidated-before-fill/expired-unfilled/intrabar-ambiguity/outcome
simulation in Phase B's discovery replay are correspondingly reported as
`NOT_ATTEMPTED`, never fabricated.

## Why this stays open

Per `docs/specs/LARGE_SMC_V1_SPEC.md` §15/§31 (UC-009), the *candidate-invalidation*
half of C10 is already resolved and reused verbatim
(`SMCEntryCombinationResult.invalidation*`, sourced from
`entry_confirmation/invalidation.py`). What remains open is the *SL-distance* half: how
a structural invalidation reference becomes an actual, simulatable broker stop price.
No AG-native rule for this exists anywhere in the repository (confirmed by the same
grep-based audit that resolved C12 — zero hits for a stop-distance formula outside
research references).

Choosing a formula changes the strategy's economics (risk distance, R-multiples,
target-reachability, win rate, expectancy) — it is a genuine strategy-authorship
decision, not an implementation detail, per this task's own instruction not to invent
it silently.

## Candidate options (research references only — `RESEARCH_REFERENCE`, none adopted)

Per `docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md`'s source precedence, these are
drawn from the project's own approved research references, not invented for this
packet:

1. **ST-C1 G7 — unified stop rule** (`smc-lss-platform/strategies/candidates/ST-C1_v1.1.0.yaml`):
   a single stop-placement rule applied identically regardless of which M-model produced
   the candidate. Simplicity trade-off: does not account for the different structural
   anchors M1 (inducement level)/M2 (opposing zone boundary)/M3 (swept liquidity level)
   naturally offer.
2. **`v3.6` per-model formulas** (`smc-lss-platform/specs/v3.6.yaml`): a distinct stop
   formula per confirmation model, anchored to each model's own structural reference
   (M1: beyond the inducement level; M2: beyond the new zone's far boundary; M3: beyond
   the swept/reclaimed liquidity level). Better structural fit than ST-C1 G7, more
   moving parts to freeze and test.
3. **AG-native structural-anchor composition** (not in either external resource, offered
   for completeness): reuse the already-signed `invalidation_price` field
   (`SMCEntryCombinationResult.invalidation_price`, copied verbatim from the underlying
   M-model) as the stop's structural anchor directly, then apply a separately-signed
   spread/friction buffer and broker minimum-stop-distance check. This has the advantage
   of reusing an already-frozen, already-tested field with zero new detection — the only
   genuinely new decision would be the buffer/minimum-distance numbers themselves.

## What a signed C10 contract must specify (per this task's own requirement)

Regardless of which structural-anchor approach is chosen, the frozen contract must
state, explicitly, for each of M1/M2/M3 (no cross-model default):

- structural anchor per M-model;
- bid/ask side used;
- spread treatment;
- additional friction buffer (if any) and its provenance;
- pip/point conversion;
- price normalization (broker tick size);
- minimum broker stop-distance behavior;
- decision timestamp (must match the same no-lookahead guarantee C11's `anchor_price`
  already uses — no future information);
- missing-data behavior (must fail closed, consistent with every other contract here);
- reason/provenance fields for the simulated stop.

## Non-options (excluded, per task instruction)

Never substitute: zero, current market price, a fixed risk multiple, the nearest
convenient swing chosen ad hoc, a default session, a guessed spread, or a rule imported
wholesale from another repository without an explicit provenance record and separate
authorization.

## Next step

Owner reviews this packet and either (a) selects one of the above (or a variant),
producing a new, explicit `strategies/ST_LARGE_SMC_V1.yaml` C10 contract with a strategy
version bump (`docs/VERSION_HISTORY.md`: "stop" is an explicit bump trigger), or (b)
requests further research. Until then, C10 stays `UNSIGNED` and the engine continues to
fail closed.
