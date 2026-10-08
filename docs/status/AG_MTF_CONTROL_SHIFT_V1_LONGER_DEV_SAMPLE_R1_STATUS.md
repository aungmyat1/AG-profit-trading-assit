# AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1 — Status

## Mission

Diagnostic follow-up to `AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1` (PR #46): re-run
`INT_C002` (`ST_MTF_CONTROL_SHIFT_V1`, PR #34, unmodified engine) with more EURUSD
D1/H4 history, to try to explain its `HOLD_SAMPLE_REQUIRED` verdict (0 signals across
the parent campaign's ~1-year DEV sample). Preparation/evidence only — no strategy
rule, threshold, or production authority changed.

## Governance

- `BASE_SHA` resolved live from `origin/main` at runtime: `fc60cdbf603146b1408dba9184e6c146bdcf4ea5`.
- Work done on the fixed session branch `arena/d1cea83b-ag-profit-trading-assit`
  (= PR #46's head branch). PR #46 (OPEN, draft) already exists on this branch, so the
  draft-PR-before-push requirement is satisfied by its prior existence.
- Parent prereg `AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_PREREG_V1` (`PREREG_SHA256=
  342482c9972d1029d85b5ce4ab4792d4d147617d110aa88a6b020e32b707912b`) was **not edited**.
  A new, separate prereg was frozen before this replay:
  `research_external/candidate_factory/PREREG_MTF_LONGER_SAMPLE_R1.json`
  (`PREREG_ID=AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1_PREREG_V1`,
  sha256 in `PREREG_MTF_LONGER_SAMPLE_R1.sha256.txt`).
- Kill-policy thresholds (`AG_CF_R1_DEV_SCREEN_V1`: min_trade_count=30,
  min_profit_factor=1.30, max_drawdown_R=15.0, ...) reused by reference, unchanged, not
  re-derived or loosened.
- No OOS/sealed/FINAL_HOLDOUT data opened. The new data source used
  (`SSC_V1_0_1_G2_DEV_002`) is `data_role: DEVELOPMENT` in its own manifest; its
  pre-2026-06-21 H1 history is explicitly tagged `WARMUP_CONTEXT_ONLY` by its own
  manifest for its original (different) strategy campaign, and this mission
  independently adopts the same restriction: used only to derive D1/H4 structure/bias,
  never to add a new M15 decision day.
- `BROKER_MUTATION_COUNT=0`, `DEMO_AUTHORIZED=FALSE`, `LIVE_AUTHORIZED=FALSE`,
  no production registry touched, PR #45 untouched.

## What changed vs. the parent run

Only D1/H4 derivation: instead of 40/80-bar bounded tail windows ending at each
decision point (the parent run's documented tractability shortcut), this run derives
D1/H4 from a genuinely longer H1 series (2025-01-01→2026-09-15, extended backward
~8.5 months via `SSC_V1_0_1_G2_DEV_002`, verified byte-identical to the parent
dataset in their overlap window) and passes the **full closed-to-date series** at every
decision point (no truncation). The M15 decision population (HIST1Y, 2025-09-14→
2026-09-15), session windows, symbol, and the engine itself are all unchanged.

## Results

| Cycle | Days evaluated | CONTEXT pass | → LOCATION pass | → H1_CONTROL_SHIFT pass | → M15_REFINEMENT | Signals | Trades |
|---|---|---|---|---|---|---|---|
| LONDON_NEWYORK | 314 | 55 (17.5%) | 5 | 0 | 0 | 0 | 0 |
| ASIAN_LONDON | 314 | 50 (15.9%) | 4 | 0 | 0 | 0 | 0 |

Parent run (40/80-bar bounded D1/H4): CONTEXT pass rate was 53/305 = 17.4% — essentially
identical to this run's ~16–17.5% despite ~7.7x more D1/H4 history (confirmed:
`n_d1_bars=220` already on the first evaluated day here, vs a bounded 40 in the parent run).

## Conclusion

- **Explanations C (timeframe derivation/data inadequacy) and D (adapter/replay
  mismatch via bounded tail windows) are REJECTED** as causes of the dominant
  `HTF_BIAS_NOT_ALIGNED` blocker: the pass rate did not move with far more D1/H4 history.
- **A sharper, previously-hidden bottleneck was found**: of the handful of days that
  reach `H1_CONTROL_SHIFT` (5 and 4, out of 314), **zero ever pass it** in either cycle —
  the engine's 4-bar control-shift recency window (`H1_SHIFT_MAX_AGE_BARS=4`), combined
  with the LOCATION-stage requirement, appears to be the real limiting joint condition.
  This is recorded as an observation only — **no threshold was loosened**.
- **Explanation A (genuinely extremely selective) is now better supported**; B, E
  remain `NOT_VERIFIED` (B would need more M15 history, which does not exist in this
  checkout; E was not separately tested).
- **Verdict: `HOLD_SAMPLE_REQUIRED`, UNCHANGED.** 0 trades in both cycles; `min_trade_count=30`
  not met. `min_trade_count` was not lowered. No freeze campaign proposed.

## Evidence paths

- Prereg: `research_external/candidate_factory/PREREG_MTF_LONGER_SAMPLE_R1.json` (+ `.sha256.txt`)
- Extended H1 data: `research_external/candidate_factory/data/EURUSD_H1_WARMUP_EXTENDED_JAN2025_SEP2026.csv`
- Replay script: `research_external/candidate_factory/replay/run_int_c002_longer_sample.py`
- Run outputs: `research_external/candidate_factory/dev_replay/INT_C002_MTF_CONTROL_SHIFT_V1__EURUSD__{LONDON_NEWYORK,ASIAN_LONDON}__LONGER_SAMPLE_R1/`
  (`run_manifest.json`, `decisions.csv`, `trades.csv`, `metrics.json`, `diagnostic_funnel.json`)
- Candidate record: `research_external/candidate_factory/candidates/INT_C002_LONGER_SAMPLE_R1.json`
- Updated plan: `docs/plans/AG_MTF_CONTROL_SHIFT_SAMPLE_ADEQUACY_R1.md` (addendum at top)
- Updated table: `research_external/candidate_factory/CANDIDATE_TABLE.md` (addendum, original row untouched)

## Safety

`PROMOTE_TO_FREEZE_CAMPAIGN=0`, `NEW_LOGIC_VERIFIED=0`, `NEW_EDGE_VERIFIED=0`,
`BROKER_MUTATION_COUNT=0`, `PRODUCTION_REGISTRY_CHANGED=FALSE`, `OOS_DATA_TOUCHED=FALSE`,
`ASIAN_SWEEP_R4A_TOUCHED=FALSE`.
