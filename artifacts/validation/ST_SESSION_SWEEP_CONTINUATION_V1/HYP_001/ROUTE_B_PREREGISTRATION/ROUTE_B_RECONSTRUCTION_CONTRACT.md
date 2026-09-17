# Route B Reconstruction Contract (RB-G3–G6) — preregistered only, NOT executed

## RB-G3 — `CAUSAL_OCCURRENCE_RECONSTRUCTION` (Phase 1)

A future, separately-executed mission must:
1. Consume only the hash-admitted datasets in `GEN_001_ADMISSION.md`/`GEN_002A_ADMISSION.md` (plus GEN_002's already-fully-admitted in-repo triplet from the prior recovery audit) — no substitution, no window change.
2. Use the frozen historical strategy/config authority confirmed identical in `H1_BIAS_AUTHORITY.md` (same `h1_bias.py`, `bias_gate.py`, `replay.py` mechanism as current HEAD; current `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` + corrected `outcome_resolution.py`, per `STRATEGY_IDENTITY_MANIFEST.md`).
3. Reproduce setup eligibility causally — re-run `entry_2_sweep`/S1/S2/S3 evaluation exactly as the original generation scripts did, using only candles available at each historical decision timestamp (no lookahead — enforced structurally by the existing `run_replay` control flow, unchanged).
4. Reconstruct and freeze, per occurrence: occurrence identity, direction, entry timestamp, entry price, initial stop, initial risk, `reference_high`, `reference_low`, and the complete required post-entry M1 candle path (or a deterministic hash/pointer to it).
5. Preserve GEN population separation (GEN_001/GEN_002A/GEN_002 remain three distinct, separately-fingerprinted populations — never merged).
6. Make no exit-target optimization decisions during this phase — `runner_target_r` is not consulted at all in Phase 1, consistent with `PAIRED_OCCURRENCE_PROOF.md`'s own code-line evidence from the prior recovery audit.
7. Generate `RECONSTRUCTED_OCCURRENCE_POPULATION_HASH` and freeze it **before** any CONTROL or TREATMENT outcome is calculated.

## RB-G4 — Corrected CONTROL replay contract (Phase 2, CONTROL only)

Only after Phase 1's population hash is frozen, a future mission may run:
- SSC v1.0.1, `runner_target_r = 3.0`, `OPPOSITE_SESSION_BOUNDARY` (LONG→`reference_high`, SHORT→`reference_low`), identical stop/entry/setup logic, the frozen Phase-1 population.
- No tuning. CONTROL outcomes only. **The 1.5R treatment must not be calculated in the same execution mission.**

## RB-G5 — Treatment firewall

```
CONTROL runner  = 3.0R
TREATMENT runner = 1.5R
occurrence_population_hash_CONTROL MUST EQUAL occurrence_population_hash_TREATMENT
```
Per `PAIRED_OCCURRENCE_PROOF.md`, this equality is provably achievable (runner_target_r has zero upstream code dependency). A future treatment run must not regenerate occurrences, and must not alter setup eligibility, H1 bias, regime classification, entry, stop, session references, occurrence ordering, or dataset — only the exit-capture treatment dimension may differ.

## RB-G6 — Evidence classification

Any Route B reconstruction, once executed, is `DEVELOPMENT_EVALUATION` / `HYPOTHESIS_GENERATION`-role evidence for HYP_001 — it must **not** silently become fresh prospective confirmation, `CONFIRM_001`, final holdout evidence, or Demo authorization evidence by itself. The existing HYP_001 prospective-evidence requirements (fresh data no earlier than `2026-09-15T00:00:00Z`, `CONFIRM_001` no earlier than `2026-10-13T00:00:00Z`) are unaffected and unchanged by this preregistration.

**Nothing in this contract is executed by this mission.**
