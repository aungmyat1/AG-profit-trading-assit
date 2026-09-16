# SSC ONE-DAY DEMO PILOT V2 — SPECIFICATION

pilot_id: `SSC_ONE_DAY_OPTIMIZATION_PILOT_V1`
strategy_id: `ST_SESSION_SWEEP_CONTINUATION_V1`
work_package: `SSC1D-WP0`
status: `SPECIFICATION_ONLY — NOT ACTIVATED`
authored_utc: 2026-09-16
lane: SEPARATE / MANUAL — not part of AG_AUTO_VALIDATION_ORCHESTRATOR_V1 (AVO), not part of canonical HYP_001/HYP_002 lineage

---

## 0. Purpose and boundary declaration

This document specifies a **separate, manual, one-day optimization and Demo-qualification
research lane** for `ST_SESSION_SWEEP_CONTINUATION_V1` ("SSC"). It exists to explore whether a
bounded, evidence-gated parameter search can produce a candidate worth a short, tightly
constrained Demo exposure — **without touching canonical SSC validation state**.

This is **NOT**:
- AVO automation (`docs/validation/AG_AUTO_VALIDATION_ORCHESTRATOR_V1.md`, AVO-WP1 state model at
  `src/validation_orchestrator/status.py`) — this pilot has no orchestrator integration.
- A continuation of canonical `HYP_001_EXIT_CAPTURE` or `HYP_002_SETUP_SELECTIVITY`.
- An authorization of Demo or Live trading for SSC in any form.

This work package (`SSC1D-WP0`) delivers **specification, dataset-role inventory, pilot
schemas, and an implementation plan only**. No optimization, no OOS access, no SSC code change,
no Demo authorization, no order placement, and no automated scheduler occur under WP0.

### 0.1 Explicit non-actions (hard boundary)

The pilot, at every future work package, must never:

| # | Forbidden action | Why |
|---|---|---|
| 1 | Overwrite `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` (frozen parent, v1.0.0) | that is canonical SSC, governed by `config/governance/strategy_lifecycle.yaml` |
| 2 | Reopen `HYP_002_SETUP_SELECTIVITY` | closed `VALIDATED_NEGATIVE`, terminal per `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_CLOSURE/hypothesis_closure_record.json` |
| 3 | Interfere with the open `HYP_001_EXIT_CAPTURE` prospective lane (`HYP_001_FRESH_CONFIRM_001/`, `HYP_001_GBPUSD_REPLICATION_R1/`) | independently running canonical evidence acquisition |
| 4 | Create a `HYP_003` under the canonical SSC hypothesis ledger | `HYP_003_DECISION/hyp003_decision.json` already declined a HYP_003 in favor of continuing HYP_001 — a pilot-local hypothesis must use a pilot-local ID namespace (`SSC1D-H<n>`), never `HYP_00N` |
| 5 | Consume `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json`'s `holdout` (currently `null`, `holdout_run_count: 0`) or any future canonical SSC final holdout | canonical holdout is sealed, single-use, not this pilot's to spend |
| 6 | Change canonical SSC semantics (entry/exit/session/setup rules in the frozen v1.0.0 spec) | any change is a **candidate**, tracked in the pilot's own candidate ledger, never written back to the canonical file |
| 7 | Change `demo_authorized` / `live_authorized` for SSC anywhere | authorization is exclusively canonical governance's decision, this pilot may only *design* (P12) a proposed contract for owner review |
| 8 | Modify `strategies/registry.yaml`, `config/governance/strategy_lifecycle.yaml`, `state/proposal_ledger/proposal_ledger.json`, or any AVO-WP1 state file | out of scope for this pilot entirely |

---

## 1. Pilot identity

```
pilot_id:            SSC_ONE_DAY_OPTIMIZATION_PILOT_V1
strategy_id:         ST_SESSION_SWEEP_CONTINUATION_V1
parent_spec:         strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml  (v1.0.0, frozen, unmodified)
classification:      NON-CANONICAL RESEARCH
governed_by:         this document only, until a later governed adoption decision
adoption_path:       none defined yet — any promotion of a pilot candidate into canonical
                      SSC status requires a separate, explicit owner-approved governance act,
                      out of scope for this pilot
work_packages:        SSC1D-WP0 (this doc)  →  SSC1D-WP1 .. SSC1D-WPn (future, not started)
```

