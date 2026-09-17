# SSC_V1_0_1_CORRECTED_CONTROL_BASELINE_V1 — Execution Attempt

## P0/P1 — Preregistration and strategy fingerprint verification: PASS

- Preregistration commit `2300d007ce2450b86d0ef52c3f6c73b7c8e99af8` verified present.
- Preregistration fingerprint re-verified: `sha256:4a784f47a8979f891bc48be0ab492e5667726f9bbd2db40def6cbaec83c98232` — exact match.
- Current strategy fingerprint re-verified against all 7 preregistered hashes (`outcome_resolution.py`, `strategy.yaml`, `session_sweep_continuation/__init__.py`, adapter, `decision.py`, `export_ssc_svos_context.py`, `strategy_lifecycle.yaml`) — **all 7 identical, zero drift** since preregistration.
- `CONTROL_ID = SSC_V1_0_1_CONTROL_3R`, `runner_target_r = 3.0`, resolver semantic `OPPOSITE_SESSION_BOUNDARY` — loaded from the frozen contract, not reinferred from this mission's prompt.

## P4 — Friction verification: PASS

Loaded exactly the preregistered contract (EURUSD 1.0/0.2/0.3 pips, GBPUSD 1.4/0.2/0.4 pips spread/commission/slippage, both `MODELED`). No new value introduced.

## P2/P6 — Dataset / occurrence-population loading: **BASELINE_EXECUTION_ERROR**

Per the frozen amendment's own `next_gate` description, this experiment is *"a read-only re-derivation over already-frozen historical occurrence populations (GEN_001/GEN_002A/GEN_002) through the corrected `resolve_campaign_entry()`"* — i.e. reusing each occurrence's already-detected entry/setup/stop/reference-boundary data, re-running only the outcome-resolution step, not fresh setup detection from raw candles.

**Direct inspection of every population artifact reachable from `main` (this mission, read-only):**

| Population | File(s) inspected | `reference_high`/`reference_low` present? |
|---|---|---|
| GEN_002A (GBPUSD, N=15 per `population_manifest.json` — see note below) | `HYP_001_GBPUSD_REPLICATION_R1/POPULATION/canonical_population.json` | **No** — records contain `entry_price`, `initial_stop`, `initial_risk`, `events[]`, `final_state`, `gross_R`/`net_R`/`friction_R`, but no session-box boundary fields |
| GEN_002 (EURUSD, N=21) | `HYP_002_FAILURE_DECOMPOSITION/occurrence_level_decomposition.json` | **No** — records contain `entry_time`, `direction`, `h1_bias`, `regime`, `setup`, `mfe_R`/`mae_R`/`net_R`, but no session-box boundary fields |
| GEN_001 (EURUSD, N=31) | `EXP_EXPOSURE_EFFICIENCY_V1/*` | **Not accessible at all** — confirmed absent from `main`'s working tree; exists only on the unmerged branch `refactor/architecture-boundary-hardening-v3` (already flagged as an execution-time prerequisite in the preregistration itself) |

A repo-wide search (`grep -rl "reference_high\|reference_low\|box_high\|box_low"` under `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/`) confirms these fields exist only in two governance/discussion documents, never in any per-trade population record.

**Consequence:** `resolve_campaign_entry(entry_time, entry_price, stop_price, reference_high, reference_low, runner_target_r, partial_pct, runner_pct, subsequent_candles, session_exit_time, friction)` cannot be called for any stored occurrence — the required `reference_high`/`reference_low` arguments (needed specifically to compute the corrected `OPPOSITE_SESSION_BOUNDARY` partial target) do not exist in any artifact currently reachable from `main`, and neither does the `subsequent_candles` raw M15 series needed to re-walk each occurrence's own post-entry window.

**Note on GEN_002A's own internal inconsistency (observed, not resolved):** `population_manifest.json` states `"economics_computed": false` and *"No net_R/gross_R/expectancy/profit_factor/drawdown computed or stored in this artifact"*, yet `canonical_population.json`'s own records already contain `gross_R`/`net_R`/`friction_R` fields (computed under the v1.0.0 buggy resolver, per the `strategy_version: "1.0.0"` stamp on every record). This is a pre-existing documentation/artifact mismatch in the repository, not something introduced or repaired by this mission.

**Path not taken, and why:** re-deriving `reference_high`/`reference_low` by re-running full Asian/session-box construction and setup detection from raw H1/M15/M1 candles would produce a valid corrected-CONTROL population, but it is a materially larger scope than the preregistered "outcome-only re-derivation over already-frozen occurrences" (`POPULATION_MANIFEST.md`, `CONTROL_CONTRACT.md`) — attempting it here would silently redesign the experiment, which this mission's own top-level instruction explicitly forbids ("Do NOT redesign the experiment"). No code was patched, no fresh replay was run, no economics were approximated or fabricated as a workaround.

## Terminal classification

```
BASELINE_EXECUTION_ERROR
```
Per the frozen terminal vocabulary: *"Replay cannot complete because of technical/runtime/data-processing failure."* This is not a profitability judgment and is not `BASELINE_CONTRACT_CONFLICT` (no semantic contradiction was found — the resolver semantic itself is correct and consistently represented; the blocker is missing input data for the preregistered minimal-scope re-derivation method).

## Execution count

```
CONTROL_EXECUTION_COUNT (valid, economics-producing) = 0
attempted_executions = 1
attempt_outcome = GENUINE_TECHNICAL_FAILURE_BEFORE_VALID_EVIDENCE (per P5's own stated rerun-exception clause)
```
No rerun was performed within this mission. No parameter, filter, threshold, friction value, or population was changed in response to this finding.

## Firewalls maintained

`HYP_001_TREATMENT_EXECUTED = false`, `CONFIRM_001_ACCESSED = false`, `OOS_ACCESS_COUNT = 0`, `FINAL_HOLDOUT_ACCESSED = false`, `PROSPECTIVE_EVIDENCE_CONSUMED = false`, `ECONOMIC_RESULTS_CONSUMED = false` (no economics were computed at all, so none could be consumed).

## Next safe action (recorded as observation only, not authorized)

`POST_CONTROL_OBSERVATION_NOT_AUTHORIZED_FOR_CURRENT_HYPOTHESIS`: a future, separately-scoped and separately-preregistered mission would need to either (a) obtain `reference_high`/`reference_low` and `subsequent_candles` for each existing occurrence (if such a richer artifact exists on the unmerged branch or elsewhere, not yet located), or (b) explicitly preregister a full fresh-replay-based re-derivation (a larger scope change) as its own experiment. Neither is authorized or attempted here.
