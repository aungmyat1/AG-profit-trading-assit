# AG V1.0.3 BTC Observation Campaign Authorization Status

**Decision date:** 2026-09-06  
**Decision timestamp:** 2026-09-06T06:52:42Z  
**Classification:** `OWNER_AUTHORIZED_NOT_STARTED`

## Owner decision

The owner explicitly authorized starting the existing BTC production-market observation
campaign for `ST_LIQUIDITY_SWEEP_RETEST_V1`'s `CRYPTO_PERP` research profile.

```text
campaign                         = BTC 30-valid-observation qualification campaign
market data                      = Bybit public/unauthenticated BTCUSDT linear perpetual
strategy authority               = RESEARCH_ONLY
observation campaign authorized  = YES
observation campaign started     = NO
valid observations completed     = 0/30
```

Authorization is limited to read-only market-data acquisition, deterministic research
evaluation, proposal/ticket reporting explicitly labeled non-broker, and immutable
evidence archiving under `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`.

## Explicit exclusions

This decision does not authorize:

- crypto order construction or submission;
- authenticated/private Bybit endpoints;
- Demo, Testnet, or live-money execution;
- changing strategy, session, risk, entry, stop, target, or data-quality semantics;
- retroactively counting the 2026-09-05 diagnostic or any missed report window;
- installing or enabling an operating-system scheduler without a separate request.

`ST_LIQUIDITY_SWEEP_RETEST_V1` remains `demo_authorized: false` and
`live_authorized: false`. `CryptoExecutionAdapter` remains fail-closed and unimplemented.

## First eligible observation

The authorization was recorded at 06:52 UTC, after the frozen 00:05-00:15 UTC report
window for observation date 2026-09-05. That date is not backfilled. The first counted
observation must be generated in a future eligible report window and satisfy the frozen
complete-evidence and immutable-archive rules. `observation_campaign_started` becomes
true only when that first eligible observation is actually archived.

## Files changed

- `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`
- `PROJECT_STATUS.md`
- `docs/PROJECT_CAPABILITY_COMPLETENESS.md`
- `docs/README.md`
- this status document

No strategy, execution, Telegram, broker, market-data, or scheduler code changed. No
campaign observation was run or counted in this authorization milestone.
