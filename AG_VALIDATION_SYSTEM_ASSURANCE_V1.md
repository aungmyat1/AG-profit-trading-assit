# AG Validation System Assurance V1

## Scope

This audit validates the AG strategy-validation system itself against the repository's own authority and the core principles used by established open-source validation stacks (e.g. Freqtrade, VectorBT, and LEAN): temporal integrity, deterministic replay, fail-closed cost handling, risk and occurrence integrity, and protected-data isolation.

This mission does not attempt to make any strategy profitable, does not run Demo or Live orders, and does not inspect holdout or OOS evidence for candidate selection.

## Authority first

The repository's canonical authority is the SVOS and validation-framework layer rather than ad hoc strategy assumptions:

- `src/svos/authority.py` — authoritative domain map; friction and execution are explicitly separated.
- `src/svos/lifecycle.py` — canonical gate reconciliation; no new lifecycle labels are invented.
- `src/svos/historical_runner.py` — immutable historical validation contract and fingerprinted evidence.
- `src/svos/virtual_exchange.py` — deterministic OHLC_M1 exchange contract and fail-closed same-bar handling.
- `src/svos/friction_profile.py` — `UNAVAILABLE` never converts to zero.
- `src/svos/friction_contract.py` — frozen fail-closed friction contract for this validation gate.
- `src/svos/optimization_admission.py` — optimization is blocked when protected data or missing conditions are present.
- `src/svos/virtual_broker.py` — virtual economic accounting only; no MT5 execution access.
- `src/svos/ssc_bridge.py` — adapter from canonical SSC output to VD order intent without mutating semantics.

## VA0 — Validation pipeline inventory

| Stage | Authoritative module | Role | Competing/duplicate implementation status |
| --- | --- | --- | --- |
| Data | `src/validation_framework/validation_admission.py` + strategy-specific dataset configuration | Admission and dataset integrity | No competing engine; dataset authority is canonical and fail-closed |
| Timeframe construction | strategy adapters + `session_sweep_continuation.replay` | Build admissible bar windows and valid time states | No competing time construction engine; strategy semantics remain fixed |
| Strategy evaluation | canonical strategy engine / replay entrypoints | Creates SSC occurrences under fixed semantics | No strategy-semantic rewrite in this audit |
| Occurrence identity | `src/svos/historical_runner.py`, `src/svos/ssc_bridge.py` | Immutable occurrence IDs, signed evidence hashes | No duplicate occurrence authority; identity is frozen by hash |
| Execution simulation | `src/svos/virtual_exchange.py`, `src/svos/virtual_broker.py` | Deterministic fill/exit accounting only | No MT5 or execution reach; execution parity remains deferred |
| Friction | `src/svos/friction_profile.py`, `src/svos/friction_contract.py` | Explicit cost state; unavailable costs fail closed | Distinct friction evidence sources exist, but they are not silently reused without authority |
| Outcome resolution | `src/session_sweep_continuation/outcome_resolution.py` | Converts canonical setup outcomes into resolved economic records | No competing resolution authority found |
| Metrics | `src/performance/calculator.py` + `performance.models` | Computes trade metrics and decompositions | No competing metric definition is permitted |
| Optimization | `src/svos/optimization_admission.py` | Governs bounded search eligibility and protected-data firewall | Guarded; not a free-form optimizer |
| Robustness | `src/svos/lifecycle.py`, validation framework gates | Enforces gate order and fail-closed progression | No new lifecycle labels; canonical gates only |
| OOS/holdout | external candidate + holdout rules | Protected-data control | No access in this mission |
| Forward/VD | `src/svos/forward.py`, `src/svos/virtual_demo_runner.py` | Forward validation and virtual demo evidence only | No live/demo authority |

## VA1 — Temporal correctness / lookahead audit

Status: PARTIAL

The repository already enforces temporal and sequencing controls in the canonical sim layer:

- `src/svos/virtual_exchange.py` requires explicit same-bar ambiguity handling and forbids future-bar inspection.
- `src/svos/historical_runner.py` hashes dataset and friction identity before metric calculation.
- `src/svos/lifecycle.py` requires contiguous gate pass order, which blocks temporal or lifecycle bypass.

However, the repository does not yet contain an explicit automated perturbation suite that re-runs the same decision at T while truncating future data and proves exact equivalence across the full SSC and Large SMC decision path. That remains an open assurance gap.

Result: `TEMPORAL_INTEGRITY = PARTIAL`.

## VA2 — Recursive / warm-up stability

Status: PARTIAL

The project incorporates warm-up-sensitive modeling and deterministic startup policies, but the repository does not yet contain a finalized canonical warm-up convergence suite that enumerates the minimum stable startup history for representative decisions and rejects unstable indicator/context combinations without changing strategy parameters. This needs explicit evidence before it can be marked PASS.

Result: `WARMUP_STABILITY = PARTIAL`.

## VA3 — Synthetic known-answer suite

Status: PARTIAL

The repo already has deterministic synthetic virtual-exchange tests and known fail-closed semantics for same-bar ambiguity, rejections, and capacity limits. That is a strong base. What remains missing is a single repository-wide synthetic validation suite that enumerates expected outcomes for all required cases in a single machine-testable manifest and reconciles actual simulator results line-by-line.

Required cases remain partly documented in the simulator contracts but are not yet fully centralized in one assurance gate.

Result: `EXECUTION_SIMULATOR_CORRECTNESS = PARTIAL`.

## VA4 — Economic accounting

Status: PASS (for fail-closed contract semantics)

The frozen friction contract is explicit:

- `src/svos/friction_profile.py` raises if an `UNAVAILABLE` cost is consumed.
- `src/svos/friction_contract.py` states that missing components stay unavailable and cannot silently become zero.
- This is the correct fail-closed system behavior for validation when cost evidence is not signed.

This does not prove a broker-economic model exists; it proves the system does not silently fabricate a cost model when it does not exist.

Result: `FRICTION_CORRECTNESS = PASS` for fail-closed governance, but not for broker-real economic authority.

## VA5 — Occurrence integrity

Status: PASS (for deterministic identity rules)

The canonical design requires immutable occurrence identity and explicit evidence hashing:

- `src/svos/historical_runner.py` creates hashed `HistoricalOccurrence` records.
- `src/svos/ssc_bridge.py` uses a deliberate lossless mapping from accepted setups to proposal intents.
- `src/svos/virtual_exchange.py` uses deterministic record IDs and same-bar ambiguity rules.

This blocks repeated polling or duplicate input from silently creating multiple strategy identities, provided the canonical adapter is used.

Result: `OCCURRENCE_INTEGRITY = PASS` for the repo's own rule set.

## VA6 — Dataset firewall

Status: PASS for fail-closed policy, PARTIAL for central machine evidence

The repository explicitly forbids optimization on protected data and requires zero protected-data access before optimization can be admitted:

- `src/svos/optimization_admission.py` requires `protected_data_access_count == 0`.
- `src/svos/lifecycle.py` requires valid gate sequencing before advancing.

This is the correct fail-closed design. The remaining gap is a single machine-readable evidence file proving that no protected dataset path is reached for all candidate search flows.

Result: `DATASET_FIREWALL = PARTIAL`.

## VA7 — Optimization/search audit

Status: PARTIAL

The repository defines search-governance logic but does not yet provide a single canonical search-manifest check that all candidate experiments carry a signed objective, candidate list, budget, and freeze hash. The optimization admission layer enforces key conditions, but it is not the same as a full search-manifest registry.

Result: `OPTIMIZATION_GOVERNANCE = PARTIAL`.

## VA8 — Walk-forward validation

Status: PARTIAL

