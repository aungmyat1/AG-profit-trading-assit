# DEV002 H1 Remediation — Verified Values (computed 2026-09-21 from repo HEAD c995f08)

All values below were computed from actual bytes; the agent must RE-VERIFY each before use
(P1 instruction: "Recompute hashes from bytes").

## Facts

| Item | Value |
|---|---|
| File | `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/EURUSD_H1.csv` |
| Actual committed bytes, sha256 | `9cb7c2da900e958ec092327d08e4506007146bda611c4b056c396f0e121dfa6f` |
| Stale fingerprint in frozen manifests | `93d27d8cbeb85c0b595ece7d18a43ac66219ae9fbb137e23a9826b84fc191c79` |
| File added in single commit | `f66d555` ("SSC v1.0.1 G2: build DEV_002 H1-warmup remediation dataset + registry supersession") |
| Bytes changed since f66d555? | **NO** — `git show f66d555:<path>` hashes to the same value as the working tree |
| Rows | 9 843 |
| Root cause class | `MANIFEST_FROZEN_AGAINST_PRE_COMMIT_BYTES` |
| Additional defect (R3, 2026-09-19) | File is DST-mixed: winter bars align at −1h, summer bars at 0h vs canonical M1 — legacy dev evidence only, never a one-year replay input |

## Combined-fingerprint re-derivation (formula verified)

Formula: `combined_dataset_fingerprint = sha256(canonical_input_string)` where the string is
`EURUSD|H1|<h1>\nEURUSD|M15|<m15>\nEURUSD|M1|<m1>` — verified by recomputing the declared
value `05b05972…` from the old input (exact match).

| Field | Old | New (remediated) |
|---|---|---|
| per_file.EURUSD_H1.sha256 | `93d27d8c…fc191c79` | `9cb7c2da…ec3eedef` (full: `9cb7c2da900e958ec092327d08e4506007146bda611c4b056c396f0e121dfa6f`) |
| combined_dataset_fingerprint | `05b059720a7457d15a7fbc4cd7f0c15e62df86b7857c1f122edc49a0d3a2baf5` | **`55cffa7ce3363e11028060969338e88675aee54a803b2886354d3462ec3eedef`** |
| M15 sha (unchanged) | `cefed9705bf9609329183c9bc44b7536eafdf070950ff6bcd45b759623ccd063` | same |
| M1 sha (unchanged) | `b760a2a65f8f453d121500657e824daec63579bfa4e67895e4501454dedc7458` | same |

## Reference inventory for the stale hash (grep of `93d27d8c` at HEAD)

| File | Disposition |
|---|---|
| `config/historical_datasets/EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml` | **REMEDIATE** (binding manifest; P1 patch) |
| `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/dataset_manifest.json` | **REMEDIATE** (per_file + combined; P1 patch) |
| `tests/test_ssc_dev002_h1_metadata_manifest.py` | **REMEDIATE** (split frozen-blocker vs remediated constants; P1 patch) |
| `artifacts/.../SSC_V1_0_1_G2_DEV_002/G2_HISTORICAL_REPLAY_BLOCKER.json` | **IMMUTABLE** — frozen evidence; remediation record supersedes |
| `artifacts/.../SSC_V1_0_1_G2_DEV_002/G2_POPULATION_PREREGISTRATION.json` | **IMMUTABLE** — sealed preregistration |
| `artifacts/.../SSC_V1_0_1_DATA_CONSUMPTION_REGISTRY_V1.json` | **IMMUTABLE** (dated registry snapshot) — record identity chain in remediation doc; regenerate only if owner authorizes a new dated registry version |
| `artifacts/.../SSC_V1_0_1_HIST_1Y_001/DATA_COVERAGE_AUDIT_V1.json` | **IMMUTABLE** — dated audit output |
| `scripts/run_ssc_v1_0_1_g2_dev002_population.py` | **VERIFY** — if it re-checks the hash at runtime, update with remediation citation; if historical comment only, annotate |
| `src/data_archive/lineage_audit.py` | **VERIFY** — same treatment as above |

## Verification performed with P1 patch applied (Linux, 2026-09-21)

- `tests/test_ssc_dev002_h1_metadata_manifest.py` — **3/3 PASS** (was 3 FAIL)
- `tests/test_external_candidate_governance_invariance.py` — **PASS** with P1.5 patch (was 1 FAIL)
- `tests/test_topdown_composer_replay.py` / `test_td8e_*` — fingerprint failures resolved;
  residual failures are now `MT5StubOperationAttempted(symbol_info)` — the separate
  runtime-MT5 marking category (WP0.2), not a fingerprint binding. On the Windows dev box
  with real MT5 these are expected to pass; agent must confirm and mark/monkeypatch for
  non-Windows honesty.
