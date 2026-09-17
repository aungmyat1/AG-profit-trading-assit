# ES-S5 Post-Benchmark Source Reconstruction

`v0.1.0 = FROZEN_LOW_CORRESPONDENCE_INTERPRETATION`. Not modified. 18-event table permanently reclassified `SOURCE_REPLICATION_REFERENCE_CONSUMED` — never again eligible as blind/OOS/holdout/economic-validation evidence.

## P3 — Time-authority investigation

**Dataset clock (unchanged, not questioned):** `D:\EURUSD_M15_202210030000_202210212345.csv` raw broker time → UTC via `broker_time − 3h`, derived independently from weekend-reopen-gap evidence (`src/mt5/broker_time.py` methodology), zero-residual on two independent weekends (ES-R2A). No DST transition inside the Oct 3–21 window. Not altered here.

**Benchmark/presenter clock — re-examined:** ES-S4's comparison applied the *same* `−3h` conversion to the 18-event table's `"@ HH:MM"` timestamps, treating them as broker-local. Re-reading the source material's own primary specification text (tier `PRIMARY_FLOWCHART`/`SIGNED_SOURCE_SPECIFICATION`, already established `VERIFIED`/`STRONGLY_SUPPORTED` in ES-S1R): the Asian session and active-window boundaries are stated explicitly and repeatedly **in UTC** ("00:00–07:00 UTC", "07:00–22:00 UTC"/"07:00–16:00 UTC"). Nothing in the source material states the *benchmark table specifically* uses a different, broker-local convention — that was an assumption ES-S4 imported from a separate discussion (about which MT5 *data source* could run the backtest), not from anything said about the table's own timestamp format.

