<!-- GENERATED FILE — DO NOT MANUALLY EDIT. Regenerate with scripts/generate_live_status.py -->
<!-- LIVE_STATE_FINGERPRINT: 19f768772a546b471e187124a693a7203260ea1b85ee5664d4f040f049575835 -->

# Project Live Status

Schema: `AG_LIVE_STATUS_SNAPSHOT_V2`  
Generated: 2026-09-17T15:49:20.811789+00:00

## 1. Repository Identity

- Branch: `main`
- HEAD: `c57406cab1a6f9d5af177d4924c1f82738a6c9be`
- Working tree clean: `False`

## 2. Repository Provenance

- Reconciled through: `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md`
- Reconciliation status: `MIXED_BUT_RECONCILED`
- Known mixed integration commits: `873dd68`

## 3. Runtime Status

- RUNTIME_STATUS is a **separate authority** from GOVERNANCE_STATUS. A probe result here never changes `validation_state`, `demo_authorized`, `live_authorized`, blockers, or next-safe-actions (sections 5/8/11/12), and is excluded from the governance state fingerprint below.
- Checked at: `2026-09-17T15:49:23.999420+00:00`

| subsystem | status | detail |
|---|---|---|
| fastapi | UNAVAILABLE | API gateway unreachable: timed out |
| mt5 | UNAVAILABLE | probed via API gateway; API gateway unavailable |
| broker | UNAVAILABLE | probed via API gateway; API gateway unavailable |
| market_data | UNAVAILABLE | probed via API gateway; API gateway unavailable |
| proposal_ledger | AVAILABLE | 68 active canonical proposal(s) in ledger |
| scheduler | UNAVAILABLE | checkpoint not yet created (scheduler not started) |
| ssc | AVAILABLE | adapter importable (session_sweep_continuation.replay.ReplayResult.accepted_setups) |
| lsmc | AVAILABLE | adapter importable (large_smc_research.decision.LargeSMCResearchDecision) |

## 4. Project Readiness Gates

- Readiness gates (R0-R9) are owned by `docs/PROJECT_ROADMAP.md`; this generator does not duplicate that matrix. See the roadmap for current gate definitions.

## 5. Strategy Validation Matrix

| strategy_id | version | lifecycle_stage | validation_state | current_gate | furthest_verified_gate | demo_authorized | live_authorized | next_safe_action |
|---|---|---|---|---|---|---|---|---|
| ST_ASIAN_SWEEP_5R_V1 | 1.1.1 | OPERATIONAL_SHADOW | EVIDENCE_INCOMPLETE | FRICTION_STRESS_TEST | HISTORICAL_REPLAY | False | False | CONTINUE_EVIDENCE_COLLECTION |
| SESSION_TRADE_V1 | - | - | NO_VALIDATION_ADAPTER | - | - | True | False | NONE_NO_ADAPTER_WIRED |
| SMC_3R_V1 | - | - | NO_VALIDATION_ADAPTER | - | - | False | False | NONE_NO_ADAPTER_WIRED |
| ST_LARGE_SMC_V1 | 1.0.7 | FORWARD_RESEARCH | EVIDENCE_INCOMPLETE | FRICTION_STRESS_TEST | HISTORICAL_REPLAY | False | False | CONTINUE_EVIDENCE_COLLECTION |
| ST_LIQUIDITY_SWEEP_RETEST_V1 | 2.0.0 | FORWARD_RESEARCH | EVIDENCE_INCOMPLETE | HISTORICAL_REPLAY | NO_LOOKAHEAD | False | False | CONTINUE_EVIDENCE_COLLECTION |
| ST_SESSION_SWEEP_CONTINUATION_V1 | 1.0.1 | OFFLINE_RESEARCH | EVIDENCE_INCOMPLETE | DETERMINISM | SPEC_FIDELITY | False | False | CONTINUE_EVIDENCE_COLLECTION |
| R8_OBM_V1 | - | - | NO_VALIDATION_ADAPTER | - | - | False | False | NONE_NO_ADAPTER_WIRED |

## 6. Proposal Platform Status (V1.2)

- Informational proposal capability (`proposal_capable`) is independent of economic edge (`economic_edge_established`) and execution eligibility (`execution_eligible`): a `proposal_capable = true` entry can still be `economic_edge_established = false` and `execution_eligible = false`. Proposal generation is OBSERVATION ONLY and grants no validation or execution authority.

| strategy_id | proposal_capable | proposal_generation_authorized | economic_edge_established | execution_eligible | broker_mutation_blocked |
|---|---|---|---|---|---|
| ST_SESSION_SWEEP_CONTINUATION_V1 | True | True | False | False | True |
| ST_LARGE_SMC_V1 | True | False | False | False | True |

