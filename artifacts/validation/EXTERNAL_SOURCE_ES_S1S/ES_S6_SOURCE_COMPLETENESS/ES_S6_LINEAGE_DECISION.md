# ES-S6 Lineage Decision (P2, P9–P12)

## P2 — Implementation-scope classification

| Contract | Scope | Status |
|---|---|---|
| **A. Detection** (does an M15 structural Sweep exist) | Asian range, strict penetration, close-back-inside, direction | Fully `PRIMARY_SOURCE_DIRECT`-supported and correctly implemented in v0.1.0 |
| **B. Eligibility** (does a detected Sweep become an actual trade) | Range filters, multiplicity control, context/discretionary filtering, entry cutoff | Overwhelmingly `SOURCE_MISSING`/`SOURCE_AMBIGUOUS` (see `ES_S6_ELIGIBILITY_INVENTORY.md`) — not implemented in v0.1.0, and not implementable from available evidence |
| **C. Management** (what happens after entry) | Stop, target, partial/BE, M15 ambiguity governance | Fully `PRIMARY_SOURCE_DIRECT`-supported and correctly implemented, with two narrow, explicitly-flagged gaps (BE cost adjustment, end-of-session disposition) |

**Classification: `DETERMINISTIC_SWEEP_CORE_WITH_INCOMPLETE_ELIGIBILITY`.** This is not inferred from implementation completeness or passing tests (v0.1.0's 20 tests and 114 regression tests passing says nothing about source completeness) — it is inferred directly from the source-authority matrix: contracts A and C have direct primary support, contract B does not.

## H-ELIG-01 — Multiplicity control: **not adopted, `SOURCE_AMBIGUOUS`/`NO_SOURCE_SUPPORT`**

No specific rule (one-and-done, max-one-per-direction, max-one-per-session) has direct source backing; every numeric variant found in the chat log was introduced or changed to chase benchmark trade counts. The frozen 66-occurrence decomposition shows a real, large multiplicity gap worth noting descriptively (max 8 occurrences on a single day, 11 of 15 available days with ≥4 occurrences, 46 same-direction repeat occurrences) — but this descriptive fact does not itself supply a rule, and none is adopted.

## H-ELIG-02 — HTF/context alignment: **rejected, `NOT_APPLICABLE`**

Directly contradicted by primary source evidence (M15-only execution/analysis, no H1 usage). This is not an open question — v0.1.0's M15-native contract is preserved and correctly excludes H1/H4/D1 from eligibility.

## H-ELIG-03 — Rejection quality (wick/body ratio): **not adopted, `POST_BENCHMARK_HYPOTHESIS_ONLY`**

The only quantitative wick-ratio rule found (35%) was constructed specifically to let one already-known benchmark trade pass a momentum filter that had wrongly rejected it. No quantitative threshold is source-authoritative; existence-only qualitative "liquidity rejection" language is present but does not amount to a testable rule.

## P9 — Source eligibility completeness: **`INSUFFICIENT`**

Per the mission's own definition ("use `INSUFFICIENT` when critical trade-selection behavior appears to exist but available evidence cannot reproduce it deterministically"): the presenter's own narrative directly confirms that *some* selection process governs which of the mechanically-valid sweeps become actual trades (discretionary judgment, stopping after losses, "clean setup" filtering) — this is not absent, it is *evidenced but non-quantifiable*. That is exactly the `INSUFFICIENT` case, not `PARTIAL` (which would require the missing rules to be non-critical — they are not: they directly govern the 66-vs-18 gap, the central question of this mission).

## P10 — v0.2 source justification: **`V0_2_SOURCE_JUSTIFIED = false`**

No independent source-authoritative evidence exists for any of the eligibility rules a v0.2 would need (multiplicity control, range/wick thresholds, entry cutoff). Every candidate value on record is `POST_BENCHMARK_HYPOTHESIS`, explicitly disqualified by this mission's own P10 criteria ("better correspondence... reducing 66 toward 18... plausible trading explanation" are all explicitly insufficient). **What would resolve this:** the actual original video/transcript (never available to this agent — only a secondhand chat log about attempts to backtest it), or an explicit, quantitative, presenter-attributed statement of the selection rule, or direct owner clarification.

## P11 — Research-fork viability: **`SOURCE_INSPIRED_RESEARCH_LINEAGE_VIABLE = true`**

The Detection and Management contracts are fully specified, deterministic, and self-contained: explicit M15 Sweep detection, explicit entry geometry, explicit `0.25×A` stop, explicit 5R target, explicit 75/25 partial+BE contract, explicit M15 intrabar-ambiguity governance (never assumes order). None of this depends on the unresolved eligibility questions to *run* — it can generate a (high-frequency, unfiltered) occurrence stream on any fresh M15 dataset and be evaluated on its own terms as an independent research hypothesis, explicitly *not* claiming to replicate the presenter's curated trade selection. No economic edge is claimed here — viability is about specification completeness for research purposes, not profitability.

## P12 — Path classification

`SOURCE_ELIGIBILITY_COMPLETENESS = INSUFFICIENT` **AND** `SOURCE_INSPIRED_RESEARCH_LINEAGE_VIABLE = true` →

**`NEXT_LINEAGE_PATH = PATH_B_RESEARCH_FORK`**

This is a governance/process recommendation, not a profitability claim, and nothing was implemented in this mission.
