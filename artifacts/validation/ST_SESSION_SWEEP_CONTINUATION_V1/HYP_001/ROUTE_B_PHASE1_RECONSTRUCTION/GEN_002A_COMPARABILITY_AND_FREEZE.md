# GEN_002A Phase 1 Comparability (P4) and Freeze (P5)

## P4 — comparability vs historical original

Historical original: recovered read-only via `git show a608cf5:artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_002A/canonical_lifecycle_population.json`
(not on `main`'s working tree; commit-only, 57 records; `admission_reason`/`decision_snapshot`/`post_entry_path_ref`
fields all null in the historical original -- confirms the recovery audit's own finding that reference_high/low
were never captured historically for this population).

Reconstructed: `_CHECKPOINTS/GEN_002A_RUN_1.json` (occurrence-identity fields only, no outcome/gross_R/net_R).

```
reconstructed_count = 57
historical_count    = 57
trade_id sets equal = true (zero missing, zero extra)
field checks (direction, entry_price, stop_price vs initial_stop, entry_time): 0 differences across all 57 matched occurrences
```

Classification: **EXACT_MATCH** on `historical_occurrence_identity` vs `reconstructed_occurrence_identity`.

`reconstructed_population_hash` (`b5a77c4951b0f8ecaf4308e8421087ff3bd4f240ddf31e3326b536989d5f63e7`) differs from
`historical_population_hash` (`2a2fb946f995805ccc56342a712376ccf5ee9fb1e324fa383e7d08c5d3e54fd8`) for the same
reason as GEN_001 -- `replay_evidence_enrichment` fields added, outcome fields omitted -- not `MATERIAL_OCCURRENCE_DRIFT`.

## P5 — freeze

```
GEN_002A_RECONSTRUCTED_POPULATION_HASH = sha256:b5a77c4951b0f8ecaf4308e8421087ff3bd4f240ddf31e3326b536989d5f63e7
GEN_002A_OCCURRENCES = 57 (matches expected)
dataset_hashes = {H1: a82275bc..., M15: 11929912..., M1: 390798de..., symbol_metadata: sha256:a82275bc...}
lookahead_violations = [] (none)
```

Determinism (P6) pending GEN_002A/RUN_2 completion in the same live process.
