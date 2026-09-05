# AG_BTC_DAILY_OBSERVATION_CONTRACT_V1

## Purpose

Freezes the BTC daily observation/evidence-reporting boundary for
`AG_TRADE_ASSISTANT_V1_0_3`'s BTC qualification path
(`ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0, `CRYPTO_PERP` profile, BTCUSDT), so the Bybit
daily-decision runtime has an unambiguous, deterministic definition of: which date is
being evaluated, when that date is complete, which candles must be closed, when the
final decision should normally be delivered, and how late/corrected data is handled.

This is a **reporting/evidence-aggregation boundary**. It does not define, redefine, or
constrain any strategy session, entry window, signal window, or qualification rule --
see "Strategy-timing compatibility" below for the explicit finding that no conflict
exists.

## Authority

Governance/documentation contract, part of
`AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3`
(owner-approved read-only scope). Does not itself authorize execution, trading, or the
30-day observation campaign start.

## Strategy-timing compatibility (verified, not assumed)

Read directly from `strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml`'s `CRYPTO_PERP`
profile:

```yaml
reference:
  kind: PREVIOUS_DAY
  label: PreviousDay
  # "Strict UTC midnight-to-midnight day boundary (spec)"   <- already the strategy's
  #                                                             own frozen day-boundary
  #                                                             contract, not invented here
execution_windows:
  - name: Strategy_Activity_Window
    start_time_gmt: "13:30"
    end_time_gmt: "16:00"        # entirely within one UTC calendar day, never crosses midnight
```

```text
FINAL_REQUIRED_TIMEFRAME  = M5 (SWEEP_MSS_RETEST, per timeframe_responsibilities) and
                            H1 (DIRECTIONAL_MARKET_STRUCTURE_ONLY) -- matches
                            src/btc_sweep_research/pipeline.py's existing
                            M5_LOOKBACK_COUNT/H1_LOOKBACK_COUNT and the Bybit adapter's
                            _TIMEFRAME_TO_BYBIT_INTERVAL = {"M5": "5", "H1": "60"};
                            no new timeframe introduced by this contract
FINAL_REQUIRED_CANDLE       = the M5 candle whose close_time == 16:00:00 UTC on the
                              observation date -- the strategy's own execution_windows
                              close before that candle's own reference-day boundary
                              ends, so no new occurrence can be enumerated for that
                              trading day after 16:00 UTC (pipeline.run_research_cycle's
                              own window-gated enumerate_sweep_candidates() already
                              enforces this; unchanged by this contract)
strategy_timing_semantics_changed = NO
```

**Finding: no conflict.** The strategy's own execution window (13:30-16:00 UTC) closes
hours before the proposed daily-report target window (00:05-00:15 UTC the *following*
day) even begins -- the report boundary is comfortably, conservatively later than the
last possible moment the strategy could produce a new occurrence for that date. Using
the proposed report window can never involve an in-progress bar for the observation
date it reports on.

## Canonical (machine) contract

```text
BTC_OBSERVATION_TIMEZONE       = UTC
BTC_OBSERVATION_DATE_DEFINITION    = UTC calendar date (matches the strategy's own
                                     PREVIOUS_DAY reference boundary above -- not a
                                     separate/competing definition)
BTC_OBSERVATION_INTERVAL_SEMANTICS     = half-open: [start, end)
BTC_OBSERVATION_DAY_START                  = 00:00:00 UTC (inclusive) on the observation date
BTC_OBSERVATION_DAY_END                        = 00:00:00 UTC (exclusive) on the NEXT calendar date

Example -- observation date 2026-09-07:
  interval = [2026-09-07T00:00:00Z, 2026-09-08T00:00:00Z)

BTC_DAILY_REPORT_TARGET_WINDOW      = [2026-09-08T00:05:00Z, 2026-09-08T00:15:00Z]
                                      (00:05-00:15 UTC on the day AFTER the observation date)
BTC_MYANMAR_DELIVERY_WINDOW              = [06:35, 06:45] MMT (UTC+06:30), same calendar
                                          conversion, following local day -- MMT is a
                                          DISPLAY conversion only; UTC remains the sole
                                          canonical evidence authority
```

```text
PROVIDER_TIMESTAMP_SEMANTICS (internal expectation this contract freezes; the actual
Bybit endpoint fields are separately verified in
src/execution_runtime/bybit_linear_perp_feed.py against Bybit's official V5 docs, not
re-derived here):
  - bar identity is keyed by its normalized UTC OPEN timestamp (candle_time, as
    strategy_engine.session.Candle already represents it)
  - a bar is considered CLOSED only when the runtime's authoritative "now" is >= that
    bar's deterministic interval close (open_time + timeframe duration) -- same rule
    the Binance and Bybit adapters both already enforce (_drop_forming_candle)
  - provider server time is not required as a separate authority beyond the adapter's
    own injected clock (same dependency-injection pattern as
    execution_runtime.binance_usdtm_feed.BinanceUSDTMFeed) -- no new time source
    introduced
```

## Report precondition (fail-closed)

The final BTC daily report for a given observation date may be generated only when
**all** of the following hold -- reaching the target clock window (00:05-00:15 UTC) is
necessary but never sufficient on its own:

1. the observation day interval `[start, end)` has fully elapsed;
2. the M5 candle closing at `16:00:00 UTC` on the observation date (the last candle the
   strategy's own execution window could have used) is confirmed closed by the
   provider/adapter's own closed-bar rule;
3. required production data (H1 + M5 series covering the observation date and its
   `PREVIOUS_DAY` reference) is available and passes data-quality validation;
4. if (3) fails, the daily result deterministically resolves to a fail-closed decision
   state (`DATA_ERROR`) rather than blocking report generation indefinitely.

No in-progress/forming bar may ever be used, regardless of clock time.

## Late-data policy

```text
at 00:05 UTC (window open):    check required data completeness
if complete:                    finalize the daily report normally within the window
if incomplete (plausibly late): may re-check until 00:15 UTC (window close) -- no
                                 favorable retry beyond that, no fabricated data
at/after 00:15 UTC (cutoff):        if still incomplete, produce the fail-closed
                                    DATA_ERROR daily report for that observation date
                                    using whatever partial evidence exists -- never
                                    invent missing candles/decisions
if valid data later resolves
the issue (after the original
report was already produced):           create an ADDITIVE_CORRECTION artifact (see
                                        below); never overwrite the original
retroactive VALID_DAY counting
for a corrected DATA_ERROR day:            NOT AUTHORIZED BY THIS CONTRACT -- recorded
                                           as an explicitly unresolved governance
                                           question, not guessed at here. A future,
                                           separately authorized reconciliation rule
                                           would be required before any corrected day
                                           could count toward the 30-observation target.
```

## Correction policy (reuses the existing append-only archive convention unchanged --
## `post_asian_pilot.report_archive.write_report`, already generic over `report_type`)

```text
original report      = immutable, never overwritten
identical re-run          = IDEMPOTENT (same path returned, no new file)
changed evidence              = ADDITIVE_CORRECTION (`<date>.correction-NNN.json`,
                                carrying `original_record_identity`,
                                `correction_reason`, `corrected_at`, `supersedes`,
                                `new_record` -- identical shape already proven by the
                                FX daily archive)
```

## Daily decision family

Reuses the existing project decision vocabulary exactly -- no new status invented for
scheduling purposes:

```text
READY | WATCH | NO_TRADE | DATA_ERROR | BLOCKED | EXPIRED
```

`DAILY_DECISION_REQUIRED = YES`, `PROPOSAL_REQUIRED = NO` (a READY proposal is
conditional on the existing strategy engine's own qualification, never forced).
`EXECUTION = DISABLED` throughout; this contract has no bearing on and does not touch
execution authority.

A separate, explicitly distinct **evidence classification** layer (e.g.
`PENDING_RECONCILIATION`) may describe the archive-level state of a given date without
being confused with the strategy's own decision for that date -- the two are never
conflated in the daily report schema.

## Valid-observation rule (reference; governs `30/30`, not decided by this contract
## alone -- restated here for a single source of truth)

```text
target                  = 30 VALID daily production-market observations, not 30 elapsed
                          calendar days
elapsed_day_auto_counts     = NO
weekends_eligible               = YES, subject to the same evidence-completeness rule as
                                  any other day (BTC trades continuously; nothing in
                                  this contract excludes a weekend UTC date)
mock/fixture/testnet/backtest_data_counts = NO
```

## Examples

```text
Observation date 2026-09-07 (Monday):
  interval          = [2026-09-07T00:00:00Z, 2026-09-08T00:00:00Z)
  last strategy-relevant candle = M5 bar closing 2026-09-07T16:00:00Z
  report target      = [2026-09-08T00:05:00Z, 2026-09-08T00:15:00Z]
  Myanmar display        = 2026-09-08, 06:35-06:45 MMT

Observation date 2026-09-13 (Sunday):
  interval          = [2026-09-13T00:00:00Z, 2026-09-14T00:00:00Z)
  same rules apply -- BTC/Bybit data exists on weekends; no exclusion
```

## What this contract does NOT do

- does not implement the Bybit adapter, HTTP client, or any provider call;
- does not start BTC observation Day 001 or mutate the 0/30 counter;
- does not change `ST_LIQUIDITY_SWEEP_RETEST_V1`'s sessions, entry rules, risk, or
  qualification logic;
- does not change FX timing (Asian-London 07:00-11:00 UTC / final 11:00 UTC;
  London-New York 12:00-15:00 UTC / final 15:00 UTC; combined FX report ~15:05 UTC --
  all verified unchanged, see the accompanying status document's FX protection check).
