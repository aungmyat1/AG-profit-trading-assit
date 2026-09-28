# FX Discovery V1 — OSS Evaluation and Semantic Parity

**Date:** 2026-09-28. Canonical semantics were fixed **before** any strategy outcome was computed.

**Harness:** `scripts/research/fx_discovery_parity_harness.py`. It ran in an isolated scratch venv (Python 3.14.7, pandas 3.0.6, numpy 2.5.3). OSS code was loaded from pinned clones and **nothing was installed into the project**.

**Raw output:** `FX_DISCOVERY_V1_SEMANTIC_PARITY_REPORT.json`.

All three components have EXECUTION_AUTHORITY = NONE and PROPOSAL_AUTHORITY = NONE.

## Components evaluated

| Project | Commit / version | License | Maintenance | Upstream tests (isolated) | Decision |
|---|---|---|---|---|---|
| [smart-money-concepts](https://github.com/joshyattridge/smart-money-concepts) | `1b62fd6c41e1f508e7ed76831a039fa4c82d42f6`, v0.0.27 (2026-04-03) | MIT (© 2020 NeuralNine) | 157 commits, ~6 recent authors | `unit_tests.py` 10/10 pass | **REJECT for signal use** (non-causal). Reference only. |
| [smc-mcp](https://github.com/AkhileshSelvan/smc-mcp) | `719862b404ec4bd4d52b3bfa4c39ef0c034bb654`, v0.1.0 (2026-06-14) | MIT (© 2026 Akhilesh) | 2 commits, 1 author | 7/7 pass on the pure `smc_mcp.smc` subpackage; the MCP server, `mcp` and `yfinance` were never loaded | **Semantic reference.** Its causal swing and BOS/CHoCH design is re-implemented in AG (about 100 lines, with attribution). It is not a dependency (young project; MCP and yfinance dependencies). |
| [pandas-ta-classic](https://github.com/xgboosted/pandas-ta-classic) | `8afeec2250c7c114c5d647ade5e2319b67e1aaa2`, 0.8.33.dev171 (2026-09-26) | MIT | 1,383 commits, active | ATR/EMA tests 5/5 pass (the `hypothesis` optional test was not installed) | **Indicator oracle.** AG ATR/EMA are parity-checked against it. It is not added as a dependency. |

## Semantic differences (k = 2, fixtures in the harness)

1. **Swing timing.**
   - AG and `smc-mcp` use a strict fractal and treat the swing as known at `i + k`. They agree on every fixture.
   - `smart-money-concepts` uses a centered rolling window (L−1 bars before, L after) and stamps the swing at the pivot bar, with no confirmation time.
2. **Equal highs.** AG and `smc-mcp` produce no swing (strict `>`). `smart-money-concepts` produces a swing (non-strict `==` rolling max).
3. **Endpoint and repainting behavior (`smart-money-concepts`).**
   - It overwrites the first and last bars with synthetic opposite-type swings.
   - It removes consecutive same-type swings using *later* swings.
   - It marks a swing on a forming last bar.
   - Its prefix output changes when future candles are mutated (future-mutation test **FAIL**). AG and `smc-mcp` pass.
4. **BOS/CHoCH.**
   - AG and `smc-mcp` define a break as a **close** beyond the last known, unconsumed swing, stamped at the breaking bar. Its label depends on the prior trend; the first break is CHoCH.
   - `smart-money-concepts` classifies from a 4-swing *pattern*, stamped at an earlier swing, with the break time in `BrokenIndex`.
   - On `choch_down`, AG and `smc-mcp` report a bearish **CHoCH** at bar 11. `smart-money-concepts` reports a bearish **BOS** stamped at bar 5 (broken at 11).
5. **Liquidity sweep.**
   - `smc-mcp` sweeps the most recent swing with `index < i`, **including unconfirmed swings**. That is look-ahead, and it contradicts its own structure module.
   - AG sweeps only swings with `known_at < i`.
   - On `choch_down`, AG finds the bearish sweep of the confirmed 108 high at bar 8. `smc-mcp` misses it because it compares against the 115 swing, which is not confirmed until bar 9.
   - `smart-money-concepts`' `liquidity()` is a clustering of swings, not a sweep detector.
6. **Wick vs close-through.** Every implementation treats a wick-and-reclaim as a sweep and a close beyond the level as a break. AG's session sweep rule (`entry_2_sweep`) agrees: VALID on `wick_sweep` at bar 8, NO_SETUP on `close_through`.
7. **FVG.** All implementations agree on direction and levels. `smart-money-concepts` requires the middle candle's body direction. AG and `smc-mcp` treat the gap as known at the close of bar `i + 1`.
8. **ATR/EMA.** AG EMA is identical to `pandas-ta-classic`. AG ATR (Wilder, SMA-seeded) differs by at most 9.3e-6 at the seed (about 1% of ATR) and by 3.9e-10 after 150 bars; the difference is seeding convention only.

## Canonical AG semantics

`src/fx_discovery/features.py` is the canonical implementation, covered by `tests/test_fx_discovery_features.py`, which has no OSS dependency. OSS objects never cross into AG code.
