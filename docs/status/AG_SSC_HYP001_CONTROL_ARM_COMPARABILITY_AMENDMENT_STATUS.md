# AG SSC HYP_001 Control-Arm Comparability Amendment — Status

Status: HISTORICAL_STATUS (dated evidence snapshot per `docs/status/LIVE_STATUS_MAINTENANCE.md`).
Generated 2026-09-17. This document does not edit or supersede
`docs/status/AG_SSC_HYP001_POST_V1_0_1_REASSESSMENT_STATUS.md`; it records the
follow-on owner adjudication.

Full amendment artifact:
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_POST_V1_0_1_REASSESSMENT/HYP_001_CONTROL_ARM_COMPARABILITY_AMENDMENT_V1.json`

Mission: `SSC_HYP_001_CONTROL_ARM_COMPARABILITY_AMENDMENT_V1` (governance/documentation
only — no execution, no economic replay, no new population, no CONFIRM_001/holdout
access, no parameter or authority change).

## Headline

```
reassessment_classification = REQUIRES_AMENDMENT
owner_adjudication           = APPROVE_ADDITIVE_CONTROL_COMPARABILITY_AMENDMENT
amendment_status              = FROZEN
hypothesis_id                 = HYP_001_EXIT_CAPTURE (preserved, not replaced)
parent_preregistration        = immutable (not edited)
```

The additive amendment records that historical v1.0.0 CONTROL-arm evidence
(GEN_001/GEN_002A/GEN_002) cannot be assumed to represent the corrected v1.0.1 exit
lifecycle, because the old resolver's partial-target-direction defect could prevent an
occurrence from ever reaching the runner-target evaluation path. No magnitude or
direction of economic effect is claimed or estimated — this is a mechanistic,
non-quantitative comparability finding only. Historical CONTROL evidence is
reclassified `PRE_REMEDIATION_CONTROL_CONTEXT_ONLY`: usable for lineage/context, not
usable as corrected-baseline economics or as confirmation evidence. No historical
artifact content was modified.

Every setup/entry/stop/risk/friction rule, the runner-target treatment definition
(CONTROL 3.0R / TREATMENT 1.5R), the preregistered candidate value, the CONFIRM_001/
002/003 confirmation calendar, data-role boundaries, and the holdout boundary remain
exactly as frozen in the original preregistration.

## Representational gap (recorded, not resolved)

AVO-WP1's `StrategyValidationStatus` model (`src/validation_orchestrator/status.py`)
represents validation state per strategy, not per sub-hypothesis. It has no field for
"HYP_001 = AMENDED_PENDING_CORRECTED_CONTROL_BASELINE" and was not modified to add one
by this mission — expanding AVO's schema is out of scope for a documentation-only
mission and was not attempted. `docs/status/PROJECT_LIVE_STATUS.md` therefore continues
to report SSC at strategy granularity only (version 1.0.1, validation_state, demo/live
authorization); hypothesis-level state (this amendment, HYP_002's closure, HYP_003's
non-opening) remains visible only through the `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/`
evidence tree and `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md`, not through the
generated live-status file.

## Next gate

```
name    = GENERATE_V1_0_1_CORRECTED_CONTROL_BASELINE
purpose = Establish corrected v1.0.1 CONTROL-arm evidence under the frozen strategy/
          configuration without changing HYP_001 treatment parameters or consuming
          CONFIRM_001/holdout.
executed = false
```

This gate is a read-only re-derivation over already-frozen historical populations, but
it IS an economic re-evaluation and requires its own explicit owner preregistration and
sign-off before execution — not authorized by this amendment.

CONFIRM_001 remains independently calendar-frozen; its earliest possible evaluation is
2026-10-13T00:00:00Z, unaffected by this amendment.
