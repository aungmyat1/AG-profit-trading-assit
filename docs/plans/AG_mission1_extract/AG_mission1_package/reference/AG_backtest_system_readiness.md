# Backtest System Readiness Analysis — AG Profit Trading

**Repo:** aungmyat1/AG-profit-trading-assit @ c995f08 (+ portability patch) · **Date:** 2026-09-21
**Scope:** only the historical-replay / backtest subsystem (`historical_replay/`, `svos/`,
`replay_evaluation/`, `canonical_experiments/`, their tests, data estate, and validation missions)

---

## One-line verdict

> **Architecture and engineering discipline: READY. Evidence production: NOT READY.**
> The backtest system is an unusually rigorous, fail-closed simulation framework — and it has
> **never yet completed an economic replay**. Every attempt so far has been stopped, correctly,
> by its own data and assurance gates.

---

## 1. What the system consists of

| Layer | Module(s) | Size | Role |
|---|---|---|---|
| Point-in-time data | `src/historical_replay/` | ~2,100 LOC | candle store, MT5-export loader w/ gap reports, broker-aligned resampler, dataset identity & fingerprints, symbol-metadata manifests, warmup readiness, M1 derivation |
| Replay isolation | `historical_replay.data_source_patch` | — | hard block of live MT5 candle/tick access during replay |
| Shared eval context | `historical_replay.evaluation_context` (TD-8E) | — | one caller-controlled historical clock consumed by both Asian engine and SSC canonical shadow consumer |
| Virtual simulation (SVOS) | `src/svos/` | ~4,300 LOC | virtual time/exchange/broker/account/ledger, historical runner with fingerprinted evidence, friction contracts, capacity-risk contract, lookahead contract, optimization admission w/ protected-data firewall |
| Strategy adapters | `src/replay_evaluation/{asian,ssc}.py`, `svos/adapters/`, `svos/ssc_bridge.py` | — | replay calls the **same entrypoints as live** — no re-detection, no parallel semantics |
| Experiments | `src/canonical_experiments/` | ~350 LOC | population/splits/policies for controlled experiments |
| Governance | `validation_framework/`, `config/governance/`, preregistration + dataset-role manifests | — | gate ordering, admission, holdout firewall |

Design principles match best-practice backtesting (Freqtrade/LEAN-class concerns): explicit
signal lag, fail-closed costs (`UNAVAILABLE` never becomes zero), dataset fingerprinting,
no-lookahead perturbation tests, live/replay code-path identity, protected-data isolation.

## 2. Test health of the subsystem (run on Linux, 2026-09-21)

**46 backtest-related test files → 396 passed, 6 skipped, 9 failed.**

| Failure cluster | Count | Root cause |
|---|---|---|
| `test_topdown_composer_replay` (7) + `test_ssc_dev002_h1_metadata_manifest` (3) + `test_td8e_*` (1) | 8* | **DEV002 H1 dataset fingerprint mismatch**: committed `EURUSD_H1.csv` (`sha256:9cb7c2da…`) ≠ frozen manifest (`sha256:93d27d8c…`). The project's own integrity gate catching a real data regression |
| `test_historical_replay_no_lookahead::test_stage2_entry_only_reuses_historical_data_not_live_mt5` | 1 | test reaches an unmarked live-MT5 fallback; needs `live_mt5` mark or monkeypatch (portability follow-up) |

\* counted within the 9 subsystem failures; manifest tests overlap the composer chain.
Notable green areas: fill simulator, resampler (incl. broker-aligned), warmup readiness,
dataset identity, no-lookahead contract tests, all 20+ SVOS cycle tests (virtual time/
exchange/broker/account/ledger, friction, capacity contract, optimization admission,
MT5 isolation), golden two-stage vertical slice, SSC replay determinism.

## 3. Has an economic backtest actually been produced? **No.**

Evidence from the repo's own mission records:

| Mission (date) | Final status | Why |
|---|---|---|
| SSC v1.0.1 one-year replay, R0–R17 (2026-09-19) | `BLOCKED_CROSS_LEG_TIMEZONE_INCONSISTENT` | H1/M15 legs not in the same time base as the M1 leg; gate fired before any replay. *"No replay was executed, no population was created, and no economic metric exists."* |
| SSC v1.0.1 one-year backtest preflight (2026-09-19) | `BLOCKED_INCOMPLETE_ONE_YEAR_DATA` | canonical M1 `FILL_RESOLUTION_INPUT` missing for ~first 8 months of any one-year EURUSD window |
| HYP_002 setup-selectivity, Stage-2 | `TERMINAL_FAIL` gate in `CURRENT_VALIDATION_STATE.json`; Attempt 1 = `INCONCLUSIVE_DATA_CONTEXT_INADEQUATE` (insufficient H1 warmup); `economic_evaluation.json` shows `sample_size: 0`, every metric `NOT_EVALUATED` | warmup-context defect, not a market finding — correctly refused interpretation |
| SVOS capacity cycles 1–2 (2026-09-20) | `VD_STRATEGY_CAPACITY_SIMULATOR_NOT_READY` | fixture-only integration proofs; no admitted development replay run |
| TD-8E shared-context integration (2026-09-20) | `PASS` but explicitly `NON_COUNTING_INFRASTRUCTURE_EVIDENCE` | one controlled event, read-only |

