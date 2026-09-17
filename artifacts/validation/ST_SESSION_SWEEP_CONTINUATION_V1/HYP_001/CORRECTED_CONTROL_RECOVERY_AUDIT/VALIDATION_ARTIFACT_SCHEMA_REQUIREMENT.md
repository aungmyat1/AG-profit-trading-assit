# Validation Artifact Schema Requirement (P8) — a schema recommendation, not a strategy-rule change

Future self-contained occurrence records for this strategy family should retain, at minimum:

`occurrence_id`, `strategy_id`, `strategy_version`, `symbol`, `setup_type`, `direction`, `session_id`,
`reference_window_start`, `reference_window_end`, `reference_high`, `reference_low`,
`detection_timestamp`, `entry_timestamp`, `entry_price`, `initial_stop`,
`source_dataset_fingerprint`, `strategy_fingerprint`, `friction_contract_fingerprint`,
`post_entry_evidence_reference`, `post_entry_evidence_hash`

This would have made the current recovery mission unnecessary — the exact gap found (`reference_high`/`reference_low` and post-entry evidence absent from every existing GEN_001/GEN_002A/GEN_002 artifact) is precisely what this schema closes. **No canonical SSC behavior is modified by recording this recommendation.** Adoption is a decision for a future, separately-scoped control-plane/tooling mission.
