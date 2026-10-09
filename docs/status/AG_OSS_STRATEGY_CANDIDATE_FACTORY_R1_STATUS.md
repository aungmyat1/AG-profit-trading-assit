# AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 — Status

```
MISSION = AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1
STATUS  = COMPLETE (R1 scope only: no promotion produced; see candidate table)

REPO       = aungmyat1/AG-profit-trading-assit
MAIN_SHA   = fc60cdbf603146b1408dba9184e6c146bdcf4ea5
MAIN_TREE  = adf5b0ea0ba43681ce7a2d4665e40559e56e4f33
WORK_BRANCH_BASE_SHA = fc60cdbf603146b1408dba9184e6c146bdcf4ea5 (clean worktree verified)
WORK_BRANCH = arena/d1cea83b-ag-profit-trading-assit
```

## Branch-policy note (read first)

This Arena session is permanently bound to `arena/d1cea83b-ag-profit-trading-assit`
(one-writer-per-branch, matching `AGENTS.md`'s own "Branch, push and merge discipline"
rule). The mission's preferred branch name
`research/oss-strategy-candidate-factory-r1` could not be created without violating that
binding. Per the mission's own fallback ("If branch policy requires a naming variant,
follow policy and report the actual branch"), this work is committed to
`arena/d1cea83b-ag-profit-trading-assit` instead. This is **not**
`arena/3b8a0571-ag-profit-trading-assit` (PR #45's branch) and no commit here touches
that branch, its ref, or any file associated with it — see `ASIAN_SWEEP_R4A_TOUCHED`
below. This is treated as a reported policy variant, not `BLOCKED_BRANCH_POLICY`,
because the hard requirement (a dedicated branch, isolated from PR #45) is satisfied.

```
PREREG_ID      = AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_PREREG_V1
PREREG_SHA256  = 342482c9972d1029d85b5ce4ab4792d4d147617d110aa88a6b020e32b707912b
DATA_MATRIX    = research_external/candidate_factory/data_capability_matrix.json

N_CANDIDATES      = 5
N_TRIALS          = 5
DEV_REPLAY_COUNT  = 5   (cap: MAX_DEV_REPLAYS=6, MAX_DISCOVERED=20)
```

## Candidates

See `research_external/candidate_factory/CANDIDATE_TABLE.md` for the full gate table.
Summary:

| ID | Source | SB | G1 | G2 | G3 | G4 | G5 | AG_REPRODUCED | Friction | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| INT_C001 `SESSION_TRADE_V2` (PR #33) | internal | SB0 | PASS | PASS | PASS(EURUSD) | PASS | EXACT | TRUE | FAIL | **REJECTED** |
| INT_C002 `ST_MTF_CONTROL_SHIFT_V1` (PR #34) | internal | SB0 | PASS | PASS | PASS(EURUSD) | PASS | EXACT | N/A (0 trades) | **HOLD_SAMPLE_REQUIRED** |
| OSS_FX_C001 ORB-at-NY-open | Zarattini & Aziz 2023, rule-extracted | SB4 | PASS* | PASS | PASS(EURUSD) | PASS | MATERIAL_DEVIATION | TRUE | FAIL | **REJECTED** |
| OSS_CRYPTO_C001 Donchian/Turtle | rule-extracted | SB5 | PASS | FAIL | FAIL(no data) | — | — | FALSE | N/A | **HOLD_DATA** |
| OSS_CRYPTO_C002 freqtrade EMA-cross | rule-identified, not fully extracted | SB3 | HOLD_SPEC | FAIL(presumed) | FAIL(no data) | — | — | FALSE | N/A | **HOLD_DATA** |

\* PASS for this mission's own operationalized doji threshold; the source's literal rule
is `HOLD_SPEC` because the paper's "about the same" threshold is unquantified in the
secondary summary available to this mission.

### Why both internal candidates were run, and why neither was promoted

Per the internal-first shortcut, `SESSION_TRADE_V2` (INT_C001, the LONDON_NEWYORK-capable
internal candidate) was replayed first, against the real `PR #33` engine (byte-identical
copy, provenance recorded) over 9 months of real EURUSD M15 data (`TRAIN` partition only;
`VALIDATION` left untouched, `FINAL_HOLDOUT` never opened). It produced a decisively
negative gross expectancy in both supported sessions (-0.25R LONDON_NEWYORK, -0.14R
ASIAN_LONDON, N=65/89 trades), below every preregistered kill threshold before friction.
It does **not** pass, so the shortcut's "promote immediately" branch does not apply, and
external discovery proceeded as planned (capped at one serious LONDON_NEWYORK comparator
plus crypto discovery, per the mission's own budget).

`ST_MTF_CONTROL_SHIFT_V1` (INT_C002, PR #34) was replayed the same way over ~1 year of
real EURUSD D1/H4/H1/M15 data (D1/H4 derived by causal resample of a real H1 series). It
produced **zero** qualifying signals in either session — not a negative-expectancy
result, but an insufficient-sample one (`HOLD_SAMPLE_REQUIRED`, since `min_trade_count=30`
is never lowered after seeing a result).

### External discovery

One LONDON_NEWYORK comparator (`OSS_FX_C001`, an Opening-Range-Breakout rule extracted
from Zarattini & Aziz 2023, translated to EURUSD at AG's own session-open convention) was
rule-extracted (no code imported/executed, per the EXTERNAL CODE RULE) and DEV-replayed on
the same EURUSD TRAIN data: gross expectancy was barely positive (+0.045R, N=176) but
below the profit-factor kill threshold even before cost, and turned net-negative once the
preregistered VT Markets spread scenario was applied. **REJECTED.**

Two crypto candidates (`OSS_CRYPTO_C001` Donchian/Turtle breakout, `OSS_CRYPTO_C002`
freqtrade EMA-crossover) were discovered, provenance-recorded, and gate-classified, but
both are blocked at `G3_DATA_VENUE_FIT`: **this environment has zero historical OHLC bars
for BTCUSD or ETHUSD** — only a single point-in-time VT Markets symbol-metadata snapshot
(spread, overnight SWAP, contract size). No DEV replay was possible or attempted for
either; both resolve to `HOLD_DATA`, not `REJECTED` (nothing here says the underlying idea
is uneconomic — only that it could not be evaluated). Per the mission's own priority order,
no Asian→London external comparator was pursued (0 of the allowed 0-1 budget spent),
since that session already has a mature owner-designed campaign (PR #45, untouched).

## Data capability (see data_capability_matrix.json for full detail)

- **EURUSD**: real DEV data available at M5 (9-month `TRAIN` partition, `VALIDATION`
  reserved/unused, `FINAL_HOLDOUT` sealed/untouched) and at H1+M15 (~1 year, D1/H4
  derived). Used for all 5 DEV replays.
- **GBPUSD**: only a ~6-week real DEV window physically present — too short for this
  mission's own `min_trade_count=30` policy within a single session; not replayed.
- **USDJPY, XAUUSD**: no OHLC history of any kind in this checkout (only a single
  point-in-time symbol-metadata snapshot); `config/historical_datasets/*.yaml` manifests
  reference a wider history, but its `source_file` is a `D:\` path on the owner's Windows
  host, not present in this git checkout.
- **BTCUSD, ETHUSD**: no OHLC history of any kind; only point-in-time VT Markets CFD
  symbol metadata (spread, overnight SWAP — not a perpetual funding rate).

## Pre-existing documentation/implementation drift finding (not caused by this mission)

`docs/status/AG_EXTERNAL_CANDIDATE_VALIDATION_LAYER_V1_STATUS.md` and
`docs/specs/AG_RESEARCH_FACTORY_V1_GOVERNANCE_SPEC.md` describe `src/external_candidate/`
and `performance/` as already built, tested infrastructure. Neither physically exists
anywhere in this repository's git history (`git log --all -- src/external_candidate`
returns nothing; no `performance/` directory exists anywhere under `src/`).
`scripts/generate_economic_evidence_report.py` and `research_external/run_s2r_baseline.py`
both fail today with `ModuleNotFoundError: No module named 'performance'` on a clean
checkout of this branch. This mission does not attempt to silently resurrect that name;
the small `research_external/candidate_factory/replay/common.py` and `friction.py`
modules built here are new, minimal, and separately named. Flagged for owner attention,
not resolved here (out of this mission's scope).

## Architectural boundary

Added `tests/test_research_external_boundary.py`: a static AST scan asserting no file
under `src/` imports `research_external` (verified: zero existing imports; test passes).

## Safety / parallel-track confirmation

```
PARALLEL_ASIAN_SWEEP_PR = 45
ASIAN_SWEEP_R4A_TOUCHED = FALSE
ASIAN_SWEEP_HANDOFF_IDENTITY_CHANGED = FALSE
OOS_DATA_TOUCHED = FALSE
PRODUCTION_REGISTRY_CHANGED = FALSE
BROKER_MUTATION_COUNT = 0
DEMO_AUTHORIZED = FALSE
LIVE_AUTHORIZED = FALSE
AUTOMATED_EXECUTION = FALSE
NEW_LOGIC_VERIFIED = 0
NEW_EDGE_VERIFIED = 0
BOUNDARY_TEST_SRC_IMPORTS_RESEARCH_EXTERNAL = PASS
```

## Promoted candidates

None. `PROMOTE_TO_FREEZE_CAMPAIGN = 0`. Per the mission's own success criteria, R1 does
not require profitability, `LOGIC_VERIFIED`, or `EDGE_VERIFIED` — the objective was an
auditable screen, which this report and its underlying artifacts provide.

## Next steps (not started by this mission)

- `ST_MTF_CONTROL_SHIFT_V1` remains genuinely unscreened (not rejected): a future mission
  with a longer admitted EURUSD D1/H4 history (or a second real symbol) could re-run
  exactly this harness against `PREREG_SHA256` above and reach an actual economic
  verdict.
- No `*_FREEZE_R2` mission is proposed from this run, since nothing passed. If the owner
  wants to pursue `ST_MTF_CONTROL_SHIFT_V1` further, the next mission would be
  `AG_INT_MTF_CONTROL_SHIFT_V1_LONGER_DEV_SAMPLE_R1` (more DEV data, same harness), not a
  freeze campaign yet.
- Crypto BTC/ETH candidate evaluation is blocked on acquiring any real historical OHLC
  data for those symbols in this environment; that is itself a prerequisite task, not a
  strategy-research one.

## Artifacts

```
research_external/candidate_factory/PREREG_CANDIDATE_FACTORY_R1.json
research_external/candidate_factory/PREREG_CANDIDATE_FACTORY_R1.sha256.txt
research_external/candidate_factory/data_capability_matrix.json
research_external/candidate_factory/README.md
research_external/candidate_factory/CANDIDATE_TABLE.md
research_external/candidate_factory/internal_reference/{session_trade_v2,mtf_control_shift}/
research_external/candidate_factory/replay/{common.py,friction.py,run_*.py}
research_external/candidate_factory/dev_replay/<6 run directories>/
research_external/candidate_factory/candidates/{INT_C001,INT_C002,OSS_FX_C001,OSS_CRYPTO_C001,OSS_CRYPTO_C002}.json
tests/test_research_external_boundary.py
docs/status/AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1_STATUS.md (this file)
```

## Blockers

None blocking this mission's own completion. Listed as findings, not blockers:
GBPUSD/USDJPY/XAUUSD/BTC/ETH lack sufficient admitted DEV data in this environment for a
DEV replay; `performance/`/`src/external_candidate/` documentation drift (pre-existing).
