# Agent Prompt — AG Edge + AI Runtime V1 Foundation (P0 + P1 + P2)

You are the primary repository builder for AG Profit Trading. Execute only the bounded foundation mission below. Do not continue into MT5 indicator implementation, strategy migration, risk migration, Control API implementation, or Demo execution changes.

## Mission

Implement the foundation for `AG Edge + AI Runtime V1`:

- P0 — reconcile and freeze the migration baseline;
- P1 — define/freeze canonical Contracts V1;
- P2 — create the non-disruptive target architecture shell and dependency boundaries.

Read first:

1. `AGENTS.md`
2. `PROJECT_STATUS.md` current rolling classification
3. `docs/plans/AG_EDGE_AI_RUNTIME_V1_IMPLEMENTATION_PLAN.md`
4. current Gate-2 / owner-decision / execution status documents referenced by `PROJECT_STATUS.md`
5. `strategies/registry.yaml`
6. relevant execution/MT5/authorization source and tests needed to prove no authority regression

## Critical baseline rule

The planning document was committed from planning baseline:

`1a8e7c5d922ba48423dca1b7858f8895afe0d66f`

Do NOT assume that SHA is the final implementation baseline. Current Gate-2 work may have a newer accepted candidate. Before writing production-adjacent foundation code:

1. fetch/reconcile current `origin/main` and relevant accepted Gate-2 lineage;
2. identify the latest owner-accepted / independently verified baseline suitable for migration;
3. if acceptance is ambiguous, STOP and report `MIGRATION_BASELINE_AMBIGUOUS` rather than choosing silently;
4. freeze the selected SHA/tree in the migration status/ADR.

Never merge unfinished Gate-2 remediation into architecture changes.

## Global invariants

You MUST preserve all of these:

- zero AI broker execution authority;
- no automatic execution;
- no Live authorization expansion;
- no Demo authorization expansion;
- no strategy semantic changes;
- no risk-policy changes;
- no change to current broker mutation behavior;
- no new broker mutation route;
- no deletion/relocation of the existing runtime in this mission;
- no MT5 indicator implementation in this mission;
- no cloud deployment;
- no Vite/frontend rewiring;
- no scheduler migration;
- no historical evidence rewriting;
- no weakening/skipping of existing safety tests to obtain green results.

The canonical owner decision and execution boundaries remain authoritative until later parity-gated replacement work.

## Git/worktree discipline

Use one dedicated branch/worktree from the frozen implementation baseline, e.g.:

`arch/edge-ai-runtime-v1-foundation`

One writer only. Do not push unless the owner separately instructs you to push. Do not modify remote `main`.

Before changes record:

- branch;
- HEAD;
- origin/main;
- selected migration baseline SHA;
- tree hash;
- worktree cleanliness;
- relevant authorization state;
- current broker mutation surfaces.

## P0 — Freeze migration baseline

Create a migration status artifact under `docs/status/` and an architecture ADR under `docs/architecture/` (use repository naming conventions discovered from the repo).

Record at minimum:

- `MIGRATION_BASE_SHA`
- `MIGRATION_BASE_TREE`
- why this baseline is accepted;
- Gate-2 relationship/status;
- baseline test evidence available/reproduced;
- known baseline/environment failures separately classified;
- current strategy registry Demo/Live authorization state;
- canonical owner-decision route/entrypoint;
- all production `order_check` / `order_send` call sites;
- current legacy-route containment state;
- rollback/base recovery instructions.

Do not claim tests you did not run.

P0 exit:

`ARCH_BASELINE_FROZEN = PASS`

Otherwise stop.

## P1 — Contracts V1

Create the new package boundary without moving old code:

```text
packages/contracts/
```

Define canonical, versioned contracts for:

- `MarketState`
- `Opportunity`
- `ProposalEligibilityDecision`
- `Proposal`
- `OwnerDecision`
- `ExecutionRequest`
- `ExecutionResult`
- `AccountState`
- contract/semantic errors

Use the project's supported Python/tooling conventions; do not introduce a large new framework unless existing dependencies justify it.

### Contract design requirements

Applicable contracts carry stable provenance/identity:

- `schema_version`
- `event_id`
- `created_at`
- `symbol`
- `source`
- `correlation_id`
- `semantic_hash`

Do not mechanically force fields where semantically invalid; document any exception.

Required properties:

- deterministic serialization;
- deterministic semantic hash over canonical semantic fields;
- finite-number validation for trading numeric values;
- explicit timestamps/timezone semantics;
- immutable decision/proposal identity once created;
- explicit reason codes for fail-closed/rejected states;
- version-aware parsing;
- no broker objects/types in contracts;
- no MetaTrader5 import;
- no AI/LLM dependency;
- no execution side effect.

### MarketState rule

MarketState represents facts only. It may contain facts such as:

- session state/levels;
- market structure facts;
- liquidity/sweep facts;
- spread/price metadata;
- freshness/provenance.

It MUST NOT contain authoritative `BUY`, `SELL`, approved volume, risk approval, owner approval, or broker execution commands.

### Funnel semantics

Preserve:

```text
MarketState -> Strategy -> Opportunity -> ProposalEligibilityDecision -> Proposal
```

An Opportunity may exist while eligibility is rejected. A rejected eligibility decision MUST NOT masquerade as an executable Proposal.

### Contract tests

Add focused tests for at least:

