# Research contract — ST_SESSION_SWEEP_CONTINUATION S2 (breakout/displacement continuation)

Status: **DEFINED, NOT RUN.** No candidate ID exists yet. No results, metrics, hashes,
or trade counts from any prior external narrative (`CANDIDATE_V1_4_S2_REGIME`,
`CANDIDATE_V1_5_S2_CLEAN` — both `NON_AUTHORITATIVE_EXTERNAL_NARRATIVE`) are used
anywhere in this contract or may be used to seed the future run.

This document specifies the boundary policy a future, separately-authorized research
task must follow when it actually runs. Writing this file performs no research,
computes no metric, and creates no candidate.

## Hypothesis family

`ST_SESSION_SWEEP_CONTINUATION` S2 setup only (breakout/displacement continuation),
over its existing frozen `v1.0.0` reference implementation
(`src/session_sweep_continuation/`) — see
`docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md` and the
`PLAN2_CANONICAL_OBSERVATION_PARITY` artifact for why this is the architecture's
proven reference strategy. A future S2-focused candidate is a **new version**, never
a mutation of `v1.0.0`'s frozen, already-evaluated evidence.

## Dataset splits (predeclared, not chosen post-hoc)

Reusing the existing dataset manifests already on file
(`config/historical_datasets/ST_SESSION_SWEEP_CONTINUATION_V1_EURUSD_PACKAGE.yaml`)
where their coverage applies; any additional data acquired for TRAIN/VALIDATION must
follow the same manifest-fingerprint convention (`config/historical_datasets/*.yaml`).

```
TRAIN       : research start of available EURUSD H1/M15/M1 coverage -> a predeclared
              cutoff set BEFORE any run starts, never chosen after seeing results.
VALIDATION  : a predeclared window strictly after TRAIN's cutoff, used only to select
              among candidates already generated from TRAIN -- never used to tune.
PROSPECTIVE : real forward market data acquired only after a candidate from this
              family is frozen. Never historical. Never touched before freeze.
```

Required invariant, checked mechanically before any candidate from this family may
enter `src/external_candidate/admission.py`:

```
TRAIN_max_timestamp < VALIDATION_min_timestamp < PROSPECTIVE_activation_timestamp
```

## Strategy specification requirements

- Exact entry/exit/direction/regime/session/filter/SL/TP/management rules, in the
  same structured form `src/external_candidate/models.py::REQUIRED_RULE_SECTIONS`
  already requires (no new schema).
- No parameter may be filled from this document, chat, or narrative text — every
  parameter must come from the actual frozen run's own recorded config.

## Friction requirements

Must state spread/commission/slippage/funding explicitly (`FrictionAssumptions`,
already implemented) — reuse `performance/cost_model.py`'s one signed scenario
(`CONTRACT_CEILING`) as the comparison baseline via
`external_candidate/friction.py::classify_friction_compatibility()`. No new friction
scenario may be invented for this family.

## Ledger requirements

Signal and trade ledgers must be produced as real files (Parquet, via
`research_external/tooling/artifact_io.py`, or an equivalent write→reopen→hash-twice
verified format) — never estimated, summarized, or narrated. Every SHA-256 recorded
for this family must satisfy the same rule already proven in
`research_external/runs/ARTIFACT_PROOF_001/` and `REAL_DATA_PROOF_001/`: computed
from actual bytes, reproduced on a second read, never typed by hand.

## Freeze requirements

Once a candidate from this family is selected from VALIDATION-ranked TRAIN
candidates, it must be frozen (`candidate_frozen: true`, immutable rules/parameters)
before any prospective/forward data is ever read. Freezing before opening prospective
data is the same discipline the mission's holdout-sealing rule already requires for
any out-of-sample evidence.

## Package requirements

Export as `AG_EXTERNAL_CANDIDATE_PACKAGE_V1` (`src/external_candidate/models.py` —
reused unmodified) and run through the existing
`src/external_candidate/admission.py::validate_external_candidate_package()` before
any parity/OOS/walk-forward/friction evaluation proceeds.

## What this contract explicitly forbids

- Populating this document, or any future package built from it, with the
  `CANDIDATE_V1_4_S2_REGIME` / `CANDIDATE_V1_5_S2_CLEAN` metrics, hashes, trade
  counts, or freeze timestamps circulated earlier — those remain
  `NON_AUTHORITATIVE_EXTERNAL_NARRATIVE` permanently, not a starting point.
- Running TRAIN optimization automatically as a continuation of this document. That
  requires its own separate, explicitly-authorized task.
