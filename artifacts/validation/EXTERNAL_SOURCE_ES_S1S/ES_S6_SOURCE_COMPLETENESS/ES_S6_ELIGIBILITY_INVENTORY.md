# ES-S6 Eligibility Rule Inventory (P4)

| # | Rule | Classification |
|---|---|---|
| 1 | Directional/context bias (HTF alignment) | `POST_BENCHMARK_HYPOTHESIS_ONLY` (rejected — see H-ELIG-02) |
| 2 | Asian-range qualification (does a range exist at all) | `SOURCE_VERIFIED_QUALITATIVE` — the range is always constructed from the fixed 00:00–07:00 UTC window; no separate "does it qualify" gate beyond range existence itself is source-verified |
| 3 | Tight-range rejection | `SOURCE_AMBIGUOUS` — existence supported (`POST_BENCHMARK_REFERENCE` tier, Setup #10), no threshold |
| 4 | Excessive-range rejection | `SOURCE_MISSING` — never mentioned in either direction |
| 5 | Volatility requirements (separate from range width) | `SOURCE_MISSING` |
| 6 | Rejection-wick requirements (existence) | `SOURCE_AMBIGUOUS` — plausible given "liquidity rejection" language used loosely, but no explicit standalone rule stated independent of the already-verified close-back-inside predicate |
| 7 | Wick/body ratio (quantitative) | `POST_BENCHMARK_HYPOTHESIS_ONLY` — the 35% figure is a benchmark-fit artifact (H-ELIG-03) |
| 8 | HTF context (H1/H4/D1) as eligibility | `NOT_APPLICABLE` — directly contradicted by primary source evidence (M15-only); not merely unresolved, actively excluded |
| 9 | First-sweep-only per day | `SOURCE_AMBIGUOUS` — no explicit statement; existence of *some* selection process is plausible (discretionary filtering), specific rule is not |
| 10 | Max entries/session | `SOURCE_AMBIGUOUS` — values found (1/3) are all `POST_BENCHMARK_HYPOTHESIS` |
| 11 | Max entries/day | `SOURCE_AMBIGUOUS` — same as above (session ≈ day here) |
| 12 | Repeated same-direction sweeps | `SOURCE_MISSING` |
| 13 | Opposite-direction sweeps (sequential) | `SOURCE_MISSING` |
| 14 | Setup priority (S1/S2/S3-equivalent) | `NOT_APPLICABLE` — Sweep-only component, Range/Trend quarantined |
| 15 | London/NY eligibility beyond entry-cutoff | `SOURCE_MISSING` |
| 16 | New-entry cutoff | `SOURCE_AMBIGUOUS` — unchanged from ES-S1R/ES-S5 |
| 17 | News restrictions | `SOURCE_MISSING` |
| 18 | Weekday restrictions | `SOURCE_MISSING` |
| 19 | Previous-day structure | `SOURCE_MISSING` |
| 20 | Discretionary chart context (qualitative) | `SOURCE_VERIFIED_QUALITATIVE` — the *existence* of discretionary judgment in the presenter's own process is directly and repeatedly stated; no quantitative rule is extractable |
| 21 | Invalidation after prior setup that day | `SOURCE_MISSING` |

No quantitative threshold was invented for any `SOURCE_MISSING` or `SOURCE_AMBIGUOUS` row above.
