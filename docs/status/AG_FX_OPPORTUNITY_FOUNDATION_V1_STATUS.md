# AG FX Opportunity Foundation V1 — Status

**Date:** 2026-09-28
**Classification:** `EURUSD_OPPORTUNITY_REPLAY_VERIFIED / LIVE_MT5_NOT_EVALUATED / PROPOSAL_FAIL_CLOSED`
**Branch:** `restore/fx-opportunity-foundation-v1`
**Publication base:** `origin/main` `4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8` (tree `95b5cb38aebe985b457c3aa8e6acd3b9ae537281`)
**Restoration source:** `2b75bbf0d290cbf3b52684f87770396442790639` (tree `e9448d16dc9e9d2db144dd8e0ea7baabdbe0d926`), the direct parent of deletion commit `3f1f955`

This is a selective restoration, not a rollback. `main` was not reset, reverted, or force-pushed. This change adds no strategy promotion, authorization, execution path, or broker call.

## What now works

```
MT5 M15 candles (mt5.market_data.get_candles, or a hash-pinned MT5 export in REPLAY mode)
  -> post_asian_pilot.snapshot        reference-session completeness / forming-bar guard
  -> strategy_engine.evaluate         ST_ASIAN_SWEEP_5R_V1 v1.1.1, unchanged
  -> post_asian_pilot.decision        canonical PostAsianDecision
  -> opportunity.asian_sweep_adapter  + opportunity.engine funnel -> OpportunityCandidate
  -> opportunity.candidate_store      idempotent persistence (journal/fx_opportunity/)
  -> opportunity.proposal_eligibility existing boundary, unchanged; reported as evidence only
  -> STOP: Proposal = NO_PROPOSAL_AUTHORITY, TradeTicket = NOT_CREATED
```

Cycles: `POST_ASIAN` (the `ASIAN_LONDON` pilot config) and `POST_LONDON` (the `LONDON_NEWYORK` pilot config). Session windows come from `config/canonical_sessions.yaml` through `session_clock` and the existing pilot configs; none are redefined. The only symbol in scope is EURUSD (`fx_opportunity.runner.SLICE_SYMBOLS`).

## Restoration manifest (Phase 1)

### RESTORE_BYTE_EXACT (25 files; every blob verified equal to the `2b75bbf` blob)

| Path | Blob | Verify |
|---|---|---|
| `strategies/registry.yaml` | `38fefa17ff8a` | MATCH |
| `strategies/STRATEGY_LEDGER.md` | `f7f75a0c464a` | MATCH |
| `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` | `36a16ee9d6b9` | MATCH |
| `src/opportunity/asian_sweep_adapter.py` | `18f5289f7b33` | MATCH |
| `src/post_asian_pilot/__init__.py` | `eb14d4a0819d` | MATCH |
| `src/post_asian_pilot/decision.py` | `c9e628e746b1` | MATCH |
| `src/post_asian_pilot/snapshot.py` | `09410ef38a37` | MATCH |
| `src/post_asian_pilot/fingerprint.py` | `eb33b1e37009` | MATCH |
| `src/post_asian_pilot/pilot_config.py` | `d56e5d811f5a` | MATCH |
| `src/mt5/market_data.py` | `c12e4994e3d4` | MATCH |
| `src/mt5/broker_time.py` | `f72079897d6a` | MATCH |
| `src/shared_cache/__init__.py` | `ad89f16a7fbd` | MATCH |
| `src/shared_cache/bounded_cache.py` | `1deb77385568` | MATCH |
| `src/shared_cache/derived_fact_cache.py` | `5980d27da2a0` | MATCH |
| `tests/test_opportunity_asian_sweep_adapter.py` | `04d4ebdd6573` | MATCH |
| `tests/test_opportunity_registry_binding.py` | `410a077ffc5f` | MATCH |
| `tests/test_broker_time.py` | `e111281ee593` | MATCH |
| `tests/test_market_data.py` | `e52f6a78dcd3` | MATCH |
| `tests/test_mt5_market_data_guards.py` | `746808694816` | MATCH |
| `tests/test_mt5_market_data_raw_cache.py` | `c14aed63b11e` | MATCH |
| `tests/test_shared_cache_bounded_cache.py` | `3c10d7682a32` | MATCH |
| `tests/test_shared_cache_no_strategy_import_guard.py` | `a6dc9d17c039` | MATCH |
| `tests/test_session_clock.py` | `32c33f475958` | MATCH |
| `tests/test_session_router.py` | `c2931ce3a78b` | MATCH |
| `tests/test_strategy_engine.py` | `f640b95b3a36` | MATCH |

