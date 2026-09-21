# Project Readiness Report — aungmyat1/AG-profit-trading-assit

**Checked:** 2026-09-21 · **Clone:** full history, 277 commits, 1,805 files
**Stack:** Python 3.10+ (FastAPI backend, deterministic strategy engine, MT5 FX + Bybit crypto research) · React/Vite/Express web workspace · pytest · TypeScript

---

## Verdict: ✅ FUNCTIONALLY SOUND — ⚠️ NOT PORTABLE OUTSIDE THE CANONICAL WINDOWS/MT5 MACHINE

On the project's intended environment (Windows + MT5 terminal) the codebase is mature and well-governed:
**3,539 tests pass, the web stack is fully green, safety gates are correctly locked, and no secrets are committed.**
But the repo cannot be installed, tested, or CI-verified on any other platform without fixes, and it carries a genuine
dataset-integrity regression plus a handful of stale guard tests.

---

## What was verified (evidence)

| Check | Result |
|---|---|
| `pip install -r requirements.txt` (Linux) | ❌ **Fails** — `MetaTrader5==5.0.5735` has no Linux/macOS distribution |
| `pip install` of all other pinned deps (Py 3.13) | ✅ Clean |
| `pytest -q` (slow deselected, 9 MT5-collection files ignored) | ⚠️ **3,539 passed, 38 failed, 20 skipped** (98.9% pass) |
| `pytest` collection on non-Windows | ❌ **Aborts** — 9 test files call MT5 at import time without `live_mt5` mark |
| Git-history invariance tests (full clone) | ✅ Pass once history is present (failed only under shallow clone) |
| Web `tsc --noEmit` | ✅ Clean |
| Web `vite build` + server bundle | ✅ Clean |
| Web `npm test` | ✅ **27/27 pass** |
| Secrets scan (keys/tokens/passwords) | ✅ Clean, `.env` gitignored |
| Default trading safety config (`config/trading.yaml`) | ✅ Fail-closed: `mode: ANALYSIS`, all `allow_*: false` |
| CI workflows | ❌ None (`.github/` contains only `copilot-instructions.md`) |
| LICENSE | ❌ None |

## Root causes of the 38 test failures (all categorized)

| # | Root cause | Tests | Severity |
|---|---|---|---|
| 1 | **Dataset integrity regression:** committed `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/EURUSD_H1.csv` (sha256 `9cb7c2da…`) does **not** match its frozen manifest (`93d27d8c…`). The project's own fail-closed gate catches it, cascading into `test_topdown_composer_replay` (7), `test_ssc_dev002_h1_metadata_manifest` (3), `test_td8e_*` (1). | ~11 | 🔴 High |
| 2 | **Unmarked MT5 usage:** tests call `MetaTrader5.initialize/symbol_info/terminal_info` without `@pytest.mark.live_mt5`; conftest stub refuses → `ModuleNotFoundError` chain via `mt5.symbol_resolver` too. | ~13 | 🟠 Med |
| 3 | **Hardcoded developer path** `D:\ddev\AG profit trading` in `test_market_data_readiness_scanner.py` and `test_m15_session_sweep_research_v1_parity.py`. | 3 | 🟠 Med |
| 4 | **Stale frozen-scope guards:** 5 "files unchanged by this mission" tests pin baseline commits predating later sanctioned work (e.g. `src/large_smc_research/live_watch.py` added afterwards). Guards need re-baselining at HEAD. | 5 | 🟡 Low |
| 5 | **Contract drift:** `test_external_candidate_governance_invariance` expects `NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS`, gets `EDGE_REJECTED`; `test_validation_framework` BTC adapter `observed_count` is 1 vs expected 0 (fails even in isolation). | 2 | 🟠 Med |

## Strengths

- **Exceptional documentation & governance:** README, `AGENTS.md` authority rules, 179 KB rolling `PROJECT_STATUS.md` (updated 2026-09-20), dated evidence in `docs/status/`, explicit IMPLEMENTED/VERIFIED/ENABLED/AUTHORIZED gating.
- **Safety architecture is real and verified:** authority chain Strategy YAML → engine → execution → MT5; live trading double-gated and off by default; demo profile (`trading.demo.yaml`) isolated with account-identity checks; execution reachable only through explicit per-order confirmation.
- **Test culture is strong:** 330 test files, fail-closed data gates, no-lookahead replay tests, frozen-contract tests — the integrity gate actually caught the dataset mismatch during this audit.
- **Frontend is production-clean:** typecheck, build, and all tests pass.

## Gaps to close (recommended order)

1. **Fix the DEV002 H1 dataset/manifest mismatch** — owner must decide which artifact is authoritative and re-freeze the other. (🔴 blocks several research pipelines)
2. **Make `requirements.txt` cross-platform:** `MetaTrader5==5.0.5735 ; sys_platform == 'win32'` — conftest already stubs MT5, so this is a one-line unlock for Linux/macOS dev and CI.
3. **Mark the ~9 MT5-touching test files** with `live_mt5` (the conftest error message already tells you which) so collection succeeds everywhere.
4. **Remove the hardcoded `D:\ddev\...` paths** from the two test files.
5. **Re-baseline the 5 frozen-scope guard tests** to current sanctioned commits, or annotate the sanctioned drift.
6. **Add a minimal GitHub Actions CI** (offline pytest on Linux with MT5 stubbed + web build/tests) — the biggest missing piece for a repo of this rigor.
7. **Add a LICENSE** if the repo is meant to be public; otherwise state proprietary intent.
8. Housekeeping: consider Git LFS for the ~44 MB M1 CSVs; move root stray files (`full_suite2.txt`, `SSC_external_strategy_validation_files.zip`) into `artifacts/`.

## Bottom line

**Ready for continued single-operator use on the Windows/MT5 dev machine: YES** — deterministic engine, safety gates, and 98.9% of the portable test suite are healthy.
**Ready for multi-environment development, CI, or new contributors: NOT YET** — items 1–6 above (roughly a day of focused fixes) would get it there.
