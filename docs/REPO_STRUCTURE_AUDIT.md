# Repository structure audit

Date: 2026-09-25

## Objective alignment

The repository already has the right high-level runtime boundaries for the project objective:

- `src/strategy_engine/`, `strategies/`: deterministic strategy authority.
- `execution/`, `mt5/`, `trade_management/`: execution and position-management boundaries.
- `.agents/skills/`, `.claude/skills/`: advisory skill mirrors.
- `config/`, `state/`, `data/`, `artifacts/`: configuration, runtime state, inputs, and evidence.
- `web/`: frontend surface.
- `tests/`: regression coverage.

These directories should remain separate. In particular, generated evidence must not be moved into source packages, and advisory skills must not be moved into execution packages.

## Cleanup completed

Removed local Python/test caches that are ignored by version control:

- root `__pycache__/`
- root `.pytest_cache/`

No tracked source, strategy, state, evidence, or user changes were deleted or moved.

## Findings and recommendations

1. Keep the repository root limited to project entry documents and packaging metadata. The root currently contains many historical design/status documents and generated review packets. Move future historical material into `docs/status/` or `docs/archive/` with an index; do not bulk-move existing files without checking links and lineage.
2. Treat `artifacts/` as immutable evidence output. Add retention/index tooling before deleting or consolidating artifacts; filenames encode validation lineage.
3. Keep `data/` for admitted datasets and provenance manifests. Quarantined or external datasets should remain under explicitly named subdirectories such as `data/research/` and `research_external/`.
4. Keep runtime outputs (`logs/`, `journal/`, `state/`) out of source imports. The existing ignore rules correctly exclude local logs, journals, caches, and diagnostics.
5. Preserve the current `.agents/` and `.claude/` dual skill layout until the documented runtime mirror contract is retired; deduplicating it now could break discovery.
6. Add a lightweight structure check in CI that rejects tracked caches, secrets, and generated local logs, and verifies required authority directories exist.

## Current risk

The main structural risk is document and evidence sprawl, not an unsafe source/package layout. The safest next cleanup milestone is an indexed archival policy, followed by link-aware migration of historical root documents.
