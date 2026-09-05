# AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1 -- Status (2026-09-05)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Freezes the BTC
daily observation/report timing contract. Governance/documentation only -- no adapter
code, no observation start, no strategy change.

## Baseline

```text
current_HEAD (this branch)          = 759e2cb...  (btc/bybit-qualification-v3 branch,
                                      isolated worktree -- see
                                      AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3
                                      for the branch/worktree record)
fx_behavioral_validation_baseline       = 3b2eeedcb31115795210e0ef00271b52ad6fbf53
```

## Strategy timing (verified from source, not assumed)

```text
strategy_id                = ST_LIQUIDITY_SWEEP_RETEST_V1
strategy_version                = 2.0.0
strategy_timeframes                 = M5 (SWEEP_MSS_RETEST), H1 (DIRECTIONAL_MARKET_STRUCTURE_ONLY)
strategy_session_rules                   = CRYPTO_PERP profile: reference=PREVIOUS_DAY
                                          (strategy YAML's own comment: "Strict UTC
                                          midnight-to-midnight day boundary"),
                                          execution_windows=Strategy_Activity_Window
                                          13:30-16:00 UTC (never crosses midnight)
strategy_timing_semantics_changed             = NO
```

## Observation contract (frozen)

See [`docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`](../contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md)
for the full text. Summary:

```text
observation_timezone          = UTC
observation_date_definition       = UTC calendar date (matches the strategy's own
                                    PREVIOUS_DAY reference boundary)
observation_day_start                 = 00:00:00 UTC (inclusive)
observation_day_end                       = 00:00:00 UTC next day (exclusive)
interval_semantics                            = half-open [start, end)
daily_report_target_start                         = 00:05:00 UTC (day after observation date)
daily_report_target_end                               = 00:15:00 UTC (day after observation date)
Myanmar_delivery_target_start                             = 06:35 MMT (following local day)
Myanmar_delivery_target_end                                   = 06:45 MMT (following local day)
```

## Candle contract

```text
required_timeframes         = M5, H1
final_required_timeframe        = M5
final_required_candle               = M5 candle with close_time == 16:00:00 UTC on the
                                      observation date (last candle the strategy's own
                                      execution window could use -- confirmed no new
                                      occurrence can be enumerated after that per
                                      src/btc_sweep_research/pipeline.py's existing
                                      window-gated enumerate_sweep_candidates(),
                                      unmodified)
bar_timestamp_semantics                  = keyed by normalized UTC open timestamp
                                          (Candle.time); closed only when runtime "now"
                                          >= open_time + timeframe duration
required_closed_candle_cutoff                = 16:00:00 UTC same day (comfortably
                                              earlier than the 00:05 UTC next-day report
                                              target -- 8+ hour margin)
in_progress_bar_allowed                          = NO
```

## Provider time expectation

```text
internal_timestamp_authority        = adapter-injected clock (dependency-injection,
                                      same pattern as
                                      execution_runtime.binance_usdtm_feed.BinanceUSDTMFeed)
provider_timestamp_semantics_required   = bar-open UTC epoch-ms, closed-bar-only
official_Bybit_verification_deferred_to_adapter_milestone  = NO -- already independently
                                                             verified this session via
                                                             WebFetch against Bybit's
                                                             official V5 docs
                                                             (bybit-exchange.github.io/docs/v5/market/kline
                                                             and .../instrument) while
                                                             implementing
                                                             src/execution_runtime/bybit_linear_perp_feed.py
                                                             as part of the parallel,
                                                             owner-approved V3
                                                             implementation milestone
```

## Late-data / correction policy

```text
policy                = check at 00:05 UTC; may re-check until 00:15 UTC cutoff; no
                        favorable retry beyond cutoff; incomplete data at cutoff ->
                        fail-closed DATA_ERROR for that observation date, never
                        fabricated
00_05_behavior             = check completeness, finalize if complete
00_15_behavior                  = hard cutoff -- finalize with whatever evidence exists,
                                  DATA_ERROR if incomplete
post_cutoff_behavior                 = late-arriving valid data produces an
                                      ADDITIVE_CORRECTION artifact only; original never
                                      overwritten
favorable_retry_allowed                  = NO
retroactive_VALID_DAY_counting_for_a_corrected_DATA_ERROR_day  = NOT AUTHORIZED --
                                                                explicitly recorded as
                                                                unresolved governance,
                                                                not guessed
```

