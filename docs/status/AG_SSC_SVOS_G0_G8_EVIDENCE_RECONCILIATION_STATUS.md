# AG SSC — SVOS/AG-G0-G8 Evidence Reconciliation (Cycle 1, WORK PACKAGE A)

`ST_SESSION_SWEEP_CONTINUATION_V1`, `lifecycle_stage=OFFLINE_RESEARCH`, `semantic_version=1.0.0`
(`config/governance/strategy_lifecycle.yaml`). This is a read-only inventory. No file
under `strategies/`, `config/governance/`, or `artifacts/validation/.../HYP_00*` was
modified to produce it.

## Method

Every artifact below is real and already exists (produced by earlier, informal missions
— HYP_001 lineage audit, HYP_002 full validation run). This mission's new code
(`hypothesis_stage.py`, `svos_contracts.py`, `g2_population_identity.py`, `g3_gate.py`,
`svos_context_export.py`) FORMALIZES the shapes these artifacts already use; it does not
reinterpret their verdicts.

## G0 — Contract Audit

| | |
|---|---|
| Status | **PARTIAL / CONTRACT_CONFLICT (v1.1.0 candidate only)** |
| Classification | `PRE_REMEDIATION` |
| Evidence | `artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001_LINEAGE_AUDIT/hyp001_lineage_audit.json` (sha256 `ebc7a99f84646362acb7d73367089146bb6d0ecbc4ea7d6bf9612e0554969ba7`) |
| Finding | v1.0.0's own contract (`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`) is internally consistent. The v1.1.0 candidate spec's cited provenance (`candidate_manifest.json`) does not exist anywhere in the repository, on either branch — a genuine spec/evidence disagreement for that candidate only, already correctly flagged `NEEDS_PREREGISTRATION_REPAIR` by the prior audit. Per this mission's own safety rule, HYP_001/v1.1.0 validation stays STOPPED pending owner repair; this is not a new finding, only a formal re-confirmation. |

## G1 — Hypothesis Preregistration

| Hypothesis | Status | Classification | Evidence |
|---|---|---|---|
| HYP_002_SETUP_SELECTIVITY | **PASS (frozen, closed)** | `COUNTING` | `HYP_002_PREREGISTRATION/HYP_002_SETUP_SELECTIVITY_PREREGISTRATION.md`, hash `4e2e4f21c8bf2fe5b461b29ceff670e769445be913d3f193a73e96cc84492fb7` |
| HYP_001_EXIT_CAPTURE (v1.1.0) | **BLOCKED** | `PRE_REMEDIATION` | `HYP_001_PREREGISTRATION/HYP_001_EXIT_CAPTURE_PREREGISTRATION.md` exists but its cited rationale chain is broken (see G0) |

## G2 — Deterministic Population

| Hypothesis | Status | Classification | Evidence |
|---|---|---|---|
| HYP_002 Attempt 1 | INCONCLUSIVE (0 occurrences, insufficient warmup) | `NON_COUNTING` (preserved, never edited) | `HYP_002_ECONOMIC_RESULT/ATTEMPT_1_CLASSIFICATION.json` |
| HYP_002 Attempt 2 | **PASS** — 43 dates, 86 decision cycles, population hash reproducible across 2 independent runs | `COUNTING` | `HYP_002_POPULATION_ATTEMPT_2/population_manifest.json`, population_hash `cf098f9a1d6459618d6c775a087b5cb443b7f1f7d915f650eeb8268381c2eb94` |
| HYP_001_GBPUSD_REPLICATION_R1 | Population generated; adequacy not yet evaluated at mission close | `PRE_REMEDIATION` | `HYP_001_GBPUSD_REPLICATION_R1/POPULATION/` |

`g2_population_identity.compute_population_identity()` (this mission) can reproduce this
exact style of hash for any FUTURE hypothesis; it was not run retroactively against
these frozen historical artifacts, which remain byte-identical to their original form.

## G3 — Economic Gate

| Hypothesis | Status | Classification | Evidence |
|---|---|---|---|
| HYP_002 Attempt 2 | **FAIL** (`EDGE_REJECTED`-equivalent: treatment net expectancy −0.3564R, still ≤ 0) | `COUNTING` (terminal, decisive) | `HYP_002_ECONOMIC_RESULT_ATTEMPT_2/economic_evaluation.json` |

Note: this real evaluation predates `economic_gate.py`'s signed-contract mechanism and
this mission's `g3_gate.py` wrapper — it used a preregistered decision rule recorded
directly in the hypothesis's own preregistration document, not
`config/governance/economic_gate_contract.yaml` (which remains `PROPOSED`, not `SIGNED`,
repo-wide, per `test_economic_gate_evaluator.py::test_real_contract_file_is_proposed_not_signed`).
This is legitimate for a hypothesis-local decision rule and does not conflict with the
strategy-level economic gate remaining unsigned.

## G4 — Controlled Optimization

Not attempted for HYP_002 (correctly — terminal FAIL blocks it). Out of this mission's
authorized scope (Cycle 2, LOCKED).

## G5 — Robustness

Not attempted. Out of scope (Cycle 2, LOCKED).

## G6 — Untouched Holdout

`holdout_run_count=0` for both HYP_001 and HYP_002 — confirmed, unaccessed, sealed. Out
of scope (Cycle 3, SEALED/LOCKED).

## G7 — Canonical Parity

Not attempted. Out of scope (Cycle 4, LOCKED).

## G8 — Forward Shadow

Not attempted. Strategy remains `OFFLINE_RESEARCH`; no shadow series exists for SSC. Out
of scope (Cycle 5, LOCKED).

## EARLIEST_UNSATISFIED_GATE

**G1 (Hypothesis Preregistration) for HYP_001/v1.1.0** — blocked on a missing
`candidate_manifest.json` / unreconciled branch lineage, unchanged from the prior audit's
finding. HYP_002 (the only fully-preregistered, fully-executed hypothesis to date)
already terminated at G3 with a decisive FAIL and is permanently closed
(`VALIDATED_NEGATIVE`) — it must not be reopened. No hypothesis for this strategy has
reached G4. The strategy as a whole has no hypothesis currently eligible to progress
past G1.

## Unknown-lineage discipline

No artifact above was reclassified from its originally-recorded status. Nothing here
converts `PRE_REMEDIATION`/`NON_COUNTING` evidence into `PASS`/`COUNTING`.
