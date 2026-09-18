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

### 6.1.1 Owner adjudication (2026-09-18) — SSC1D-H1/H2 acceptance rule frozen

The owner has adjudicated the gap above for the two admitted hypotheses (SSC1D-H1, SSC1D-H2).
Full detail, threshold provenance, and the deterministic rule engine are frozen in
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_SECTION_6_1_ACCEPTANCE_RULES/SSC1D_SECTION_6_1_acceptance_rules.json`,
preregistered before any SSC1D-H1/H2 candidate is generated or replayed (zero candidates
consumed by this freeze). Owner policy values: `NET_EXPECTANCY_FLOOR > 0.0R`,
`NET_PF_FLOOR > 1.0`, `MIN_TREATMENT_N = 20` (hypothesis-level; distinct from and does not
replace `performance_attribution.min_sample_size=10`). The existing WP1 candidate-retention
safeguard (`SSC1D_WP1_optimization_objective_freeze.json`, ≈70% of baseline N) and the frozen
WP4A mechanism-specific falsification conditions (`SSC1D_WP4A_hypothesis_1_...json`,
`SSC1D_WP4A_hypothesis_2_...json`) remain independent, unmodified, additional gates.

Per-hypothesis decision table (evaluated independently per hypothesis; a candidate slot is
consumed the moment outcome information is exposed, per the budget-accounting rule below):

| State | Condition |
|---|---|
| `INVALID_PRE_EVALUATION` | Candidate rejected before any outcome/performance information is exposed (schema/config invalid, duplicate, contract violation, dataset unavailable, preflight/infra failure — all pre-replay). Budget slot **not** consumed. |
| `INVALID_EXPERIMENT` | Outcome information exposed, but the experiment itself was not legitimately evaluated (e.g. comparability/contract violation or data-integrity fault discovered only after outcome computation). Budget slot consumed. |
| `INSUFFICIENT_EVIDENCE` | Outcome exposed, but `treatment_N < 20`. Budget slot consumed. |
| `FAIL` | Outcome exposed, `treatment_N >= 20`, but any mandatory gate fails: WP1 retention safeguard (where applicable), `net_expectancy_R <= 0`, `net_PF <= 1`, the hypothesis's own mechanism/falsification gate, or the comparability/contract gate. Budget slot consumed. |
| `PASS` | Outcome exposed, `treatment_N >= 20`, WP1 retention safeguard passes (where applicable), `net_expectancy_R > 0`, `net_PF > 1`, mechanism gate passes, comparability gate passes. Does not by itself terminate search if required robustness evidence is incomplete. Budget slot consumed. |
| `TARGET_REACHED` | All PASS-level gates hold **and** required neighbor-parameter robustness passes. Budget slot consumed. |
| `TARGET_REACHED_BLOCKED_PENDING_ROBUSTNESS_PREREGISTRATION` | All PASS-level gates hold, but the operational neighbor-parameter robustness test itself is not preregistered anywhere for H1/H2 (only the principle is, in `SSC1D_WP1_optimization_objective_freeze.json`). PASS may still be reached independently of this. Budget slot consumed. |

Rule-engine unit tests (synthetic fixtures only): `tests/test_ssc1d_section_6_1_acceptance_rules.py`.
Next required gate before any SSC1D-H1/H2 candidate execution: **independent §6.1 audit**
(see the acceptance-rules artifact's `next_gate` field).

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

---

## 19. SSC1D-WP1B addendum — DEVELOPMENT/OOS gate separation (2026-09-16)

WP1B re-examined whether the M1 OOS blocker actually blocks *all* further pilot work, or only
the specific OOS evaluation step. Reading SSC's frozen timeframe contract (`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`
lines 30-33: `htf_context=H1`, `decision_timeframe=M15`, `execution_timeframe=M1`) and the
DEVELOPMENT package's own manifests (no code executed): DEVELOPMENT and OOS are two entirely
disjoint dataset packages with zero shared dates, and WP2's baseline is defined (§4) to run
against DEVELOPMENT only. The common H1+M15+M1 DEVELOPMENT interval is **2026-05-18..2026-06-19**
— bounded by the M1 leg, and not coincidentally identical to GEN_001's own original 31-trade
population window, so it is already known in advance to be data-sufficient.

**Gates are split accordingly**, recorded in `SSC1D_WP1B_gate_separation_contract.json`:

```
WP2_DEVELOPMENT_BASELINE_AUTHORIZED = true
OOS_EVALUATION_AUTHORIZED           = false
```

`PARTIAL_ESTABLISHED_H1_M15_ONLY` is explicitly **not** reinterpreted as complete OOS —
`OOS_EVALUATION_AUTHORIZED` stays `false` independent of WP2/WP3/WP4's outcome. The firewall is
made explicit: WP2-WP4 may consume DEVELOPMENT data only, must never inspect the OOS raw files,
and no optimization/candidate/diagnosis decision may be informed by an OOS outcome (enforced by
construction — `OOS_ACCESS_COUNT` stays `0` throughout). Before the P9 frozen-candidate OOS run
can ever occur, all four preconditions must hold simultaneously: candidate frozen, optimization
stopped, a complete approved OOS execution methodology assembled, and the M1 authority either
resolved or explicitly owner-approved under a preregistered reduced-precision methodology.

This addendum authorizes a future WP2 to begin DEVELOPMENT baseline work; it does not itself run
WP2, compute a baseline, or touch the OOS package.

---

## 20. SSC1D-WP2 addendum — DEVELOPMENT baseline measurement (2026-09-16)

WP2 executed one authoritative, canonical-parity SSC v1.0.0 replay over DEVELOPMENT only,
via a new pilot-local driver (`scripts/run_ssc1d_wp2_baseline_replay.py`) that reuses every
underlying canonical library call (`historical_replay.*`, `session_sweep_continuation.h1_bias`/`replay`,
`performance.calculator`) unmodified, writing output exclusively under
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP2_BASELINE/` — never
into the existing canonical `GEN_001` directory. The baseline-run contract (§P1) was frozen
(`SSC1D_WP2_baseline_run_contract.json`) before the run executed.

