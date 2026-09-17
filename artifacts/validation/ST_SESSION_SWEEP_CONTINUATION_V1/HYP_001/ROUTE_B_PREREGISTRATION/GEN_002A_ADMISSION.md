# GEN_002A Dataset Admission (RB-G1)

**Source of proof:** the actual GEN_002A generation script, `scripts/run_gen_002a_gbpusd_session_sweep_continuation_replay.py`, read via `git show refactor/architecture-boundary-hardening-v3:...` (authoritative generation code, not the unrelated N=15 `HYP_001_GBPUSD_REPLICATION_R1` artifact on `main`, which remains explicitly excluded as a different population — see the prior recovery audit's own provenance-distinction finding).

```
symbol   = GBPUSD
interval = 2026-06-08 -> 2026-07-30 (per script's own M1_CSV filename window; confirmed by input_manifest.json)

H1_CSV   = D:\GBPUSD_H1_202501020000_202607310000.csv
H1_hash_expected = a82275bcf8db245440c6f4cd15bb69ab54b7f8677025410910c913a82bcefe9e
H1_hash_actual   = a82275bcf8db245440c6f4cd15bb69ab54b7f8677025410910c913a82bcefe9e   MATCH

M15_CSV  = D:\GBPUSD_M15_202501020000_202607310000.csv
M15_hash_expected = 1192991287d7e1293c78b8037893ed50f2e0a274c6ed7ac0b1b187988344bac1
M15_hash_actual   = 1192991287d7e1293c78b8037893ed50f2e0a274c6ed7ac0b1b187988344bac1   MATCH

M1_CSV   = D:\GBPUSD_M1_202606080533_202607302357.csv
M1_hash_expected = 390798def4c598f3463be5f339d1cf2921537e96a48eca4d797aadb78c1d705c
M1_hash_actual   = 390798def4c598f3463be5f339d1cf2921537e96a48eca4d797aadb78c1d705c   MATCH

H1_manifest_path = config/historical_datasets/GBPUSD_H1_symbol_metadata.yaml
H1_manifest_authority = OWNER_APPROVED_DATASET_MANIFEST
H1_manifest_dataset_fingerprint = sha256:a82275bcf8db245440c6f4cd15bb69ab54b7f8677025410910c913a82bcefe9e  MATCH
H1_manifest_approval_date = 2026-09-14 (explicit owner authorization quoted in-manifest: "GBPUSD symbol-metadata admission is AUTHORIZED... Obtain the authoritative GBPUSD value from the project's EXISTING Vantage/MT5 symbol-metadata path... do not invent a value")
H1_manifest_location = NOT on main -- recoverable read-only via `git show refactor/architecture-boundary-hardening-v3:config/historical_datasets/GBPUSD_H1_symbol_metadata.yaml` (git history: commit ba7b6ac "data+test: admit GBPUSD H1 symbol-metadata manifest for GEN_002A (owner-authorized)")
tick_size_provenance = independently corroborated twice against live MT5 symbol_info() captures cited in the manifest's own comments (docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md, docs/status/AG_VTMARKETS_CRYPTO_MT5_EXECUTION_COMPATIBILITY_E1_STATUS.md) -- not guessed, not copied from EURUSD's value

original_population_hash = 2a2fb946f995805ccc56342a712376ccf5ee9fb1e324fa383e7d08c5d3e54fd8
original_occurrence_count = 57
```

**Status: `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` for all three raw legs on `D:\`.** The H1 owner-authorized manifest is `DATA_BYTES_RECOVERABLE_EXACT_FROM_GIT` (exists, verified, owner-approved — simply not yet present in `main`'s working tree; a future execution mission would need to restore/re-add it, an administrative step, not a provenance gap).
