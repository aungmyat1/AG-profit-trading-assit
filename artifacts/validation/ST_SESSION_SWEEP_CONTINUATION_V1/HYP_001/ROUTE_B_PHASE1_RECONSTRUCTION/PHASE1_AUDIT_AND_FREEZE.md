# Phase 1 Independent Audit and Freeze (RB-R6 / RB-A0)

Completes the takeover mission's Phase 1 obligations: confirms the freeze of the
reconstructed occurrence population and performs the independent audit pass required
before the corrected CONTROL may execute.

The frozen population files (`GEN_001/reconstructed_occurrence_population.json`,
`GEN_002A/reconstructed_occurrence_population.json`, and the four `_CHECKPOINTS/*.json`
run files) were **not** modified by this audit — read-only verification only.

## R0 — Takeover (reconciliation)

- branch = `main`, HEAD = `c57406cab1a6f9d5af177d4924c1f82738a6c9be`
- Prior PIDs (17624 / 984): no live Python process writing Route B files at takeover.
  `TAKEOVER_STATUS = COMPLETE` (not `BLOCKED_ACTIVE_ROUTE_B_WRITER`).
- Reconstruction script uncommitted delta = checkpointing wrapper only (37 insertions,
  2 deletions); `reconstruct_generation` logic unchanged from HEAD. Persistence-only
  change; no semantic change.

## Independent re-verification (this mission, fresh recomputation)

A standalone read-only verifier recomputed every hash from the actual artifact bytes
and re-derived occurrence identity from the historical originals:

| Check | GEN_001 | GEN_002A |
|---|---|---|
| historical_count | 31 | 57 |
| reconstructed_count | 31 | 57 |
| RUN_1 hash == RUN_2 hash | true | true |
| hash matches frozen authority | true | true |
| final-file hash matches | true | true |
| trade_id sets equal (missing/extra) | 0 / 0 | 0 / 0 |
| field diffs (direction/entry_time/entry_price/stop) | 0 | 0 |

Combined: `COMBINED_OCCURRENCES = 88`, combined population hash
`e21ed545b076b157139eca22c03e3efdd0870eef83e3889a9b9febd317e3683e` (recomputed, matches).

## RB-A0 audit points

1. Admitted dataset identities — **verified** (H1/M15/M1 sha256 match the Route B
   preregistration admission docs exactly).
2. Population counts — **verified** (31 / 57 / 88).
3. Original-vs-reconstructed comparability — **EXACT_MATCH** (identity fields only).
4. GEN_001 31/31 EXACT_MATCH — **pass**.
5. GEN_002A 57/57 EXACT_MATCH — **pass**.
6. Zero material occurrence drift — **pass** (hash divergence is schema-only: added
   `replay_evidence_enrichment` fields, omitted outcome fields).
7. RUN_1/RUN_2 determinism — **pass** (byte-equal hashes, counts, and ordering).
8. H1-bias authority — `RESOLVED_IDENTICAL` (commit-level audit in preregistration,
   superseding the earlier `CONTRACT_AMBIGUOUS` flag).
9. Corrected v1.0.1 semantic authority — **verified** (`version: 1.0.1`,
   `runner_target_r: 3.0`, `OPPOSITE_SESSION_BOUNDARY`).
10. Exit-policy independence — **true** (membership independent of runner target; see
    causality block below).
11. No lookahead — **true** (`lookahead_violations = []`; structurally enforced).
12. No holdout access — **true** (historical datasets only, through 2026-07-31).
13. No CONTROL/TREATMENT contamination — **true** (Phase 1 discarded all outcome
    fields; no R computed).

## Causality (P7 firewall)

- `EXIT_POLICY_INDEPENDENT = true`
- `RUNNER_TARGET_CONSULTED = false` (occurrence membership does not depend on
  `runner_target_r`; verified in `replay.py` control flow: `runner_target_r` is only
  passed to `resolve_campaign_entry` strictly after setup/stop/entry resolution).
  Transparency note: `run_replay` is monolithic and internally passes `runner_target_r
  = 3.0` into the outcome math the reconstruction then discards
  (`runner_target_consulted_by_internal_outcome_math = true` in the summary JSON) —
  this does not affect membership, consistent with `PAIRED_OCCURRENCE_PROOF.md`.
- `LOOKAHEAD_DETECTED = false`

## Classification

```
PHASE1_STATUS = RECONSTRUCTED_POPULATION_FROZEN
PHASE1_AUDIT  = PASS
```

Proceed to corrected CONTROL admission (RB-C0).
