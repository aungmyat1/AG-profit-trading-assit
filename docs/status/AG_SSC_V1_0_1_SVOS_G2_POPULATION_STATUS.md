# SSC v1.0.1 SVOS G2 Population — Status (2026-09-19)

## Summary

`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1's ONE-SHOT G2 historical population replay
over the frozen development dataset `SSC_V1_0_1_G2_DEV_002` completed and froze
`SSC_V1_0_1_G2_DEV_002_POPULATION_V1`. This closes the previous G2 blocker
(`BLOCKED_MISSING_H1_METADATA_AUTHORIZATION`, frozen in
`G2_HISTORICAL_REPLAY_BLOCKER.json`) — the DEV_002 H1 symbol-metadata manifest
(`config/historical_datasets/EURUSD_H1_SSC_G2_DEV_002_symbol_metadata.yaml`,
authority `OWNER_APPROVED_DATASET_MANIFEST`, commit `6ba8795`) binds to the DEV_002 H1
file and the canonical H1-bias preflight passes.

Research only: no strategy parameter changed, no optimization run, no protected data
(confirmation/holdout/OOS/H2) accessed, and no broker/demo/live order or authority
change. The G3 economic gate remains `NOT_EVALUATED_UNSIGNED_CONTRACT`.

## Gate results

| Gate | Result |
| --- | --- |
| G0 repository stability | `PASS` (branch `main`, HEAD `6ba8795`, foreign Large-SMC/BTC/proposal-ledger WIP left unstaged) |
| G1 dataset identity | `PASS` (H1/M15/M1 sha256, combined fingerprint, preregistration hash all match frozen values) |
| G2 metadata + warmup admission | `PASS` (BIND=PASS, warmup `WARMUP_CONTEXT_ONLY`, BIAS_PREFLIGHT=PASS) |
| G3 strategy authority | `PASS` (v1.0.1, `session_sweep_continuation.replay.run_replay`, historical↔forward parity, `OPPOSITE_SESSION_BOUNDARY`) |
| G4 protected-data firewall | `PASS` (no confirmation/holdout/OOS/H2 access) |
| G5 replay identity | `PASS` (no prior authoritative population existed) |
| G6 execute ONE replay | `PASS` (`RESEARCH_REPLAY_COUNT=1`) |
| G7 freeze population | `PASS` (`G2_POPULATION_V1.json` + manifest) |
| G8 determinism | `PASS` (identical population hash across two independent runs) |
| G9 descriptive performance | `PASS` (see below) |
| G10 failure diagnosis | `PASS` (descriptive; primary `WEAK_GROSS_EDGE`) |
| G11 economic gate | `NOT_EVALUATED_UNSIGNED_CONTRACT` (contract PROPOSED/unsigned) |
| G12 optimization admission | `OPTIMIZATION_ELIGIBLE=false` |
| G13 SVOS evidence update | `PASS` (G2 `POPULATION_FROZEN`; G3 not advanced) |
| G14 tests | `PASS` (98 passed) |
| G15 safety | `PASS` (see safety block) |
| G16 commit | `PASS` (evidence only, no push) |

## Population identity

```
population_id          SSC_V1_0_1_G2_DEV_002_POPULATION_V1
strategy_id            ST_SESSION_SWEEP_CONTINUATION_V1
strategy_version       1.0.1
dataset_id             SSC_V1_0_1_G2_DEV_002
dataset_fingerprint    05b059720a7457d15a7fbc4cd7f0c15e62df86b7857c1f122edc49a0d3a2baf5
preregistration_hash   d40fca49b2ff92768cafd45cdb5d48de96d53ad68449af68d41f8a348d4b0952
population_sha256      832e8e13c74a5401684a401cdbe4c42aa95e95661928fe596804068e7067ab5e
occurrence_count       22
determinism            PASS (identical population hash across two independent runs)
```

## Descriptive performance (DEVELOPMENT, diagnostic only)

| Metric | Value |
| --- | --- |
| N | 22 |
| Wins / Losses / Breakeven | 8 / 13 / 1 |
| Gross total R | -5.40 |
| Friction total R | 4.92 |
| Net total R | -10.32 |
| Gross expectancy R | -0.245 |
| Net expectancy R | -0.469 |
| Gross profit factor | 0.563 |
| Net profit factor | 0.339 |
| Max drawdown R | 5.90 |
| Win rate | 36.4% |

Decomposition: S1=13, S2=2, S3=7; ASIAN_LONDON=12, LONDON_NEWYORK=10; LONG=4,
SHORT=18. Full per-dimension metrics frozen in
`G2_DESCRIPTIVE_PERFORMANCE_V1.json`.

## Failure diagnosis (descriptive, not optimization)

- PRIMARY: `WEAK_GROSS_EDGE` — gross expectancy -0.245R ≤ 0 (observed fact).
- Notable observed facts: net expectancy -0.469R; direction concentration SHORT=18 vs
  LONG=4; gross PF 0.56.
- No candidate parameters created, no search run. `OPTIMIZATION_ELIGIBLE=false`.

## Safety

`STRATEGY_CHANGED=false`, `PARAMETERS_CHANGED=false`, `DATASET_CHANGED=false`,
`RESEARCH_REPLAY_COUNT=1`, `OPTIMIZATION_RUN=false`, `NEW_CANDIDATE_CREATED=false`,
`CONFIRMATION_ACCESSED=false`, `HOLDOUT_ACCESSED=false`, `OOS_ACCESSED=false`,
`H2_CONSUMED=false`, `H2_MODIFIED=false`, `VIRTUAL_BROKER_STARTED=false`,
`FORWARD_STARTED=false`, `BROKER_MUTATION=false`, `DEMO_ORDER=false`,
`LIVE_ORDER=false`, `EXECUTION_AUTHORITY_CHANGED=false`.

## Evidence

- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_POPULATION_V1.json`
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_POPULATION_MANIFEST_V1.json`
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_DETERMINISM_V1.json`
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_DESCRIPTIVE_PERFORMANCE_V1.json`
- `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC_V1_0_1_G2_DEV_002/G2_SVOS_EVIDENCE_UPDATE.json`
- Driver: `scripts/run_ssc_v1_0_1_g2_dev002_population.py`

## Test evidence

Command (narrow G14 regression):

```
python -m pytest tests/test_ssc_dev002_h1_metadata_manifest.py \
  tests/test_ssc_g2_dev002_warmup_remediation.py \
  tests/test_session_sweep_continuation_replay_determinism.py \
  tests/test_svos_ssc_adapter.py tests/test_svos_historical_runner.py \
  tests/test_svos_mt5_isolation.py tests/test_svos_optimization_admission.py \
  tests/test_svos_optimization.py tests/test_g2_population_identity.py \
  tests/test_first_canonical_population_validation.py \
  tests/test_ssc_proposal_pipeline.py tests/test_svos_lifecycle.py \
  tests/test_svos_context_export.py tests/test_svos_context_authority.py \
  -q --tb=short
```

Result: `98 passed`. Environment: Windows, Python 3.14 venv. No live/deferred checks.
