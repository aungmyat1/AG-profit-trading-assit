# research_external/ — local, artifact-first research workspace

Recorded: 2026-09-12 (AG_LOCAL_RESEARCH_BOOTSTRAP_V1)

## Why this exists

External narrative research (candidate identities, hashes, and metrics described in
conversation/prompt text, e.g. `CANDIDATE_V1_4_S2_REGIME`, `CANDIDATE_V1_5_S2_CLEAN`)
was never backed by any physical artifact in this repository — verified by direct
file search, twice. Per this project's own governance discipline, a candidate is only
real once real bytes exist and hash to what is claimed. This directory exists to
produce that evidence locally, so no future research run can be lost to an external
handoff failure again.

```
CANDIDATE_V1_4_S2_REGIME = NON_AUTHORITATIVE_EXTERNAL_NARRATIVE
CANDIDATE_V1_5_S2_CLEAN  = NON_AUTHORITATIVE_EXTERNAL_NARRATIVE
```

Neither identity's hashes, metrics, trade counts, freeze status, or candidate status
may be imported into any authoritative evidence file. They may remain referenced here
only as research notes explaining why this workspace was built.

## What this is not

- Not a strategy optimizer. No VectorBT/Optuna/NautilusTrader/Freqtrade/LEAN/ML/RL
  integration exists or is planned here without a separate, explicit task.
- Not a second validation framework. `src/external_candidate/` (candidate schema,
  admission, parity, OOS, walk-forward, friction, evidence envelope) and
  `src/validation_framework/` (lifecycle, economic gate) remain the sole promotion
  authority. Nothing here can admit a candidate, evaluate R6, or change lifecycle
  state.
- Not an execution surface. Nothing in `research_external/` imports or can reach
  `MetaTrader5.order_send`, `execution_service.authorize_demo_execution`, or any
  broker-mutation path — see `tooling/mt5_capture.py`'s own containment note.

## Structure

```
research_external/
    README.md
    runs/<run_id>/          -- one directory per research/proof run
        run_manifest.json
        proof.json | dataset manifests
        datasets/
        signals/
        trades/
        metrics/
        candidate/
    datasets/                -- reusable, deduplicated real-market dataset captures
    tooling/
        artifact_io.py       -- write/reopen/hash helpers (CSV, Parquet, JSON manifest)
        mt5_capture.py       -- real, closed-bar MT5 retrieval for research use only
```

## Hash rule

Every SHA-256 recorded anywhere under `research_external/` is computed from actual
file bytes on disk, via `tooling/artifact_io.py::sha256_of_file()` — the same
function every artifact in this workspace uses, and the value is always verified by
re-opening the file and recomputing before it is trusted. No hash is ever typed by
hand, copied from a prompt, or invented. See `runs/ARTIFACT_PROOF_001/` for the proof
this holds.

## Future research contract (defined, not yet run)

See `research_contract_S2.md` for the predeclared TRAIN/VALIDATION/prospective
boundary policy for the first real local hypothesis family
(`ST_SESSION_SWEEP_CONTINUATION` S2 breakout/displacement continuation). No results,
candidate ID, or metrics exist yet — running that research is a separate,
future, explicitly-authorized task.
