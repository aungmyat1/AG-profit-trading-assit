# Existing-Artifact Recovery Search (P2)

Read-only search performed across `main`'s current worktree, committed history (`git log --all`), and the `refactor/architecture-boundary-hardening-v3` branch (read via `git show <branch>:<path>`, no checkout/merge/cherry-pick).

## Search 1 — repo-wide grep for `reference_high` across all local branches

```
git grep -l "reference_high" <branch> -- artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/
```
run for every local branch (`main`, `origin`, `origin/main`). **Result: zero per-trade occurrence records contain `reference_high` anywhere in any branch** — only this mission's own governance documents (`OUTCOME_RESOLVER_CONTRACT.md`, `STRATEGY_IDENTITY_MANIFEST.md`, `EXECUTION_MANIFEST.md`) and two discussion documents (`HYP_001_POST_V1_0_1_PREREGISTRATION_REASSESSMENT.md`, `V1_0_1_REMEDIATION_MANIFEST.json`) reference the term at all, and none of them store per-occurrence values.

## Search 2 — richer population artifacts on the refactor branch

`git ls-tree -r refactor/architecture-boundary-hardening-v3` revealed a richer, previously-unexamined artifact set under `artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/{GEN_001,GEN_002A}/`, including `canonical_lifecycle_population.json`, `per_trade_results.csv`, `input_manifest.json`, `manifest.json`, `g0_g1_validation.json`, `canonical_replay_determinism.json`.

**Inspected directly (`git show`, read-only):**
- `GEN_001/canonical_lifecycle_population.json` — 31 records, schema: `direction, entry_price, entry_time, events[], final_state, friction_R, gross_R, initial_risk, initial_stop, net_R, remaining_quantity, resolution_time, strategy_id, strategy_version, symbol, trade_id`. **No `reference_high`/`reference_low`.**
- `GEN_001/per_trade_results.csv` — richer columns (`mfe_R, mae_R, time_to_1r/2r/3r_minutes, exit_reason, trend_regime, volatility_regime, session, higher_timeframe_bias, ...`) but **still no session-box boundary columns**.
- `GEN_001/input_manifest.json` — **does** provide the exact raw dataset identity (see `RAW_DATA_INVENTORY.md`), which is the actually-useful recovery lead from this branch, not a shortcut around regeneration.

**Conclusion:** no artifact anywhere (any branch, any commit reachable from local refs) is `RECOVERY_ROUTE_A_EXISTING_ARTIFACT`-eligible. Route A is **not available** for any of GEN_001/GEN_002A/GEN_002. This is not a main-vs-branch access problem — the richer branch-only files were checked directly and confirmed to lack the required geometry too.

## Search 3 — session-snapshot / MarketSnapshot / campaign-entry ledgers

No dedicated `MarketSnapshot`, session-box, or campaign-entry ledger artifact (distinct from the population files above) was found for GEN_001/GEN_002A/GEN_002 in this search. `state/proposal_ledger/proposal_ledger.json` was not inspected as part of this read-only search since it is unrelated to historical research populations (it is the live proposal-tracking ledger, a different subsystem).
