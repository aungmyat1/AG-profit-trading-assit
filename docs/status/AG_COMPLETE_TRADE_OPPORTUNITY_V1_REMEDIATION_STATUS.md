# AG_COMPLETE_TRADE_OPPORTUNITY_V1 -- Remediation Status (2026-09-02)

Dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`. This document
records the remediation of gaps found during independent review of the initial
`AG_COMPLETE_TRADE_OPPORTUNITY_V1` implementation (FX `LONDON_NEWYORK` cycle activation;
BTC Binance USDT-M research runtime). It does not re-describe work that was already
correct -- see `strategies/STRATEGY_LEDGER.md`'s `ST_ASIAN_SWEEP_5R_V1` and
`ST_LIQUIDITY_SWEEP_RETEST_V1` entries for the full change history.

## Baseline

- `git_head` (start of remediation): `f7d7eaf` (unchanged from the original
  implementation's own baseline -- no commits were made between implementation and this
  remediation pass).
- Branch: `main`.
- Working tree: 6 files modified, 12 files created by the original implementation, plus
  the changes below by this remediation pass.

## Gaps found and fixed

### Gap 1 -- BTC multi-occurrence collection

**Before:** the BTC research pipeline used one `setup_id` per `symbol:trading_day`.
`SweepRetestRuntime` (by design, for restart-safety) never re-evaluates a `setup_id`
already in a terminal state, so once that single day-level identity reached
`EXPIRED`/`NO_TRADE`/`BLOCKED`, a genuinely later, independent sweep the same day was
never evaluated -- opportunity evidence was silently lost.

**Fix:** `strategy_engine/sweep_retest/occurrence_enumerator.py` (new) enumerates every
qualifying sweep candidate in a window by repeatedly calling the SAME
`sweep.find_qualified_sweep` against a shrinking candle pool -- no second
sweep-qualification rule. `engine.py::evaluate_setup` gained an optional
`sweep_search_after` parameter (default `None`, zero behavior change for any existing
caller) so each enumerated candidate can be evaluated against its own, later starting
point. `btc_sweep_research/pipeline.py::run_research_cycle` now returns a
`ResearchCycleReport` with 0..N `ResearchCycleResult` occurrences (previously always
exactly one `ResearchCycleResult`), each with its own occurrence-scoped `setup_id`
(`f"{symbol}:{trading_day}:{sweep_candle_time}"`), independently tracked and
restart-safe through the same, unmodified `SweepRetestRuntime`.

**Verified:** `tests/test_btc_sweep_research_pipeline.py` --
`test_two_independent_occurrences_same_day_both_recorded`,
`test_three_independent_occurrences_no_hidden_cap`,
`test_first_occurrence_expired_does_not_block_second`,
`test_duplicate_suppressed_but_new_later_occurrence_discovered_after_restart`. Also
`tests/test_liquidity_sweep_retest_strategy.py::test_sweep_search_after_skips_earlier_sweep_in_window`.

### Gap 2 -- research occurrence vs. tradability guard

**Before:** `evaluate_setup` checked `daily_loss_guard`/`open_position_guard` before any
candle work. A genuinely qualified setup that happened to be guard-blocked was reported
identically to a setup that was never a real opportunity at all -- opportunity evidence
was erased by an unrelated portfolio-level guard.

**Fix:** guard checks moved to the END of `evaluate_setup`, applied only where the
function would otherwise return `ENTRY_READY`. `SetupState` gained three fields:
`strategy_qualified` (True once full qualification -- box, direction, sweep, MSS,
retest, target geometry, sizing -- succeeds, independent of any guard),
`tradability_blocked`, `tradability_reason`. `BTCSweepResearchProposal` gained
`tradability_allowed`/`tradability_block_reason`. The BTC pipeline now builds a proposal
and records a research-ledger row whenever `strategy_qualified` is True, regardless of
tradability -- research occurrence counts are identical whether or not a guard is
active; only simulated-trade eligibility differs. Guard RULES are unchanged (same
guards, same thresholds); only when they are consulted changed.

**Verified:** `tests/test_btc_sweep_research_pipeline.py` --
`test_open_position_guard_blocks_tradability_but_occurrence_still_recorded`,
`test_daily_loss_guard_blocks_tradability_but_occurrence_still_recorded`,
`test_research_occurrence_count_identical_regardless_of_guard_state`. Also
`tests/test_liquidity_sweep_retest_strategy.py::test_guard_blocked_setup_still_reports_strategy_qualified_true`,
`test_unblocked_entry_ready_reports_qualified_and_tradable`,
`test_non_qualifying_setup_reports_strategy_qualified_false`.

**Regression found and fixed by this change:** moving the guard check broke
`tests/test_execution_runtime_readiness.py::test_one_context_gives_consistent_blocking_between_evaluation_and_coordinator`,
which relied on the OLD guard-first shortcut to observe guard state using empty/
degenerate candle input. Fixed by giving that test a real, minimal ENTRY_READY-reaching
Forex fixture (same shape as `test_liquidity_sweep_retest_strategy.py`'s own validated
fixture) so it now genuinely reaches qualification before observing the guard --
verifying the SAME cross-call-site guard-sharing property the test always intended,
through the new (correct) checkpoint.

### Gap 3 -- explicit execution-domain rejection

**Before:** `execution.executor.execute()` accepted any object typed `command:
TradeCommand` with no runtime check; a BTC research proposal forced into it failed with
an incidental `AttributeError` the first time an FX-only field was accessed -- a shape
mismatch, not a safety gate.

**Fix:** `execute()` now checks `isinstance(command, TradeCommand)` before reading any
field, raising a new typed `UnsupportedExecutionDomain` (in `execution/executor.py`) if
not. No coupling to BTC internals -- the check is domain-agnostic (accepts only its own
`TradeCommand`), not an import of `btc_sweep_research`.

**Verified:** `tests/test_btc_proposal_execution_boundary.py` --
`test_calling_executor_execute_with_btc_proposal_raises_explicit_domain_rejection`,
`test_malformed_object_does_not_bypass_domain_check`. Existing FX executor tests
(`tests/test_execution_executor.py` and others, 155 passed together with the
`runtime_readiness` fix above) confirm the real `TradeCommand` happy path is unaffected.

### Gap 4 -- undeclared `requests` dependency

**Before:** `execution_runtime/binance_usdtm_feed.py` imports `requests`, which was not
listed in `requirements.txt` (the repository's one dependency manifest).

**Fix:** added `requests==2.34.2` to `requirements.txt` with a dated comment.

### Gap 5 -- feed validation completeness

**Before:** negative volume was not rejected; malformed/out-of-range exchange
timestamps could leak a raw `ValueError`/`OverflowError`/`OSError` instead of a typed
feed error.

**Fix:** `_parse_klines` now rejects `volume < 0` (`CANDLE_NEGATIVE_VOLUME`; `volume ==
0` remains valid -- a genuinely quiet bar). A new `_to_epoch_ms` helper normalizes
malformed timestamp fields to `CANDLE_MALFORMED_TIMESTAMP`/`CANDLE_NULL_TIMESTAMP`.
`_to_candles` normalizes out-of-range epoch values to `CANDLE_TIMESTAMP_OUT_OF_RANGE`.

**Verified:** `tests/test_binance_usdtm_feed.py` -- `test_negative_volume_rejected`,
`test_zero_volume_is_valid`, `test_malformed_open_timestamp_normalized_not_leaked`,
`test_null_close_timestamp_normalized_not_leaked`,
`test_out_of_range_open_timestamp_normalized_not_leaked` (this last one calls
`_to_candles` directly, since an out-of-range-old timestamp always trips the
forming-candle or staleness gate first through the normal `get_latest_candles` path --
both gates compare against "now" and reject it earlier; the direct call exercises the
normalization as the internal defense-in-depth it is).

### Gap 6 -- live connectivity verification

**Attempted from this development environment on 2026-09-02:**

```text
GET https://fapi.binance.com/fapi/v1/exchangeInfo -> HTTP 451
GET https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=5m&limit=5 -> HTTP 451
Response body: {"code":0,"msg":"Service unavailable from a restricted location according
to 'b. Eligibility' in https://www.binance.com/en/terms. ..."}
```

This is Binance itself explicitly geo-blocking this environment's egress IP (not a
timeout, not a DNS failure, not a proxy issue) -- the network path is reachable, but
Binance refuses service to this specific location under its own terms of service.

**Result:** `LIVE_CONNECTIVITY = BLOCKED_GEO_RESTRICTED` (this environment only). This
does NOT mean the adapter is broken -- offline/mocked validation is comprehensive and
green (see Tests below) -- but it does mean live connectivity is genuinely unverified
from here. **Before relying on this operationally, re-run the same two requests (or
`pytest -m ""` against `tests/test_binance_usdtm_feed.py::test_live_smoke_fetch_real_btcusdt_klines`
with its `skipif` removed) from the actual deployment machine/network the runtime will
use.** If that environment is also geo-restricted from Binance, this exchange choice
needs revisiting before any shadow-validation phase begins.

### Gap 7 -- status documentation

Updated per `docs/status/LIVE_STATUS_MAINTENANCE.md`'s required sequence:
`PROJECT_STATUS.md` rolling snapshot, `README.md`'s crypto/FX capability lines,
`strategies/STRATEGY_LEDGER.md` (`ST_ASIAN_SWEEP_5R_V1`'s `LONDON_NEWYORK` pilot
activation note; new `ST_LIQUIDITY_SWEEP_RETEST_V1` section), `docs/README.md`'s
evidence index, and this document.

## Exchange metadata consistency (raised during remediation, section 19/20 of the review)

**Before:** the BTC pipeline computed a fully qualified setup using
`strategy_engine.sweep_retest.crypto_symbols.crypto_symbol_meta()`'s hardcoded synthetic
tick/step/min-qty constants, even though the newly-added Binance adapter already carries
its own exchange-specific record of the same facts (`default_symbol_meta()` /
`fetch_exchange_symbol_meta()`) -- two authorities for the same numbers.

**Fix:** `execution_runtime/binance_usdtm_feed.py` gained `to_symbol_meta()`, bridging
`BinanceSymbolMeta` into the `SymbolMeta` shape `execution.risk.size_position` consumes.
`btc_sweep_research/pipeline.py` now sources `symbol_meta` (and the stop-loss tick
buffer) from `to_symbol_meta(default_symbol_meta(...))`, not `crypto_symbol_meta()`.
Still tagged `METADATA_SOURCE_SYNTHETIC_RESEARCH`, never `METADATA_SOURCE_EXCHANGE_VERIFIED`
-- that tag's real meaning elsewhere in this repo is
`execution.adapter.require_exchange_verified_metadata()`'s FX/MT5 broker-order
eligibility gate, which this crypto RESEARCH-domain record must never claim regardless
of whether the underlying numbers came from a live fetch or the offline-safe documented
default. Strategy semantics (sweep/MSS/retest/direction/entry/SL/TP rules) are
unaffected -- only price/quantity normalization inputs changed source.

## Tests

```text
tests/test_binance_usdtm_feed.py                    30 passed, 1 skipped (live smoke, skip-by-default)
tests/test_btc_occurrence_identity.py                9 passed
tests/test_btc_costs.py                              7 passed
tests/test_btc_research_ledger.py                    4 passed
tests/test_btc_proposal_execution_boundary.py       12 passed
tests/test_btc_sweep_research_pipeline.py           10 passed
tests/test_liquidity_sweep_retest_strategy.py       45 passed
tests/test_post_london_newyork_pilot.py              8 passed
tests/test_execution_runtime_readiness.py           13 passed
tests/test_execution_command_safety.py
tests/test_execution_coordinator.py
tests/test_execution_executor.py
tests/test_execution_intent_builder.py
tests/test_execution_lifecycle.py
tests/test_execution_mt5_gateway.py
tests/test_execution_safety_v1.py                  (combined with the above: 155 passed)
```

Full repository suite (after all remediation code changes, `python -m pytest -q`,
2026-09-02/03): **1356 passed, 1 skipped, 0 failed, 10743 warnings in 2389.14s
(0:39:49)**. The 1 skip is the intentional live-network Binance smoke test. All warnings
are pre-existing `datetime.utcfromtimestamp` deprecation notices, unrelated to this work.

`git diff --check`: clean (only pre-existing CRLF line-ending warnings, no conflicts).

**Note on repository state:** this working tree was shared, concurrently, with another
session doing unrelated work on `ST_LARGE_SMC_V1`/`REPLAY_METADATA_DECOUPLING_V1`
(`strategies/ST_LARGE_SMC_V1.yaml`, `docs/specs/LARGE_SMC_V1_SPEC.md`,
`docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`, a new
`docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`, and a
`journal/large_smc_discovery_2025-09_corrected.json` fixture). Something in this
environment (not this session -- no `git commit` was ever run here) committed both
sessions' work together as `d36dea7` and `be5d31a`. Every file this remediation pass
actually changed is listed above and independently verified by the test counts above;
the ST_LARGE_SMC_V1 files were never touched by this session. See the chat transcript
for the full disclosure of this cross-session collision.

## Safety

- `FX_execution_changed = NO` -- no FX execution authority, risk rule, SL/TP rule, or
  confirmation gate changed.
- `BTC_execution_enabled = NO` -- still `PROPOSAL_ONLY`, `execution_authority=DISABLED`;
  now additionally enforced by an explicit executor-side domain gate, not just absence
  of an import.
- `strategy_semantics_changed = NO` -- `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` and
  `strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml` are byte-for-byte unchanged by this
  remediation pass (verified via `git diff --stat strategies/`).

## Final

```text
FX_NEW_YORK                    = READY (unchanged by this remediation pass)
BTC_RUNTIME_WIRING              = VERIFIED
BTC_MULTI_OCCURRENCE_COLLECTION = VERIFIED
BTC_RESEARCH_GUARD_SEPARATION   = VERIFIED
BTC_OCCURRENCE_DEDUP            = VERIFIED
BTC_EXECUTION_DOMAIN_REJECTION  = VERIFIED
BTC_FEED_VALIDATION             = VERIFIED
BTC_DEPENDENCY_DECLARED         = VERIFIED
BTC_EXCHANGE_METADATA           = VERIFIED
BTC_LIVE_CONNECTIVITY           = BLOCKED_GEO_RESTRICTED (this environment) -- NOT VERIFIED

COMPLETE_TRADE_OPPORTUNITY_V1 = IMPLEMENTATION_READY_LIVE_CONNECTIVITY_PENDING
READY_FOR_SHADOW_VALIDATION   = NO (blocked solely on live Binance connectivity
                                     verification from the actual deployment environment)
```
