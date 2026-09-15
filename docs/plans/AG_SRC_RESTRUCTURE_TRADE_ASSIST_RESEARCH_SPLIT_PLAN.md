# Restructure src/ into trade_assist / research / shared

Status: PROPOSED — not yet executed. Written 2026-09-14.

## Context

The repo (`AG Trade Assistant`) has 49 Python packages sitting flat under `src/` with no grouping, mixing live trade-assist code (execution, MT5 broker, API, Telegram) with strategy-validation/research code (backtesting, research factory, governance). A read-only audit found the coupling is real: several core analysis engines (`strategy_engine`, `market_structure`, `liquidity`, `supply_demand`, `entry_confirmation`, etc.) are genuinely imported by both sides and must land in a `shared/` package, not be duplicated. Two areas need surgical (not directory-level) splits — `mt5/` and `execution/adapter.py` — and two backwards dependencies exist (`strategy_contract`→`session_sweep_continuation`, `authorization`→`post_asian_pilot`) that need inverting so the shared/trade_assist layers never depend on research.

A full physical split was chosen over a docs-only or namespace-only reorg, on the explicit condition that it must not put the live V1.0.2 pilot or the running V1.0.3 shadow-validation series at risk. This plan is therefore designed to run entirely in an isolated git worktree/branch, verified phase-by-phase, and handed back as a PR for human merge approval — never merged automatically.

## Target layout

```
src/shared/        entry_confirmation, liquidity, market_intelligence, market_structure,
                    market_swing_structure, mtf_context, proposal_envelope, proposals,
                    runtime_state, smc_map, strategy_contract, strategy_engine, supply_demand,
                    trading_skills, visual_explanation, chart_renderer, alerting,
                    session_clock.py, mt5/ (symbol_resolver.py, broker_symbol_resolver.py,
                    broker_time.py, time_contract.py + config.py/market_data.py per grep),
                    execution_contracts.py (TradeProposal, extracted from execution/adapter.py),
                    post_asian_pilot_governance/ (governor.py, pilot_config.py, preflight.py,
                    tiebreak.py — extracted from post_asian_pilot/)

src/trade_assist/  api, assistant, authorization, daytrading, daytrading_runtime,
                    daytrading_workflow, execution_runtime, notifications, smc_watcher,
                    strategy_manager, ticket_delivery, trade_management,
                    mt5/ (connection.py, account.py, account_guard.py, management_gateway.py,
                    deals.py), execution/ (everything except the extracted TradeProposal)

src/research/       ag_scheduler_v2, btc_sweep_research, canonical_experiments,
                    external_candidate, fx_friction_research, historical_replay,
                    large_smc_research, performance, research, session_sweep_continuation,
                    session_tribranch_research, validation_diagnostics, validation_framework,
                    market_data_readiness, daily_routine, surveillance,
                    post_asian_pilot/ (remainder after the governance extraction)

config/trade_assist/  trading.yaml, trading.demo.yaml, mt5.yaml, assistant_runtime.yaml,
                       ticket_delivery.yaml, releases/
config/research/       governance/, research/btc_experiments.yaml, ag_scheduler_v2.yaml,
                       pilot/, historical_datasets/
config/shared/          liquidity.yaml, market_structure.yaml, canonical_sessions.yaml,
                       ag_order_block_v1.yaml, governance/strategy_lifecycle.yaml (single
                       source, read by both sides)

scripts/trade_assist/  run_api.py, execute_trade.py, manage_positions.py, manage_trade.py,
                       web_execute_trade.py, web_manage_trade.py, web_mt5_positions.py,
                       run_ag_execution_runtime.py, run_daytrading_runtime.py,
                       run_large_smc_live_watch.py, run_strategy.py,
                       run_ticket_delivery_status.py, ticket_delivery_evidence.py,
                       trade_assistant.py, smc_assistant_live_smoke.py, check_mt5.py,
                       analyze_trade.py, dry_run.py
scripts/research/      all run_*research*, run_btc_*, run_large_smc_discovery.py,
                       run_canonical_experiments.py, run_discovery_backtest.py,
                       run_historical_replay.py, run_post_asian_pilot.py,
                       run_fx_daily_report.py, generate_*evidence*.py,
                       generate_readiness_baseline.py,
                       generate_validation_ledger_snapshot.py, replay_*.py,
                       resolve_forward_shadow_outcomes.py,
                       validate_first_canonical_population.py, analyze_structure.py,
                       run_directional_liquidity_reconstruction.py,
                       run_eligibility_reconstruction.py,
                       run_first_canonical_session_sweep_continuation_replay.py,
                       run_large_smc_outcome_lifecycle_check.py,
                       run_session_sweep_continuation_canonical_shadow_parity.py,
                       run_session_sweep_continuation_replay.py,
                       run_true_stage2_equivalence.py, run_true_stage2_from_stage1.py
scripts/dev_ops/       build_native_stage1.py, check_skill_mirror_drift.py, cleanup_mbt.ps1,
                       get_framework_status.py, git-hooks/, install_btc_daily_task.ps1,
                       run_dev.ps1, setup_dev.ps1, setup_mbt.ps1, test_dev_connection.py,
                       test_integration.ps1, validate_readiness.ps1, scheduled/

tests/                 stays FLAT (240 files) — only import statements are rewritten.
                       testpaths=["tests"] doesn't require mirroring src/, and many test
                       files are cross-cutting scenario tests that resist a clean 1:1
                       package split. File moves for tests are deferred to a future,
                       non-urgent pass.
```