Every artifact this pilot produces is namespaced under `SSC1D_` (work package prefix) or
`SSC1D-H<n>` (pilot-local hypothesis IDs), and written under
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/` — a **new, isolated
subtree**, sibling to (never inside) the canonical `HYP_001_*` / `HYP_002_*` directories.

---

## 2. Relationship to canonical validation state (read-only)

| Canonical fact (as of 2026-09-16, read-only reference) | Source |
|---|---|
| SSC lifecycle_stage | `OFFLINE_RESEARCH` | `config/governance/strategy_lifecycle.yaml` |
| SSC demo_eligible / demo_authorized | `false` / `false` | `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` |
| SSC live_authorized | `false` | same |
| HYP_002 status | `VALIDATED_NEGATIVE`, terminal, closed | `HYP_002_CLOSURE/hypothesis_closure_record.json` |
| HYP_001 status | open, blocked on evidence timing (`STOP_TIMING_NOT_YET_AVAILABLE` as of 2026-09-15), not on a negative result | `HYP_001_FRESH_CONFIRM_001/BOUNDARY_STATUS.json` |
| HYP_001 GBPUSD replication lane | terminal for that population (`REPLICATION_INCONCLUSIVE_INSUFFICIENT_SAMPLE`, N=15 < 20) | `HYP_001_GBPUSD_REPLICATION_R1/` |
| Canonical `CURRENT_VALIDATION_STATE.json` | `active_gate: TERMINAL_FAIL` (reflects HYP_002), `holdout: null`, `holdout_run_count: 0` | `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/CURRENT_VALIDATION_STATE.json` |
| G0–G10 canonical gate methodology | `AG_VALIDATION_G0_G10_V1`, only G0–G3 in-scope for "Cycle 1" | `src/validation_framework/ag_validation_methodology.py` |

This pilot **reuses gate vocabulary** (G0 Contract Audit, G1 Preregistration, G2 Deterministic
Population, G3 Economic Gate — see §7) for internal consistency with canonical AG terminology,
but its own gate passes/fails are **pilot-local** and carry no canonical weight and do not
write into `ag_validation_methodology.py`, `validation_gate_state.py`, or
`CURRENT_VALIDATION_STATE.json`.

---

## 3. P2 — Data firewall: dataset inventory and role manifest

Full machine-readable manifest: `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP0_dataset_role_manifest.json`
(schema `AG_SSC1D_DATASET_ROLE_MANIFEST_V1`). Summary:

| dataset_id | symbol | range (UTC) | timeframes | source | prior consumption | assigned role | allowed ops |
|---|---|---|---|---|---|---|---|
| `SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914` | EURUSD, GBPUSD | 2026-08-01 .. 2026-09-14 | H1, M15, M1 | `data/research/ssc_fresh_dev/SSC_FRESH_DEV_GEN_002_MT5_20260801_20260914/` | **CONSUMED** — used for HYP_002 population (both attempts) and is the active source for the still-open HYP_001 fresh-confirmation lane | `CONSUMED_NON_COUNTING` | inspection/audit only; **not** usable as this pilot's development or OOS data while HYP_001's lane remains open against it — see §3.1 |
| `EURUSD_H1_202501020000_202607310000` | EURUSD | 2025-01-02 .. 2026-07-31 | H1 | `config/historical_datasets/EURUSD_H1_202501020000_202607310000.yaml` | not confirmed consumed by SSC specifically; overlaps windows used broadly across the repo (e.g. Large-SMC) for other strategies/detection pipelines | `UNKNOWN` | none until re-audited specifically against SSC's own consumption trail |
| `EURUSD_M15_202501020000_202606192345` | EURUSD | 2025-01-02 .. 2026-06-19 | M15 | `config/historical_datasets/EURUSD_M15_202501020000_202606192345.yaml` | not confirmed consumed by SSC specifically | `UNKNOWN` | none until re-audited |
| `EURUSD_M1_202605180946_202607312356` | EURUSD | 2026-05-18 .. 2026-07-31 | M1 | `config/historical_datasets/EURUSD_M1_202605180946_202607312356.yaml` | not confirmed consumed by SSC specifically | `UNKNOWN` | none until re-audited |
| GBPUSD H1 warmup+R1 package | GBPUSD | per `GBPUSD_H1_WARMUP_PLUS_R1_symbol_metadata.yaml` | H1 | `config/historical_datasets/` | **CONSUMED** — HYP_001 GBPUSD replication lane (terminal, inconclusive) | `CONSUMED_NON_COUNTING` | none |
| any future MT5 pull dated strictly after 2026-09-14 (GEN_002's frozen_end) not yet acquired | EURUSD | none acquired yet | — | not yet created | none | `OOS_UNTOUCHED` **candidate only** — does not exist in the repo yet | none — must be freshly acquired, hashed, and admitted through a new admission record before any use |
| SSC final holdout | any | none defined | — | none | none | `FINAL_HOLDOUT_SEALED` — **not established**; canonical `CURRENT_VALIDATION_STATE.json` shows `holdout: null` | none — this pilot has no authority to define or seal a canonical SSC holdout |

### 3.1 Finding: no legitimate untouched OOS exists today

No dataset in the repository qualifies as `OOS_UNTOUCHED` for SSC/EURUSD or SSC/GBPUSD as of
2026-09-16. The only fresh-dated SSC package (`GEN_002`, ending 2026-09-14) is concurrently
in active use by the canonical, independently-running `HYP_001_FRESH_CONFIRM_001` lane, which
makes it ineligible for this pilot's development use (it would create cross-lane contamination
between canonical HYP_001 evidence and pilot candidate selection) and ineligible as pilot OOS
(it is not untouched).

**Per mission instruction P2: this pilot STOPS at the OOS boundary.** This is a designed,
expected stop — not a failure of WP0. Concretely:

```
DATASET_ROLE_STATUS = NO_LEGITIMATE_OOS_ESTABLISHED
NEXT_SAFE_ACTION     = ACQUIRE_NEW_POST_2026-09-14_EURUSD_PACKAGE_VIA_EXISTING_MT5_INFRASTRUCTURE,
                       THEN RE-RUN DATASET-ROLE CLASSIFICATION BEFORE SSC1D-WP1 MAY PROCEED
                       PAST P2