**Result**: 66 decision cycles → 31 resolved occurrences (0 unresolved), matching GEN_001's own
population exactly — `population_hash` `8e32a7498e5a1c7df6658e6700ff3386fb38821ed189619a20224ce032d9166d`,
confirmed identical both internally (RUN_1 vs RUN_2, `G0_REPRODUCIBILITY_PASS`) and against the
pre-existing GEN_001 canonical evidence (read-only cross-check, `matches_gen001=true`). This is
the strongest available reproducibility proof: an independently re-executed process reproduced
GEN_001's population byte-for-byte without touching GEN_001's own files.

**`SSC1D_BASELINE` anchor** (`SSC1D_BASELINE_anchor.json`): `net_expectancy_R = -0.1896`,
`gross_expectancy_R = +0.0003`, `profit_factor (gross-based) = 1.0008`, `win_rate = 48.4%`
(15W/15L/1BE), `max_drawdown_R = 4.55`, `friction_total_R = 5.89` over 31 occurrences,
`2026-05-18..2026-06-19`. Full setup/session/direction/regime/exit-reason decomposition and a
read-only MAE/MFE summary (sourced from GEN_001's own already-existing per-trade CSV, justified
only by the confirmed population-hash match) are in the same output directory. This anchor
records the measurement only — no economic interpretation, no diagnosis, no optimization
hypothesis. `HYPOTHESIS_1` has not been formulated.

All P5 integrity checks passed (`wp2_integrity_report.json`): no duplicates, no timestamps outside
the DEVELOPMENT interval, structurally no path to OOS/holdout/prospective data, all exclusions
recorded and labeled rather than dropped. `OOS_ACCESS_COUNT` remains `0`; final holdout and
post-2026-09-14 prospective evidence remain untouched.

---

## 21. SSC1D-WP3 addendum — evidence-backed failure diagnosis (2026-09-16)