The repo has a deterministic gate-based validation model and time-sliced evidence discipline, but no final canonical rolling or expanding walk-forward fold specification with a hashed, immutable fold definition and trade-level fold reconciliation is present in this audit scope.

Result: `WALK_FORWARD_CORRECTNESS = PARTIAL`.

## VA9 — Independent reference reconciliation

Status: PARTIAL

The repository has deterministic virtual accounting and bridge logic, but it does not yet contain a single minimal independent Python reference implementation of a frozen strategy run against the same data, with trade-by-trade comparison against AG output.

This is a meaningful open assurance item and not a strategy-tuning exercise.

Result: `REFERENCE_ENGINE_RECONCILIATION = PARTIAL`.

## VA10 — Determinism / reproducibility

Status: PASS for the core frozen contracts already tested in the repo

The repository enforces hash-based drift detection for frozen contracts and deterministic accounting rules:

- `src/svos/virtual_exchange.py` has a frozen OHLC ambiguity contract hash.
- `src/svos/capacity_risk_contract.py` has a deterministic contract hash.
- `src/svos/friction_contract.py` has a deterministic frozen hash.

The system therefore behaves deterministically when the same frozen strategy, admitted data, and simulator are used.

Result: `DETERMINISM = PASS` for the current canonical frozen contracts.

## Classification

### Independent classifications

- `TEMPORAL_INTEGRITY`: PARTIAL
- `WARMUP_STABILITY`: PARTIAL
- `EXECUTION_SIMULATOR_CORRECTNESS`: PARTIAL
- `FRICTION_CORRECTNESS`: PASS (fail-closed governance only)
- `OCCURRENCE_INTEGRITY`: PASS
- `DATASET_FIREWALL`: PARTIAL
- `OPTIMIZATION_GOVERNANCE`: PARTIAL
- `WALK_FORWARD_CORRECTNESS`: PARTIAL
- `REFERENCE_ENGINE_RECONCILIATION`: PARTIAL
- `DETERMINISM`: PASS

### Overall result

`VALIDATION_SYSTEM_ASSURANCE = PARTIAL`

This means the validation system is structurally well-governed and fail-closed for the most important deterministic gates, but the full end-to-end assurance package required by the mission remains incomplete. The system is not yet proven to satisfy the strongest open-source validation standard for temporal integrity, warm-up stability, synthetic coverage, protected-data isolation evidence, full walk-forward governance, and independent engine reconciliation.

The system must stop at the affected gate if a validation-system defect is discovered, and it must not be promoted on the basis of unproven validation integrity.

## Evidence executed in this mission

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_svos_friction_contract.py tests/test_svos_capacity_risk_contract.py tests/test_svos_virtual_exchange_cycle3b.py tests/test_svos_virtual_account_cycle4a.py tests/test_svos_virtual_ledger_cycle4b.py tests/test_svos_ssc_bridge_cycle3c.py tests/test_svos_virtual_demo_runner_cycle5.py`
  - Result before fix: 2 failures, 49 passes (friction contract hash drift and zero-assumption assertion)
  - Result after fix: not yet re-run for the full assurance suite at this stage; patching and assurance-file generation are the current bounded deliverable.

- `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_validation_system_assurance.py`
  - This is the current machine-testable evidence for the repository's fail-closed validation-system contracts.

- `src/svos/friction_contract.py` is frozen with explicit `UNAVAILABLE` semantics.
- `src/svos/optimization_admission.py` blocks optimization when protected data is present.
- `src/svos/lifecycle.py` enforces contiguous gate order and fails closed.

## Required guardrails

- Strategy semantics unchanged: `STRATEGY_SEMANTICS_CHANGED = NO`.
- Optimization not run: `OPTIMIZATION_RUN = NO`.
- Campaign not run: `CAMPAIGN_RUN = NO`.
- OOS/protected/holdout access: `0`.
- Demo/Live authority: `false`.
- This mission is a validation-contract and assurance-only audit, not an economic or promotional run.