Import convention: explicit prefixed imports everywhere (`from shared.market_structure import ...`, `from trade_assist.execution import ...`, `from research.historical_replay import ...`) — not a multi-root pythonpath trick, which would reintroduce the exact bare-name ambiguity this migration exists to remove. `pyproject.toml`'s `[tool.setuptools.packages.find] where=["src"]` needs no change (it auto-discovers the three new top-level packages).

## Execution

1. **Worktree**: `git worktree add ../AG-profit-trading-restructure -b refactor/src-package-split main`. All work happens there; `main` is never touched directly, nothing merges without explicit human sign-off given the live pilot + active shadow-validation series.

2. **Baseline check** (Phase 0): confirm `pytest -q` is green on the fresh worktree before any change.

3. **Phase order** (each phase = its own commit(s), each ends with `pytest -q` green before moving on):
   - Phase 1 — scaffold empty `src/shared/`, `src/trade_assist/`, `src/research/` `__init__.py` files.
   - Phase 2 — analysis only, no edits: grep exact call sites for the four special cases (`TradeProposal`, `post_asian_pilot` governance imports from `authorization`/`ticket_delivery`, `mt5/config.py`+`market_data.py` cross-side usage, the `strategy_contract`→`session_sweep_continuation` import line) to nail the precise file-level cut before touching code.
   - Phase 3 — move `shared/` packages one at a time via `git mv` (preserves history), then a scripted word-boundary-safe import rewrite per package name (`import pkg` / `from pkg...` → `shared.pkg`), diff-reviewed, committed, pytest green, per package.
   - Phase 4 — move `trade_assist/` packages the same way; `mt5/` and `execution/` moved whole into `trade_assist/` first (file-level split deferred to Phase 5).
   - Phase 5 — the four genuine code edits (only ones that aren't pure moves), each its own reviewable commit + pytest run:
     1. Extract `TradeProposal` from `execution/adapter.py` into `shared/execution_contracts.py`; rewrite the research-side call sites found in Phase 2.
     2. Extract `governor.py/pilot_config.py/preflight.py/tiebreak.py` from `post_asian_pilot/` into `shared/post_asian_pilot_governance/`; rewrite `authorization`/`ticket_delivery` imports to point at `shared` — this is what removes the trade_assist→research backwards dependency.
     3. Invert `strategy_contract`→`session_sweep_continuation`: read the actual import line first, then either relocate the specific shared symbol into `shared` or refactor so research calls into `strategy_contract` rather than the reverse — decide from what the code actually does, not by guessing.
     4. Split `mt5/` file-by-file: `connection.py/account.py/account_guard.py/management_gateway.py/deals.py` → `trade_assist/mt5/`; `symbol_resolver.py/broker_symbol_resolver.py/broker_time.py/time_contract.py` (+`config.py`/`market_data.py` per the Phase 2 grep result) → `shared/mt5/`.
   - Phase 6 — move remaining `research/` packages, same pattern.
   - Phase 6b — rewrite imports across all 240 flat `tests/*.py` files (same scripted approach), full `pytest -q` + `pytest -q -m slow`.
   - Phase 7 — `git mv` `config/` files/dirs per the target layout above; grep for hardcoded config paths in `src/`/`scripts/` and update the loader references; `strategy_lifecycle.yaml` → `config/shared/governance/` (single source, no duplication).
   - Phase 8 — `git mv` `scripts/` files per the target layout; update the **one** live reference in `web/server.ts` (~line 1362, `path.join(repoRoot,'scripts','web_mt5_positions.py')` → `...,'scripts','trade_assist','web_mt5_positions.py'`) — confirmed this is the only non-dead script-path reference in server.ts; everything else is a stale comment.
   - Phase 9 — orphan cleanup: move `EXP_EXPOSURE_EFFICIENCY_V1_GEN_001.md` into `artifacts/research/` or `docs/status/` (whichever already holds similar notes), remove the vestigial empty root `package-lock.json`. Do **not** touch `.claude/worktrees/*` or `research_external/` — flag both as separate follow-ups in the PR description, out of scope here.
   - Phase 10 — final verification gate (below), then open PR, no auto-merge.

4. **Import-rewrite mechanics**: a small Python script (not raw `sed`) doing word-boundary-anchored `re.sub` on lines matching `^\s*(import|from)\s+<pkg>(\.|(\s+import)|\s*$)`, run per package name (longest names first, e.g. `strategy_engine` before any shorter overlapping prefix), output diff-reviewed by hand before each commit.

## Verification (must all be green before the PR is opened)

- `pytest -q` (default suite) and `pytest -q -m slow` — 0 failures/errors/collection errors.
- `pytest -q -m live_mt5` — green if an MT5 terminal is connected, or a clean `SKIP` (via `tests/conftest.py`'s guard) if not — never a silent 0-test run.
- Entrypoint import-smoke-test: every `scripts/**/*.py` file byte-compiles and top-level-imports cleanly (`runpy.run_path(..., run_name='__x__')` or `--help` where supported) — run after every phase that moves importable code, not just at the end.
- `web/server.ts`'s `/api/mt5/positions` route manually verified (via the `run` skill or a direct request against the dev server) against the moved `scripts/trade_assist/web_mt5_positions.py`.
- `python -c "from setuptools import find_packages; print(find_packages(where='src'))"` shows exactly `trade_assist`, `research`, `shared` (+ their subpackages) — no orphaned flat leftovers.
- Grep sweep confirms **zero** remaining un-prefixed imports of any migrated package name across `src/` and `tests/`.
- `ls src/` shows only `trade_assist/`, `research/`, `shared/` — no duplicate leftover directories (e.g. no stray `src/mt5/` alongside `src/trade_assist/mt5/` + `src/shared/mt5/`).
- `git diff --stat main...refactor/src-package-split` reviewed end-to-end as a pure refactor: every line outside the four Phase-5 special-case edits should be a mechanical move/import-rewrite, not a behavior change.

## Critical files

- `pyproject.toml` — verify (not modify) `[tool.setuptools.packages.find] where=["src"]` picks up the new layout correctly.
- `src/execution/adapter.py` — `TradeProposal` extraction site (Phase 5.1).
- `src/post_asian_pilot/{governor,pilot_config,preflight,tiebreak}.py` — shared-governance extraction site (Phase 5.2).
- `src/strategy_contract/` (post-move: `src/shared/strategy_contract/`) — backwards-dependency inversion site (Phase 5.3).
- `src/mt5/` — file-level split site (Phase 5.4).
- `web/server.ts` (~line 1362) — the one live script-path reference to update in Phase 8.
- `tests/conftest.py` — governs `live_mt5` skip behavior for correct verification-result interpretation.

## Explicitly out of scope

- `web/server.ts` internal reorganization (it's already confirmed to be a thin BFF that needs no split beyond the one path update).
- `research_external/` reconciliation with `src/research/`/`src/external_candidate/` — separate follow-up.
- Pruning the ~18 stale `.claude/worktrees/*` directories — separate follow-up.
- Any internal split of `strategy_engine/` itself (moved wholesale into `shared/` despite being the heaviest cross-import hub — internal surgery is a later, separate pass).