```

A future work package (SSC1D-WP1) must acquire a fresh, dated, hashed EURUSD (and optionally
GBPUSD) package strictly after 2026-09-14 using the same admitted MT5 acquisition path already
used for `GEN_002` (see `FRESH_DATA_ADMISSION/` for the admission-record pattern), assign it
`assigned_role: DEVELOPMENT_REUSABLE` for pilot candidate search, and — **separately** — either
reserve an unopened slice of that same fresh pull or acquire a second, later-dated pull to serve
as `OOS_UNTOUCHED` for this pilot's P9. **No OOS may be designated retroactively from data
already viewed during development.**

---

## 4. P3 — Baseline contract (definition only; not executed under WP0)

The frozen baseline candidate is canonical SSC v1.0.0 exactly as registered:
`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` (`runner_target_r: 3.0`, S1/S2/S3 as
configured, campaign caps `max_entries=3`, `maximum_total_risk_pct=1.0`). No modification.

When SSC1D-WP1 runs the baseline (against the `DEVELOPMENT_REUSABLE` dataset established per
§3.1), the baseline report must record, reusing the existing SSC replay/attribution engine
(`src/session_sweep_continuation/replay.py`, `canonical_observations.py`,
`scripts/run_session_sweep_continuation_replay.py`) rather than a new engine:

```
N, wins, losses, net_R, expectancy_R, profit_factor, max_drawdown_R, MFE, MAE
```

decomposed by: `setup (S1/S2/S3)`, `session (ASIAN_LONDON / LONDON_NEWYORK)`, `direction`,
`regime`, `exit_reason` — with **occurrence identity preserved** (each observation keeps a
stable ID traceable back to its source candle/session, matching the convention already used in
`canonical_observations.py`).

---

## 5. P4 — Diagnosis contract (schema)

Schema file: `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP0_diagnosis_contract_schema.json`

Every proposed optimization hypothesis under this pilot must be recorded in this shape before
any candidate is built:

```
optimization_hypothesis_id     e.g. "SSC1D-H1"  (pilot-local namespace, never HYP_00N)
observed_problem               concrete, evidence-cited (e.g. "MFE caps below 1.5R on N of M
                                baseline winners, runner_target_r=3.0 rarely reached")
supporting_metrics             pointer(s) to baseline decomposition rows/fields
mechanism                      causal hypothesis for why the problem occurs
controlled_change_family       e.g. "exit target geometry", "setup selectivity", "session gate"
parameters_allowed_to_change   explicit field list, dot-path into the YAML config
parameters_frozen              everything else — explicit statement, not "all else default"
expected_effect                directional, falsifiable prediction
rejection_condition            preregistered, fixed before candidate results are seen
```

Note: `mechanism` = "exit-capture target too far" for SSC already exists as canonical
`HYP_001_EXIT_CAPTURE`. Per the existing `HYP_003_DECISION` precedent, this pilot must not
re-litigate that exact mechanism under a pilot-local ID as if it were novel — if a pilot
hypothesis's mechanism duplicates an open or closed canonical HYP, the diagnosis record must say
so explicitly and explain why a separate, non-canonical, time-boxed pilot exploration is still
warranted (e.g. a bounded one-day Demo-qualification objective distinct from HYP_001's
prospective/fresh-confirmation objective).

---

## 6. P5 — Optimization budget (pre-registered)

```
max_major_hypotheses = 3
max_total_candidates  = 20
max_search_time       = 3 hours (wall-clock, development-phase only, excludes OOS/WFA)
```

Stop reasons (exactly one must be recorded at closure):

```
TARGET_REACHED
BUDGET_EXHAUSTED
NO_IMPROVEMENT
INVALID_HYPOTHESIS
ENGINE_FAILURE
```

### 6.1 TARGET_REACHED is undefined — owner action required

No universal PF/expectancy/Sharpe threshold exists anywhere in this repository's validation
docs (confirmed by discovery: `docs/validation/AG_ACCELERATED_VALIDATION_PLAN_V1.md` §9
explicitly forbids inventing one — "Do not impose universal metrics... unless explicitly
preregistered for the strategy"). The established repo pattern (HYP_001, HYP_002) is a
per-hypothesis decision rule fixed in the preregistration artifact before evidence is seen,
e.g. HYP_002's `PASS: TREATMENT_N>=10 AND delta_net_expectancy_R>0 AND
TREATMENT_net_expectancy_R>0`.

Per mission instruction P5, this pilot does **not** invent a profitability threshold.

```
TARGET_REACHED_DEFINITION_STATUS = OWNER_TARGET_DEFINITION_REQUIRED
NEXT_SAFE_ACTION                 = owner (or governed successor process) must fix the
                                    per-hypothesis PASS/FAIL/INCONCLUSIVE decision rule for
                                    each SSC1D-H<n> hypothesis, before that hypothesis's
                                    candidates are backtested — same discipline as
                                    HYP_001/HYP_002 preregistration, applied per hypothesis,
                                    not once for the whole pilot
```

---

## 7. P6 — Candidate ledger (schema)

Schema file: `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP0_candidate_ledger_schema.json`

Fields per candidate (immutable once written; rejected candidates are retained, never deleted
or overwritten):

```
candidate_id                 e.g. "SSC1D-H1-C03"
parent_candidate_id           null for a hypothesis's first candidate, else prior candidate_id
hypothesis_id                 SSC1D-H<n>
semantic_config_hash          hash of the full effective config (parent YAML + diff)
changed_fields                explicit dot-path diff from strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml
development_dataset_hash      hash of the DEVELOPMENT_REUSABLE dataset slice used
N, expectancy_R, PF, max_DD_R, MFE, MAE
setup_decomposition            per S1/S2/S3, session, direction, regime, exit_reason
result                         raw metrics outcome
decision                       RETAIN | REJECT
decision_reason                tied to the hypothesis's preregistered rejection_condition (§5)
```

This mirrors, at pilot scale, the immutability and full-history-retention pattern already used
by `state/proposal_ledger/proposal_ledger.json` (`current` + `history` per entry) — this
pilot's ledger is a **separate file**, never written into the canonical proposal ledger.

---

## 8. P7 — Optimization loop (process only, not executed under WP0)

```
BASELINE → DIAGNOSE → FORM HYPOTHESIS (§5) → BOUNDED CANDIDATES (§7) →
BACKTEST ON DEVELOPMENT DATA ONLY → COMPARE → REJECT/RETAIN → NEXT HYPOTHESIS OR FREEZE
```

Constraints carried into SSC1D-WP1: prefer stable parameter neighborhoods over isolated maxima;
no OOS access permitted anywhere in this loop; loop stops at whichever of the §6 stop reasons
fires first.

---

## 9. P8 — Candidate freeze contract (schema, not executed)

Before first OOS access, SSC1D-WP1 (or later) must record, in a file named
`SSC1D_WP<n>_candidate_freeze.json`:

```
candidate_id
strategy_semantic_hash        (of the frozen candidate config, derived from parent v1.0.0)
configuration_hash
development_dataset_hash
candidate_ledger_hash         (hash of the full ledger file at freeze time)
optimization_budget_consumption   { hypotheses_used, candidates_used, search_time_used }
oos_dataset_identity_hash     (of the dataset established per §3.1, once it exists)
```

After this record is written, no further optimization is permitted inside the pilot.

---

## 10. P9 — OOS protocol (not executed)

The frozen candidate runs exactly once against the assigned OOS dataset (§3.1), under this
pilot's protocol, using the existing SSC replay engine. No parameter changes after observing
OOS results.

```
if OOS fails:
  SSC_ONE_DAY_DEMO_PILOT_READY = false
  NEXT_SAFE_ACTION = CONTINUE_RESEARCH_WITH_NEW_GENERATION
  the exposed OOS dataset becomes CONSUMED_NON_COUNTING permanently —
  it may never be re-designated OOS_UNTOUCHED for this or any later SSC1D generation
```

---

## 11. P10 — WFA / robustness (not executed; only after OOS permits continuation)

Using the existing validation framework (`src/validation_framework/`) where applicable:
cross-period stability, setup/session concentration, friction sensitivity (reusing
`src/session_sweep_continuation/friction.py` cost model — cost_status stamped
KNOWN/MODELED/UNAVAILABLE per existing convention, never silently treated as included),
parameter-neighborhood stability, drawdown sensitivity. Any friction stress multiplier applied
is explicitly a scenario, not a claim about empirical broker cost, unless supported by real
broker evidence (matching the existing convention already established for the Large-SMC
friction campaign, `[[project_large_smc_eurusd_friction_campaign_wp3a1]]`).

---

## 12. P11 — Final status contract

This pilot's terminal/interim status vocabulary (pilot-local, does not write into canonical
`CURRENT_VALIDATION_STATE.json` or `ag_validation_methodology.py`):

```
DATA_HYGIENE_PASS | BASELINE_COMPLETE | OPTIMIZATION_COMPLETE | CANDIDATE_FROZEN |
OOS_PASS | OOS_FAIL | WFA_PASS | WFA_FAIL | ROBUSTNESS_PASS | ROBUSTNESS_FAIL |
AUDIT_REQUIRED | DEMO_PILOT_READY | DEMO_PILOT_NOT_READY
```

Every status report from this pilot must separately and explicitly state:

```
CANONICAL_DEMO_ELIGIBLE = false
LIVE_ELIGIBLE           = false
```

unless those statuses are independently changed by SSC's existing canonical governance
(`config/governance/strategy_lifecycle.yaml` + owner authorization) — which this pilot has no
authority to do.

---

## 13. P12 — Demo contract design (specification only — NOT activated)

This is a **design artifact for future owner review**, not a live authorization. Recorded at
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP0_demo_contract_design.json`.
Recommended maximum shape, if and only if a future work package reaches `DEMO_PILOT_READY`:

```
environment            = DEMO
symbol                 = EURUSD
max_open_positions     = 1
max_new_entries         = 1
strategy_config         = frozen candidate only (candidate_id pinned, §9)
owner_approval_required = true
live_authorized         = false
automatic_expiry        = end of pilot day (UTC)
no_valid_setup_policy   = NO_TRADE_VALID_DAY  — strategy rules are never loosened to force a trade
```

`activation_status: NOT_ACTIVATED`. No code path in this repository currently reads or enforces
this contract; activating it is out of scope for every work package up to and including this
one.

---

## 14. P13 — Implementation scope for SSC1D-WP0 (this work package)

Delivered by WP0:
- This specification document.
- Dataset role manifest (§3, JSON).
- Diagnosis contract schema (§5, JSON).
- Candidate ledger schema (§7, JSON).
- Demo contract design (§13, JSON, NOT_ACTIVATED).
- Implementation plan for SSC1D-WP1 (§15 below).

Explicitly NOT delivered by WP0 (deferred to SSC1D-WP1 or later, each gated on explicit
re-authorization): optimization runs, OOS access, holdout access, SSC code/config
modification, Demo authorization, order placement, automated scheduler/orchestration.
SSC1D-WP1 does not start automatically as a consequence of this document existing.

---

## 15. Implementation plan (SSC1D-WP1, proposed — not started)

1. Resolve the §3.1 OOS gap: acquire a fresh, hashed, dated EURUSD (and optionally GBPUSD)
   MT5 package strictly after 2026-09-14, via the existing admitted acquisition path
   (pattern: `FRESH_DATA_ADMISSION/`). Split into `DEVELOPMENT_REUSABLE` and
   `OOS_UNTOUCHED` slices at acquisition time, before either is inspected.
2. Re-run and freeze the P2 dataset-role manifest against the newly acquired data.
3. Run P3 baseline using `scripts/run_session_sweep_continuation_replay.py` against
   `DEVELOPMENT_REUSABLE` only; publish the baseline report.
4. Obtain owner sign-off on a per-hypothesis PASS/FAIL/INCONCLUSIVE decision rule (§6.1)
   before forming SSC1D-H1.
5. Execute the P4–P8 loop within the pre-registered budget (§6).
6. Freeze candidate (§9), then run P9 OOS exactly once.
7. If OOS passes, run P10 WFA/robustness; else stop per §10 and report
   `NEXT_SAFE_ACTION = CONTINUE_RESEARCH_WITH_NEW_GENERATION`.
8. Publish P11 final status; if `DEMO_PILOT_READY`, hand the P12 design (§13) to the owner for
   an explicit, separate authorization decision. This pilot does not self-authorize Demo.

---

## 16. P14 — Verification (WP0)

See `SSC1D_WP0_STATUS` report delivered alongside this document's commit. Summary: all
diffs against SSC semantics, HYP_001, HYP_002, holdout authority, Demo authority, Live
authority, execution authority, and the Large-SMC campaign are `EMPTY` — WP0 added new files
only, under new paths, and modified no existing file.

---

## 17. SSC1D-WP1 addendum — data authority + objective freeze (2026-09-16)

WP1 resolved the two WP0 blockers only to the extent evidence allowed, without running any
SSC baseline, optimization, OOS evaluation, or Demo action. Full artifacts under
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/`.

**Correction to §3 above**: the three EURUSD H1/M15/M1 packages marked `UNKNOWN` in the
original WP0 dataset-role manifest were an error — an independent WP1 audit (hash-verified)
found all three are proven inputs to SSC's own `GEN_001` experiment
(`artifacts/research/EXP_EXPOSURE_EFFICIENCY_V1/GEN_001`), already documented in
`POST_JULY31_CONSUMPTION_AUDIT/consumption_audit.json`. They are now correctly classified
`CONSUMED_NON_COUNTING`, and — because GEN_001 was hypothesis-generation-only and is not part
of any currently open canonical evidence lane — reused as this pilot's own `DEVELOPMENT_REUSABLE`
data (H1 full range, M15 full range, M1 proven-consumed segment 2026-05-18..2026-06-19 only;
the M1 tail 2026-06-20..2026-07-31 remains `UNKNOWN`/excluded, unresolved by a prior canonical
audit). See `SSC1D_WP0_dataset_role_manifest.json`'s `wp1_correction` note for full detail.

**OOS**: no genuinely untouched *historical* EURUSD interval existed anywhere in the repo, so
WP1 acquired one via the existing read-only MT5 infrastructure (`scripts/acquire_ssc1d_wp1_oos_eurusd_2024q1.py`,
no trading function called): EURUSD H1 + M15, 2024-01-01..2024-03-31, chosen purely on
chronological non-overlap with every known SSC artifact (predates GEN_001 by 12+ months),
frozen as `OOS_UNTOUCHED`, `access_count=0`. The M1 leg could not be acquired for this window —
this MT5 terminal's M1 retention is empirically limited to roughly the trailing ~120 days, and
every in-retention M1 interval is already consumed, unresolved, or the reserved
post-2026-09-14 prospective window this mission explicitly forbade using as an OOS substitute.
OOS is therefore `PARTIAL_ESTABLISHED_H1_M15_ONLY` — sufficient for diagnostic use, insufficient
for a canonical-parity SSC replay (which requires M1 fill resolution) until this gap is resolved.

**Optimization objective** (§6 development-zone candidate retention rules) is frozen in
`SSC1D_WP1_optimization_objective_freeze.json`: primary criterion (`expectancy_R` improves vs.
baseline), safeguards (PF, max DD, N >= 70% of baseline), and a neighboring-parameter robustness
requirement. Not yet evaluated.

**OOS decision contract structure** is frozen in `SSC1D_WP1_oos_decision_contract.json`: a
relative criterion (vs. DEVELOPMENT-frozen-candidate result) combined with an absolute floor
criterion, specifically to prevent an OOS result passing merely for being less negative than an
already net-negative baseline. The absolute floor's *value* is left undefined —
`OOS_ABSOLUTE_ECONOMIC_FLOOR = OWNER_DEFINITION_REQUIRED` — because no such floor exists
anywhere in canonical governance and this pilot has no authority to invent one.

**Net effect**: `SSC1D_CAN_CONTINUE_TO_OPTIMIZATION = false` as of WP1, independently for two
reasons — the missing absolute economic floor (§6.1/§17 above) and the unresolved OOS M1 gap.
Development data and the H1/M15 OOS package are both frozen and ready for reuse once those two
blockers are cleared by the owner or a resolved data source.

---

## 18. SSC1D-WP1A addendum — OOS economic floor + M1 resolution attempt (2026-09-16)

**Economic floor: RESOLVED.** Owner supplied the absolute OOS floor without any OOS outcome
being inspected first: `expectancy_R > 0.0 AND profit_factor > 1.0` (post-friction). Full
deterministic definitions — R-multiple/expectancy formula, profit_factor zero-loss-denominator
handling (reported `UNDEFINED`, never infinite or synthetic), resolved-vs-unresolved occurrence
scope, minimum-sample-size flagging (reusing SSC's existing `performance_attribution.min_sample_size=10`
convention), and the friction basis (SSC's own existing cost model, cost-status stamped
KNOWN/MODELED/UNAVAILABLE, never silently treated as included) — are in
`SSC1D_WP1A_economic_floor_contract.json`. This supersedes the `OWNER_DEFINITION_REQUIRED`
placeholder in `SSC1D_WP1_oos_decision_contract.json`; that file's relative criterion and
combined PASS rule (both relative and absolute must hold) are otherwise unchanged.

**M1 gap: still `M1_UNRESOLVED`.** Both preferred acquisition paths were audited and neither
is defensible:

- *Same-broker/same-feed (Vantage MT5)*: confirmed unavailable by both bar and tick history —
  `mt5.copy_rates_range` and `mt5.copy_ticks_range` for EURUSD 2024-01-02..2024-01-03 both
  returned zero results. This is consistent with an empirically observed ~120-day M1/tick
  retention boundary on this terminal (clean data at 30/60/90 days back, none at 120+).
- *Independently sourced*: FMP's forex endpoints are plan-gated (Premium/Ultimate/Enterprise
  required; current plan denied access, and the tool explicitly instructed against retrying).
  AlphaVantage's `FX_INTRADAY` endpoint has no historical date-range parameter at all — it
  structurally cannot target 2024 Q1 regardless of plan tier.

Per the mission's own fallback (option 3), this is reported as `M1_UNRESOLVED` rather than
worked around. No candidate M1 series was ever obtained, so no cross-source comparison against
the sealed H1/M15 legs was possible. Full audit trail in `SSC1D_WP1A_m1_resolution_report.json`.

**OOS package status unchanged**: `PARTIAL_ESTABLISHED_H1_M15_ONLY`, `OOS_ACCESS_COUNT=0`. WP2
remains blocked — now solely on the M1 gap, since the economic floor blocker is cleared.
Resolving M1 requires an owner decision this pilot has no authority to make unilaterally: either
authorize a paid data-source upgrade, or explicitly accept a reduced-fill-precision OOS
methodology for this pilot.
