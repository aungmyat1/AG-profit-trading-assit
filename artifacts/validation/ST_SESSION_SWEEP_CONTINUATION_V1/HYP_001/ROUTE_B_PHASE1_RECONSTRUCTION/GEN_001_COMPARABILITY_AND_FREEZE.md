# GEN_001 Phase 1 Comparability (P4) and Freeze (P5)

## P4 — comparability vs historical original

Historical original: `artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_001/canonical_lifecycle_population.json`
(on `main`, 31 records).

Reconstructed: `_CHECKPOINTS/GEN_001_RUN_1.json` (this mission, occurrence-identity fields only,
no outcome/gross_R/net_R computed or read).

```
reconstructed_count = 31
historical_count    = 31
trade_id sets equal = true (zero missing, zero extra)
field checks (direction, entry_price, stop_price vs initial_stop, entry_time): 0 differences across all 31 matched occurrences
```

Classification: **EXACT_MATCH** on `historical_occurrence_identity` vs `reconstructed_occurrence_identity`
(direction/entry_time/entry_price/stop/setup membership identical for all 31 occurrences).

`reconstructed_population_hash` (`1b6cda1733e8d0edb2dfb90ed092ab3445543ff01bce97d52ad5d04256609285`) differs from
`historical_population_hash` (`8e32a7498e5a1c7df6658e6700ff3386fb38821ed189619a20224ce032d9166d`) **only** because the
reconstructed record schema adds `replay_evidence_enrichment` fields absent from the historical lifecycle schema
(`reference_high`, `reference_low`, `h1_bias`, `h1_bias_confidence`, `decision_timestamp`, `post_entry_m1_reference`,
`session_pair`, `trading_date`) and omits outcome fields (`gross_R`, `net_R`, `friction_R`, `events`, `final_state`)
deliberately per this mission's scope. Per P4's own instruction, this is an acceptable, expected hash divergence
because economic occurrence identity is unchanged (EXACT_MATCH above) — not `MATERIAL_OCCURRENCE_DRIFT`.

`PHASE1_STATUS` contribution: not blocked.

## P5 — freeze

```
GEN_001_RECONSTRUCTED_POPULATION_HASH = sha256:1b6cda1733e8d0edb2dfb90ed092ab3445543ff01bce97d52ad5d04256609285
GEN_001_OCCURRENCES = 31 (matches expected)
dataset_hashes = {H1: f1b456e4..., M15: 7f750293..., M1: 55422a1c..., symbol_metadata: sha256:f1b456e4...}
lookahead_violations = [] (none)
```

## P6 — determinism proof

```
run1_population_hash = sha256:1b6cda1733e8d0edb2dfb90ed092ab3445543ff01bce97d52ad5d04256609285
run2_population_hash = sha256:1b6cda1733e8d0edb2dfb90ed092ab3445543ff01bce97d52ad5d04256609285
hashes_equal          = true
counts_equal          = true (31 == 31)
occurrence_order_equal = true
dataset_hashes_identical = true (same frozen H1/M15/M1/symbol_metadata inputs, same implementation --
                                  RUN_1 and RUN_2 executed inside the same monolithic process, same
                                  code path, per amended runtime instruction)
checkpoint_file_sha256_identical = true (byte-for-byte identical JSON: e804f6673e4088e4e638bd80e112ea2009908efed1ba67eefef8ef674e22705c)
```

`GEN_001_DETERMINISTIC = true`. No third execution launched (RUN_1/RUN_2 pair sufficed, per instruction).
