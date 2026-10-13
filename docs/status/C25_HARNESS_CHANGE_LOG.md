# AGP-C25 harness change log (2026-10-14)

Every change made to `scripts/c25_oss_differential.py` after its first run, with before/after counts and the
justification. The first-run script is kept byte-for-byte as
`artifacts/oss_differential/harness_history/S0_first_run.py.txt`. Its raw divergences are in
`artifacts/oss_differential/c25_first_run_divergences.json`. Each step `S(n)` is `S(n-1)` plus one change; the
unified diffs are in `harness_history/step<n>.diff` and the per-step summaries are in `step_summaries.json`.

All eight step versions were re-run on the committed 60d data (resource class R1, about 55 s each). S0 reproduces
the first-run numbers. S7 is byte-identical to the report committed in `b9bc475`
(`8af20fc6…`), so the history is complete.

Owner rule applied: a change justified only by "makes it agree" is reverted and its divergence reported.

| Step | Change | Before → after | Justification | Decision |
|---|---|---|---|---|
| S1 | Oracle: two anchor rows; place the bracket on the first `next()` | ASW AGREE 3 → 228, ORACLE_DEFECT 270 → 2. CCFD ORACLE_DEFECT 8 → 1, AGREE 0 → 6 | backtesting.py never calls `Strategy.next()` on row 0 (`backtesting/backtesting.py:1318` `start = 1 + warmup`), so no order was ever placed. This was an oracle-harness defect | KEPT |
| S2 | smc level compare `abs_tol=1e-6` → `rel_tol=1e-6` | smc sweep-level agreement 12.5% → 100% | smc returns float32 levels (`smartmoneyconcepts/smc.py:248`). At BTC/ETH prices the float32 step exceeds 1e-6 absolute | KEPT |
| S3 | CCFD fuzz evaluated at the ticket's recorded `now` instead of the signal close | no count change (CCFD fuzz FAIL 1 → 1) | The owner definition says "bars after the signal close removed", so the signal close is the literal evaluation time | **REVERTED** in S8. The ticket `now` is used only by the supplementary check |
| S4 | Fuzz (c): perturb the latest bar *after* the signal bar instead of the signal bar | ASW fuzz FAIL 172 → 0. CCFD FAIL 1 → 0 (+1 NOT_EVALUABLE) | Only that a signal-bar change is "not a repaint". The owner definition perturbs the last bar of the truncated input, which is the signal bar | **REVERTED** in S8. The literal check is restored as the verdict (ASW 172 FAIL, reported below). The S4 check is kept as supplementary only |
| S5 | Oracle expiry: drop the manual close; add a flat terminal row at the horizon | ASW AGREE 228 → 269, UNCLASSIFIED 43 → 2 | The repo resolver books EXPIRY at the close of the last bar in [start, horizon) (`src/v1_tickets/outcome.py:27-28`). backtesting.py never processes its final row and exited one bar early (`backtesting.py:1324`, `finalize_trades` at `:1341`). The mission requires an identical horizon | KEPT |
| S6 | Classifier: TP gap fill and data-ends-before-horizon become SPEC_DIFFERENCE | ASW UNCLASSIFIED 2 → 0 (SPEC_DIFFERENCE 1 → 3). CCFD UNCLASSIFIED 1 → 0 | Repo books TP1 at the level (`outcome.py:45,53`) and refuses data past its end (`outcome.py:56`). These become SPEC_DIFFERENCE, never AGREE | KEPT |
| S7 | Compare only engine-valid signals. ASW excludes target-order-blocked tickets; CCFD keeps `ENTRY_VALID` only | ASW compared 274 → 55 (98.2% → 98.2%). CCFD 8 → 7 | The blocked tickets are TICKET_BLOCKED, not trades: `FAIL_CLOSED_IF_TP1_BEYOND_TP2` (`strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml:181`, `src/v1_tickets/target_geometry.py:34-48`, `src/reporting/asw_lane.py:141-144`). The CCFD one excluded is BTCUSD LONG 2026-09-13 `NO_TRADE_TARGET_GEOMETRY` (`src/crypto_cfd_contract/rules.py:78-80`). Agreement is unchanged, so the filter is not agreement-driven. The oracle is still run on all 219 as supplementary (215 AGREE, 4 SPEC_DIFFERENCE, 0 defect) | KEPT |
| S8 | C25 follow-up: restore literal L3; add guard reasons, uniqueness, supplementary oracle on blocked tickets, CCFD exclusion list | ASW fuzz FAIL 0 → 172. CCFD FAIL 0 | Reverts S3/S4 per the owner rule | — |
| S9 | Test definition per the owner/PM ruling 2026-10-14 (supersedes the ambiguous "last bar perturbed" wording). L3 = (a) truncation + (b) perturbation strictly after the signal close incl. the forming bar. (c) Signal-bar perturbation becomes an L4 contract-formula check, branch-aware | L3 FAIL 172 → 0 (ASW), 0 → 0 (CCFD). L4 0 FAIL / 274 | Justified by the owner ruling (test definition), not by agreement. A first branch-blind L4 check gave 116 FAIL. All of them had switched to the RANGE_REJECTION branch, whose own formulas (yaml:147-150) the engine matches. The check now applies the formulas of the branch the engine took (`step9_owner_l3_ruling.diff`) | KEPT |

## S8 state (superseded by S9)

The owner L3 definition is applied: truncate after the signal close, then perturb the last bar (the signal bar,
range shrunk 25%), and require the signal to be identical or absent.

- **ASW v1.1.3: 172 of 274 FAIL.** 26 of these are among the 55 engine-valid signals.
  - The other outcomes are 89 ABSENT and 13 IDENTICAL.
  - Every FAIL keeps direction and signal time. Only levels the contract derives from the perturbed candle
    move: stop 172, targets 171, entry 103.
  - Those rules are stop = sweep-candle wick extreme (`ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml:170`), entry = body edge
    (`:158/:163`), and targets from risk (`:181`).
  - Truncation (0) and future perturbation (0) never changed a signal. There is no look-ahead.
  - Classification: SPEC_DIFFERENCE between the fuzz definition and the contract's level rules, not an
    ENGINE_DEFECT. The owner must rule whether this counts as repaint (proposal P1 in the status doc).
- **CCFD 1.0.0: 0 of 7 FAIL** (5 IDENTICAL, 2 ABSENT).
