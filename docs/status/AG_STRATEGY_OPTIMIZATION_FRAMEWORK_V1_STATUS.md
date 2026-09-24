# AG Strategy Optimization Framework V1 — Status

**As of:** 2026-09-24<br>
**Classification:** `CONTROL_PLANE_IMPLEMENTED; NO_OPTIMIZATION_AUTHORIZED`<br>
**Lifecycle authority:** unchanged — `config/governance/strategy_lifecycle.yaml` through `validation_framework.lifecycle_registry`<br>
**Execution / Demo / Live authority:** unchanged and owner-controlled

## 1. Outcome and scope boundary

The common, strategy-agnostic research control plane is implemented under
`src/strategy_optimization/`. It provides immutable baseline, hypothesis, candidate,
dataset, result, and owner-decision contracts; a per-experiment write-once registry;
a monotonic research-candidate state machine; an explicit dataset-role firewall; and a
paired metric identity/comparison schema.

It is a wrapper around existing authorities, not a replacement lifecycle, optimizer,
strategy engine, trade manager, or execution service. It does not mutate strategy
configuration, `strategies/registry.yaml`, lifecycle stages, owner decisions, broker
state, or Demo/Live permission. A `PromotionDecision` is evidence of a human decision;
recording one never edits strategy authority.

The bootstrap only read strategy/configuration and existing status/provenance metadata.
It did not load price/trade rows, execute a replay, compare arms, calculate economic
metrics, optimize parameters, or consume OOS/final-holdout inputs.

## 2. Reused canonical authorities

| Concern | Reused authority | Framework boundary |
|---|---|---|
| Per-strategy rules/version | `strategies/<ID>.yaml` | Frozen by source SHA in an inventory/experiment; not edited |
| Execution/demo/live permission | `strategies/registry.yaml` and existing authorization checks | Read-only; no permission is inferred from registration or experiment state |
| Strategy lifecycle | `config/governance/strategy_lifecycle.yaml` via `validation_framework.lifecycle_registry` | Sole lifecycle authority; program candidate states are subordinate research workflow only |
| Hypothesis preregistration | `svos.hypothesis.HypothesisContract` | Adapter requires a frozen SVOS hash; it does not preregister by construction |
| Candidate freeze | `svos.candidate.CandidateFreeze` / `freeze_candidate` | Adapter delegates only after a candidate version is assigned; no second freeze authority |
| Bounded optimization | `svos.optimization.BoundedOptimizer` | Existing bounded search remains the optimizer; framework adds admission/identity/access controls, not a new search algorithm |
| Optimization admission | `svos.optimization_admission.evaluate_under_contract` and `config/governance/optimization_admission_contract.yaml` | Registry evaluates the canonical signed contract before `DEVELOPMENT_TESTED` or `ROBUSTNESS_PASS` |
| Dataset legacy compatibility | `external_candidate.models.DatasetRole` | Program roles remain distinct; only development roles map to legacy `OPTIMIZATION` |
| Performance calculations | `performance.calculator` / `performance.models.TradeMetrics` | Adapter normalizes fields; it does not recalculate or infer unavailable net results |
| Fingerprints | `post_asian_pilot.fingerprint.fingerprint` | Canonical hasher reused for manifests and hash chains |

The optimization-admission contract is currently `PROPOSED`, not signed. Therefore the
framework's development-result and robustness transitions are presently blocked even if
other preconditions were later supplied. This package does not sign or repair that
contract.

## 3. Frozen strategy-track inventory

The initial, write-once inventory is
[`AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1_INITIAL_FREEZE.json`](../../artifacts/optimization/inventory/AG_STRATEGY_OPTIMIZATION_FRAMEWORK_V1_INITIAL_FREEZE.json).
It stores each canonical config fingerprint, lifecycle/version identity, authority
flags, strategy-specific adapter, existing evidence references, and any version
conflicts. It is an inventory snapshot, not a lock on canonical config files.

| Strategy track | Canonical version / stage | Current inventory observation | Scope decision |
|---|---|---|---|
| `ST_SESSION_SWEEP_CONTINUATION_V1` | `1.0.1` / `OFFLINE_RESEARCH` | `CURRENT_VALIDATION_STATE.json` declares `1.0.0`; the inventory flags this stale/version-mismatched evidence snapshot without replacing the lifecycle authority. HYP_001 remains frozen and unexecuted; its next safe gate is owner adjudication of the control-arm comparability amendment. | No WP4B, new replay, or parameter search. No new SSC hypothesis or measurement was started. |
| `ST_LIQUIDITY_SWEEP_RETEST_V1` | `2.0.0` / `FORWARD_RESEARCH` | Task C is an implemented engineering candidate, but the 99/50/49/48 control population and friction assumptions remain unreproduced. | Registered as `IMPLEMENTED / BLOCKED_REPRODUCIBILITY / NOT_AVAILABLE`; no candidate comparison or replay. |
| `ST_LARGE_SMC_V1` | `1.0.7` / `FORWARD_RESEARCH` | Existing forward-to-shadow evidence-contract packet is an unsigned draft; this mission ran no measurement. | No E-to-M or C10 measurement work was started. |
| `ST_ASIAN_SWEEP_5R_V1` | `1.1.1` / `OPERATIONAL_SHADOW` | Kept as a distinct strategy/version/data/evidence track; Demo and Live remain unauthorized. The request's weak-edge focus was not independently re-evaluated here. | Inventory only; no replay, strategy change, or promotion. |

