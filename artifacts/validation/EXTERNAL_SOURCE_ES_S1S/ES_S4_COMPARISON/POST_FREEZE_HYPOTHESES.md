# ES-S4 Post-Freeze Hypotheses (recorded only — no rule change, no remediation)

## Preregistered-uncertainty check (P7)

None of the 6 reference events that mapped to a blind occurrence (PROBABLE or AMBIGUOUS) mapped to an occurrence carrying any `SOURCE_RULE_DEPENDENT_UNRESOLVED` flag — every mapped occurrence's `uncertainty_reasons` was empty. This means the post-freeze evidence gathered here provides **no information** about `NEW_ENTRY_CUTOFF` or `TIGHT_RANGE_FILTER_THRESHOLD` specifically — the low correspondence is not explained by those preregistered gaps at all, so no hypothesis is recorded for either. This is reported as an absence of signal, not silently skipped.

## POST_FREEZE_REMEDIATION_HYPOTHESIS_1 — timestamp offset / Asian-session definition

Converting the reference table's broker-local times to UTC (using the +3h INFERRED-tier offset from ES-S0/ES-S1S) places several reference events (REF_03, REF_07, REF_10, REF_13) **before 07:00 UTC** — i.e., structurally inside this candidate's own Asian reference-range window, not the post-session trade window. A signal generated during range construction is impossible in this implementation by design. This suggests either (a) the +3h offset does not correctly represent the video's actual Eightcap broker convention, or (b) the source video's presenter used a different or looser Asian-session boundary than this candidate's frozen 00:00–07:00 UTC spec. Not resolved, not acted upon.

## POST_FREEZE_REMEDIATION_HYPOTHESIS_2 — entry price semantic

For the 6 mapped events, entry-price differences range from 0.1 to 32.4 pips and TP differences up to ~59 pips — too large to be measurement noise. This is consistent with ES-S1S/ES-S1R's own already-flagged `AMBIGUOUS` finding on entry semantic (sweep-candle-close vs. boundary-limit vs. rejection-wick-confirmed entry each appeared as "the" rule at different points in the source chat). The reference table's own entry prices may reflect a later retest/continuation level rather than this candidate's strict first-qualifying-candle close. Not resolved, not acted upon.

## POST_FREEZE_REMEDIATION_HYPOTHESIS_3 — discretionary filtering vs. mechanical generation

60 of 66 blind occurrences have no reference counterpart at all, and 12 of 18 reference events have no blind counterpart at all. The source chat itself repeatedly describes the presenter applying visual/discretionary judgment (HTF context, "which setups looked clean") that a strict mechanical implementation does not replicate. This is directionally consistent with the already-preregistered `MAX_ENTRIES_PER_SESSION`/`MAX_ENTRIES_PER_DAY` and `TIGHT_RANGE_FILTER_THRESHOLD` gaps, but this evidence does not pin any specific numeric value for either — it only reinforces that some filtering mechanism is plausibly missing, which was already known before this comparison. Not resolved, not acted upon.

**No source rule, cutoff, threshold, or geometry was changed in response to any of the above.**
