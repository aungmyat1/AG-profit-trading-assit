# ES-R1 Hypothesis Registry

`BASELINE_CORE_FROZEN` — not optimization dimensions: M15-only architecture; Asian range 00:00–07:00 UTC; strict penetration; close-back-inside; market entry at qualifying M15 close; `R = 0.25×A`; `TP2 = 5R`; 75% opposite-boundary partial; BE after confirmed partial; 25% runner; explicit `INTRABAR_ORDER_UNRESOLVED`. None of these may be touched by any candidate in this or any hypothesis below.

## R-H01 — Multiplicity control (primary)

**Question:** does deterministic control of repeated structural Sweep occurrences improve post-friction economics?

| Candidate | Definition |
|---|---|
| `H01_C0` (baseline) | `ALL_STRUCTURAL_OCCURRENCES` — every occurrence `generate_occurrences()` produces, unfiltered |
| `H01_C1` | `FIRST_OCCURRENCE_PER_SESSION` — first qualifying occurrence per calendar day's post-Asian window |
| `H01_C2` | `FIRST_OCCURRENCE_PER_DIRECTION_PER_SESSION` — first LONG and first SHORT occurrence per day, independently |
| `H01_C3` | `FIRST_OCCURRENCE_PER_DAY` — same as C1 (session == day in this baseline, since there is one Asian reference window per calendar day); retained as a distinct named candidate per the mission's own list, not merged, in case a future session-splitting hypothesis changes the definition of "session" |

No numeric parameter is optimized for H01 — these are 4 fixed, named policies, none chosen for proximity to any historical count.

## R-H02 — Asian range regime (primary)

**Question:** does excluding objectively abnormal Asian ranges (relative to recent volatility, not a raw pip threshold) improve post-friction economics?

**Reused convention (not reinvented):** Wilder's ATR, period 14, computed on M15 candles — `src/session_sweep_continuation/swing_structure.py::compute_atr` (existing, already-governed repo utility; fail-closed if fewer than 15 candles available).

**Research variable:** `ASIAN_RANGE_RATIO = A / ATR_REFERENCE`, where `A = AsianHigh − AsianLow` (this strategy's own existing range) and `ATR_REFERENCE` = Wilder ATR(14) computed over the M15 candles strictly closed before the Asian session's own 00:00 UTC start on that day (no lookahead into the session being measured).

| Candidate | Definition |
|---|---|
| `H02_C0` (baseline) | No filter |
| `H02_C1` | `ASIAN_RANGE_RATIO >= 0.5` (exclude only ranges narrower than half of recent typical volatility) |
| `H02_C2` | `ASIAN_RANGE_RATIO >= 1.0` |
| `H02_C3` | `ASIAN_RANGE_RATIO <= 3.0` (exclude only ranges wider than 3x recent typical volatility) |
| `H02_C4` | `0.5 <= ASIAN_RANGE_RATIO <= 3.0` (both-sided band) |

5 configurations total (including baseline), within the `<=5` ceiling. All thresholds are round, generic multiples (0.5×, 1×, 3×) chosen without inspecting any Oct-2022 or D:\ economic result — **`efficiency_ratio <= 0.35` is explicitly not inherited** as baseline authority.

## R-H03 — Rejection quality (primary)

**Question:** does objective rejection quality improve post-friction economics?

**New deterministic statistic (independently defined, not D:\'s 0.35 wick/body rule):**
```
For a SHORT (upper sweep) on qualifying candle c:
  rejection_ratio = (c.high - c.close) / (c.high - c.low)
For a LONG (lower sweep) on qualifying candle c:
  rejection_ratio = (c.close - c.low) / (c.high - c.low)
```
Symmetric long/short, deterministic, computable entirely from the qualifying candle's own OHLC at signal close, no future information.

| Candidate | Definition |
|---|---|
| `H03_C0` (baseline) | No filter |
| `H03_C1` | `rejection_ratio >= 0.2` |
| `H03_C2` | `rejection_ratio >= 0.4` |
| `H03_C3` | `rejection_ratio >= 0.6` |
| `H03_C4` | `rejection_ratio >= 0.8` |

5 configurations total, an evenly-spaced generic grid across [0,1] in fifths — deliberately not `0.35` (D:\'s value), and not chosen from any economic inspection.

## Deferred / diagnostic-only hypotheses

- **R-H04 (Session effect):** `DIAGNOSTIC_STRATIFICATION_ONLY`. ES-R2/ES-R3 may *report* London vs. New York economics as a breakdown, but session membership must not veto any trade in the first search.
- **R-H05 (Open-inside requirement):** `DEFERRED_INDEPENDENT_HYPOTHESIS`. Not included in this search, to avoid mixing too many eligibility mechanisms into the first candidate family.

## Total candidate budget

`H01: 4` + `H02: 5` + `H03: 5` = **14 total first-pass evaluations**, at the `<=14` ceiling. Baseline (`H01_C0`/`H02_C0`/`H03_C0`) is the same single unfiltered population and is cached/reused deterministically, not recomputed three times as independent evidence.
