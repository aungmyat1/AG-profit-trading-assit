# AG Profit Trading Documentation Governance

**Status:** `ACTIVE_MAINTENANCE_CONTRACT`  
**Introduced:** 2026-09-21  
**Authority boundary:** documentation governance only; this document grants no strategy, proposal, Demo, Live, broker-send, or external-delivery authority.

## Purpose

This contract defines the repository-wide documentation architecture used by humans and coding agents. It keeps current truth, design intent, historical evidence, machine-readable evidence, and execution authority separate while making documentation discoverable and maintainable.

## Authority hierarchy

| Concern | Primary source |
|---|---|
| Whole-project current status | `PROJECT_STATUS.md` |
| Documentation navigation | `docs/README.md` |
| Master readiness plan | `docs/PROJECT_ROADMAP.md` |
| Domain navigation | `docs/<domain>/README.md` |
| Architecture/design contracts | relevant `docs/**/*.md` design documents |
| Dated implementation/validation evidence | `docs/status/*.md` |
| Machine-readable frozen evidence | relevant manifests / JSON artifacts |
| Agent operating rules | `AGENTS.md` |
| Strategy registration/authorization | `strategies/registry.yaml` and `strategies/STRATEGY_LEDGER.md` |
| Runtime execution gates | authoritative runtime/configuration contracts |

A lower-authority document must not override the source that owns the claim.

## Non-collapsible states

```text
DESIGN != IMPLEMENTED
IMPLEMENTED != VALIDATED
VALIDATED != STRATEGY_AUTHORIZED
CANDIDATE != PROPOSAL
PROPOSAL != RISK_APPROVAL
RISK_APPROVAL != EXECUTION_AUTHORIZATION
RESEARCH_QUALIFIED != ACTIONABLE_READY
```

Documentation wording, serialization, UI compatibility, or agent interpretation must not collapse these boundaries.

## Document classes

- `CURRENT` — rolling present truth.
- `DESIGN` — intended architecture or contract; non-authorizing by itself.
- `ROADMAP` — planned gates and work sequence.
- `STATUS_EVIDENCE` — dated evidence for implementation, validation, or operations.
- `AUTHORITY` — explicit bounded authority source.
- `OPERATIONS` — setup/runbook/maintenance instructions.
- `HISTORICAL` — retained evidence that may have been superseded.

New high-value documents should make their role and authority boundary explicit without requiring repository-wide front-matter migration.

## Navigation rules

1. `docs/README.md` is the human and agent entry point for repository documentation.
2. Every primary `docs/<domain>/README.md` must be discoverable from `docs/README.md`.
3. Domain indexes own detailed navigation for their domain; the root index should link rather than duplicate.
4. New material status evidence should be linked from the relevant current-status or domain navigation surface.
5. Internal links should normally be repository-relative.

## Historical evidence rules

Dated status evidence is not a rolling wiki. Preserve what was established at that time.

If later evidence supersedes a result, create a new status record or add an explicit dated addendum where a correction is necessary. Do not silently rewrite history merely to make an old status read like the current project state.

A correction should identify:

- correction date;
- original statement or gap;
- authoritative evidence now available;
- whether implementation or authorization changed.

## Machine-readable evidence

Manifests and JSON evidence should be preferred for deterministic facts such as fingerprints, counts, frozen identities, gate results, and structured status fields. Narrative documents should reference them rather than duplicating mutable values unnecessarily.

Machine-readable evidence does not grant trading authority unless the governing authority explicitly defines that effect.

## Documentation change checklist

For documentation-affecting work:

1. identify the authority owning each changed claim;
2. update `PROJECT_STATUS.md` when current whole-project truth materially changes;
3. preserve dated historical evidence or use an explicit correction/addendum;
4. update `docs/README.md` when a document domain is added, moved, renamed, or materially changes role;
5. check relative Markdown links after moves/renames;
6. keep strategy and execution authority unchanged unless separately and explicitly authorized;
7. record exact tests/evidence rather than using broad words such as `supported` or `working`;
8. run the repository documentation-integrity check when available.

## Integrity gate

The target documentation integrity gate is:

```text
DOCS_LINK_CHECK = PASS
BROKEN_RELATIVE_LINKS = 0
UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0
```

A lightweight checker should validate relative Markdown link destinations and root discoverability for primary documentation-domain indexes. It should be deterministic, standard-library-first where practical, and must not become a competing documentation framework.

Until automated enforcement is committed, these checks remain a required review responsibility.

## Fail-closed terminology

Keep these states distinct:

- `NOT_IMPLEMENTED`
- `INTERFACE_ONLY`
- `UNIT_TESTED`
- `RESEARCH_ONLY`
- `NOT_VALIDATED`
- `BLOCKED`
- `NOT_AUTHORIZED`
- `DEMO_VERIFIED`
- `LIVE_VERIFIED`

Do not infer a stronger state from a weaker one.

## V2 application

`docs/v2/README.md` is the V2 navigation surface. V2 architecture, roadmap, opportunity-strategy model, and safety/authority documents are design/contracts unless dated implementation evidence establishes otherwise. Current whole-project truth remains owned by `PROJECT_STATUS.md`.

## Maintenance authority

Operational update procedure remains defined by `docs/status/LIVE_STATUS_MAINTENANCE.md`. This governance document defines the repository-wide documentation model; the maintenance document defines how status evidence is kept synchronized during project work.