- round-trip serialization;
- stable semantic hashing;
- hash changes on semantic mutation;
- non-finite NaN/Inf rejection;
- malformed timestamp rejection;
- schema-version behavior;
- identity immutability or equivalent construction discipline;
- symbol/provenance mismatch validation where applicable;
- Opportunity vs Proposal distinction;
- MarketState cannot encode an execution command;
- no broker/MT5 imports in `packages/contracts`.

P1 exit:

`CONTRACTS_V1_FROZEN = PASS`

## P2 — Architecture shell + dependency boundaries

Create empty/minimal package shells only as needed for:

```text
apps/
  control-api/
  owner-edge/
  web/
packages/
  contracts/
  strategy-core/
  risk-engine/
  execution-core/
mt5/
  indicators/
  expert/
  include/
research/
  backtests/
  replay/
  virtual_demo/
  optimization/
  experiments/
  reports/
```

Do not move existing `src/`, `scripts/`, `web/`, strategy implementations, replay implementations, or execution code in this mission.

Add machine-checkable dependency/boundary tests where practical. At minimum prove:

- contracts cannot import broker/MT5 modules;
- strategy-core shell cannot depend on owner-edge or broker mutation modules;
- control-api shell has no direct broker mutation dependency;
- AI-facing layer has no direct broker mutation dependency;
- only the future owner-edge boundary is designated to contain new-order broker mutation after later gates;
- current production mutation surfaces remain unchanged from baseline.

P2 exits:

- `NEW_ARCH_SHELL_READY = PASS`
- `OLD_RUNTIME_UNCHANGED = PASS`
- `BROKER_CALL_DELTA = 0`
- `STRATEGY_SEMANTIC_DELTA = 0`
- `RISK_POLICY_DELTA = 0`
- `AUTHORIZATION_DELTA = 0`
- `DEMO_AUTHORIZATION_EXPANSION = NO`
- `LIVE_AUTHORIZATION_EXPANSION = NO`

## Validation strategy

Use progressive testing:

1. new contract unit tests;
2. new architecture/dependency tests;
3. affected existing owner-decision/execution safety tests;
4. broader relevant backend regression;
5. full backend suite only if environment capacity makes it reasonable and repository policy requires it.

Classify every failure as one of:

- candidate regression;
- pre-existing baseline;
- environment/live-state;
- stale expectation;
- unknown.

Never convert an unknown into a pass.

If the host is resource constrained, do not change safety semantics to make tests run. Report environment blocking separately.

## Files allowed

Expected scope is limited to new foundation architecture/contracts/tests/docs plus minimal packaging configuration required to make those tests importable.

Examples:

- `packages/contracts/**`
- minimal `apps/**` shell files
- minimal `packages/strategy-core/**` shell files
- minimal `packages/risk-engine/**` shell files
- minimal `packages/execution-core/**` shell files
- minimal `mt5/**` placeholder/readme/package-boundary files, NOT MQL5 logic
- minimal `research/**` placeholder/readme/package-boundary files
- `tests/**` for contract/boundary tests
- `docs/architecture/**`
- `docs/status/**`
- docs indexes/status references if repository policy requires them
- minimal `pyproject.toml`/test config change only if necessary

Any modification to existing production strategy, risk, execution, MT5 gateway, API execution route, scheduler, or frontend production logic is OUT OF SCOPE. Stop and ask for a new bounded mission if required.

## Explicitly prohibited files/behaviors

Do not modify production behavior in:

- existing `src/execution/**`
- existing `src/mt5/**` broker mutation logic
- existing owner-decision behavior
- `strategies/registry.yaml` authorization values
- trading authorization config
- legacy route containment behavior
- execution confirmation semantics

Do not add `.mq5` trading/indicator implementations yet.

## Required final report

Produce `AG_EDGE_AI_RUNTIME_V1_FOUNDATION_STATUS` with:

```text
CLASSIFICATION = FOUNDATION_PASS | FOUNDATION_FAIL | FOUNDATION_BLOCKED

MIGRATION_BASE_SHA = ...
MIGRATION_BASE_TREE = ...
BRANCH = ...
HEAD = ...
WORKTREE = CLEAN/DIRTY

P0_ARCH_BASELINE_FROZEN = PASS/FAIL
P1_CONTRACTS_V1_FROZEN = PASS/FAIL
P2_NEW_ARCH_SHELL_READY = PASS/FAIL
OLD_RUNTIME_UNCHANGED = PASS/FAIL

BROKER_CALL_DELTA = 0/...
STRATEGY_SEMANTIC_DELTA = 0/...
RISK_POLICY_DELTA = 0/...
AUTHORIZATION_DELTA = 0/...
DEMO_AUTHORIZATION_EXPANSION = NO/YES
LIVE_AUTHORIZATION_EXPANSION = NO/YES

NEW_TESTS = ...
AFFECTED_REGRESSION = ...
FULL_BACKEND = ... or NOT_RUN(reason)
FAILURE_CLASSIFICATION = ...

FILES_CHANGED = ...
COMMITS = ...
PUSHED = NO unless explicitly authorized

NEXT_GATE = INDEPENDENT_FOUNDATION_AUDIT
```

Include exact commands and observed results. Do not fabricate counts.

## Stop condition

After P0/P1/P2 are implemented and locally committed, STOP. Do not begin P3 MT5 MarketState work. The next action is an independent audit of the foundation candidate.
