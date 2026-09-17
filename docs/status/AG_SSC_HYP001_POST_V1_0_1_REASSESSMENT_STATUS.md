# AG SSC HYP_001 Post-v1.0.1 Reassessment — Status

Status: HISTORICAL_STATUS (dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`).
Generated 2026-09-17. Full analysis:
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_POST_V1_0_1_REASSESSMENT/HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT.md`

Mission: `SSC_HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT_V1` (governance reassessment
only — no execution, no new population, no holdout/OOS access, no parameter
optimization, no economic replay, no semantics or authority change).

## Headline

`CLASSIFICATION = REQUIRES_AMENDMENT`

The v1.0.1 `PARTIAL_TARGET_DIRECTION_INVERSION` fix sits directly upstream, in the same
production function (`outcome_resolution.py::resolve_campaign_entry`), of the only code
path that ever checks `runner_target_r` — the exact quantity HYP_001 studies. Under the
pre-v1.0.1 inverted mapping, the partial-target fail-closed guard very likely routed the
large majority of GEN_001/GEN_002A occurrences to a fallback path
(`_resolve_full_position_only`) that never evaluates the runner target at all. HYP_001's
mechanism class, and every entry/setup/stop/risk/friction assumption, remain verified
unchanged and valid. What requires amendment is narrower: the v1.0.0-era "actual"
CONTROL-arm economics and the literal "0/88 reached 3R" claim do not reliably describe
the strategy-as-specified exit lifecycle and must not be cited as a comparability
baseline for the still-pending CONFIRM_001 fresh-confirmation result without an explicit
caveat.

`HYP_001_executed = false` (unchanged; `fresh_confirmation_runs = 0`). The prospective
CONFIRM_001 acquisition window remains frozen and cannot be evaluated before
2026-10-13T00:00:00Z regardless of this reassessment.

## Next safe gate

`OWNER_ADJUDICATION_OF_CONTROL_ARM_COMPARABILITY_AMENDMENT` — an additive-only governance
amendment to `HYP_001_EXIT_CAPTURE_PREREGISTRATION.md` (same pattern as the existing
`EXTENSION_CHECKPOINT_POLICY.json`), not a rewrite. See the full analysis document,
Section 7, for the proposed amendment text and Section 8 for gate detail.
