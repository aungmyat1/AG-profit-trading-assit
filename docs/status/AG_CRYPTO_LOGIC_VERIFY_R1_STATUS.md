# AG_CRYPTO_LOGIC_VERIFY_R1 — Status

## Governance

- `MAIN_SHA` resolved live at runtime: `fc60cdbf603146b1408dba9184e6c146bdcf4ea5`.
- Work done on the fixed session branch `arena/d1cea83b-ag-profit-trading-assit`
  (= PR #46's head). PR #46 (OPEN, draft) already exists on this branch — draft-before-
  push requirement satisfied by its prior existence; no new branch/PR opened (same
  policy variant reported in prior missions on this branch).
- **No broker activity, no strategy registry mutation, no demo/live authorization
  change.** Nothing in `strategies/registry.yaml` touched. `BROKER_MUTATION_COUNT=0`.
- **Strategy mutation freeze**: the T2 spec (`CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1_SPEC.md`,
  sha256 `5bc8eccca6c90f4002a7c75b5c5e9046df7f61ce42097b0416050d5b2630ba52`) was frozen
  BEFORE T3/T4/T5 and not edited afterward.

## Input verification (done first)

- **VT Markets BTCUSD/ETHUSD data pack from `AG_V1_HOST_HARDENING_R1` T4: NOT FOUND.**
  Searched `origin/main` and every currently open PR (#48, #45, #46, #44, #36, #34, #33,
  #32, #31, #30, #20, #19, #18, #17, #11, #1) for any manifest or file referencing that
  mission name, or any new BTCUSD/ETHUSD OHLC file — zero hits. No manifest hash exists
  to verify. `HOST_DATA_NOT_VERIFIED` (not `NO_DATA_EXISTS`). Per the mission's own
  fallback instruction, T1–T5 below are built on **fixtures only**; no exchange
  (Bybit/Binance perpetual) data was substituted as ticket evidence anywhere.
- **`LSMC_ACTIONABILITY_POLICY_V1`: found as a SIGNED owner-decision DOCUMENT only**
  (`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, in open PR #48
  — not merged, not touched by this mission). **No implementing state-machine code exists
  anywhere in this repository** — PR #48 itself shipped only an alert-dedup fix and a
  display-tick-normalization fix, not the D1 (freshness)/D2 (remaining-R) engine its own
  "Implementation priority" section lists as still-P0/outstanding. Per the mission's
  explicit instruction, **no separate freshness/R logic was implemented** here; T2's spec
  records this as an unresolved upstream dependency and stops at the deterministic-
  opportunity layer (see spec's "Explicit non-scope" section).
- Related, out-of-scope discovery (recorded only): PR #30 (`ST_CRYPTO_CFD_SWEEP_
  RETEST_V1`) and PR #31 already define a separate, swing/BOS/sweep-based internal
  BTCUSD/ETHUSD CFD contract. Not touched, not treated as a T1 candidate (T1 was
  explicitly scoped to OSS_CRYPTO_C001/C002 only).

## Gate results

| Task | Result | Summary |
|---|---|---|
| T1 Candidate selection | **HOLD** (selection PASS; real-data replay HOLD_DATA) | Primary: **OSS_CRYPTO_C001** (Donchian/Turtle, via new derived ticketized candidate). Rejected: **OSS_CRYPTO_C002** (freqtrade EMA cross) — G1 HOLD_SPEC never resolved, worse ticketability mismatch, lower evidence class (SB3 vs SB5). Real VT-data DEV replay blocked pending the data pack. |
| T2 Frozen spec | **PASS** | `CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1_SPEC.md` v1.0.0, frozen+hashed, all 5 declared deviations from source explicitly labeled `MATERIAL_DEVIATION`. |
| T3 Fixtures + property tests | **PASS** | 5 golden fixtures + 4 hypothesis property tests (no look-ahead, close-confirmed, expiry terminates, tick-grid alignment) — 9/9 pass. |
| T4 Differential check | **PASS** (with scope note) | Candidate itself has no swing/BOS/sweep logic; differential run against the repo's existing `mtf_control_shift` swing code vs `smartmoneyconcepts` PyPI instead. 98.33% agreement across 6 seeds; both disagreements classified `SPEC_DIFF` (boundary-handling convention); **0 BUG**. |
| T5 Blind handoff | **PASS** | Sanitized R4A package built: spec + anonymized fixtures + I/O schema + manifest with `PACKAGE_SHA256`. No reference implementation, no expected outputs included. R4B (actual blind comparison) **NOT_RUN** — requires a genuinely separate agent/session context, per the PR #45 precedent. |

## Safety

`PROMOTE_TO_FREEZE_CAMPAIGN=0`, `NEW_LOGIC_VERIFIED=0`, `NEW_EDGE_VERIFIED=0`,
`DEMO_AUTHORIZED=FALSE`, `LIVE_AUTHORIZED=FALSE`, `BROKER_MUTATION_COUNT=0`,
`PRODUCTION_REGISTRY_CHANGED=FALSE`, draft PR only (#46, OPEN).

## Evidence paths

- `research_external/candidate_factory/crypto_logic_verify_r1/T1_CANDIDATE_SELECTION.md`
- `research_external/candidate_factory/crypto_logic_verify_r1/spec/CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1_SPEC.md` (+ `.sha256.txt`)
- `research_external/candidate_factory/crypto_logic_verify_r1/engine/turtle_breakout_d1.py`
- `research_external/candidate_factory/crypto_logic_verify_r1/fixtures/*.csv` (+ `README.md`)
- `research_external/candidate_factory/crypto_logic_verify_r1/tests/test_golden_fixtures.py`,
  `test_properties_hypothesis.py`
- `research_external/candidate_factory/crypto_logic_verify_r1/differential/T4_DIFFERENTIAL_REPORT.md`,
  `run_swing_differential.py`, `swing_differential_report.json`, `robustness_check.json`
- `research_external/candidate_factory/crypto_logic_verify_r1/blind_handoff/CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1/`
  (`BLIND_TASK.md`, `spec.md`, `schema.json`, `dataset.json`, `fixtures/fixture_0{1..5}.csv`, `handoff_manifest.json`)

## Next steps (not started; owner input needed)

1. When the `AG_V1_HOST_HARDENING_R1` T4 VT data pack lands: verify its manifest hashes,
   then re-run T1 as real DEV replay against actual VT Markets BTCUSD/ETHUSD OHLC.
2. `LSMC_ACTIONABILITY_POLICY_V1`'s D1/D2 state-machine implementation is a separate,
   P0 prerequisite (per PR #48's own priority list) before ANY candidate (crypto, Asian
   Sweep, or LSMC) can emit a ticket through it — this mission does not build it.
3. R4B blind comparison against the T5 package requires a genuinely separate agent
   context, same constraint already documented for the Asian Sweep R4A/R4B lane.
4. If the owner wants T4 literally against a swing/BOS/sweep crypto candidate, PR #30's
   `ST_CRYPTO_CFD_SWEEP_RETEST_V1` is the natural target — not evaluated here since T1
   explicitly scoped this mission to OSS_CRYPTO_C001/C002.
