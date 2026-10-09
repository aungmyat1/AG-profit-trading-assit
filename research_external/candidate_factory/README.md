# AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 — Candidate Factory home

Recorded: 2026-10-07. Mission `AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1`.

This directory is the Candidate Factory's home, per the mission's instruction to reuse
`research_external/` rather than create a second research root. It does not replace or
modify `research_external/README.md`'s own existing scope (S2R baseline research), nor
`src/validation_framework/` (lifecycle/economic-gate vocabulary, unchanged, not extended
or re-signed here).

## What this mission is

A controlled, auditable DEV-stage screen that takes internal AG research-shadow
candidates (PR #33 `SESSION_TRADE_V2`, PR #34 `ST_MTF_CONTROL_SHIFT_V1`) and a small,
deliberately limited set of external/OSS strategy ideas through five identical gates
(G1 Contractable, G2 Ticketable, G3 Data/Venue Fit, G4 Causality/Warm-up, G5 Translation
Fidelity), a preregistered DEV replay, and a preregistered friction screen — ending in one
of `PROMOTE_TO_FREEZE_CAMPAIGN / HOLD_DATA / HOLD_COST / HOLD_SPEC /
HOLD_SAMPLE_REQUIRED / REJECTED` per candidate.

## What this mission is not

- Not EdgeLab. It does not run OOS, walk-forward, regime, or stability analysis, and does
  not touch any SEALED/FINAL_HOLDOUT dataset.
- Not a second validation framework, candidate schema, or replay engine where one already
  exists and works. (One documented exception: `src/external_candidate/` and `performance/`
  are referenced extensively by existing docs as already-built infrastructure but are not
  physically present anywhere in this repository's git history — see
  `data_capability_matrix.json` → `cross_cutting_findings`. This mission does not silently
  resurrect that name; the small modules under `replay/` are new, minimal, and separately
  named.)
- Not a promotion authority. `CONTRACT_FROZEN`, `LOGIC_VERIFIED`, and `EDGE_VERIFIED`
  remain `FALSE`/unset for every candidate here, regardless of verdict.
- Not a production dependency surface. See `tests/test_research_external_boundary.py`:
  no file under `src/` may import `research_external` at all.

## Structure

```
PREREG_CANDIDATE_FACTORY_R1.json   -- frozen BEFORE any replay; immutable; new PREREG_ID
                                       required for any policy change
PREREG_CANDIDATE_FACTORY_R1.sha256.txt
data_capability_matrix.json        -- what this checkout can actually replay today
internal_reference/                -- read-only byte-identical copies of PR #33 / PR #34
                                       source, each with its own PROVENANCE.json
replay/                            -- NEW, minimal replay harness (common.py, friction.py,
                                       one runner script per DEV-replayed candidate)
dev_replay/<run_id>/               -- run_manifest.json, decisions.csv, trades.csv,
                                       metrics.json, friction.json per executed replay
candidates/<ID>.json               -- full G1-G5 + SB-class + verdict record per candidate
CANDIDATE_TABLE.md                 -- one-page summary of every candidate's verdict
```

## Safety

`BROKER_MUTATION_COUNT=0`, `DEMO_AUTHORIZED=FALSE`, `LIVE_AUTHORIZED=FALSE`,
`AUTOMATED_EXECUTION=FALSE`, `OOS_DATA_TOUCHED=FALSE`,
`PRODUCTION_REGISTRY_CHANGED=FALSE` for the whole mission. No order submission, no broker
credential, no MT5/execution import anywhere under this directory.