`CURRENT_VALIDATION_STATE.json`: `robustness: null · candidate: null · holdout: null ·
holdout_run_count: 0 · demo_eligible: false`. Existing parquet ledgers under
`artifacts/backtests/` are **observational discovery runs** (Aug–Sep 2025 setup ledgers),
not economic evidence — the repo itself draws that line.

## 4. Assurance gates (the project's own audit, `AG_VALIDATION_SYSTEM_ASSURANCE_V1.md`)

| Gate | Status | Notes |
|---|---|---|
| VA1 temporal / no-lookahead | PARTIAL → frozen as `VD_TEMPORAL_LOOKAHEAD_V1` | deterministic perturbation test now exists (decisions at T unchanged by future continuation) |
| VA2 warm-up stability | **PARTIAL / unproven** | no finalized canonical warm-up convergence suite |
| VA3 synthetic known-answer suite | **PARTIAL** | strong base (deterministic virtual-exchange tests) but no single repo-wide machine-testable manifest |
| VA4 economic accounting | **PASS** (fail-closed semantics) | `UNAVAILABLE` cost can never silently become zero |
| VD capacity simulator | **NOT_READY** | friction/metric/qualification contracts + manifest unfrozen; OHLC same-bar ambiguity unresolved; BE/partial virtual lifecycle undefined; leverage/margin/slippage/latency deferred as `DEFERRED_EXECUTION_PARITY` |

## 5. Known completeness gaps (declared, fail-closed)

1. **Historical session-box reconstruction** — replay reports `HISTORICAL_SESSION_DATA_UNAVAILABLE` and degrades explicitly; session-dependent strategy semantics can't be fully replayed yet.
2. **OHLC intra-bar ambiguity** — `VirtualExchange` has first-eligible-open + same-bar fail-closed rules, but SL/TP-within-bar ordering remains unresolved by design (not invented).
3. **Large-SMC replay metadata decoupling gap** — dedicated status doc; symbol-metadata replay gap documented.
4. **Data estate** — one-year M1 leg exists (~43 MB committed) plus H1/M15 derived legs, dev datasets, warmup contexts, all manifest-bound; but (a) cross-leg timezone inconsistency, (b) 8-month M1 coverage hole, and (c) the DEV002 fingerprint regression currently break admissibility.
5. **Machine coupling** — backtest data comes from Windows MT5 exports; golden-slice raw CSV is machine-local (`D:\…`, skips gracefully). Non-Windows machines can run all offline backtest *tests* but cannot originate new datasets.

## 6. Readiness verdict by dimension

| Dimension | Verdict | Basis |
|---|---|---|
| Architecture & anti-leakage design | 🟢 **READY** | live/replay code-path identity, MT5-isolation patch, lookahead contract, fingerprints |
| Engineering verification (unit level) | 🟢 **MOSTLY READY** | 396/405 pass; 8 of 9 failures trace to one dataset regression |
| Data admissibility | 🔴 **NOT READY** | timezone leg inconsistency, M1 coverage gap, DEV002 fingerprint mismatch |
| Evidence production (economic replay) | 🔴 **NOT READY** | zero completed economic replays; current hypothesis at `TERMINAL_FAIL` data gate |
| Robustness / OOS | ⚪ **NOT STARTED** | robustness/holdout artifacts null by policy (correct: nothing to challenge yet) |
| Safety | 🟢 **EXEMPLARY** | no backtest path can reach order send; every gate fails closed; blocked missions change nothing |

## 7. Recommended order to reach a first trustworthy backtest

1. **Resolve the DEV002 H1 dataset/manifest mismatch** (owner decides which artifact is authoritative, re-freeze the other) — unblocks 8 tests and the TD-8E/SSC integration chain.
2. **Fix cross-leg timezone authority** — re-express H1/M15 in the M1 time base (the durable R2/R3 gate now exists to enforce this; re-run coverage audit).
3. **Close the M1 coverage hole** — acquire the missing ~8 months of M1 fill-resolution history, or formally shrink the one-year window to an admissible span.
4. **Re-run the one-year replay mission (R0–R17)** — first legitimate economic population + replay.
5. **Finish assurance gates**: VA2 warm-up convergence suite, VA3 repo-wide synthetic known-answer manifest, VD capacity friction/metric/qualification contracts + manifest; resolve OHLC same-bar policy via an explicit contract.
6. **Session-box reconstruction** for replay fidelity of session-dependent strategies.
7. Only then: robustness battery (walk-forward, cost stress, parameter surface) per the `robustness-validation` skill — the project's own rule is falsification-first, never tune on the final test set.

**Bottom line:** this is not a backtest system with hidden quality problems — it is a
high-quality backtest system honestly reporting that it has no data-admissible window in
which to produce evidence yet. Its gates are doing exactly what gates are for. The
critical path is data (items 1–3), not code.
