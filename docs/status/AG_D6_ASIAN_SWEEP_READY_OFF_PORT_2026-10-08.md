# D6 port to main — ST_ASIAN_SWEEP_5R_V1 READY authority OFF (2026-10-08)

Ports `hotfix/d6-asian-sweep-ready-off` onto `main` (`3496ec3`) as a registry/config flag
(`config/v1_tickets/ready_authority.yaml`). No code is deleted, and strategy logic, levels and
thresholds are unchanged.

## Equivalence vs 9419b21 (verdict before this port: main NOT equivalent)

| Output | main 3496ec3 (before) | Hotfix 9419b21 | This port |
|---|---|---|---|
| Legacy V1 ticket `decision: READY` | **emitted** (no switch) | SHADOW_INFO_ONLY | SHADOW_INFO_ONLY |
| Manual `TICKET_READY` | blocked only because v1.1.1 L2 always FAILs (incidental) | TICKET_BLOCKED (`READY_AUTHORITY_OFF_D6`) | same as hotfix |
| `WATCH_READY` (actionability) | blocked only because the policy is unsigned (incidental) | n/a — `actionability.py` postdates the hotfix | **INFO_ONLY_SUPPRESSED**, terminal, even with a signed policy |

The hotfix was based on `fc60cdb`, which predates `actionability.py`. Ported as-is, a
SHADOW_INFO_ONLY ticket fell through actionability's signal path. With a signed policy, that
path reaches `WATCH_READY`, which
`test_actionability_and_canonical_ticket.py::test_fresh_actionable_signal_is_watch_ready`
showed with the switch OFF. The added guard closes this gap. The port is otherwise identical
to the hotfix.

## Commits

| Port | Hotfix | Note |
|---|---|---|
| `1168912` | `9419b21` | config switch, `ready_authority.py`, fx wiring, tests (patch-equivalent) |
| `4ded91f` | `ccdbbef` | READY-ON opt-in for pre-D6 tests (patch-equivalent) |
| `14cbbc4` | `afbc49a` | opt-in list +3 files (patch-equivalent) |
| this PR | — | actionability guard, two pre-port main test files added to the opt-in list, AGP-LOGIC-AS-02 note |

Hotfix-only commits not ported: **none** (`git cherry` shows all three as equivalent).

## AGP-LOGIC-AS-02

Re-enabling (`ready: ON`) requires explicit owner confirmation recorded in `docs/governance/`.
Passing tests or a logic-verified candidate (v1.1.2, PR #62) never re-enable it.

## Tests (2026-10-08, Linux)

- `tests/test_d6_actionability_suppressed.py`: 8 passed. Covers the signed-policy case,
  terminal at any time, the daily evaluator, and ON restoring the pre-D6 WATCH_READY.
- `tests/test_d6_ready_authority.py` + `tests/test_actionability_and_canonical_ticket.py` + the new file: **40 passed**
- `python -m pytest tests -q`: **1165 passed, 2 skipped**
