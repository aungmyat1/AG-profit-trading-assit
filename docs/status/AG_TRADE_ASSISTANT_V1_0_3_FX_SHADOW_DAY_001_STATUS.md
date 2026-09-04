# AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_STATUS -- Day 001 (2026-09-02)

`VALIDATION_SERIES_ID`: `AG_V1_0_3_FX_SHADOW_SERIES_001`
`APPLICATION_VERSION`: `AG_TRADE_ASSISTANT_V1_0_3`
`FX_STRATEGY_VERSION`: `ST_ASIAN_SWEEP_5R_V1 v1.1.1`
`DATE`: `2026-09-02`

## What happened

Shadow-validation Day 1 was authorized this turn. Before running any evaluation, this
day's evidence was checked against the frozen `AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1`
(`docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_VALIDATION_STATUS.md`) and found not to
qualify as a fair test of the frozen runtime, for reasons that are all pre-existing/
external per the contract's own `EXCLUDED_DAY` definition -- not a runtime, strategy, or
manifest defect.

1. **Both execution windows for 2026-09-02 had already closed before authorization.**
   System UTC time at authorization was `2026-09-02T22:42:27Z`; MT5 broker server time
   (checked read-only via `mt5.symbol_info_tick`) was `2026-09-03T01:42:26Z`. Under
   either clock, `ASIAN_LONDON`'s execution window (`07:00`-`11:00` UTC) closed roughly
   11-12 hours before authorization, and `LONDON_NEWYORK`'s (`12:00`-`15:00` UTC) closed
   roughly 7-8 hours before. There was no remaining window left to observe today.

2. **Both cycles' ledgers already contain real, pre-existing claimed slots for
   2026-09-02, tagged to the prior release.** Read directly from
   `journal/post_asian_pilot/daily_trade_ledger.json` and
   `journal/post_london_newyork_pilot/daily_trade_ledger.json` (read-only, no write
   performed by this check):

   ```text
   ASIAN_LONDON   2026-09-02: EURUSD CLAIMED (ready_at 07:30 UTC, claimed_at 11:16 UTC), GBPUSD CLAIMED (ready_at 07:00 UTC, claimed_at 11:16 UTC) -- release_id AG_TRADE_ASSISTANT_V1_0_2
   LONDON_NEWYORK 2026-09-02: EURUSD CLAIMED (ready_at 12:15 UTC, claimed_at 18:29 UTC), GBPUSD CLAIMED (ready_at 12:30 UTC, claimed_at 18:29 UTC) -- release_id AG_TRADE_ASSISTANT_V1_0_2
   ```

   All four slots were claimed hours before this milestone's authorization, under the
   application's ordinary, pre-existing V1.0.2 operation (the pilot runtime's
   `DEFAULT_RELEASE_CONFIG_PATH` still points at V1.0.2 by design -- V1.0.3 is
   descriptive-only and was never wired into the running default, per the manifest-
   freeze milestone). This activity is real, legitimate prior operation, but it is not
   attributable to the newly-frozen `AG_V1_0_3_FX_SHADOW_SERIES_001` -- it happened
   before the series existed.

3. **One read-only probe was run** (`python scripts/run_post_asian_pilot.py --once
   --json`, the same one-shot, proposal-only entrypoint the pre-existing
   `scripts/scheduled/run_asian_london_once.bat` already uses -- never `--watch`, never
   `order_send`-reachable) to confirm current live state before deciding. It returned
   `WATCH` / `WAITING_CLOSED_M15_CONFIRMATION` for both `ASIAN_LONDON` symbols at
   `evaluation_time_utc = 2026-09-02T22:40:32Z`, well after that cycle's window close,
   with `daily_opportunity_ledger.used = 2/2` (matching the pre-existing claims above).
   No LONDON_NEWYORK cycle was run live -- the same closed-window/pre-existing-ledger
   finding was already established for it by the read-only ledger check, and running it
   again would have added no new information.

