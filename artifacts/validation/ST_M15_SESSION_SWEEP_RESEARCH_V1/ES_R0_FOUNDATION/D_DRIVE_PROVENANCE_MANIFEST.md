# D:\ Provenance Manifest

**Project:** `D:\ddev\Session Trade Codex`
**Repository HEAD observed during ES-R0A:** `d026f09a6fc79b5f0eabfd438252d0a545cb4d05` (branch `master`, git repository)
**Role:** `LEGACY / EXTERNAL RESEARCH REFERENCE` — corroborating evidence and a source of potentially reusable *concepts* only. **Not a runtime dependency. No code is imported from it. No network or file call from AG reaches it.** It continues to evolve independently outside this lineage.

## Documented strategy versions observed (internal version churn — not one static implementation)

| Version | Status observed | Notes |
|---|---|---|
| `ASIAN_SESSION_V1` (`config/strategy.yaml`) | `LEGACY_FROZEN` | Predecessor |
| `STRATEGY_TRUTH_SOURCE.md` v3.0 (2026-08-15) | Self-marked `SUPERSEDED` at the time, pointing to `SESSION_FLOW_V1` | Most rigorous, best-documented formalization found; source of the corroborating formulas in `BASELINE_STRATEGY_CONTRACT.md` |
| `ASIAN_SESSION_V2` (`config/strategy_v2.yaml`, 2026-08-26) | `analysis_only`, all execution permissions `false` | Canonical-session successor; uses `00:00–06:00 UTC` Asian window, differing from v3.0/AG |
| `SESSION_SIMPLE_V1` | Current `FROZEN` per `STATUS.md` (2026-08-25) | Simplified: fixed 5R, max trades = 1, **no** partial/BE management |

## ⚠️ MT5 execution/identity safety finding (recorded, not acted upon)

`D:\ddev\Session Trade Codex` has live MT5 execution infrastructure wired (`session_strategy/mt5_gateway.py`, `execution/executor.py`) and, as observed in `ACTIVE_STATUS.md` (2026-08-26), a connected account with one open position and two pending limit orders using **magic number `777001`** — the same magic number as AG's own `strategies/ST_ASIAN_SWEEP_5R_V1.yaml`. See `MT5_IDENTITY_RISK_RECORD.md`.

## Corroborating value

D:\'s `STRATEGY_TRUTH_SOURCE.md` v3.0 independently states the *identical* stop/target formula AG reconstructed in ES-S1R (`Stop = E − S×D`, `TP5 = E + S×5D`, `D = 0.25A`), including explicitly forbidding any structural buffer — strong independent corroboration that AG's Class-A baseline is not an artifact of AG's own reasoning alone.
