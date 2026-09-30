# AG_RULE_ATTRIBUTION_V1 — SSC rule-attribution pipeline status (2026-09-30)

Research only. Branch `research/attribution-v1` (draft PR, not merged). Environment:
Claude Code cloud container (Linux, Python 3.11). No broker/exchange calls, no
live/demo code changes, no protected data (CONFIRM_001/HOLDOUT/OOS/H2) accessed.

**FINAL_STATUS = `PIPELINE_BUILT_DATA_GATE_FAIL`.** The code runs end to end. It
stopped at G2 because no admissible public development data exists, so there was
no ledger and no economics. Steps 1–7 are `NOT_EVALUATED`.

## Gates

| Gate | SSC `ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1 | `ST_ASIAN_SWEEP_5R_V1` v1.1.1 |
|---|---|---|
| G0 admission | PASS. `ECONOMIC_GATE_FAIL` (HYP_002 Attempt 2: −0.3564R; G2 DEV_002: −0.47R net). Owner directive: `OPTIMIZATION_ELIGIBLE=TRUE`, `DATA_ROLE=DEVELOPMENT_ONLY`, `HOLDOUT_ACCESS=FORBIDDEN` | CHECKS_ONLY. `NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS`, so not eligible for optimization |
| G1 semantic | PASS. Engine tree `a11a9e49` at `2b75bbf0` and config blob `2ad318c4` are byte-identical | PASS. `version 1.1.1`, registered, engine present, config sha256 `baed22b7…` |
| G2 data | **FAIL** `PUBLIC_DEV_MANIFEST_MISSING` | **FAIL** (same) |

Why G2 failed:
- The network policy denied `datafeed.dukascopy.com` and `www.histdata.com`
  (CONNECT 403, 2026-09-30T07:43Z).
- No in-repo data before 2025-09-14 is admissible:
  - `SSC1D_WP1_OOS_EURUSD_2024Q1` is OOS, so it is protected.
  - The part of DEV_002 before 2025-09-14 is EURUSD H1 warm-up from a broker. It has no
    M15 or M1 data and is not a public source.

## Results

| Item | Value |
|---|---|
| Ledger N | 0 |
| Category / ablation / diagnosis tables | NOT_EVALUATED |
| Hypothesis | NOT_PREREGISTERED (`research/attribution/PREREGISTRATION.yaml`). It needs a diagnosis first |
| Variants / verdicts | none (no variants were run) |
| Trial count | 0 |
| DSR / PBO | NOT_EVALUATED |

## Governance notes

- The frozen SSC engine was deleted from `main` in `3f1f955`. `research/attribution/frozen_engine.py`
  loads it read-only from git history, pinned by commit and tree hash. It does not copy or edit it.
- `config/governance/optimization_admission_contract.yaml` stays `PROPOSED`. The eligibility
  record in `research/attribution/ADMISSION.yaml` is an owner directive for this mission, not a
  signed admission.
- The VT Markets cost table is `PLACEHOLDER_NOT_BROKER_MEASURED`, because VT MT5 spreads have not
  been captured.

## Evidence

- `python -m pytest -q tests/test_research_attribution.py` gave 15 passed, including the
  frozen-engine parity check in a subprocess (relax=() gives output identical to a plain
  `run_replay`, and the ledger contains every baseline fill).
- `python -m research.attribution.run_attribution` gave `{"stopped_at": "G2_data", "ledger_n": 0, "trial_count": 0}`.
  The report is at `research/attribution/reports/attribution_report_v1.json`.

## To resume

1. Allow the Dukascopy/HistData hosts, or supply those files.
2. Write `data/research/public_dev/manifest.json` with `DEVELOPMENT_ONLY` EURUSD/GBPUSD
   H1/M15/M1 data ending before 2025-09-14, with sha256 hashes.
3. Add owner-approved H1 symbol-metadata manifests.
4. Re-run the pipeline.
