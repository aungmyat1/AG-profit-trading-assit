# Corrected v1.0.1 CONTROL Contract

```
CONTROL_ID       = SSC_V1_0_1_CONTROL_3R
runner_target_r  = 3.0  (FIXED_R, unchanged from the frozen v1.0.1 parent)
partial_target_pct = 0.50
runner_pct       = 0.50
runner_target_mode = FIXED_R
```

All other semantics are frozen identical to the v1.0.1 parent (`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`, hash above) — setup (S1/S2/S3), entry, regime, stop (ATR period=14, stop_buffer_multiplier=0.20), risk/campaign allocation, friction, and session windows are all byte-identical, per the already-independently-verified diff in `HYP_001_LINEAGE_AUDIT/hyp001_lineage_audit.json` phase5 (`ENTRY/SETUP/REGIME/STOP/RISK/FRICTION = UNCHANGED`).

**Ambiguity handling:** `SAME_BAR_POLICY = AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER` (unchanged, byte-identical code path).

**This reconstruction differs from historical v1.0.0 CONTROL evidence ONLY in the outcome-resolver's partial-target-direction mapping** (`INVERSE_BOUNDARY` → `OPPOSITE_SESSION_BOUNDARY`), exactly the already-approved v1.0.1 semantic remediation — no additional repair, filter, or parameter change is introduced by this preregistration.