## 7. Campaign / Evidence State

- Campaign-level evidence (observation counts, friction-campaign day counts) is not yet tracked by AVO-WP1 (`dataset_role_status`/`lineage_status`/`holdout_status` are reported as `NOT_TRACKED_BY_WP1` per strategy above). See `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md` section 6 for the point-in-time campaign snapshot until a canonical multi-strategy reader exists.

## 8. Active Blockers

- ST_ASIAN_SWEEP_5R_V1:SHADOW_SERIES_COMPLETION
- ST_ASIAN_SWEEP_5R_V1:FRICTION_STRESS_TEST
- ST_ASIAN_SWEEP_5R_V1:OOS_VALIDATION
- SESSION_TRADE_V1:no validation_framework adapter is registered for this strategy_id (see api.strategy_service.has_validation_adapter)
- SMC_3R_V1:no validation_framework adapter is registered for this strategy_id (see api.strategy_service.has_validation_adapter)
- ST_LARGE_SMC_V1:LARGE_SMC_SHADOW_ENTRY_PREFLIGHT
- ST_LIQUIDITY_SWEEP_RETEST_V1:HISTORICAL_REPLAY
- ST_LIQUIDITY_SWEEP_RETEST_V1:NATURAL_CAMPAIGN_ACCRUAL
- ST_SESSION_SWEEP_CONTINUATION_V1:DETERMINISM
- ST_SESSION_SWEEP_CONTINUATION_V1:HISTORICAL_REPLAY
- R8_OBM_V1:no validation_framework adapter is registered for this strategy_id (see api.strategy_service.has_validation_adapter)

## 9. Concurrent / Foreign WIP

- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001/ROUTE_B_PHASE1_RECONSTRUCTION/GEN_001_COMPARABILITY_AND_FREEZE.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001/ROUTE_B_PHASE1_RECONSTRUCTION/_CHECKPOINTS/GEN_001_RUN_1.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `src/runtime_status/__init__.py` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `src/runtime_status/probe.py` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `tests/test_cross_strategy_ledger.py` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `tests/test_live_status_proposal_platform.py` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `tests/test_runtime_status_probe.py` — UNCOMMITTED / NOT YET AUTHORITATIVE

## 10. Owner Decisions Required

- Foreign/concurrent WIP present -- confirm ownership and freeze/discard intent before it is treated as authoritative: artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001/ROUTE_B_PHASE1_RECONSTRUCTION/GEN_001_COMPARABILITY_AND_FREEZE.md, artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001/ROUTE_B_PHASE1_RECONSTRUCTION/_CHECKPOINTS/GEN_001_RUN_1.json, src/runtime_status/__init__.py, src/runtime_status/probe.py, tests/test_cross_strategy_ledger.py, tests/test_live_status_proposal_platform.py, tests/test_runtime_status_probe.py

## 11. Next Safe Actions

- ST_ASIAN_SWEEP_5R_V1:CONTINUE_EVIDENCE_COLLECTION
- SESSION_TRADE_V1:NONE_NO_ADAPTER_WIRED
- SMC_3R_V1:NONE_NO_ADAPTER_WIRED
- ST_LARGE_SMC_V1:CONTINUE_EVIDENCE_COLLECTION
- ST_LIQUIDITY_SWEEP_RETEST_V1:CONTINUE_EVIDENCE_COLLECTION
- ST_SESSION_SWEEP_CONTINUATION_V1:CONTINUE_EVIDENCE_COLLECTION
- R8_OBM_V1:NONE_NO_ADAPTER_WIRED

## 12. Execution Authority

| strategy_id | demo_authorized | live_authorized |
|---|---|---|
| ST_ASIAN_SWEEP_5R_V1 | False | False |
| SESSION_TRADE_V1 | True | False |
| SMC_3R_V1 | False | False |
| ST_LARGE_SMC_V1 | False | False |
| ST_LIQUIDITY_SWEEP_RETEST_V1 | False | False |
| ST_SESSION_SWEEP_CONTINUATION_V1 | False | False |
| R8_OBM_V1 | False | False |

## 13. Generator Provenance

- Generator: `scripts/generate_live_status.py` (schema `AG_LIVE_STATUS_SNAPSHOT_V2`)
- State fingerprint: `19f768772a546b471e187124a693a7203260ea1b85ee5664d4f040f049575835`
- Fingerprint excludes `generated_at_utc` and every per-strategy `updated_at_utc`; it changes only when meaningful state changes.
