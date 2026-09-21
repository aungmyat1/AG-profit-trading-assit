# Mission 1 Implementation Materials — SSC ONE-YEAR REPLAY DATA AUTHORITY + WARMUP READINESS

Companion package for `AG_mission1_final_prompt.md`. Every artifact here was derived from
the actual repo at HEAD `c995f08` on 2026-09-21; values were computed from bytes and the
two patches were **verified by applying them and running the affected tests**.

## Contents

```
mission1_materials/
├── README.md                        ← this file: contents, usage, provenance
├── MISSION_CHECKLIST.md             ← fill-in tracking sheet (P0–P8 + final classification)
├── values/
│   └── DEV002_VERIFIED_VALUES.md    ← verified hashes, fingerprint formula proof,
│                                      pre-computed remediated values, 9-file reference inventory
├── patches/                         ← machine-generated unified diffs (git apply)
│   ├── P1_dev002_remediation.patch       YAML rebinding + dataset_manifest.json recompute
│   │                                     + test-constant split  → manifest tests 3/3 PASS (verified)
│   └── P1_5_governance_test_fix.patch    unsigned-contract scenario constructed explicitly
│                                         + signed-gate no-bypass test → PASS (verified)
├── templates/                       ← commit-ready JSON artifacts (fill <FILL> fields)
│   ├── DEV002_H1_MANIFEST_REMEDIATION_V1.json
│   ├── GEN_002_QUARANTINE_RECORD_V1.json
│   ├── ONE_YEAR_REPLAY_STACK_V1.schema.json        (P2/P8 manifest schema + annotated example)
│   └── SSC_ONE_YEAR_REPLAY_CONTRACT_V1.template.json (R5 for MISSION 2 — do not use in Mission 1)
└── code/                            ← integration-ready DRAFTS (repo APIs verified)
    ├── cross_leg_timebase_arbiter.py        P3 — bucketing + bounded shift scan + DST adjudication
    ├── test_cross_leg_timebase_gate.py      P3 — 6 synthetic tests (the 5 required cases + API invariant)
    ├── build_ssc_v1_0_1_one_year_replay_stack.py  P2 — read-only admission builder + freeze emitter
    └── test_warmup_convergence_gate.py      P4 — VA2 convergence proof skeleton
```

## How to use (order)

1. **P0** — fill `MISSION_CHECKLIST.md` preflight.
2. **P1** — re-verify `values/DEV002_VERIFIED_VALUES.md` from bytes, then
   `git apply patches/P1_dev002_remediation.patch`; commit the filled remediation record.
3. **P1.5** — `git apply patches/P1_5_governance_test_fix.patch`.
4. **P3 first, then P2** — drop the arbiter into `src/historical_replay/timebase_arbiter.py`
   (adjust the test import if placed elsewhere), get its 6 tests green, then adapt the P2
   builder script to `scripts/` and run it with `--check` until all gates PASS.
5. **P4** — finalize the warmup test's two TODO points (decision enumeration, stack manifest
   binding) and reach `WARMUP_STABLE`.
6. **P5–P6** — quarantine record + firewall counters.
7. **P7** — verification exactly as checklist; do not repair unrelated failures.
8. **P8** — freeze `ONE_YEAR_REPLAY_STACK_V1` (builder writes it when run without `--check`).

## Provenance & verification log

| Material | Verification performed |
|---|---|
| P3 arbiter + synthetic tests | copied into live repo, run against real `Candle` — **7/7 PASS** (after fixing a season-lumping defect in the DST criterion) |
| P1 patch | applied → `test_ssc_dev002_h1_metadata_manifest.py` **3/3 PASS**; repo restored clean |
| P1.5 patch | applied → governance invariance tests **PASS**; repo restored clean |
| Combined fingerprint `55cffa7c…` | formula validated by reproducing the old value `05b05972…` exactly |
| Bytes stability of DEV002 H1 | `git show f66d555:<path>` hash == working-tree hash |
| Arbiter/builder/warmup drafts | written against verified APIs: `utc_export_csv_loader.load_utc_export_csv`, `HistoricalCandleStore.load_series`, `warmup_readiness.closed_h1_bar_count`, `resolve_h1_market_bias(h1_store, manifest, symbol, decision_time, session_pair)`, `evaluate_economic_gate(...)` |
| R3 numbers in quarantine template | transcribed from `SSC_V1_0_1_ONE_YEAR_HISTORICAL_REPLAY_STATUS.md` (best shifts +3h, rates 0.783602/0.778562, tautological parity_diagnostic) |

## Known limitations (honest fine print)

- **P3 code is verified end-to-end:** `cross_leg_timebase_arbiter.py` +
  `test_cross_leg_timebase_gate.py` were copied into the live repo and run against the
  real `strategy_engine.session.Candle` type — **7/7 PASS** (initial draft had a
  season-lumping defect in DST detection; fixed with a per-bucket bimodal-shift census
  before release). P2 builder and P4 warmup test compile and are written against verified
  API signatures, but still need the agent's path/TODO finalization and a dev-box run.
- The composer_replay/td8e tests, after P1, no longer fail on fingerprints; their residual
  Linux failures are the separate runtime-MT5 marking category (WP0.2 of the portability
  work). On the Windows dev box they are expected green — the agent must confirm.
- `EXTERNAL_D_ROOT` sources live on the dev machine only; the stack builder expects the
  warmup H1 to be packaged into the repo (UTC-normalized) before freezing.
- Nothing in this package executes a replay, touches protected data, or changes strategy
  semantics — same boundary as the mission itself.
