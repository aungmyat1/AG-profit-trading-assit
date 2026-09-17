# Population Comparability Contract

Future corrected CONTROL and the (still-frozen, unexecuted) HYP_001 TREATMENT evaluation must use an identical admissible population unless an already-preregistered exclusion applies. Frozen identical:

- Same dates (GEN_001/GEN_002A/GEN_002 as identified in `POPULATION_MANIFEST.md`)
- Same symbols (EURUSD for GEN_001/GEN_002, GBPUSD for GEN_002A)
- Same session definitions (ASIAN_LONDON / LONDON_NEWYORK, byte-identical `session_pairs`/`trade_session` windows)
- Same source hashes (population_hash for GEN_001; canonical_population.json for GEN_002A; occurrence_level_decomposition.json for GEN_002)
- Same setup-generation universe (S1/S2/S3, byte-identical entry/setup/regime/stop logic — CONTROL and TREATMENT are two exit policies applied to the SAME frozen occurrence population, not independent samples, per `HYP_001_EXIT_CAPTURE_PREREGISTRATION.md`'s own established method)
- Same friction model (byte-identical `friction` config section)
- Same resolver semantics (the corrected `resolve_campaign_entry`, `OPPOSITE_SESSION_BOUNDARY`)
- Same ambiguity policy (`AMBIGUOUS_SEQUENCE_NO_ASSUMED_INTRABAR_ORDER`)

**Only `runner_target_r` may differ** in the later CONTROL-vs-TREATMENT experiment (3.0 vs. 1.5) — no other dimension may vary between the two arms.
