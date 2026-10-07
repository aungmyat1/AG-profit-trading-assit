# T4 — Swing/BOS/Sweep Differential Check vs `smartmoneyconcepts`

## Scope note (read first)

The T2-frozen primary candidate (`CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1`) is a pure
Donchian/channel-breakout strategy with **no swing/BOS/sweep concept at all**. T4 as
literally written ("differential check of swing/BOS/sweep detection... on the same bars")
does not apply to it. The closest actual swing/BOS/sweep-style code in this repository is
`research_external/candidate_factory/internal_reference/mtf_control_shift/structure.py`
(`confirmed_swings`, used by `ST_MTF_CONTROL_SHIFT_V1`/PR #34/INT_C002 — a different,
already-DEV-replayed candidate with a `HOLD_SAMPLE_REQUIRED` verdict, parked). This
report differentially tests **that** code against `smartmoneyconcepts.smc.
swing_highs_lows` as the best-available, honest fulfillment of T4's intent given the scope
mismatch. Also discovered and recorded (not acted on): PR #30 (`ST_CRYPTO_CFD_SWEEP_
RETEST_V1`, open, unmerged) already defines a dedicated swing/BOS/sweep-based BTCUSD/
ETHUSD CFD contract — a better future differential target if the owner wants T4 re-scoped.

`smartmoneyconcepts` (PyPI, MIT) is used ONLY as a one-off differential oracle for this
report. It is not added as a project dependency and is not imported by any `src/` or
production `research_external/candidate_factory` code.

## Method

A deterministic synthetic 120-bar OHLC series (seed=42, trend legs + pullbacks + periodic
exact-tie highs; see `run_swing_differential.py::make_synthetic_series`) was run through:
- our `confirmed_swings(candles, strength=2)`
- `smc.swing_highs_lows(df, swing_length=2)`

Every bar index was labelled HIGH / LOW / NEITHER by each implementation and compared.
Robustness: the same comparison was repeated with 5 additional seeds (1, 7, 99, 123,
2026) — identical structural result every time (see `robustness_check.json`).

## Result

```
n_bars = 120
agreement_rate = 98.33% (118/120 bars agree)
disagreements = 2 (both: SPEC_DIFF, 0 BUG, 0 UNEXPLAINED)
```

Both disagreements are at the series' first and last bar index. Classification:
**SPEC_DIFF — boundary-handling convention.** Our `confirmed_swings()` only evaluates
`range(strength, n-strength)` and structurally cannot label the first/last `strength`
bars (no left/right neighbors exist to compare against — this is a deliberate
no-fabrication design, not an oversight). `smc.swing_highs_lows()` explicitly
force-flips the label of the first and last detected swing position (hardcoded in its
source: `if swing_highs_lows[positions[0]] == 1: swing_highs_lows[0] = -1`, etc.) as a
documented edge-case convention of its own. Both behaviors are internally consistent
with their own stated designs; neither is a defect.

Two further SPEC_DIFF classes were anticipated and instrumented for (alternation
enforcement — smc enforces strict H/L alternation via a post-processing pass our code
does not have; tie-breaking — smc's equality-to-rolling-extreme test vs our strict/
non-strict split comparison) but **did not occur in any of the 6 seeds tested** — the
interior of the series agreed completely in every run.

## Classification table

| Disagreement | Bar index | Classification | Reason |
|---|---|---|---|
| 1 | 0 (first bar) | SPEC_DIFF | Boundary-handling convention (see above) |
| 2 | 119 (last bar) | SPEC_DIFF | Boundary-handling convention (see above) |

**No BUG found.** No disagreement was left `UNEXPLAINED`.

## Gate result

```
T4 = PASS
```
100% of observed disagreements are explained by documented, cross-checked algorithmic
differences; none indicate a defect in our `confirmed_swings()` implementation. This
result applies to the swing-detection code it was run against (`mtf_control_shift/
structure.py`), not to the T2 primary candidate, which has no equivalent code to test
(recorded as the scope note above, not glossed over).

## Evidence paths

- `research_external/candidate_factory/crypto_logic_verify_r1/differential/run_swing_differential.py`
- `research_external/candidate_factory/crypto_logic_verify_r1/differential/swing_differential_report.json`
- `research_external/candidate_factory/crypto_logic_verify_r1/differential/synthetic_bars_used.csv`
- `research_external/candidate_factory/crypto_logic_verify_r1/differential/robustness_check.json`