These identities and evidence remain strategy-scoped. The common framework does not pool
samples, hypotheses, candidate versions, metrics, or decisions across the four tracks.

## 4. Contracts and immutable registry

The strategy-agnostic contracts are in `src/strategy_optimization/models.py`:

- `StrategyBaseline` — strategy/version, canonical config SHA, reproducibility status,
  baseline SHA, dataset/population/friction identities, source refs, and blockers.
- `ExperimentHypothesis` — statement/mechanism, exactly declared permitted and forbidden
  deltas, preregistration status/hash, development identity, protected dataset IDs,
  acceptance rule, and bounded-search budget. Its adapter must match the canonical SVOS
  preregistration hash.
- `CandidateStrategy` — parent/candidate version, candidate config and implementation
  hashes, permitted/forbidden changes, and owner version-assignment status. The later
  freeze delegates to `svos.candidate`.
- `DatasetManifest` — strategy-scoped dataset ID/hash/role and reuse lineage.
- `ExperimentMetrics` / `ExperimentResult` — distinct gross, friction, and net fields,
  gross-classification labels, funnel/concurrency slots, sample size, and evidence refs.
  Unavailable values remain `null`/`NOT_EVALUATED`, never zero.
- `PromotionDecision` — explicit owner, rationale, timestamp, authority reference, and
  decision disposition. It cannot claim to change execution authority.

`ExperimentRegistry` writes a manifest once, appends state/result/decision events to a
hash-chained JSONL ledger, revalidates result artifacts and their registered dataset/read
provenance, rejects ID reuse, and fails closed on missing/tampered ledgers. Entering
`PREREGISTERED` requires a reproducible baseline with a matching development dataset plus
an SVOS hypothesis whose frozen preregistration hash verifies. The paired-comparison API
requires that explicit reproducible baseline and matching control config/dataset/population/
friction identities before it can emit numeric deltas. A terminal state cannot be reset;
remediation requires a new experiment ID. Only the existing signed admission contract can
permit a transition into development-result/robustness stages. The exact contract bytes
and condition map are retained and re-evaluated from the event evidence; the protected-data
count is reconciled against validated access ledgers. A caller cannot override these gates
with a boolean flag.

## 5. Candidate state and terminal outcomes

The program workflow uses the proposed research states:

`DRAFT → PREREGISTERED → DEVELOPMENT_TESTED → ROBUSTNESS_PASS → CANDIDATE_FROZEN →
REPLICATION_PASS → OOS_PASS → HOLDOUT_PASS → PARITY_PASS → FORWARD_RESEARCH → OWNER_REVIEW`.

`CandidateState` is not `LifecycleStage` and never advances the canonical strategy
lifecycle. Each transition requires typed evidence references; development and robustness
also require the signed optimization-admission contract. Terminal outcomes include
`BLOCKED_REPRODUCIBILITY`, `BLOCKED_DATA`, `BLOCKED_SEMANTICS`, `BLOCKED_AUTHORITY`,
`REJECTED_NEGATIVE`, `REJECTED_UNSTABLE`, `REJECTED_SAMPLE_INSUFFICIENT`, and
`REJECTED_OWNER_DECISION`. Owner rejection is terminal and can only be recorded through
the immutable owner-decision API; a generic research transition cannot impersonate it.
Terminal states are irreversible, and a failed stage never falls through into parameter
search.

## 6. Dataset roles and fail-closed access

Program dataset roles are `DEVELOPMENT`, `DEVELOPMENT_REUSED`, `REPLICATION`, `OOS`,
`FINAL_HOLDOUT`, and `FORWARD_SHADOW`. Only the first two can map to the existing SVOS
optimizer's `OPTIMIZATION` role. Legacy `VALIDATION` does not collapse replication and
OOS in program manifests. `FINAL_HOLDOUT` maps to the existing holdout role; forward
shadow has no historical optimizer mapping.

