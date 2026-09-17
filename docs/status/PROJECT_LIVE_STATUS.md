<!-- GENERATED FILE — DO NOT MANUALLY EDIT. Regenerate with scripts/generate_live_status.py -->
<!-- LIVE_STATE_FINGERPRINT: 81774fce9fe07c2b33f86d84fd880de5cb9dae12805ea07dab5d067c8436ee20 -->

# Project Live Status

Schema: `AG_LIVE_STATUS_SNAPSHOT_V1`  
Generated: 2026-09-17T07:07:05.860601+00:00

## 1. Repository Identity

- Branch: `main`
- HEAD: `d4e3b3d05edb11ce47efb6f6937a1942a2fbd1d2`
- Working tree clean: `False`

## 2. Repository Provenance

- Reconciled through: `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md`
- Reconciliation status: `MIXED_BUT_RECONCILED`
- Known mixed integration commits: `873dd68`

## 3. Runtime Status

- No runtime probe is wired into this generator (AVO-WP1 scope). Runtime/broker/feed status is out of scope for this snapshot.

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

## 6. Campaign / Evidence State

- Campaign-level evidence (observation counts, friction-campaign day counts) is not yet tracked by AVO-WP1 (`dataset_role_status`/`lineage_status`/`holdout_status` are reported as `NOT_TRACKED_BY_WP1` per strategy above). See `docs/status/RECONCILIATION_AUDIT_POST_BB6AC0F.md` section 6 for the point-in-time campaign snapshot until a canonical multi-strategy reader exists.

## 7. Active Blockers

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

## 8. Concurrent / Foreign WIP

- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/COMPARISON_CONFIGURATION.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/ES_S4_HASHES.txt` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/POST_FREEZE_HYPOTHESES.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/aggregate_summary.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/blind_extra_ledger.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/compare.py` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/mapping_ledger.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/reference_table.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/reference_table_normalized.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/ES_S5A_HASHES.txt` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/ES_S5A_REPORT.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/clock_sensitivity_result.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/compare_sensitivity.py` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/per_event_delta_table.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5_RECONSTRUCTION/ES_S5_DIAGNOSTIC_REPORT.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_A_ASIAN_REFERENCE_raw.jsonl` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_A_ASIAN_REFERENCE_summary.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_B_PRE_LONDON_raw.jsonl` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_B_PRE_LONDON_summary.json` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_M15_SESSION_SWEEP_RESEARCH_V1/ES_R1_PREREGISTRATION/HYPOTHESIS_REGISTRY.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_POST_V1_0_1_REASSESSMENT/HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `docs/status/AG_SSC_HYP001_POST_V1_0_1_REASSESSMENT_STATUS.md` — UNCOMMITTED / NOT YET AUTHORITATIVE
- `journal/reports/btc/2026/2026-09-16.json` — UNCOMMITTED / NOT YET AUTHORITATIVE

## 9. Owner Decisions Required

- Foreign/concurrent WIP present -- confirm ownership and freeze/discard intent before it is treated as authoritative: artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/COMPARISON_CONFIGURATION.md, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/ES_S4_HASHES.txt, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/POST_FREEZE_HYPOTHESES.md, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/aggregate_summary.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/blind_extra_ledger.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/compare.py, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/mapping_ledger.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/reference_table.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S4_COMPARISON/reference_table_normalized.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/ES_S5A_HASHES.txt, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/ES_S5A_REPORT.md, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/clock_sensitivity_result.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/compare_sensitivity.py, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5A_CLOCK_SENSITIVITY/per_event_delta_table.json, artifacts/validation/EXTERNAL_SOURCE_ES_S1S/ES_S5_RECONSTRUCTION/ES_S5_DIAGNOSTIC_REPORT.md, artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_A_ASIAN_REFERENCE_raw.jsonl, artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_A_ASIAN_REFERENCE_summary.json, artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_B_PRE_LONDON_raw.jsonl, artifacts/validation/ST_LARGE_SMC_V1/EURUSD_ADMISSION_CONTRACTS/friction_campaign_wp3a1/sessions/2026-09-17_WINDOW_B_PRE_LONDON_summary.json, artifacts/validation/ST_M15_SESSION_SWEEP_RESEARCH_V1/ES_R1_PREREGISTRATION/HYPOTHESIS_REGISTRY.md, artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_POST_V1_0_1_REASSESSMENT/HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT.md, docs/status/AG_SSC_HYP001_POST_V1_0_1_REASSESSMENT_STATUS.md, journal/reports/btc/2026/2026-09-16.json

## 10. Next Safe Actions

- ST_ASIAN_SWEEP_5R_V1:CONTINUE_EVIDENCE_COLLECTION
- SESSION_TRADE_V1:NONE_NO_ADAPTER_WIRED
- SMC_3R_V1:NONE_NO_ADAPTER_WIRED
- ST_LARGE_SMC_V1:CONTINUE_EVIDENCE_COLLECTION
- ST_LIQUIDITY_SWEEP_RETEST_V1:CONTINUE_EVIDENCE_COLLECTION
- ST_SESSION_SWEEP_CONTINUATION_V1:CONTINUE_EVIDENCE_COLLECTION
- R8_OBM_V1:NONE_NO_ADAPTER_WIRED

## 11. Execution Authority

| strategy_id | demo_authorized | live_authorized |
|---|---|---|
| ST_ASIAN_SWEEP_5R_V1 | False | False |
| SESSION_TRADE_V1 | True | False |
| SMC_3R_V1 | False | False |
| ST_LARGE_SMC_V1 | False | False |
| ST_LIQUIDITY_SWEEP_RETEST_V1 | False | False |
| ST_SESSION_SWEEP_CONTINUATION_V1 | False | False |
| R8_OBM_V1 | False | False |

## 12. Generator Provenance

- Generator: `scripts/generate_live_status.py` (schema `AG_LIVE_STATUS_SNAPSHOT_V1`)
- State fingerprint: `81774fce9fe07c2b33f86d84fd880de5cb9dae12805ea07dab5d067c8436ee20`
- Fingerprint excludes `generated_at_utc` and every per-strategy `updated_at_utc`; it changes only when meaningful state changes.
