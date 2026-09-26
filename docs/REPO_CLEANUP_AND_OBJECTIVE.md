# Repo cleanup and objective-first path

This repository is already rich in evidence, but the current structure creates a false choice between "read the latest status" and "read the historical design archive." The fastest way to reach the actual objective is to make the active path explicit and keep legacy material clearly labelled as historical context.

## Objective-first priority order

1. Confirm the current authority chain
   - `AGENTS.md`
   - `config/agent_context.json`
   - `PROJECT_STATUS.md`
   - `strategies/registry.yaml`
   - `config/trading.yaml`

2. Keep the active workstream narrow
   - Focus only on one implementation lane at a time: proposal pipeline, validation assurance, execution, or documentation readiness.
   - Do not treat every historical status file as active work.

3. Protect the objective boundary
   - Research-only work stays research-only.
   - Demo/live execution remains gated separately and must not be inferred from presence of code.
   - Proposal output is not an order.

## What should stay high-visibility

Keep these at the top of the navigation surface:

- `README.md` — project purpose, safety model, quick start, and repo map
- `AGENTS.md` — mandatory agent rules
- `PROJECT_STATUS.md` — current state and current blockers
- `docs/README.md` — docs entrypoint and canonical navigation
- `docs/PROJECT_ROADMAP.md` — master roadmap and capability gates
- `strategies/registry.yaml` — strategy authority registry
- `config/trading.yaml` — live/demo safety config
- `tests/` and `scripts/` — the practical execution surface

## What should be treated as historical context

These files are valuable but should not sit in the main entry path unless the task is specifically historical review:

- top-level legacy design snapshots such as `AG_MARKET_INTELLIGENCE_V1_CYCLE*.md`
- one-off investigation documents such as `DEEPSEEK_REVIEW_PACKET.md`
- ad hoc strategy drafts such as `EXTERNAL_SOURCE_STRATEGY_SPEC_DRAFT.md`
- large archive bundles such as `SSC_external_strategy_validation_files.zip`
- large raw research exports under `research_external/` and heavy generated outputs under `artifacts/`

These should be archived into a clear historical bucket or left as intentionally retained evidence files, but they should never be the default path for new work.

## Recommended repo structure

The repo already has the right domains. The cleanup should be organizational, not a rewrite:

- `config/` — active operational config only
- `strategies/` — active strategy authority and registry only
- `src/` — implementation code only
- `tests/` — test assets and focused regression checks
- `docs/status/` — dated evidence; keep the current summary in `PROJECT_STATUS.md`
- `docs/plans/` — active planning documents only
- `docs/archive/` or similar — historical research/design docs when the project is ready to formally archive them
- `artifacts/` — generated outputs only, with clear retention policy
- `data/` and `research_external/` — keep for payload or reference evidence; do not make them the default project entry point

## Recommended cleanup actions

### Immediate (low-risk, high-value)

- Keep one canonical start page: `README.md` plus `docs/README.md`
- Add an objective-first section to the top-level README
- Keep `PROJECT_STATUS.md` as the current source of truth for active status
- Label historical files as "design-only" or "historical evidence" in their headers
- Avoid creating new roadmap docs while the active roadmap remains unclear

### Next wave

- Move older design snapshots under `docs/archive/legacy/` after a reference check
- Consolidate duplicate status documents or group them by milestone
- Add a lightweight retention policy for generated artifacts and journal files
- Reduce top-level noise by moving non-authoritative root docs under a legacy folder only after confirming no active links depend on them

### Avoid for now

- Mass renames of directories or files that are still linked from the project status and docs index
- Rewriting strategy logic or deleting dated evidence without explicit project approval
- Changing the authority chain while the active validation gate remains incomplete

## Shortest path to project objective

The project objective is faster when every new task begins from this sequence:

1. Read `AGENTS.md`
2. Read `PROJECT_STATUS.md`
3. Read the relevant strategy or config authority
4. Run the smallest relevant check or status script
5. Make one narrow change
6. Re-run the focused proof

This avoids the main trap in the repo today: chasing historical documents instead of working from the current authority and evidence record.
