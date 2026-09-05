# AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3 -- Status (2026-09-05)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. Owner-approved,
implemented, and provenance-frozen on an isolated branch/worktree, never touching the
active FX validation workspace.

## Baseline

```text
source_HEAD (branch start)   = 759e2cbefb02ed47555ce9bb691b4ee6fee8308c
fx_behavioral_validation_baseline = 3b2eeedcb31115795210e0ef00271b52ad6fbf53 (untouched)
btc_branch                            = btc/bybit-qualification-v3
btc_worktree                              = .claude/worktrees/btc-qualification-v3
```

## Owner authority

```text
explicit_owner_approval_found   = YES -- direct instruction, twice: once via
                                  AskUserQuestion ("Yes, approve read-only-only scope")
                                  and once as an explicit itemized message
                                  ("I approve: V1_0_3_BYBIT_QUALIFICATION_EXCEPTION =
                                  APPROVED_READ_ONLY_ONLY ...") -- neither is prompt
                                  text or a recommendation; both are the user's own words
qualification_exception            = APPROVED_READ_ONLY_ONLY, recorded durably in
                                     config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml's
                                     new qualification_exception block
authorized_scope                       = registration reconciliation; public
                                        unauthenticated Bybit market data; data-quality
                                        validation; existing-engine wiring; daily
                                        decisions; immutable archive; isolated
                                        branch/worktree; focused governance/
                                        implementation/provenance commits, not pushed
forbidden_scope                            = private/auth endpoints; order create/
                                            check/submit/modify/cancel; wallet/deposit/
                                            withdrawal/transfer; demo/live/automatic
                                            execution; BTC/FX strategy-semantic
                                            changes; FX session/risk/quota/proposal
                                            changes; geo/provider circumvention; mock/
                                            fixture/testnet/invalid data counting;
                                            starting the 30-day campaign before
                                            production validation
```

## Observation contract

