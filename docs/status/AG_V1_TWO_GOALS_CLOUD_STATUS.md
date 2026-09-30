# AG V1 — Two Goals: Cloud (code-only) Status

- Date: 2026-09-29, Linux cloud container, Python 3.11.15
- Branch: `v1/two-goals-cloud`, cut from `origin/main`
- BASELINE_SHA: `ce09e8d8a1606e1c90cd0fbc23e49796902bfcc2`
- Result: **BLOCKED_AT_T1**. The mission assumes code that is not on main. Everything after
  the T1 gate is `NOT_EVALUATED` or `CUT` on this branch. The only commits are docs:
  governance (T2) and this status record (T9).
- Broker / exchange calls: 0. `order_send` = 0, `order_check` = 0, position mutations = 0.
  No network market-data calls were made.

## T1 — Baseline (FAILED gate)

| Required on main | Found on `ce09e8d` |
|------------------|--------------------|
| `src/ticket_delivery` | **ABSENT**. Also **forbidden**: `tests/test_proposal_eligibility_hardening_v1.py::test_proposal_stage_modules_are_not_importable_execution_surfaces` asserts that `src/{execution,authorization,owner_decision,ticket_delivery,trade_management,svos}` do not exist. |
| Asian Sweep engine | **PRESENT**. `src/strategy_engine/{engine,loader,models}.py` and `session/*` are byte-identical to `2b75bbf`, except that `session/candidate_stop_models.py` was removed. `strategies/` (registry + `ST_ASIAN_SWEEP_5R_V1.yaml`) is **ABSENT**, so the loader has no contract to read. |
| BTC daily CLI | **ABSENT**. `scripts/run_btc_daily_report.py`, `src/btc_sweep_research/` and `src/strategy_engine/sweep_retest/` are not on main. |
| `fx_discovery/features.py` | **ABSENT from main**. It is on unmerged branches only: `audit/tradeticket-vertical-slice-v1(-r1)`, `audit/wp7a…`, `audit/wp7b…`, `audit/vt-*`, `audit/unit-f…`. It is byte-identical on all of them (blob `f16baab`, introduced in `c38f53b`, 2026-09-28). |

