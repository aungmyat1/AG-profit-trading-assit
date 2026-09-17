# ES-R1 Development Data Admission Contract

**No dataset is selected in this mission.** This is an inventory-inspection-only pass (P6) to identify already-known contamination, not a data-access or economic-consumption step. Actual admission and window selection occurs in ES-R2.

## Exclusions (hard requirements for any future DEVELOPMENT dataset)

- Not the Oct-2022 (2022-10-03..21) EURUSD source benchmark or its derived UTC-normalized artifacts.
- Not ES-S3/S4/S5/S5A/S6 evidence (`SOURCE_RECONSTRUCTION_GOVERNANCE_ONLY`).
- Not any D:\ddev\Session Trade Codex benchmark-tuning population.
- Not the sealed final holdout (undefined/unselected as of this mission).

## Candidate pool identified (inventory only, not admitted)

The repository already owns EURUSD M15/H1 datasets covering **2025-01 through 2026-07**, entirely disjoint from Oct 2022:

| Dataset | Coverage (UTC) | Timezone status | Quality |
|---|---|---|---|
| `EURUSD_H1_202501020000_202607310000` (`config/historical_datasets/EURUSD_H1_202501020000_202607310000.yaml`) | 2025-01-01T21:00Z – 2026-07-30T21:00Z | `BROKER_OFFSET_CONFIRMED` | `PASS` |
| `EURUSD_M15_202501020000_202606192345` (`config/historical_datasets/EURUSD_M15_202501020000_202606192345.yaml`) | overlapping range, M15 | `BROKER_OFFSET_CONFIRMED` | `PASS` |

Both already carry a recorded `dataset_fingerprint` (deterministic sha256) and an established owner-authorized timezone resolution — satisfying the "timezone authority known" and "deterministic dataset fingerprint" requirements without new acquisition work.

## Friction evidence

Not yet confirmed available or bounded for this specific candidate strategy/dataset pairing — to be resolved explicitly in `FRICTION_CONTRACT.md` (this mission) and re-verified at ES-R2 admission time, not assumed here.

## Not consumed

No row of any dataset above was read, loaded, or used to generate an occurrence in this mission.