These were committed in two restoration-only commits, with no modernization mixed in.

### ALREADY_PRESENT_EQUIVALENT

The 33 files in `src/opportunity/*` (except eligibility), `src/proposal_envelope/*`, `src/strategy_engine/**`, `src/mt5/{__init__,symbol_resolver}.py`, `src/session_clock.py`, `src/runtime_state/*`, `config/canonical_sessions.yaml`, `config/mt5.yaml`, `MetaTrader5.py` and `tests/conftest.py` are byte-identical to `2b75bbf`.

`src/opportunity/proposal_eligibility.py` differs from the source. The difference is `main`'s legitimate post-deletion hardening (`0f149c5`), so it is kept unchanged.

### ADAPT_REQUIRED (new code; composition only)

- `src/fx_opportunity/{__init__,runner}.py` replaces the data→decision portion of the historical `post_asian_pilot.pipeline._evaluate_pair` without its execution coupling. It adds three things:
  - an explicit closed-bar filter;
  - a post-session duplicate/order guard;
  - a fail-closed proposal-authority gate.
- `scripts/run_fx_opportunity_once.py` is the live CLI. It attaches to a running terminal with no credentials, and replaces the broker-mutation APIs with blocking counters.
- `scripts/replay_fx_opportunity.py` replays a hash-pinned MT5 export in REPLAY mode.

### SECURITY_SENSITIVE_DEFER (not restored)

- `post_asian_pilot/{pipeline,proposal,store,governor,preflight}.py` all import `execution.*` or `execution_runtime.*`.
- `execution/`, `authorization/`, `ticket_delivery/`, `notifications/`.
- `mt5/{connection,account,account_guard,management_gateway,deals,config}.py`: credential login, account access and position mutation.

### NOT_REQUIRED / DEFERRED

- `market_structure/`, `liquidity/`, `supply_demand/`, `mtf_context/`: the selected strategy does not consume them.
- `ag_scheduler_v2/`: see Phase 8.
- `strategy_manager/`: the `SESSION_TRADE_V1` external-engine adapter.

### CONFLICT

There were no file conflicts. There is one authority conflict, described in the next section.

## Strategy authority (Phase 4; nothing was changed)

| Strategy | Registered | Active | Locally runnable | Economic validation | Binding `proposal_authority` | Demo eligible / authorized | External repo |
|---|---|---|---|---|---|---|---|
| `SESSION_TRADE_V1` | yes | yes | **no**: engine is in `D:\ddev\Session Trade Codex`, and `strategy_manager` adapter was deleted | none recorded | True (describes the deleted dispatch path) | — / **true** | **yes** |
| `ST_SESSION_SWEEP_CONTINUATION_V1` | yes | no | no: `src/session_sweep_continuation/` not restored | research only | False | false / false | no |
| `ST_ASIAN_SWEEP_5R_V1` | yes | yes (research) | **yes**: `strategy_engine` is present | none (`economic_edge_established` has no authority anywhere; ledger lists an open causal-backtest contract gap) | **False** | false / false | no |

The conflicting evidence for `ST_ASIAN_SWEEP_5R_V1`:
- **Against proposal authority:** `StrategyBinding.proposal_authority=False`.
- **For proposal authority:**
  - `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml` sets `FX_PROPOSALS: PROPOSAL_ONLY` and names this strategy as the pilot-scoped `SOLE_DAY_TRADING_STRATEGY`;
  - the lifecycle stage is `OPERATIONAL_SHADOW`;
  - `opportunity.proposal_eligibility` deliberately ignores `proposal_authority`.

There is no explicit `proposal_generation_authorized` flag for this strategy, and the pilot runtime that carried the release designation is not restored. The resolution is therefore fail-closed: **`PROPOSAL_AUTHORITY = NONE`** for this slice, pending an explicit owner decision. The existing eligibility boundary still runs and its result is reported, but the runner never constructs a `CanonicalProposal`.

## Evidence

### Real MT5 EURUSD data: replay (REPLAY mode)

- **Dataset:** `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_001/raw/EURUSD_M15.csv`, sha256 `cefed970…c063`, which matches the manifest's M15 fingerprint component.
  - Source: Vantage Demo, MT5 5.0.5735.
  - Role: DEVELOPMENT; not a holdout; admitted by the SSC data-coverage audit.
  - Timestamps are true UTC: the first bar is Sunday 21:00 UTC, the FX weekly open.
