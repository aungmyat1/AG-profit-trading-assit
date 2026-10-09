# AG Asian Sweep V1.2 Evidence Seal and Blind Parity R3

Verdict: **NOT_VERIFIED — blind-reference isolation unavailable**  
Date: 2026-10-07

## Identity gate

The checked-out contract, R2 identity artifact, and freeze commit agree:

- `ST_ASIAN_SWEEP_5R_V1@1.2.0`
- contract SHA-256 `c96221e69ad10bd016d072688c3cf791caaac9afe4bdb74be289cc50f5b34770`
- freeze commit `6c483fd834e772f9f41179ef939dd4eb4d082286`

No contract, owner decision, strategy threshold, or production evaluator was changed.

## Sealed dataset

Dataset `AG_ASIAN_SWEEP_V1_2_R3_LOGIC_PARITY_001` was committed before any production
run at `6cc247ed3397d91746a7fea2514f7dd635d801bd`. Its canonical semantic SHA-256 is
`a3c1ee5b04792dcea4defbd868cb0ed1a048927deddb68b9b67ecf842856fd80`.

The prior source population has 23 rows: 14 ASIAN_LONDON and 9 out-of-scope
LONDON_NEWYORK. Eleven ASIAN_LONDON rows lack committed raw reference/trade candle
slices and were excluded rather than reconstructed from entries or ticket timestamps.
Three EURUSD cases from the committed raw M15 fixture were admitted. Every admitted
confirmation close and decision timestamp comes from the raw candle; decision time is
bar-open plus 15 minutes. No filename/ticket/engine timestamp was used.

All three cases lack authoritative contemporaneous spread and risk metadata, so they
belong to Dataset A only. Dataset B has zero cases. Spread pass/fail is `N/A`, not zero.
`FULL_HISTORICAL_L5_COST_EVIDENCE = MISSING`.

## Production run and regression

The unchanged production engine ran against the sealed cases and emitted
`r3_dataset/production_results.json`. Two cases reject at wick clearance; one passes
core geometry and then blocks with `SPREAD_UNKNOWN`. This is expected separation of
core logic from full ticket eligibility, not a spread failure.

R2 focused/selected regression: **87 passed**. Entry-close, 25% stop, wick clearance,
target order, split exit, expiry, fixed UTC, future mutation, streaming parity and
determinism remain passing.

## Mandatory blind-reference stop

This environment exposes no separate agent/context facility. Repository instructions
also bind work to one branch. The primary agent therefore could not truthfully create a
*blind-authored* evaluator. It did not reuse the R2 reference implementation or present
self-authored output as blind evidence. Consequently:

- `BLIND_REFERENCE_ISOLATION = BLOCKED`
- `REFERENCE_ENGINE_PARITY = NOT_RUN`
- `PARITY_MISMATCHES = N/A`
- golden promotion is prohibited
- `LOGIC_VERIFIED = FALSE`
- `TICKET_READY_AUTHORITY = FALSE`

A genuinely isolated agent should receive only the frozen contract, owner packet,
generic schema, and sealed dataset. Its source/results can then be compared without
editing this dataset. Host and Telegram acceptance remain independently resource-blocked.
Broker mutation count is zero.