Applying **no offset** (treating the table's times as already UTC) is at least as well-supported by direct source text as the `−3h` conversion ES-S4 used, and is arguably better supported since it requires no extra unstated assumption. Under the zero-offset reading, several previously "before-Asian-close" reference events (REF_03 @ 08:00, REF_07 @ 09:00, REF_10 @ 08:30, REF_13 @ 07:30) fall cleanly **after** 07:00 UTC — resolving the structural impossibility ES-S4 found (a "post-Asian sweep" landing inside the Asian window itself).

**`TIME_AUTHORITY_ROOT_CAUSE = BENCHMARK_TIME_INTERPRETATION_ERROR_SUPPORTED`** — the error is attributed to ES-S4's own comparison methodology (an unjustified extra conversion), not to the frozen dataset's UTC transformation (which remains untouched, per this mission's explicit instruction) and not to v0.1.0's implementation.

This conclusion is **not** selected because it produces more matches (that count was not computed here) — it is selected because it removes an assumption unsupported by direct source text, per P3's own instruction not to pick the mapping with the highest match count.

## P4 — Entry-semantic reconstruction

| Variant | Description | Classification |
|---|---|---|
| A | Strict penetration + close-back-inside → market entry at qualifying candle's own close | `PRIMARY_SOURCE_SUPPORTED` — identical, independent restatement across multiple "official flowchart" turns; this is what v0.1.0 implements |
| B | Boundary/retest limit entry, no close confirmation | `POST_BENCHMARK_HYPOTHESIS` (unchanged from ES-S1R) — introduced explicitly to hit one specific benchmark price, in the same turn that reports the resulting R-improvement |
| C | Sweep → rejection/confirmation → later entry | `POST_BENCHMARK_HYPOTHESIS` (unchanged) — introduced explicitly "to skip the unconfirmed low-side breakdowns," after seeing Oct 3 results |
| D | (none found) | — |

**Finding:** no entry-semantic variant beyond A is eligible for use (B and C remain contaminated, per the firewall). The ES-S4 entry-price mismatches are therefore hypothesized to be a **downstream consequence of the time-authority question (P3)** — a different candle is identified as "the qualifying sweep candle" under the wrong clock assumption, not a wrong entry rule. This is not verified; it is `ES_S5_H2` below.

## P5 — Opportunity-set reconstruction (66 blind vs. 18 reference)

| Candidate filter | Classification | Basis |
|---|---|---|
| Range-session qualification concept itself | `SOURCE_AMBIGUOUS` | Already found internally contradictory in ES-S0/ES-S1S ("almost always YES" vs. a competing Range=NO/Trend framing) |
| Tight-range rejection (existence) | reclassified here as **`POST_BENCHMARK`**, not source-derived | Correction: this finding originates from the sealed 18-event table's own Setup #10 "Filtered" row (Population B), not from the flowchart/presenter-statement tiers. Earlier missions (S0/S1R) cited it without being fully explicit that its evidentiary root is the benchmark table itself. Corrected here for intellectual honesty — still existence-only, no threshold. |
| Volatility requirement (separate from range) | `UNSUPPORTED` | No distinct statement found |
| HTF/directional context filter | `POST_BENCHMARK_HYPOTHESIS_ONLY` | The H1/4H filter idea was invented and retracted purely via outcome-chasing (ES-S0); not source-derived |
| Max entries per session/day | `SOURCE_AMBIGUOUS` | Unchanged from ES-S1R — no non-outcome-derived numeric value exists |
| Repeated same-side / opposite-side sweep handling | `SOURCE_AMBIGUOUS` / `UNSUPPORTED` | Unchanged |
| Setup priority among simultaneous candidates | `UNSUPPORTED` | No source statement found |
| **Discretionary/contextual filtering (qualitative)** | **`SOURCE_SUPPORTED`** (existence only, no numeric rule) | Multiple `PRIMARY_PRESENTER_STATEMENT`-tier remarks describe the presenter's own process as using discretionary/HTF judgment a mechanical implementation does not replicate (e.g., stopping after a loss, subjective "clean setup" judgment) — genuine source evidence, but non-quantifiable |
| Entry cutoff | `SOURCE_AMBIGUOUS` | Unchanged from ES-S1R |

No threshold was fit to reduce 66 toward 18; none of the above were selected or tuned by match count.

## P6 — Geometry reconstruction

Given P3/P4's findings, SL/TP numeric differences are treated as **downstream** of the (candidate) time-authority error and, secondarily, of unresolved feed-identity questions (P7) — not evidence against the verified `SL = 0.25×A` formula itself, which is not reconsidered here per this mission's explicit instruction ("do not abandon... unless primary source evidence requires reconsideration" — no such evidence was found). A full numeric decomposition (`entry difference + range difference + geometry difference`) was not completed in this pass because it requires re-running the comparison under the P3 hypothesis, which is remediation and out of scope for ES-S5 (diagnostic only, no rule change, no rerun).

## P7 — Feed comparison

Re-checking the actual ES-S4 mapping ledger: **no reference event was tagged `DATA_FEED_DIFFERENCE`** in the frozen comparison (all 18 reference dates fall on trading days with an available Asian range in the frozen dataset; none coincide with the two real weekend gaps). This category is therefore **not applicable** to any of the 18 events — corrected from an imprecise mention in the prior ES-S4 summary text. No Eightcap raw data was ever available for direct feed-level comparison, so for the 6 mapped events' residual price differences: `FEED_MAY_CONTRIBUTE` (cannot be ruled in or out — no independent Eightcap OHLC exists to compare against), never `FEED_EXPLAINS_EVENT` (no positive evidence) and never fully `FEED_NOT_SUPPORTED_AS_CAUSE` (absence of evidence is not evidence of absence here).

## P8 — Earliest-divergence distribution

For all 18 reference events, the earliest identified divergence point is **`TIME`** — the clock/session-timestamp interpretation question (P3) precedes and contaminates every downstream comparison (reference range, entry, stop, target). None of the 18 events could be confidently attributed a *later*-stage earliest divergence (e.g., `SWEEP_DETECTION` or `ENTRY`) while the clock question remains open, because a wrong clock assumption can by itself explain why the "wrong" candle was compared in the first place. This is a deliberately conservative conclusion — it does not claim the geometry/entry logic is correct, only that it cannot yet be *blamed* ahead of the clock question.

## P9 — Bounded hypothesis registry (ranked upstream-first, not by benchmark-match improvement)

### ES_S5_H1 (highest priority)
- **OBSERVED_PROBLEM:** ES-S4's `−3h` broker-to-UTC conversion applied to the reference table's timestamps produces 4/18 events landing before 07:00 UTC (structurally impossible) and large (75–375 min) deltas for all 6 mapped events.
- **PROPOSED_SEMANTIC_CHANGE:** For future comparison methodology only — treat the reference table's timestamps as already UTC (no conversion), matching the primary specification's own explicit UTC framing. This is a *comparison-methodology* correction, not a change to v0.1.0, the dataset's UTC authority, or any strategy rule.
- **SOURCE_EVIDENCE:** Primary specification text states Asian/active-window boundaries in UTC directly, multiple independent restatements (`PRIMARY_FLOWCHART`/`SIGNED_SOURCE_SPECIFICATION` tier, ES-S1R).
- **POST_BENCHMARK_EVIDENCE:** Removing the offset resolves the 4 structurally-impossible pre-07:00 events and reduces (unquantified in this pass) several mapped events' time deltas.
- **EXPECTED_MECHANISM:** Corrects an unjustified assumption in the comparison step itself.
- **CONTAMINATION_STATUS:** POST_BENCHMARK
- **IMPLEMENTATION_ALLOWED:** false

### ES_S5_H2
- **OBSERVED_PROBLEM:** Entry/SL/TP numeric mismatches on the 6 mapped events.
- **PROPOSED_SEMANTIC_CHANGE:** None to the entry rule itself (Variant A remains the only `PRIMARY_SOURCE_SUPPORTED` semantic) — hypothesizes the mismatches are downstream of H1, not a wrong entry rule.
- **SOURCE_EVIDENCE:** Variant A's `PRIMARY_SOURCE_SUPPORTED` status, unchanged.
- **POST_BENCHMARK_EVIDENCE:** Entry-difference magnitude correlates with time-delta magnitude across the 6 mapped events.
- **EXPECTED_MECHANISM:** If H1 is adopted in a future comparison, entry/SL/TP differences should shrink if this hypothesis is correct — untested here.
- **CONTAMINATION_STATUS:** POST_BENCHMARK
- **IMPLEMENTATION_ALLOWED:** false

### ES_S5_H3 (lowest priority — most downstream / least specific)
- **OBSERVED_PROBLEM:** 66 blind occurrences vs. 18 reference events.
- **PROPOSED_SEMANTIC_CHANGE:** None numeric — flags that a qualitative discretionary/contextual filter of unknown exact mechanism plausibly exists beyond the mechanical Sweep rule.
- **SOURCE_EVIDENCE:** Multiple `PRIMARY_PRESENTER_STATEMENT`-tier remarks describing discretionary/HTF judgment in the source's own narrative.
- **POST_BENCHMARK_EVIDENCE:** The large blind-only count is consistent with (but does not by itself prove) this hypothesis.
- **EXPECTED_MECHANISM:** Unknown — no numeric rule is extractable from available material.
- **CONTAMINATION_STATUS:** POST_BENCHMARK
- **IMPLEMENTATION_ALLOWED:** false

## P10 — v0.2 readiness

**`V0_2_SPEC_PREREGISTRATION_READY = false`.** Even ES_S5_H1, the strongest and most upstream hypothesis, is a *comparison-methodology* correction, not a verified new rule for the strategy itself, and has not been used to re-run or re-score anything. ES_S5_H3 has no extractable numeric rule at all. What is still needed before any v0.2 preregistration: (1) the actual original video/transcript or explicit owner clarification of the benchmark table's own timestamp timezone convention (never available to this agent — only a secondhand chat log), and (2) any concrete, quantitative statement of the discretionary filter the presenter used, which no available material provides.