Frozen in a prior commit on this same branch (`692c040`, "Freeze BTC daily observation
time contract") -- see `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md` and
`docs/status/AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1_STATUS.md`. Summary:
`document = FROZEN`, `observation_timezone = UTC`, `observation_date_definition = UTC
calendar date`, `observation_day_start/end = [00:00:00Z, next-day 00:00:00Z)`,
`daily_report_target_start/end = 00:05:00Z/00:15:00Z next day`,
`Myanmar_delivery_target_start/end = 06:35/06:45 MMT next day`.

## Registry

```text
schema_preserved         = YES -- only the existing fields (registered, active,
                           research, demo_authorized, live_authorized, config_source,
                           engine, note) were used; no new field added (tested)
strategy_id                   = ST_LIQUIDITY_SWEEP_RETEST_V1
registry_registered               = true
registry_active                       = false (Forex profile has no operating pilot;
                                       Crypto profile is proposal/observation-only via
                                       a dedicated runner, not a continuous pilot cycle)
registry_research                         = true
registry_demo_authorized                      = false
registry_live_authorized                          = false
registry_config_source                                = strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml
registry_engine                                           = RESEARCH_ONLY -- engine path,
                                                             BTC orchestration, market-data
                                                             adapters listed (see registry.yaml)
registry_note                                                 = reconciliation-only,
                                                               2026-09-05, no authority change
registry_consistent                                              = YES (tested,
                                                                    tests/test_btc_strategy_registration.py)
```

## Ledger

```text
strategy_version                = 2.0.0 (agrees with strategy YAML's own `version` field)
status                              = ACTIVE_INCUBATION (agrees with strategy YAML's own
                                    `status` field and STRATEGY_LEDGER.md)
execution_authority                    = DISABLED
generic_strategy_manager_dispatch          = NOT_REQUIRED -- not claimed, not
                                            implemented; registry.yaml's own header
                                            comment already documents no
                                            strategy-manager runtime exists in this
                                            repo, and this milestone did not build one
                                            (tested: test_generic_strategy_manager_dispatch_not_claimed)
```

## Bybit adapter

```text
implemented          = YES -- src/execution_runtime/bybit_linear_perp_feed.py
public_only               = YES
authentication_required       = NO
private_endpoints                = NONE
order_endpoints                      = NONE
wallet_endpoints                         = NONE
official_docs_used                           = YES -- WebFetch against
                                              bybit-exchange.github.io/docs/v5/market/kline
                                              and .../instrument this session, not
                                              assumed from memory; confirmed: category=linear,
                                              interval strings are bare integers ("5","60",
                                              not "5m"/"1h"), kline list is DESCENDING
                                              (reversed by the adapter), no explicit close
                                              time (derived), retCode/retMsg envelope
```

## Instrument

```text
provider          = BYBIT
internal_symbol       = BTCUSDT
provider_symbol           = BTCUSDT (category=linear)
market_type                   = LinearPerpetual (Bybit's own contractType string; internal
                              constant CONTRACT_TYPE = "LinearPerpetual")
```

## Data quality

```text
implemented         = YES (src/execution_runtime/bybit_linear_perp_feed.py, mirrors the
                      Binance adapter's fail-closed contract exactly)
symbol_identity          = enforced (ValueError if symbol != BTCUSDT)
instrument_identity          = enforced (category=linear only)
timeframe_mapping                = M5->"5", H1->"60" -- matches
                                  btc_sweep_research.pipeline's existing M5/H1
                                  requirement, no new timeframe
timestamp_normalization               = UTC, derived close_time = open_time + interval
                                       (Bybit provides no explicit close time)
closed_bar_only                           = enforced (_drop_forming_candle)
ordering                                      = enforced (_validate_series after
                                                reversing Bybit's own descending order)
duplicates                                        = rejected (CANDLE_DUPLICATE_TIMESTAMP)
missing_data                                          = rejected (CANDLE_UNEXPECTED_SPACING)
freshness                                                 = enforced (BybitFeedStaleData,
                                                           3x-timeframe threshold, same
                                                           as Binance adapter)
future_bars                                                   = N/A (Bybit does not return
                                                               future timestamps; forming-
                                                               candle drop covers the
                                                               boundary case)
malformed_OHLCV                                                   = rejected
                                                                   (CANDLE_OHLC_INCONSISTENT,
                                                                   CANDLE_NON_POSITIVE_PRICE)
non_finite_data                                                       = rejected
                                                                       (CANDLE_NAN_FIELD)
provider_errors                                                           = rejected
                                                                           (non-zero
                                                                           retCode ->
                                                                           BybitFeedRequestError)
overall                                                                       = PASS (24
                                                                               focused tests)
```

## BTC engine

```text
existing_engine_reused       = YES -- strategy_engine.sweep_retest (unchanged);
                               btc_sweep_research.pipeline.run_research_cycle (existing
                               orchestration, only additively parametrized)
strategy_semantics_changed       = NO
production_data_wired                = YES (via exchange_id/symbol_meta parameters)
```

## BTC daily runtime

```text
code_ready               = YES -- src/btc_sweep_research/daily_report.py
production_operational        = NO (see Production validation below)
daily_decision_generated          = YES (9 focused tests: WATCH/NO_TRADE/READY/DATA_ERROR)
zero_proposal_supported                = YES
READY_proposal_supported                   = YES
DATA_ERROR_supported                           = YES (feed exception -> DATA_ERROR,
                                                never an uncaught exception)
generic_strategy_manager_dispatch_required         = NO
operational_CLI_entrypoint                             = NOT BUILT this milestone --
                                                        daily_report.py exposes
                                                        build_btc_daily_report()/
                                                        archive_btc_daily_report() as
                                                        library functions (same
                                                        function-level granularity
                                                        FX's daily_fx_report.py has);
                                                        a scripts/run_btc_daily_report.py
                                                        CLI wrapper (analogous to
                                                        scripts/run_fx_daily_report.py)
                                                        was judged additional scope
                                                        beyond what was requested and
                                                        was not built -- explicitly
                                                        flagged here so
                                                        "code ready" is not overstated
                                                        as "operational"
```

## BTC report

```text
schema             = AG_BTC_DAILY_REPORT_V1
implemented             = YES
deterministic                = YES (pure function of feed + already-computed cycle result)
immutable_archive                = YES -- reuses post_asian_pilot.report_archive.write_report
                                  unchanged (generic over report_type; no new archive
                                  mechanism)
late_data_supported                   = policy frozen in the observation contract;
                                        not itself enforced by a scheduler (none built --
                                        see operational_CLI_entrypoint above)
correction_supported                      = YES (tested: CREATED, IDEMPOTENT,
                                           correction-001 with original preserved)
```

## Archive

```text
first_write         = CREATED (tested)
identical_repeat         = IDEMPOTENT (tested)
changed_content              = ADDITIVE_CORRECTION (tested, correction-001, original
                              untouched, `supersedes` correctly points at it)
historical_overwrite             = never occurs (same mechanism already proven for FX)
```

## Execution firewall

```text
automatic_execution      = DISABLED
demo_execution                = DISABLED
live_execution                    = DISABLED
order_check_calls                     = 0
order_send_calls                          = 0
crypto_order_calls                            = 0
broker_mutation_calls                             = 0
exchange_mutation_calls                               = 0
broker_ticket_returned                                    = NONE
exchange_order_id_returned                                    = NONE
```

Verified structurally (no import of `execution.executor`/`execution.coordinator`/
`mt5.management_gateway` anywhere in the 3 new/changed modules -- same boundary
`tests/test_btc_proposal_execution_boundary.py` already proves for the unmodified
pipeline) and by a focused test
(`test_daily_report_module_never_references_execution_send_path`).

## Production validation

```text
environment                  = this development environment (unchanged from prior
                               milestones)
Bybit_connectivity                = ENVIRONMENT_BLOCKED -- freshly re-tested 2026-09-05
                                    (after the adapter was implemented, using its own
                                    base URL, GET /v5/market/instruments-info):
                                    HTTP 403, "The Amazon CloudFront distribution is
                                    configured to block access from your country" --
                                    identical to the 2026-09-03 finding, not merely
                                    assumed unchanged
instrument_metadata                    = NOT RETRIEVABLE from this environment
closed_candles                             = NOT RETRIEVABLE from this environment
data_quality                                   = NOT EXERCISED against live data (only
                                                against the 24 offline fixture tests)
daily_runtime                                      = NOT EXERCISED against live data
                                                    (only against the 9 offline fixture
                                                    tests)
archive                                                = exercised offline only
result                                                     = BLOCKED_ENVIRONMENT
```

No circumvention (VPN/proxy/geo-relay) attempted or considered.

## BTC observation

```text
target                = 30 VALID DAILY PRODUCTION-MARKET OBSERVATIONS
campaign_started          = NO
observation_ready             = NO (blocked on Production validation above, not on
                              code readiness)
valid_observations                = 0/30
mock_evidence_counts                  = NO
fixture_evidence_counts                   = NO
testnet_evidence_counts                       = NO
```

## FX protection

```text
behavioral_baseline       = 3b2eeedcb31115795210e0ef00271b52ad6fbf53
protected_surfaces_changed    = NO -- confirmed by targeted diff at every stage
                                (before implementation, after governance commit, after
                                implementation commit): git diff 759e2cb -- src/post_asian_pilot/
                                strategy_engine/ config/pilot/
                                strategies/ST_ASIAN_SWEEP_5R_V1.yaml
                                config/canonical_sessions.yaml
                                scripts/run_post_asian_pilot.py
                                scripts/run_fx_daily_report.py -- empty every time
comparability_preserved           = YES
```

## Tests

```text
governance_tests         = tests/test_btc_strategy_registration.py (4 tests) +
                           tests/test_large_smc_registration.py (2, unchanged, reused
                           as the pattern) -- 6 passed
implementation_tests         = tests/test_bybit_linear_perp_feed.py (24) +
                              tests/test_btc_daily_report.py (9) -- 33 passed
regression_check                  = full existing BTC suite (test_btc_sweep_research_pipeline,
                                    test_btc_occurrence_identity, test_binance_usdtm_feed,
                                    test_btc_costs, test_btc_research_ledger,
                                    test_btc_proposal_execution_boundary) -- 72 passed,
                                    1 skipped (pre-existing, unrelated), 0 failed --
                                    proves the additive pipeline.py parametrization is
                                    byte-behavior-identical for every existing caller
combined_total                        = 111 passed, 1 skipped, 0 failed across all BTC-
                                        related tests this milestone touched or could
                                        have affected
large_backtests_run                       = NO
```

## Documentation

```text
README_updated              = NO -- no operational CLI entrypoint exists yet (see BTC
                               daily runtime above); nothing new is user-facing to
                               describe truthfully
docs_README_updated              = NO -- consistent with this session's established,
                                  repeatedly-confirmed convention (grep shows none of
                                  the ~12 other new V1.0.3/BTC status docs this session
                                  were added to docs/README.md's index either)
observation_contract_added           = YES (prior commit, 692c040)
PROJECT_STATUS_updated                   = YES -- 3 concise rolling lines across this
                                          milestone (observation-contract-freeze,
                                          governance, and this provenance-freeze entry)
manifest_updated                             = YES -- qualification_exception block
                                              added; btc_market_data_authority.adapter_status
                                              IMPLEMENTED; release_qualification_gates.btc
                                              fields updated; unrelated fx: gates and
                                              scope_freeze untouched
strategy_ledger_updated                          = NO -- already accurate since
                                                    2026-08-30, no edit needed
strategy_registry_updated                            = YES (governance commit)
status_document_updated                                  = YES (this file)
```

## Provenance

```text
governance_commit           = 705a790... (full: run `git log` on branch
                              btc/bybit-qualification-v3 -- "Authorize V1.0.3
                              read-only Bybit qualification path")
implementation_commit            = 0c5cda1... ("Implement read-only Bybit BTC daily
                                  decision path")
btc_implementation_baseline          = 0c5cda1... (implementation_commit -- the
                                      behavioral/source authority for this BTC capability)
provenance_freeze_commit                 = (this commit -- see final report for hash)
btc_behavioral_diff                          = src/execution_runtime/bybit_linear_perp_feed.py
                                              (new), src/btc_sweep_research/pipeline.py
                                              (additive params only),
                                              src/btc_sweep_research/daily_report.py (new)
fx_protected_surface_diff                        = NONE
```

## Push

```text
performed    = NO
```

## Final classification

**`BTC_IMPLEMENTED_PRODUCTION_VALIDATION_BLOCKED`**

Governance complete, implementation complete, all focused tests pass, FX protection
passes, execution firewall passes, provenance frozen -- but permitted production Bybit
access remains unavailable from this environment (freshly re-confirmed, not assumed).

```text
BTC_PRODUCTION_DAILY_DECISION_OPERATIONAL   = NO
BTC_OBSERVATION_READY                            = NO
BTC_VALID_OBSERVATIONS                               = 0/30
```

## Next action

`VALIDATE_BYBIT_BTC_PATH_IN_PERMITTED_ENVIRONMENT` -- from an environment where
`api.bybit.com` is reachable, re-run the same narrow read-only smoke test (instrument
metadata + recent closed candles + one daily report + archive) this milestone already
attempted and found blocked. Do not circumvent the restriction. Only after that passes
should a separate milestone consider authorizing the 30-day observation campaign start.
