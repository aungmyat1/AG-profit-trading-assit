# GEN_001 Dataset Admission (RB-G1)

**Source of proof:** the actual GEN_001 generation script, `scripts/run_first_canonical_session_sweep_continuation_replay.py`, read directly via `git show refactor/architecture-boundary-hardening-v3:scripts/run_first_canonical_session_sweep_continuation_replay.py` (its own `input_manifest.json`/`manifest.json` outputs, already inspected in the prior recovery audit, only confirmed the M1 leg — this script is the actual generation code and is the authoritative source for all three legs).

```
symbol   = EURUSD
interval = 2026-05-18 -> 2026-06-19 (script date_start/date_end, matches manifest.json exactly)

H1_CSV   = D:\EURUSD_H1_202501020000_202607310000.csv
H1_hash_expected = f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060
H1_hash_actual   = f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060   MATCH

M15_CSV  = D:\EURUSD_M15_202501020000_202606192345.csv
M15_hash_expected = 7f7502938862f4a3779f018caab468fe4445a4d8c676c8393dc29ca57fc43a65
M15_hash_actual   = 7f7502938862f4a3779f018caab468fe4445a4d8c676c8393dc29ca57fc43a65   MATCH

M1_CSV   = D:\EURUSD_M1_202605180946_202607312356.csv
M1_hash_expected = 55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23
M1_hash_actual   = 55422a1ccdf4ca76fd25451fbf849d559bed45d839891a3ada7a37f9f7dd6a23   MATCH

H1_manifest_path = config/historical_datasets/EURUSD_H1_symbol_metadata.yaml
H1_manifest_authority = OWNER_APPROVED_DATASET_MANIFEST  (present on main, live, re-verified this mission)
H1_manifest_dataset_fingerprint = sha256:f1b456e4b50215ad23370949f15faaa8548f9c03053a20d8974d6e9fd480a060  MATCH

original_population_hash = 8e32a7498e5a1c7df6658e6700ff3386fb38821ed189619a20224ce032d9166d
original_occurrence_count = 31
generation_commit = f0a9827eac1bddcc96f3b91db32ed0bac5736aa9 (2026-09-13, confirmed reachable)
```

**Status: `DATA_BYTES_ACCESSIBLE_AND_HASH_VERIFIED` for all three raw legs. `GEN_001_RECOVERABLE_EXACT = true`.** The generation script itself and its manifests are recoverable read-only from the unmerged branch (`git show`, no merge/checkout).