## Correction policy

```text
original_overwrite     = NO (forbidden)
identical_rerun             = IDEMPOTENT
changed_evidence                 = ADDITIVE_CORRECTION
```

Reuses `post_asian_pilot.report_archive.write_report` unchanged (already generic over
`report_type` -- no new archive mechanism built for this contract).

## Decision

```text
daily_decision_required   = YES
possible_states                = READY, WATCH, NO_TRADE, DATA_ERROR, BLOCKED, EXPIRED
                                (existing project vocabulary, none invented)
proposal_required                  = NO
execution                              = DISABLED
```

## Observation validity

```text
target                    = 30 VALID DAILY PRODUCTION-MARKET OBSERVATIONS
elapsed_day_auto_counts        = NO
weekends_eligible                  = YES, subject to the same evidence-completeness rule
mock_data_counts                       = NO
fixture_data_counts                        = NO
testnet_data_counts                            = NO
```

## FX timing (verified unchanged)

```text
Asian_London_window       = 07:00-11:00 UTC
Asian_London_final            = 11:00 UTC
London_NewYork_window             = 12:00-15:00 UTC
London_NewYork_final                  = 15:00 UTC
combined_FX_report                        = ~15:05 UTC
fx_timing_changed                             = NO
```

## FX protection

```text
fx_protected_surface_diff   = NONE (git diff 759e2cb -- src/post_asian_pilot/
                              strategy_engine/ config/pilot/
                              strategies/ST_ASIAN_SWEEP_5R_V1.yaml
                              config/canonical_sessions.yaml
                              scripts/run_post_asian_pilot.py
                              scripts/run_fx_daily_report.py -- empty)
comparability_preserved         = YES
```

## Documentation

```text
contract_created         = YES (docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md)
status_created                = YES (this file)
PROJECT_STATUS_updated            = YES (one concise rolling line)
docs_README_updated                   = NO -- consistent with this session's established,
                                       observed convention: docs/README.md's "Status and
                                       evidence" index does not list every dated status
                                       document (confirmed by grep in an earlier
                                       milestone this session -- zero of the ~10 other
                                       new V1.0.3/BTC status docs were added there
                                       either); adding only this one would be an
                                       inconsistent one-off deviation
README_updated                            = NO -- no user-facing capability exists yet to
                                           describe (the adapter/runtime this contract
                                           feeds is still mid-implementation in the
                                           parallel V3 milestone)
manifest_reference_updated                    = NO this commit -- the V3 governance
                                               commit (same branch) is the more
                                               appropriate place to record the
                                               observation-contract reference alongside
                                               the qualification-exception/adapter-status
                                               fields it is already touching, avoiding
                                               two separate touches to the same manifest
                                               file
```

## Tests

```text
focused_tests      = none added this milestone -- purely a documentation/contract
                     freeze; nothing executable to test. The contract's concrete claims
                     (timeframe requirements, window boundaries, closed-candle
                     semantics) are exercised indirectly by the existing
                     src/btc_sweep_research tests (unchanged) and by the new adapter
                     tests being added in the parallel V3 implementation milestone.
backtests_run           = NO
```

## Commit

```text
created          = YES (this branch, btc/bybit-qualification-v3 -- see final report for hash)
message               = "Freeze BTC daily observation time contract"
pushed                    = NO
```

## BTC observation

```text
ready_to_implement_runtime   = YES -- no strategy timing conflict found
campaign_started                  = NO
valid_observations                    = 0/30
```

## Final classification

**`BTC_OBSERVATION_TIME_CONTRACT_FROZEN`**

## Next action

Resume the separately authorized, already-in-progress
`AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3` implementation
milestone (same isolated branch/worktree), which will consume this frozen contract's
UTC boundary/closed-candle-cutoff/late-data/correction rules for the daily report it
builds. Not performed automatically by this contract-freeze milestone itself.