**Why the code is missing.** Commit `3f1f955` ("feat: initialize project structure",
author `ifashion101gm`, 2026-09-27) is the direct child of `2b75bbf` (PR #8). It deleted
1,047 files (+2,767 / −931,870 lines), including `strategies/`, `src/ticket_delivery`,
`src/large_smc_research`, `src/strategy_engine/sweep_retest`, `src/execution` and
`src/trade_management`. Since then main has been rebuilt in audited
"capability-zero restoration" slices (`92b4fd1`, `0f149c5`), under the no-execution-surface
invariant above.

**The two PRs behind `ce09e8d`.**

| PR | Opened by | Commit author | Merged by | Scope |
|----|-----------|---------------|-----------|-------|
| [aungmyat1/AG-profit-trading-assit#14](https://github.com/aungmyat1/AG-profit-trading-assit/pull/14) | aungmyat1 | Claude Code | ifashion101gm | MT5 MCP startup timeout |
| [aungmyat1/AG-profit-trading-assit#13](https://github.com/aungmyat1/AG-profit-trading-assit/pull/13) | aungmyat1 | Claude Code | ifashion101gm | Claude Desktop MCP installer |

Neither PR touches strategy or runtime code.

**Current-main regression baseline.** `python -m pytest -q tests`: 350 passed, 1 failed.
The failure (`test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection`)
is pre-existing and not related to this mission.

## T3 — Logical status (pre-wipe evidence only)

The engines cannot be reached on main, so the existing focused tests were run in a
scratch worktree of `2b75bbf`, the last main commit before the wipe. This is historical
evidence about the frozen code; it does not show that main can run it.

Command (at `2b75bbf`): `python -m pytest -q` on `test_strategy_engine`,
`test_strategy_decision_no_lookahead`, `test_historical_replay_no_lookahead`,
`test_fx_session_daytrade_eurusd`, `test_post_asian_pilot`, `test_post_london_newyork_pilot`,
`test_session_tribranch_replay`, `test_td8c_session_replay_parity`,
`test_liquidity_sweep_retest_strategy`, `test_btc_{daily_report,daily_cli,occurrence_identity,strategy_registration,sweep_research_pipeline}`,
`test_binance_usdtm_feed`, `test_ticket_delivery_{fx_cycle_integration,identity_and_archive,concurrency_and_restart}`,
`test_large_smc_{research_engine,watch_lifecycle,live_watch_hardening,registration}`.

Result: **403 passed, 4 skipped, 2 failed**. Both failures are environmental: the tests
reach `MetaTrader5.initialize()` and the conftest MT5 stub refuses it on Linux.

| Strategy | LOGICAL_STATUS |
|----------|----------------|
| ST_ASIAN_SWEEP_5R_V1@1.1.1 | `PASS_AT_2B75BBF` / `NOT_EVALUATED_ON_MAIN`. The engine is on main but its contract YAML is not. |
| ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0 | `PASS_AT_2B75BBF` / `NOT_REACHABLE_ON_MAIN`. The engine is absent and imports `execution.risk`, `execution.daily_loss_guard` and `execution.position_guard`, which main forbids. |
| ST_LARGE_SMC_V1@1.0.7 | `PASS_AT_2B75BBF` / `NOT_REACHABLE_ON_MAIN`. `src/large_smc_research` reaches `trade_management` through `historical_replay`→`daytrading`, which main forbids. |
| ST_LARGE_SMC_V1@1.1.0 | `NOT_IMPLEMENTED`. See T5. |

## T4–T8 — Outcome

| Task | Status | Reason |
|------|--------|--------|
| T2 governance | DONE | `docs/governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md` |
| T3 | PARTIAL | Evidence recorded only at `2b75bbf`; see above. |
| T4 restore Large-SMC research modules | CUT | Restoring from `2b75bbf` pulls in `trade_management` (and via its package `__init__`s, `assistant`/`daytrading`). That breaks T4's own "no execution/mt5 management imports" boundary and main's forbidden-package test. Weakening that test is not a conservative choice. |
| T5 Large-SMC 1.1.0 | NOT_STARTED | Missing inputs: (a) the rule-option catalogue (`9ed8135`) is unreachable; (b) `features.py` is only on unmerged `audit/*` branches (D8); (c) the "existing delivery journal" (`src/ticket_delivery`) is forbidden on main; (d) `AG_ORDER_BLOCK_V1` and `AG_ENTRY_DISPLACEMENT_V1` implementations sit in packages whose `__init__` pulls in the assistant/daytrading stack. |
| T6 crypto fallback + ETHUSDT | NOT_STARTED | The crypto engine is not reachable on main (see T3). `src/execution_runtime/binance_usdtm_feed.py` at `2b75bbf` imports only modules already on main, so it is a candidate for a byte-exact single-file restore once the owner approves. |
| T7 USDJPY / XAUUSD | NOT_STARTED | The frozen `ST_ASIAN_SWEEP_5R_V1@1.1.1` contract (at `2b75bbf`) already lists `instruments: [EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD]` and a frozen `LONDON_NEWYORK` pair (06:00–11:00 → 12:00–15:00 GMT), so no window needs inventing. The ticket-cycle runner (`scripts/run_post_asian_pilot.py`) imports `execution.mt5_gateway`/`executor`, which main forbids. |
| T8 hardening + full regression | NOT_EVALUATED | Nothing new to harden. The current-main baseline is recorded above. |

Also not done: the D3 test update (`SESSION_TRADE_V1` `demo_authorized=false`). The registry
and its tests are not on main, and the attempt to restore `strategies/` from `2b75bbf` was
refused by the session's permission layer, so D3 has nothing to act on yet.

## Per-instrument paths

| Instrument | TICKET_PATH | WATCH_PATH |
|------------|-------------|------------|
| EURUSD | CUT (no contract/cycle runner on main) | CUT (no 1.1.0 implementation) |
| GBPUSD | CUT (same) | CUT (same) |
| USDJPY | CUT (same) | CUT (same) |
| XAUUSD | CUT (same) | CUT (same) |
| BTCUSDT | CUT (crypto engine forbidden-dependency) | CUT (same) |
| ETHUSDT | CUT (same) | CUT (same) |

## Owner decisions needed to unblock

1. **Baseline.** Choose one:
   - (a) Restore the pre-wipe stack onto a branch and change the capability-zero forbidden-package invariant.
   - (b) Keep the invariant and have V1 re-host the frozen engines behind a boundary that does not import `execution`/`trade_management`. This means relocating `size_position` and the guards, which touches a frozen file's imports; the rules are unchanged.
   - (c) Build V1 on the in-flight `audit/*` stack once it is audited and merged.
2. **Audit branches.** Allow a byte-exact copy of `src/fx_discovery/features.py` (blob `f16baab`) from an `audit/*` branch, or wait for that branch to merge.
3. **Rule catalogue.** Publish `spec/large-smc-rule-options-v1` (`9ed8135`) so that every D00–D34 `(rec)` option can be applied.
4. **Session permissions.** Allow restoring files from `2b75bbf` (`git checkout 2b75bbf -- strategies`) in this environment.

## Host-only remaining (unchanged by this mission)

- Real MT5 symbol metadata for USDJPY / XAUUSD, if no repository evidence exists once the
  baseline is resolved: `digits`, `point`, `trade_tick_size`, `trade_tick_value`,
  `trade_contract_size`, `volume_min`, `volume_step`, `volume_max`, `spread`,
  `trade_stops_level`, `currency_profit`, and the server-time offset.
- Any live or demo run, Telegram activation, and scheduler installation. All are out of scope.
