# Implementation Plan — Bringing the AG Profit Trading Backtest System to First Trustworthy Evidence

**Repo:** aungmyat1/AG-profit-trading-assit · **Date:** 2026-09-21 · **Companion doc:** `AG_backtest_system_readiness.md`
**Target:** complete one canonical, economically-scored one-year historical replay of
`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1 with all assurance gates machine-verified — the
capability the system was built for but has not yet achieved.

---

## How to execute this plan (repo conventions — non-negotiable)

Every work package below must follow the project's own mission discipline, as evidenced in
`docs/status/SSC_V1_0_1_ONE_YEAR_HISTORICAL_*_STATUS.md`:

1. **Mission record per WP** — R0 preflight (`branch`, `HEAD_BEFORE`, concurrent-writer check),
   `HEAD_AFTER`, dated status doc under `docs/status/`, registered in `docs/README.md`.
2. **Read-only by default** — data is never interpolated, manufactured, or M5-substituted;
   protected datasets (`CONFIRM_001`, `HOLDOUT`, `OOS`) are metadata-only, `access_count` asserted 0.
3. **Frozen things stay frozen** — strategy YAML, frozen contracts, and sealed evidence are never
   edited in place; corrections are new-versioned or remediated additively (the
   `V1_0_1_REMEDIATION/V1_0_1_REMEDIATION_MANIFEST.json` pattern).
4. **Every rolling-doc change follows** `docs/status/LIVE_STATUS_MAINTENANCE.md`
   (`PROJECT_STATUS.md` dated delta + `AG_VALIDATION_SYSTEM_ASSURANCE_V1_manifest.json` bump).
5. **Environment split:** WP code/tests run anywhere (Linux CI included, per the portability
   patch); data acquisition and replay execution happen on the Windows/MT5 dev box.

---

## Dependency graph (critical path in bold)

```
WP0.1 (DEV002 manifest remediation) ─┐
WP0.2 (test portability marks)       ├─► WP1.1 (single-source leg stack) ─► WP1.2 (quarantine GEN_002)
                                     │            │
                                     │            ▼
                                     └──► WP2.1 (freeze R5 contract) ─► WP2.2 (R6 canonical replay)
                                                                              │
            WP3.1 VA2 warmup ──────────────┐                                  ▼
            WP3.2 VA3 known-answer ────────┤                        WP2.3 (R7 determinism)
            WP3.3 VA6/VA7 machine evidence ├──► assurance re-classification   │
            WP3.4 VA8 walk-forward ────────┤                                  ▼
            WP3.5 VA9 reference engine ────┘                        WP2.4 (metrics R8–R13)
            WP3.6 VD capacity contracts ──► (independent)                    │
            WP4.1 session-box reconstruction ──► (fidelity, independent)     ▼
            WP4.2 friction evidence H2 ──► (after first replay)     WP5 (robustness battery)