- **Rejected dataset:** `SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914` has a quarantine record (`GEN_002_QUARANTINE_V1`): its timestamps are broker time mislabelled as UTC (+3h). It was not used.
- **Evidence file:** `artifacts/validation/AG_FX_OPPORTUNITY_FOUNDATION_V1/EURUSD_REPLAY_SSC_V1_0_1_G2_DEV_001.json`.

Results:
- 30 trading days (2026-06-22 → 2026-07-31) × 2 cycles × {mid-window, window-end} = 120 evaluations, each run twice. **Determinism mismatches: 0.**
- At window end:
  - `POST_ASIAN`: READY 21, EXPIRED 6, NO_TRADE 3, so 21 opportunities and 9 no-opportunity.
  - `POST_LONDON`: READY 17, EXPIRED 8, NO_TRADE 5, so 17 opportunities and 13 no-opportunity.
- All 26 mid-window opportunities reappear at window end with the same candidate id, direction, entry and invalidation. This is a look-ahead consistency check on real data.
- All 120 evaluations ended with eligibility `BLOCKED` (`REPLAY_DATA_NOT_BROKER_EXECUTABLE`), proposal `NO_PROPOSAL_AUTHORITY`, and ticket `NOT_CREATED`.

The opportunity count reflects this research-stage strategy's own rules and is not an economic result. It authorizes nothing.

### Live MT5: NOT_EVALUATED (environment blocker)

`python scripts/run_fx_opportunity_once.py --cycle POST_LONDON` was run at about 14:55 UTC. It returned `MT5_INITIALIZE_FAILED (-6) "Terminal: Authorization failed"`, both with auto-discovery and with the explicit path of the running terminal, `C:\Users\aungp\AppData\Roaming\MetaTrader 5\terminal64.exe`, which was started at 13:27 UTC.

The same terminal served the WP3A.1 friction campaign successfully at 09:14 UTC. No credentials were read or passed. The fix is to re-log the terminal in, then rerun the command above.

### Tests (Windows, Python 3.14.0, owner `.venv`, MetaTrader5 5.0.5735)

- Restored focused tests, 11 files: **128 passed, 4 skipped**. The skips are the `test_market_data.py` live tests that require a running MT5 terminal.
- `tests/test_fx_opportunity_runner.py`: **21 passed**. It covers:
  - authority, and READY → blocked;
  - the gate still blocking when eligibility is ELIGIBLE;
  - WATCH/EXPIRED, the pre-reference and pre-window waits, and the post-London windows;
  - missing, duplicated and post-session-duplicated bars, and MarketDataError;
  - the forming-candle guard and future-candle mutation;
  - deterministic replay, and identity/idempotent persistence across restart;
  - scope guards;
  - the zero-broker-call sentinel, the fresh-interpreter import-isolation check, and a static capability scan.
- Branch suite `pytest -q tests`: **501 passed, 4 skipped, 1 failed**. The failure is `test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection`. It is **pre-existing**: it fails identically on untouched `origin/main` because `src/api/app.py` was deleted in `3f1f955`.

### Zero execution

- **Measured at runtime:** broker `order_send`, `order_check`, `positions_*`, `orders_*` and `trade_*` calls are **0**. This is enforced by the sentinel test and by the CLI's blocking counters.
- **Import isolation:** in a fresh interpreter, `fx_opportunity.runner` imports no module from `execution*`, `authorization`, `ticket_delivery`, `notifications` or `proposal_envelope`, and none of the credential or mutation MT5 modules.

## Phase 8: scheduler, DEFERRED

`ag_scheduler_v2/pipeline.py` (17 files) is hard-wired to `strategy_manager.manager.evaluate` (the `SESSION_TRADE_V1` external adapter) and to `assistant.models`. Wiring EURUSD Opportunity into it would mean restoring about 20 files and changing scheduler dispatch, which is outside this mission's scope.

The existing Windows tasks `AG_FX_ASIAN_LONDON_SHADOW` and `AG_FX_LONDON_NEWYORK_SHADOW` belong to the owner's other worktree and were not touched. Post-Asian and post-London evaluation is invocable manually, per cycle, with `scripts/run_fx_opportunity_once.py --cycle POST_ASIAN|POST_LONDON`.

## Known limitations

- The repository-root `MetaTrader5.py` stub (from `6365a53`) shadows the real package whenever the repo root is on `sys.path`. The live CLI refuses to run in that situation (`MT5_REAL_PACKAGE_UNAVAILABLE`) rather than continuing without the real package.
- `mt5.market_data` uses the deprecated `datetime.utcfromtimestamp`. It was restored byte-exact, and fixing it is out of scope.