## ASIAN_LONDON

- EURUSD state: `N/A_WINDOW_ALREADY_CLOSED` (live probe returned stale post-window
  `WATCH`; ledger already shows this symbol `CLAIMED` from pre-existing activity)
- GBPUSD state: `N/A_WINDOW_ALREADY_CLOSED` (same)
- duplicate status: `N/A` -- no new claim was attempted or made by this milestone
- quota/isolation status: `N/A_NOT_EVALUATED_THIS_SERIES` -- the 2/2 slots present belong
  to pre-existing V1.0.2 activity, not this series

## LONDON_NEWYORK

- EURUSD state: `N/A_WINDOW_ALREADY_CLOSED`
- GBPUSD state: `N/A_WINDOW_ALREADY_CLOSED`
- duplicate status: `N/A` -- no new claim was attempted or made by this milestone
- quota/isolation status: `N/A_NOT_EVALUATED_THIS_SERIES`

## Data

- completeness: N/A for this day's classification -- not a data-availability question
- errors: none (no `DATA_ERROR`, no `SYSTEM_COULD_NOT_EVALUATE`; the underlying data
  path was already proven ready by the prerequisite MT5-readiness closure milestone)

## Restarts

- count: 0
- reconciliation: N/A

## Execution safety

- proposal_only: YES
- broker_send_reachable: NO -- the one read-only probe run today used the existing
  `--once` entrypoint, which never calls `execution.executor` / `mt5_gateway` /
  `order_check` / `order_send` (confirmed by that script's own module docstring and by
  the reused execution-boundary test evidence from the prerequisite preflight
  milestone, unchanged `git_head` for that code path)

## Day classification

**`EXCLUDED_DAY`**

- `exclusion_reason`: Shadow-validation authorization for `AG_V1_0_3_FX_SHADOW_SERIES_001`
  occurred after both `ASIAN_LONDON` and `LONDON_NEWYORK` execution windows for
  2026-09-02 had already closed, and after both cycles' ledgers already held real,
  pre-existing claimed slots from ordinary prior V1.0.2-labeled operation unrelated to
  this series. There was no remaining, uncontaminated window in which to fairly test
  the frozen V1.0.3 runtime today. This is the `EXCLUDED_DAY` case of "the runtime
  environment was not available for this series before the evaluation window" adapted
  to a timing/authorization-order fact rather than an outage -- not a strategy loss, not
  an absence of a setup, and not an unfavorable result (per the contract, none of those
  would qualify for exclusion; this does, on pure timing/attribution grounds).
- `evidence`: git_head `fad8ee2df8361f32df765805367b721c3cbd04f7` at authorization time
  (clean working tree, 0 ahead/0 behind origin/main); ledger excerpts above; one
  read-only `--once` probe transcript (preserved in full in this document).
- `affected_cycle`: `ASIAN_LONDON`, `LONDON_NEWYORK` (both)
- `affected_symbol`: `EURUSD`, `GBPUSD` (all four units)
- `timestamp`: authorization and evaluation both occurred at `2026-09-02T22:4x:xxZ`
  system UTC (`2026-09-03T01:4x:xxZ` MT5 broker server time)

`EXCLUDED_DAY` does not increment `VALID_DAYS`. It does not reset any prior valid day
(there are none yet in this series).

## Counters (after this day)

```text
valid_days       = 0/20
excluded_days    = 1
invalid_days      = 0
pending_days       = 0
```

## Blockers

None that block the series itself. This is a timing fact, not a defect: Day 1 proper
should begin on the next trading day whose `ASIAN_LONDON` execution window
(`07:00`-`11:00` UTC) has not yet opened at the time evaluation is next run --
i.e. `2026-09-03` (Thursday, per both system and broker clocks -- not a weekend), run
at or before `07:00` UTC, or at any point during/shortly after its window, to capture a
genuine, uncontaminated day for this series.

No discretionary strategy recommendation is included, per the frozen daily-report
contract.
