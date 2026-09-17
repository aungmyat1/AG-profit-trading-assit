# SWEEP_TIMEFRAME_CONTRACT

```
PRIMARY_TIMEFRAME = M15
SIGNAL_TIMEFRAME  = M15
EXECUTION_MODEL   = M15
H1_REQUIRED       = false
M1_REQUIRED       = false
```

**Rationale:** S0 found direct, explicit source evidence that the presenter never uses H1 (only M15 execution/analysis, with optional 4H/Daily macro context at most). This supersedes the mission's own earlier provisional `CONTEXT_TIMEFRAME = H1` framing, per this mission's P1 instruction. `ST_ASIAN_SWEEP_5R_V1 v1.1.1`'s actual code (`entry_2_sweep`, `ReferenceBox`, `post_asian_pilot/*`) has no H1 field or dependency anywhere — consistent with this contract.

**4H/Daily:** not incorporated into signal generation, per source evidence; `regime_classification.trend_bias_filter` (EMA_50) exists in the YAML but — per prior repository memory and consistent with this mission's own audit — is declared config, not consumed by the live sweep signal path (`entry_2_sweep` does not read it).

**EXT-R2B1 derived H1 file:** NOT used in this audit or in this component. No file from `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/EXT_R2B1_M15_REDUCED_PRECISION_PACKAGE/` was read, referenced, or consumed for this mission.