`DatasetAccessFirewall` pins dataset ID/hash/strategy/role manifests once, prevents a
protected content hash from being relabeled as development or aliased across strategies,
requires explicit prior experiment/dataset lineage for reused development data, and
writes access intent before invoking the reader callback. Replication, OOS, and final
holdout permit one authorized read attempt each; even a failed reader consumes the
attempt. The firewall obtains candidate state and strategy identity from the verified
experiment registry; the caller's state argument must match and cannot grant access.
Development-evaluation/robustness admission snapshots are stored with their exact contract
text and conditions and re-evaluated on ledger reads. The protected-data count is derived
from validated protected-role access ledgers, not accepted as an unchecked caller claim.
An evaluated result is accepted only when its dataset manifest matches and a completed
pre-read access record exists for the same experiment/strategy/role/purpose. Missing or
tampered access ledgers fail closed. Forward-shadow reads are logged as observations and
cannot enter the optimizer.

The firewall applies to code that routes dataset consumption through its API. It is not
an operating-system sandbox for arbitrary code that opens files directly; future replay
adapters must make this firewall the required ingestion path. The current inventory and
Task C bootstrap did not register or read any market-data dataset.

## 7. Task C registration and baseline provenance result

Task C is recorded in
[`artifacts/optimization/experiments/AG_LSR_TASK_C_PER_SYMBOL_POSITION_GUARD_V1/`](../../artifacts/optimization/experiments/AG_LSR_TASK_C_PER_SYMBOL_POSITION_GUARD_V1/):

- `implementation=IMPLEMENTED` — current implementation/test source fingerprints are
  recorded as an engineering candidate. `OpenPositionGuard` no-symbol callers remain
  global; the Sweep Retest engine explicitly passes its setup symbol. The unused
  `max_open_strategy_positions` config field remains unwired.
- `experiment=BLOCKED_REPRODUCIBILITY` — exact baseline not reproduced; dataset role is
  unset; no control or candidate result exists. The block is terminal for this experiment
  ID.
- `economic_claim=NOT_AVAILABLE` — no improvement, edge, or causal claim is asserted.
- Candidate strategy version is pending owner assignment. There is no promotion or
  lifecycle transition.

The provenance search is recorded in
[`AG_LIQUIDITY_SWEEP_RETEST_BASELINE_PROVENANCE_SEARCH_V1.json`](../../artifacts/optimization/evidence/AG_LIQUIDITY_SWEEP_RETEST_BASELINE_PROVENANCE_SEARCH_V1.json).
The reported `99 setups / 50 taken / 49 blocked / 48 historical rejections` remain
unverified claims, not registered metrics. The local clone is shallow; local history and
tags contain no source baseline, and prior remote recursive-tree queries printed no
matching paths but were inconclusive because errors were suppressed. GitHub code search
was unavailable (HTTP 404). The cited engineering commit `18947755` is absent locally;
its remote resolution was unavailable/not confirmed. The current Task C source patch is
preserved as an engineering candidate only. The write-once Task C/inventory snapshots
retain the earlier non-versioned status-document reference; that compatibility path now
links to the canonical `AG_TASK_C_PER_SYMBOL_POSITION_GUARD_V1_STATUS.md`. The current
manifest builder and track adapter use the canonical versioned path. The immutable
snapshots were not rewritten and the write-once bootstrap was not rerun.

Missing reproduction inputs include the original replay revision/script/config, exact
99-setup membership/exclusion rules, the relationship between the 50/49/48 counts,
canonical dataset identity, and the friction/fill assumptions. No substitute dataset,
replay, candidate comparison, or parameter search is authorized by this block.

## 8. Verification

Focused framework suite:

```text
PYTHONPATH=src pytest -q \
  tests/test_strategy_optimization_contracts.py \
  tests/test_strategy_optimization_registry.py \
  tests/test_strategy_optimization_dataset_firewall.py \
  tests/test_strategy_optimization_inventory.py
```

Final verification on 2026-09-24:

- Framework-focused suite: **42 passed** across contracts, registry, dataset firewall,
  and inventory tests.
- Adjacent regression suite: **32 passed** across SVOS optimization/admission,
  canonical experiments, performance metrics, and validation-system assurance.
- Documentation links: **4 passed**; `DOCS_LINK_CHECK = PASS`,
  `BROKEN_RELATIVE_LINKS = 0`, `UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0`.
- `python -m compileall` and `git diff --check`: passed.

No full project suite was run for this common control-plane change. Existing Task C
verification and full-suite classifications remain in
`docs/status/AG_TASK_C_PER_SYMBOL_POSITION_GUARD_V1_STATUS.md`.

## 9. Non-authority statement

No strategy modification, optimization search, candidate comparison, economic promotion,
portfolio allocation, lifecycle advancement, Demo/Live authorization, execution
capability, or broker operation is included. Owner authority is retained for all strategy
and trading decisions. No push or merge was performed.
