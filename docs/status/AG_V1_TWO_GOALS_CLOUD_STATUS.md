---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# AG V1 — Two Goals: Cloud (code-only) Status

- Date: 2026-09-30, Linux cloud container, Python 3.11.15
- Branch: `v1/two-goals-cloud` (draft PR aungmyat1/AG-profit-trading-assit#15). Not merged into main.
- BASELINE_SHA: `ce09e8d8a1606e1c90cd0fbc23e49796902bfcc2`
- Result: **CODE_COMPLETE_FOR_CLOUD_SCOPE**, with T4 partial and USDJPY/XAUUSD at FIXTURE_ONLY
  (details below).
- Broker/exchange calls: 0. `order_send` = 0, `order_check` = 0, position mutations = 0. No private
  exchange APIs. No network market-data calls; every feed test mocks HTTP. No Telegram,
  scheduler, sealed, OOS or holdout change.

## Round 1 (2026-09-29): blocked at T1. Superseded by round 2.

Main at `ce09e8d` lacked `strategies/`, `src/ticket_delivery`, the crypto engine,
`large_smc_research` and `fx_discovery`. Commit `3f1f955` (ifashion101gm, 2026-09-27) had deleted
1,047 files, and main's capability-zero test forbids execution-surface packages.

Correction to round 1: `scripts/run_btc_daily_report.py` **was** on main. It could not run,
because the modules it imports were absent.

PRs #13 and #14 were opened by aungmyat1 (commits by Claude Code) and merged by ifashion101gm.

## Round 2 owner decisions (2026-09-30)

These are recorded in `docs/governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md`.

1. **Narrow exception.** `src/ticket_delivery` may exist in ARCHIVE_ONLY form. `execution`,
   `trade_management`, `authorization`, `owner_decision` and `svos` stay forbidden.
2. **Sizing/guard imports.** The frozen engines' sizing and guard imports move behind a pure
   boundary, `src/sizing_math`.
3. **`features.py`.** A byte-exact copy of blob `f16baab` is approved.
4. **Rule authority.** The mission's written 1.1.0 rules are authoritative. The RMR-A branch was
   never pushed.
5. **Restores.** Restoring files from `2b75bbf` is approved.

## Task outcomes

| Task | Status | Evidence |
|------|--------|----------|
| T1 | DONE | Baseline `ce09e8d`. On main: Asian Sweep engine present; BTC CLI present but not runnable. Missing: `ticket_delivery`, `fx_discovery`. PR authors as listed above. |
| T2 | DONE | Governance record (round 1 plus the round 2 decisions). |
| T3 | DONE | Restored `strategies/` byte-exact. New `tests/test_v1_asian_sweep_logical.py` covers determinism, truncation invariance and no look-ahead, for 4 instruments × 2 pairs. Crypto engine restored byte-exact; only its 3 import lines moved to `sizing_math`. |
| T4 | PARTIAL | Byte-exact C10 (`c10_stop_policy`), C11 (`target_model`) and `decision` are in `src/large_smc_core`. `entry_confirmation`, `supply_demand` and `liquidity` are restored byte-exact. Import-boundary test added. **Not restorable:** the v1.0.7 `engine`, `live_watch`, `watch_lifecycle`, `live_ledger` and `pending_entry`. They reach `trade_management` via `historical_replay.stage2` → `daytrading_runtime` → `daytrading.risk_management`, which is forbidden. |
| T5 | DONE | `src/large_smc_watch` plus `strategies/ST_LARGE_SMC_V1_1_1_0.yaml`. 29 tests cover positive/negative fixtures, truncation invariance, no look-ahead, session-end expiry, invalidation, the NY 17:00 DST boundary, stale → suspend → expire, restart, duplicate poll, crash replay and market closed. Alerts are archived to the ticket_delivery journal (ARCHIVE_ONLY), one file per transition, exactly once. |
| T6 | DONE | `execution_runtime/public_crypto_feed.py`: Bybit primary, Binance fallback, one venue per ticket, fail-closed with both reasons. ETHUSDT profile: an additive `symbol` keyword on the BTC pipeline; ETHUSDT was already a frozen CRYPTO_PERP instrument. |
| T7 | DONE (FIXTURE_ONLY) | USDJPY and XAUUSD are covered by the Asian Sweep tickets (both pairs) and the Large-SMC watch. The repo has no symbol metadata for them, so they are stamped FIXTURE_ONLY. |
| T8 | DONE | Hardening: restart, duplicate poll, stale, market closed and 403 fallback, plus a full regression run. |
| T9 | DONE | This document, the `PROJECT_STATUS.md` snapshot, registry and ledger, and `docs/README.md`. |

**D3.** `SESSION_TRADE_V1` now has `demo_authorized: false`, and its contract has
`execution.demo: false` and `status: DEMO_WITHDRAWN`. The tests that asserted the old value
(`test_opportunity_registry_binding`, `test_validation_orchestrator_status`) are not present on
current main, so no test needed changing.

## LOGICAL_STATUS

| Strategy | Status |
|----------|--------|
| ST_ASIAN_SWEEP_5R_V1@1.1.1 | **PASS**. 5 restored tests plus 17 new V1 logical tests, run on main's engine (byte-identical to `2b75bbf`). |
| ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 (CRYPTO_PERP) | **PASS**. 151 restored engine, BTC and feed tests; they include deterministic replay, duplicate-replay idempotence and restart. Two execution-adapter tests are omitted because `src/execution` is forbidden. |
| ST_LARGE_SMC_V1@1.1.0 | **PASS (logical, fixtures only)**. Economics NOT_EVALUATED (D30). |
| ST_LARGE_SMC_V1@1.0.7 | **NOT_REACHABLE_ON_MAIN**. The engine needs `trade_management`. Evidence at `2b75bbf` is unchanged. |

## Per-instrument paths

| Instrument | TICKET_PATH | WATCH_PATH |
|------------|-------------|------------|
| EURUSD | CODE_READY | CODE_READY |
| GBPUSD | CODE_READY | CODE_READY |
| USDJPY | FIXTURE_ONLY (no repo symbol metadata) | FIXTURE_ONLY (point must be caller-supplied) |
| XAUUSD | FIXTURE_ONLY (no repo symbol metadata) | FIXTURE_ONLY (point must be caller-supplied) |
| BTCUSDT | CODE_READY | CODE_READY |
| ETHUSDT | CODE_READY (SHADOW) | CODE_READY |

CODE_READY means the code path is complete and fixture-verified. Live data is supplied by the
host: MT5 candles for FX, public exchange klines for crypto.

## Implementation choices (conservative, documented)

- **Swing width.** Fractal width k = 2, the fx_discovery canonical value.
- **Bias and context.** H1 bias is the latest close-confirmed H1 break. D1 is context only.
- **Order blocks.** The `AG_ORDER_BLOCK_V1` rules are applied to the causal primitives. The
  zone uses the frozen `_classify_family_and_zone`. The `smartmoneyconcepts` `ob()` detector is
  not used. FLIP_OB is not identified, as in the frozen contract.
- **C10 stop.** C10 runs only where a pip size is repo-evidenced (EURUSD, GBPUSD); elsewhere
  `stop_reason = C10_PIP_SIZE_NOT_EVIDENCED`. SHORT needs a live bid/ask.
- **C11 target.** The fallback tier runs on causal M5 swings. The primary tier (it needs
  `smartmoneyconcepts` structure tiers) is NOT_EVALUATED.
- **Expiry and staleness.** Opportunity expiry is the end of the canonical UTC session;
  outside a session it is the next NY 17:00 boundary. Data counts as stale after 15 minutes
  without a closed M5 bar. The FX market is closed from Friday 17:00 to Sunday 17:00 New York
  time.
- **V1 FX tickets.** Tickets are decision records in the existing journal, not the pilot
  renderer, which needs sizing fields the frozen contract leaves unspecified. Position size is
  `NOT_SPECIFIED`, and the spread check is `NOT_EVALUATED`.
- **Registry.** The registry schema is pinned by a test, so ETHUSDT SHADOW and 1.1.0 are
  recorded in the existing `note` fields.
- **Journal paths.** The ticket_delivery journal identity rejects `/`, so the alert cycle id is
  `LSMC_WATCH-<transition id>`.

## Test commands and results (Linux, 2026-09-30)

- `python -m pytest -q tests/test_v1_*.py`: **86 passed**.
- Restored suites (`test_strategy_engine`, `test_liquidity_sweep_retest_strategy`, `test_btc_*`,
  `test_binance_usdtm_feed`, `test_ticket_delivery_*`): **233 passed, 1 skipped**.
- `python -m pytest -q tests` (full): **670 passed, 1 skipped, 1 failed**. The failure,
  `test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection`,
  also fails on the unchanged baseline `ce09e8d` and is not caused by this branch.
- Live checks (MT5, exchange, Telegram): **NOT_EVALUATED** by design. Nothing here is
  live-verified.

## HOST_ONLY_REMAINING

- **USDJPY and XAUUSD metadata.** Capture the MT5 `symbol_info()` fields `digits`, `point`,
  `trade_tick_size`, `trade_tick_value`, `trade_contract_size`, `volume_min`, `volume_step`,
  `volume_max`, `trade_stops_level`, `trade_freeze_level`, `spread` and `currency_profit`, plus
  the server UTC offset. Record them as owner-approved manifests; the paths then flip from
  FIXTURE_ONLY to CODE_READY.
- **Scheduling.** Live candle sourcing and scheduling for the FX ticket cycles and the
  Large-SMC watch poll. No scheduler was installed here.
- **Live crypto fetches.** First live public fetches (Bybit, then Binance) from the host. This
  container's Binance access was previously recorded as HTTP 451.
- **Deferred.** Telegram transport (D2). Demo and live remain out of scope.