WP3 diagnosed the WP2 baseline purely descriptively, via read-only aggregation over the
population-hash-verified per-trade evidence (GEN_001's `per_trade_results.csv`, CONTROL rows
only) — no baseline rerun, no strategy code executed, no optimization. Full detail under
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP3_DIAGNOSIS/`.

**Economic attribution**: gross expectancy is effectively zero (`+0.0003R`); friction
(`5.886R`) is almost exactly equal in magnitude to the entire net loss (`-5.877R`), consuming
50.5% of all gross-positive R. This is evidence for friction overwhelming a near-zero gross
edge, not for a negative raw trade edge.

**Failure mechanism ranking** (diagnostic priority only, `SSC1D_WP3_failure_ranking_and_hypothesis_readiness.json`):
1. `FRICTION_DRAG` (DESCRIPTIVE_STRONG) — exact arithmetic reconciliation, broad/uniform across setups and sessions.
2. `STOP_LOSS_CONCENTRATION` (DESCRIPTIVE_STRONG) — 11 SL occurrences net -1.224R average, concentrated in ASIAN_LONDON (8/11) and clustering on 2 of 33 calendar days (5/11).
3. `EXIT_CAPTURE_INEFFICIENCY` (DESCRIPTIVE_MODERATE) — mean MFE 0.739R vs realized gross ~0R; **explicitly flagged as overlapping the OPEN canonical `HYP_001_EXIT_CAPTURE` lineage**, not a novel finding.
4. `SESSION_CONDITIONALITY` (DESCRIPTIVE_MODERATE) — confounded with setup-mix and largely the same evidence as rank 2.
5. `SETUP_FAMILY_WEAKNESS` — S2 (N=3, 100% instant SL) flagged `DESCRIPTIVE_WEAK`; no removal conclusion drawn per instruction.
6. `DIRECTION_SAMPLE_IMBALANCE` — a representativeness limitation, not a loss-driving mechanism.

**Direction limitation**: all 31 occurrences are SHORT (H1 bias was BEARISH throughout this
window) — nothing here generalizes to LONG behavior; no LONG data was synthesized.

**Three `HYPOTHESIS_READY_MECHANISM` candidates** recorded (mechanism + evidence + limitations +
concerned canonical component only — no parameter values, ranges, or candidate configurations,
those are reserved for WP4): friction/risk-allocation interaction, ASIAN_LONDON stop-loss
concentration, and exit-capture inefficiency (with its HYP_001 overlap flagged).

Integrity confirmed: `strategy_modified=false`, `parameters_modified=false`,
`optimization_run=false`, `candidate_count=0`, `OOS_ACCESS_COUNT=0`, final holdout and
post-2026-09-14 prospective evidence untouched.

---

## 22. SSC1D-WP4A addendum — bounded hypothesis formation (2026-09-16)

WP4A converted WP3's diagnosis into falsifiable hypotheses — no candidates run, no strategy
change, no OOS/holdout/prospective access. Full detail under
`artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/SSC1D_PILOT/SSC1D_WP4A_HYPOTHESES/`.

**Exit-capture overlap review**: `SSC1D-MECH-3` classified `MATERIALLY_OVERLAPPING` with the
open canonical `HYP_001_EXIT_CAPTURE` — same mutable component (`trade_management.runner_target_r`),
same mechanism (favorable excursion not realized; HYP_001's own historical record shows 0/88
GEN_001+GEN_002A trades ever reached the 3.0R target). **No new SSC1D hypothesis created from
it** — recorded as corroborating DEVELOPMENT evidence for HYP_001 only; HYP_001 itself untouched.

**Two hypotheses admitted** (of a 2-hypothesis cap for this stage, not forced — both
independently passed all 9 admission criteria):
- **`SSC1D-H1`** — friction/risk-geometry: friction consumes ~50% of gross-positive R, roughly
  uniform across setups/sessions; targets the already-canonical `friction.minimum_stop_multiple`
  floor (currently 3.0, already gates entries via `STOP_BELOW_FRICTION_FLOOR` in `stop_engine.py`,
  already excluded 9 decision cycles in WP2). Market friction cost inputs themselves remain frozen.
- **`SSC1D-H2`** — ASIAN_LONDON stop-loss concentration (53.3% vs 18.75% SL rate): targets
  `regime.range_max_pips` (currently 25.0). Explicitly flagged as partly informed by general
  session-volatility reasoning rather than purely DEVELOPMENT-derived, and confounded with a
  modest setup-mix difference between sessions — admitted with that caveat disclosed, not hidden.
  Does not conclude ASIAN_LONDON should be disabled.

Neither hypothesis specifies a numerical parameter value — that is explicitly reserved for
WP4B. Budget: 2/3 major hypotheses used, 0/20 candidates used, 0h/3h optimization time used.
`OOS_ACCESS_COUNT` remains `0`; canonical `HYP_001`/`HYP_002` unmodified; final holdout and
post-2026-09-14 prospective evidence untouched.
