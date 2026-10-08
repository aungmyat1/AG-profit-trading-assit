---
class: authority
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# AG Owner Decision Register

Running register of owner decisions (created 2026-10-08, DOCS-LIVE-2-NEXT). It records **only the
owner's open questions and the options the owner stated** — no recommendation and no default.
A row stays `PENDING_OWNER` until the owner records a choice here (Decision, Date, Source).
Resolved decisions keep their row and cite the authority that carries them. Dated decision
records stay where they are (e.g. `AG_V1_TWO_GOALS_OWNER_DECISIONS.md`, D1–D8); this register
does not replace them. Nothing here authorizes trading or changes a safety gate.

`scripts/docs/build_context_pack.py` counts rows whose Status cell is `PENDING_OWNER`.

## Open

| ID | Question | Options (as stated by the owner) | Status | Decision / date / source |
|---|---|---|---|---|
| C11 | Untracked `execution/`, `assistant/`, `trade_management/` code | Commit it behind disabled flags / declare host-only authority | PENDING_OWNER | — |
| C16 | PR #60 Telegram delivery scope | `WATCH_READY` + `INFO_ONLY_*` / `READY` + LSMC `OPPORTUNITY` only | PENDING_OWNER | — |
| C14 | Canonical objective and demo sequencing | Issue #47 V5 / `docs/PROJECT_OBJECTIVE.md` soak | PENDING_OWNER | — |
| C1 | Rescission of governance D2 "Telegram is DEFERRED" (`AG_V1_TWO_GOALS_OWNER_DECISIONS.md`) | Not stated | PENDING_OWNER | — |
| R6 | First-slot strategy/version and the minimum evidence it needs | Not stated | PENDING_OWNER | — |
| REG-V2-FX | V2 FX integration target | Not stated | PENDING_OWNER | — |
| REG-D6-MERGE | Merge path for the D6 READY-OFF hotfix | Not stated | PENDING_OWNER | — |
| REG-HOST-ORDER-PATHS | EA and dev order paths on the demo host | Not stated | PENDING_OWNER | — |
| REG-ARCHIVE-PLANS | Archive move of the 5 unreferenced plans (listed in PR #68) | Not stated | PENDING_OWNER | — |
| REG-INVARIANTS | Invariants authority | `AGENTS.md` + `docs/DOCUMENTATION_GOVERNANCE.md` / a new `INVARIANTS.md` | PENDING_OWNER | — |
| REG-HEARTBEAT | Host heartbeat thresholds | 1200 MB RAM / 10 GB disk (values to confirm or replace) | PENDING_OWNER | — |

## Resolved

| ID | Question | Status | Decision / date / source |
|---|---|---|---|
| D3 | `SESSION_TRADE_V1` demo authority | RESOLVED | `demo_authorized: false` (revoked 2026-09-30); source `strategies/registry.yaml`, recorded in `AG_V1_TWO_GOALS_OWNER_DECISIONS.md` |
| BACKLOG-DIFF-AUDIT | Backlog claim that a direct merge would delete files present on `main` | RESOLVED | Invalidated 2026-10-09: the counts came from two-dot tip-to-tip comparisons; three-dot merge-base audits found zero PR deletions for [#30](https://github.com/aungmyat1/AG-profit-trading-assit/pull/30), [#31](https://github.com/aungmyat1/AG-profit-trading-assit/pull/31), [#63](https://github.com/aungmyat1/AG-profit-trading-assit/pull/63), [#77](https://github.com/aungmyat1/AG-profit-trading-assit/pull/77), [#78](https://github.com/aungmyat1/AG-profit-trading-assit/pull/78), and [#81](https://github.com/aungmyat1/AG-profit-trading-assit/pull/81) |
| BACKLOG-30-31 | Disposition of [#30](https://github.com/aungmyat1/AG-profit-trading-assit/pull/30) and [#31](https://github.com/aungmyat1/AG-profit-trading-assit/pull/31) | RESOLVED | Superseded by [#85](https://github.com/aungmyat1/AG-profit-trading-assit/pull/85) on merge; owner decision 2026-10-09 |
| BACKLOG-77-78-81 | Disposition of [#77](https://github.com/aungmyat1/AG-profit-trading-assit/pull/77), [#78](https://github.com/aungmyat1/AG-profit-trading-assit/pull/78), and [#81](https://github.com/aungmyat1/AG-profit-trading-assit/pull/81) | RESOLVED | Superseded by [#84](https://github.com/aungmyat1/AG-profit-trading-assit/pull/84) on merge; owner decision 2026-10-09 |
| BACKLOG-63 | Disposition of [#63](https://github.com/aungmyat1/AG-profit-trading-assit/pull/63) | RESOLVED | Rebase by the owner of the #63 branch; owner decision 2026-10-09 |
| BACKLOG-CLOSE-48-50-86 | Disposition of [#48](https://github.com/aungmyat1/AG-profit-trading-assit/pull/48), [#50](https://github.com/aungmyat1/AG-profit-trading-assit/pull/50), and [#86](https://github.com/aungmyat1/AG-profit-trading-assit/pull/86) | RESOLVED | Close unmerged; owner decision 2026-10-09 |
