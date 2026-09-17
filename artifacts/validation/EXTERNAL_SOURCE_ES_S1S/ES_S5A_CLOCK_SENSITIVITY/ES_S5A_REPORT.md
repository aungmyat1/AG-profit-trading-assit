# ES-S5A — Post-Benchmark Reference Clock Comparison Sensitivity

Reuses the frozen ES-S3 66-occurrence population unchanged, and ES-S4's exact matching rules/tolerances (date → direction → nearest sweep timestamp; `EXACT_EVENT_MATCH` ≤30min & <2 pips entry; `PROBABLE_EVENT_MATCH` ≤90min; else `AMBIGUOUS_EVENT_MAPPING`). The **only** variable changed is the reference-table timestamp interpretation:

- **M0** = ES-S4's original assumption: reference `"@ HH:MM"` is broker-local, converted to UTC via `−3h`.
- **M1** = ES-S5's H1 hypothesis: reference `"@ HH:MM"` is already UTC, no conversion.

Neither v0.1.0, ES-S3, ES-S4, nor ES-S5 was modified. The strategy was not rerun.

## Aggregate comparison

| Metric | M0 (−3h) | M1 (as-is UTC) | Delta |
|---|---|---|---|
| Exact mappings | 0 | 0 | 0 |
| Probable mappings | 2 | 2 | 0 |
| Ambiguous mappings | 4 | 4 | 0 |
| Reference-only events | 12 | 12 | 0 |
| **Events falling before 07:00 UTC (structurally impossible)** | **4** | **0** | **−4 (fully resolved)** |
| Mean time delta (mapped events) | 185.0 min | 135.0 min | −50.0 min (improved) |
| Median time delta (mapped events) | 180.0 min | 195.0 min | +15.0 min (worsened) |
| Mean entry diff (mapped events) | 11.33 pips | 13.48 pips | +2.15 pips (worsened) |

## Per-event detail (see `per_event_delta_table.json` for full machine-readable table)

- **Clearly improved under M1:** REF_01 (time delta 300→120min), REF_07 (150→15min, upgrades `AMBIGUOUS`→`PROBABLE`), REF_08 (375→195min, stays `AMBIGUOUS`), REF_16 (180→15min, upgrades `AMBIGUOUS`→`PROBABLE`).
- **Clearly worsened under M1:** REF_05 (time delta 30→210min, **downgrades** `PROBABLE`→`AMBIGUOUS`), REF_09 (75→255min, **downgrades** `PROBABLE`→`AMBIGUOUS`).
- **Unaffected:** the 12 `REFERENCE_ONLY_NO_BLIND_MATCH` events remain exactly the same under both models — no reference-only event became mappable, and no mapped event became unmappable, under the offset change alone.
- The overall exact/probable/ambiguous *counts* are identical (0/2/4) — the offset change reshuffles *which* events fall into which bucket without changing the total.

## Structural finding (the one clean, offset-independent-of-tolerance result)

M1 fully and cleanly resolves the earlier structural impossibility: under M0, 4 reference events (REF_03, REF_07, REF_10, REF_13) land before 07:00 UTC — inside this candidate's own Asian reference-range window, where a "post-Asian sweep" cannot exist by construction. Under M1, all 18 events land at or after 07:00 UTC. This is not a tolerance-threshold artifact; it is a binary structural fact (either an event's normalized time is before or after the fixed 07:00 UTC boundary), and it resolves unambiguously in M1's favor.

## P8 reassessment — earliest divergence under M1

For the 4 previously-impossible events, `TIME` is no longer the earliest-possible divergence point under M1 — they can now, in principle, be compared at the `REFERENCE_RANGE`/`ENTRY` stage. REF_07 in particular now maps at only a 15-minute delta (`PROBABLE`), suggesting its earliest real divergence may lie further downstream (entry price still differs by 9.7 pips under M1, up from 2.2 under M0 — so while *time* alignment improved, *entry-price* alignment for this specific event got worse, an unresolved tension not explained by this sensitivity test alone). For the 14 events already after 07:00 UTC under both models, TIME remains a live, unresolved contributor for most — the mixed mean/median result means no confident claim that M1 systematically improves downstream alignment across the board.

## `REFERENCE_CLOCK_HYPOTHESIS_STATUS = PARTIALLY_SUPPORTED_BY_SENSITIVITY`

Justification: M1 delivers one unambiguous, tolerance-independent improvement (full resolution of the pre-07:00-UTC structural impossibility) — a real, meaningful signal. However, on every other metric the result is mixed: two previously-`PROBABLE` events downgrade to `AMBIGUOUS` under M1, median time delta and mean entry-price difference both worsen, and total mapped-event counts do not change at all. This does not rise to `SUPPORTED_BY_SENSITIVITY` (which would require broad, consistent improvement), nor is it `NOT_SUPPORTED_BY_SENSITIVITY` (the structural resolution is a genuine, non-trivial point in M1's favor), nor is it `INDETERMINATE` (concrete, specific evidence exists on both sides). **M1 is not claimed as the confirmed clock** — this remains an open, partially-informative sensitivity result requiring further, non-benchmark-count-driven evidence (e.g. actual confirmation of the video's own timestamp convention) to resolve.