```

Estimated total: **~3–4 weeks focused effort**; critical path (WP0.1 → WP1.1 → WP2.1 → WP2.2 → WP2.4)
is **~5–7 working days**.

---

# Phase 0 — Repo-state hygiene (1–2 days)

## WP0.1 — Remediate the DEV002 H1 dataset/manifest fingerprint mismatch 🔴 critical-path unblocker

**Established facts**
- Committed file `data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/EURUSD_H1.csv`
  = `sha256:9cb7c2da…`; bytes **unchanged since its single commit** `f66d555` ("SSC v1.0.1 G2:
  build DEV_002 H1-warmup remediation dataset + registry supersession").
- Its `dataset_manifest.json` declares `sha256:93d27d8c…` and embeds it in
  `combined_dataset_fingerprint_canonical_input`; test constant
  `EXPECTED_DEV002_H1_SHA256` in `tests/test_ssc_dev002_h1_metadata_manifest.py` repeats the manifest value.
- Conclusion: the manifest was frozen against pre-commit bytes. The file is the stable artifact.
- R3 of the one-year replay mission separately found this file **DST-mixed** (winter −1h / summer 0h)
  — so it is legacy development evidence only, never a future replay input.

**Steps**
1. Add remediation record under
   `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/V1_0_1_REMEDIATION/DEV002_H1_MANIFEST_REMEDIATION_V1.json`:
   both hashes, commit proof (`git show f66d555:<path> | sha256sum`), root-cause classification
   `MANIFEST_FROZEN_AGAINST_PRE_COMMIT_BYTES`, the DST-mixed finding, and the declaration that
   **content authority = committed bytes; the recorded fingerprint was wrong, the data was not modified**.
2. Re-freeze `dataset_manifest.json` per-file `EURUSD_H1.sha256 → 9cb7c2da…` and recompute
   `combined_dataset_fingerprint` from its canonical input string (recompute, don't hand-edit the hash).
   Add field `"manifest_remediation": "DEV002_H1_MANIFEST_REMEDIATION_V1"` for lineage.
3. Update `EXPECTED_DEV002_H1_SHA256` in the test with a comment citing the remediation record.
4. Verify downstream references: grep all manifests/ledgers for `93d27d8c` (G2 population, TD-8E event
   provenance). They reference DEV_002 *content*, which is unchanged — record that identity chain in
   the remediation doc rather than rewriting history.
5. Status doc: `docs/status/DEV002_H1_MANIFEST_REMEDIATION_STATUS.md`.

**Acceptance:** the 8 currently-red tests pass on Linux *and* Windows
(`test_ssc_dev002_h1_metadata_manifest` ×3, `test_topdown_composer_replay` ×7 chain incl. `test_td8e_*`);
`validate_manifest_for_dataset` passes; no other manifest references the old hash.

## WP0.2 — Finish test-portability marking (pairs with the already-delivered patch)

Mark `test_historical_replay_no_lookahead::test_stage2_entry_only_reuses_historical_data_not_live_mt5`
and the runtime-MT5 batch (`test_td6_*`, `test_raw_prospective_archive_partitions`,
`test_five_skill_runtime` live cases, `test_execution_mt5_gateway`, `test_post_asian_pilot` data-error
case, `test_proposal_envelope_execution_boundary` subprocess case) with `@pytest.mark.live_mt5` or
explicit monkeypatching — exactly the remedy `tests/conftest.py` prescribes.
**Acceptance:** `pytest -q` on a fresh Linux venv reports 0 unexpected failures (only owner-judgment
categories from WP1/WP3 remain if any), Windows baseline unchanged.

---

# Phase 1 — An admissible one-year dataset (2–4 days) — the true blocker

## WP1.1 — Canonicalize the single-source leg stack and promote the timezone check to a durable gate

**The solution already exists in-repo; it needs promotion, not invention:**
- M1 authority: `SSC_V1_0_1_HIST_1Y_M1_001` (373,421 bars, UTC-normalized,
  `50beb42a…`, `PASS_EXACT` parity vs canonical DEV_002 M1).
- H1/M15: `SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001` — deterministic exact-bucket aggregation of that M1
  (`derivation_class: AUTHORIZED_DETERMINISTIC_TIMEFRAME_AGGREGATION`, H1 6,241 rows,
  `reference_parity` exact_match_rate 1.0 vs the aligned external H1/M15). Single source of truth ⇒
  cross-leg timezone consistency **by construction**.
- Warmup: derived H1 starts 2025-09-14T21:00Z, so the required ≥1,000 pre-window closed H1 bars must
  come from the aligned warmup source `EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv`
  (+0h, DST-CONSISTENT, exact rate 1.000000 vs M1-derived buckets). Package it as a declared
  warmup-context dataset (model: `SSC_HYP002_H1_WARMUP_CONTEXT_…` manifest) with role
  `WARMUP_CONTEXT_ONLY`.

**Steps**
1. **New script** `scripts/build_ssc_v1_0_1_one_year_replay_stack.py` (deterministic, read-only):
   emits a frozen `ONE_YEAR_REPLAY_STACK_V1` manifest naming the three legs + warmup context, each with
   sha256, row count, range, timezone authority `UTC_SINGLE_TIMEBASE`, the cross-leg exact-bucketing
   rates, warmup bar counts per first-decision (use `historical_replay.warmup_readiness`), and the
   window `2025-09-15T00:00:00Z → 2026-09-14T23:59:59Z`.
2. **Promote the R3 arbiter into the durable gate:** extend
   `scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` (already the manifest-declared `coverage_gate`)
   with the cross-leg time-base check the replay mission invented: M1→H1/M15 exact OHLC bucketing +
   −3h…+3h whole-hour shift scan, per-DST-season verdicts, fail-closed on any leg whose best shift is
   not +0h-and-CONSISTENT. Unit-test the arbiter with synthetic misaligned fixtures (winter/summer
   mixed file must be reported `INTERNALLY_DST_INCONSISTENT`, never given a "best" shift).
3. Gate must also assert protected-dataset `access_count == 0` (already its pattern) and the warmup
   splice lineage (warmup source ≠ decision-window source is allowed only where declared `WARMUP_CONTEXT_ONLY`).

**Acceptance:** gate exits 0 reporting `DATA_COVERAGE_COMPLETE` **and**
`CROSS_LEG_TIMEBASE_CONSISTENT` for the full 365-day window; stack manifest committed with hashes
verified from bytes; status doc `docs/status/SSC_V1_0_1_ONE_YEAR_REPLAY_STACK_V1_STATUS.md`.

## WP1.2 — Quarantine the internally-inconsistent GEN_002 package (half day)

R3 falsified `SSC_FRESH_DEV_GEN_002`'s manifest claim ("timestamps persisted as UTC") — its own M1
leg matches canonical M1 at only 0.795 (−3h). Add an additive manifest addendum
`KNOWN_INTERNALLY_INCONSISTENT_2026_09_21` (never rewrite the original) so every future mission fails
closed against it, and list it in the data consumption registry's inadmissible section.

---

# Phase 2 — The first canonical replay (1–2 days of execution + recording, Windows box)

Follow the mission's own R5–R13 numbering; the replay entrypoint is already authoritative and
parity-tested: `session_sweep_continuation.replay.run_replay` (historical == forward entrypoint,
asserted by test).

## WP2.1 — Freeze the R5 replay contract *before* any run

Frozen JSON (schema `AG_SSC_ONE_YEAR_REPLAY_CONTRACT_V1`) recording: `population_id` seed rule,
stack manifest hash (WP1.1), decision window, warmup declaration, per-leg roles
(H1 `MARKET_BIAS_INPUT`+structure warmup / M15 `STRATEGY_DECISION_INPUT` / M1 `FILL_RESOLUTION_INPUT`),
friction model status `MODELED` (`session_sweep_continuation.friction`; H2 **not** consumed),
and the R8–R13 metric field skeleton pre-filled with `NOT_EVALUATED`. Commit it before executing
anything (this is precisely the gate the 2026-09-19 mission refused to shortcut).

## WP2.2 — Execute R6, the single canonical replay

Run `run_replay` over the stack with `historical_data_context` (live-MT5 access is blocked by
construction). Use the SVOS checkpoint machinery (`svos/virtual_exchange` + the Cycle-2
checkpoint/replay-prefix parity, already unit-tested) so the run is restart-safe and auditable.
Record: run command, environment, dataset fingerprints at load time, occurrence ledger, wall-clock cost.

## WP2.3 — R7 determinism proof

Re-run independently (fresh process, ideally fresh checkout); require byte-identical occurrence
ledger + population hash. Any divergence is a P0 defect, not a retry.

## WP2.4 — Metrics R8–R13 via `src/performance/calculator.py`

Gross/net R, expectancy, PF, drawdown, setup/direction/session decomposition, monthly/quarterly/DST
regime splits, MFE/MAE — all with friction declared `MODELED` on every line. Enforce the lineage rule
from R4: **DEV_002 (N=22) is a strict subset of this window and must never be pooled** — the
comparison questions are answered as subset-consistency checks, not independent samples.

## WP2.5 — Status + state updates

`docs/status/SSC_V1_0_1_ONE_YEAR_REPLAY_EXECUTION_STATUS.md` (full R-table),
`CURRENT_VALIDATION_STATE.json` advanced per its schema (`economic_result` populated with real N,
hashes recorded), `PROJECT_STATUS.md` dated delta. **This is the milestone where the backtest system
first produces evidence.**

---

# Phase 3 — Assurance gates to PASS (parallel track, 1–2 weeks)

The assurance audit (`AG_VALIDATION_SYSTEM_ASSURANCE_V1.md` +
`artifacts/validation/AG_VALIDATION_SYSTEM_ASSURANCE_V1_manifest.json`) defines exactly what is
missing. Each item below ends with the manifest bumped and the classification re-scored.

| WP | Gate | What to build (concrete) |
|---|---|---|
| **WP3.1** | VA2 warm-up stability | Canonical convergence suite: for a representative decision set, enumerate minimum stable startup history per indicator/context (build on `historical_replay/warmup_readiness.py` actual-closed-bar counting, which already replaced the calendar-hours approximation); reject unstable combinations **without touching parameters**; deliver `tests/test_warmup_convergence_suite.py` + machine manifest |
| **WP3.2** | VA3 synthetic known-answer | One repo-wide manifest enumerating expected outcomes for every virtual-exchange case (same-bar ambiguity, order rejection, capacity limit, friction `UNAVAILABLE` consumption refusal, end-of-data) reconciled line-by-line against actual test results; largely a consolidation of the existing 20+ SVOS cycle tests behind `scripts/reconcile_synthetic_known_answers.py` |
| **WP3.3** | VA6 firewall + VA7 search governance | Single machine-readable proof that no candidate-search flow reaches a protected path (extend `svos/optimization_admission.py` evidence output); search-manifest registry (signed objective, candidate list, budget, freeze hash) for `canonical_experiments` |
| **WP3.4** | VA8 walk-forward | Hashed, immutable fold definition (rolling/expanding) + trade-level fold reconciliation module under `src/validation_orchestrator/` or `svos/forward.py` |
| **WP3.5** | VA9 independent reference | Minimal, separately-written Python reference of the frozen SSC semantics run on the same admitted dev data, trade-by-trade reconciliation vs `run_replay`. This is the single highest-trust lever in the plan — budget it real time |
| **WP3.6** | VD capacity simulator | Freeze the remaining contracts around `src/svos/capacity_risk_contract.py` (friction/metric/qualification + manifest); owner decision on the OHLC same-bar ambiguity via an explicit contract; BE/partial virtual-lifecycle contract before inclusion; then an engineering-parity campaign on permitted dev evidence only |

**Ordering note:** WP3.1 should land before WP2.2 if possible (warmup is a replay input quality),
but it does not block running the replay — it blocks *trusting* it for promotion.

---

# Phase 4 — Replay fidelity gaps (independent track)

## WP4.1 — Historical session-box reconstruction

`src/historical_replay/data_source_patch.py:160` currently fails closed with
`HISTORICAL_SESSION_DATA_UNAVAILABLE` for range-based session candles. Implement reconstruction from
the bound M1/M15 series inside `historical_data_context`: session windows from the frozen
`config/canonical_sessions.yaml`, boxes computed only from fully-closed sessions, fail-closed with the
same reason code on partial sessions. Tests: replay session box == live session box for identical
closed bars (parity fixture), partial-session refusal, weekend/rollover handling. This unblocks
faithful replay for session-dependent strategies (Asian sweep family) beyond SSC.

## WP4.2 — Friction evidence promotion (after WP2, never before)

Friction is currently `MODELED`. The H2 friction-verification artifacts exist
(`H2_FRICTION_VERIFICATION`, preregistered) — per mission policy H2 is consumed only at its scheduled
gate, after the first gross replay exists (friction may never be root-caused while gross is
unevaluated). Then promote components with broker-evidenced historical spread to `KNOWN`, itemized.

---

# Phase 5 — Robustness battery (only once Phase 2 evidence exists)

Per the frozen `robustness-validation` skill contract — falsification-first, thresholds declared
**before** execution, final test set untouched:

1. Causality re-checks via `VD_TEMPORAL_LOOKAHEAD_V1` (frozen) perturbation harness.
2. Baselines (buy-and-hold/cash + trivial rules) through the same engine and cost model.
3. Parameter-surface stability only within preregistered sensitivity scope (strategy is frozen —
   any change is a new candidate version restarting validation, per `AGENTS.md`).
4. Time stability: the R10 monthly/quarterly/DST splits become the regime report (no post-hoc regime selection).
5. Cost stress multipliers, execution-delay stress, trade-block bootstrap, multiple-testing disclosure.
Deliverable: the validation matrix artifact; `CURRENT_VALIDATION_STATE.json.robustness` becomes
non-null exclusively through this path.

---

# Phase 6 — CI & portability (guardrails that keep it ready)

1. GitHub Actions workflow: Linux offline `pytest -q` (MT5 stubbed) + web `tsc`/build/tests — the
   portability patch delivered earlier makes this possible today.
2. Golden vertical-slice fixture: move `test_golden_vertical_slice.py`'s machine-local
   `D:\EURUSD_M5…csv` dependency toward a repo-tracked minimal fixture (the graceful skip stays as
   fallback) so the serialization-boundary regression lock runs in CI.
3. Data policy for git: 43 MB+ CSVs belong in Git LFS (or an artifact store with manifest pointers) —
   the fingerprint machinery already supports external references.
4. Add a LICENSE (or explicit proprietary notice).

---

# Definition of Done — "the backtest system is ready"

1. Coverage gate reports `DATA_COVERAGE_COMPLETE` + `CROSS_LEG_TIMEBASE_CONSISTENT` for the full window.
2. R5 contract frozen **before** execution; R6 executed once canonically; R7 double-run identical.
3. Economic metrics recorded with friction status explicitly `MODELED` (or `KNOWN` post-WP4.2).
4. Assurance manifest re-scored: VA1–VA3 and VA6–VA9 with dated machine evidence; `PROJECT_STATUS.md`
   rolling classification updated per `LIVE_STATUS_MAINTENANCE.md`.
5. `CURRENT_VALIDATION_STATE.json` shows real `economic_result` hashes, `robustness` reachable.
6. Full test suite green on Windows baseline and green-minus-live on Linux CI.
7. Every step traceable: mission docs, hashes, exact commands — the way the 2026-09-19 missions did it.

**Bottom line:** the engineering is already at a level most teams never reach; what stands between
this repo and its first trustworthy backtest is a *data pipeline decision* (single-source derived
legs + promoted timezone gate, Phases 0–1) and then *disciplined execution of the mission sequence
the project itself already wrote* (Phase 2). Everything else is parallelizable assurance hardening.
