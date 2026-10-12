---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: null
---
# ST_LARGE_SMC_V1@1.1.0 — C11 target recomputed after OPPORTUNITY: Decision Packet

Status: **UNSIGNED — OWNER DECISION REQUIRED**. Date: 2026-10-12. Mission: AGP-LSMC-ALERT-AUDIT item 3.

This is a decision packet, not a decision. No logic is changed. `ST_LARGE_SMC_V1@1.1.0` is the
registered SHADOW_ALERTS_ONLY watch contract; per the frozen-version rule it is not edited in place.

## Finding

- Contract: `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` `rules.targets: C11` ("structural-fallback
  semantics on causal M5 swings"). The 1.1.0 file itself says nothing about when the target is selected.
  C11 as owner-resolved (`docs/specs/LARGE_SMC_V1_SPEC.md` §16, `strategies/ST_LARGE_SMC_V1.yaml`
  `target_model.mode: STATIC`) is **selected once at qualification, no dynamic retargeting**.
- Engine: `src/large_smc_watch/watch.py:243`
  `target = c11_causal_target(m5c, o.direction, o.entry_reference, len(m5c) - 1)`. The target is
  re-evaluated on every poll against the **latest** closed M5 bar (`upto_index = len(m5c) - 1`).
  A swing swept after the CHoCH is dropped, and swings confirmed after the CHoCH become eligible.
  The stop is frozen at the CHoCH bar (`m5c[: o.choch_index + 1]`, watch.py:237). The target is not.
- Effect: under an unchanged reference (`opp_id = poi|sweep|choch`) the `target_c11` value can
  drift between polls. The tracker re-emits OPPORTUNITY with the drifted value when it re-enters
  (e.g. after STALE→SUSPENDED). Delivery dedupe (`confirmation_key` excludes the target) then
  suppresses the resend, so the Telegram text keeps the first target while the journal/archive
  records the later one. A drifted value is never re-alerted.
- Candidate `strategies/ST_LARGE_SMC_V1_1_1_1.yaml` already pins `retarget_after_selection: false`.
  That candidate is not current authority.
- Owner-provided 2026-10-09 Telegram alert fixtures are not committed to the repository, so the
  drift is shown from code, not from those alerts.

## Options (none selected)

| # | Option | Effect | Version impact |
|---|---|---|---|
| A | Freeze at qualification: compute C11 with `upto_index = o.choch_index` in a new candidate (e.g. 1.1.2) | matches C11 `mode: STATIC`; target is fixed per reference | new candidate version; validation + promotion required |
| B | Keep 1.1.0 as is and document "target is live-recomputed" as a 1.1.0 implementation choice | no code change; journal and Telegram can disagree for one ref | records divergence vs C11 STATIC in the drift table |
| C | Adopt 1.1.1's `retarget_after_selection: false` by promoting 1.1.1 | resolves via the existing candidate | full 1.1.1 validation/promotion path |

Recommendation (non-binding): A or C. Both keep the target C11-consistent, and B leaves a
contract/engine divergence open. Until a decision, 1.1.0 behaviour stays unchanged. Its alerts
remain informational (`economic_status=NOT_EVALUATED`), and no R:R gate is authorized.

Required owner input: choose A/B/C; if A, confirm the candidate version number.
