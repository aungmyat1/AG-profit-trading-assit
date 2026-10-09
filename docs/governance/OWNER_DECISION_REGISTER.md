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
| REG-S01-SIGNAL-TIME | PR #94 removal of the first-trade-bar signal-time fallback: ticket-layer correctness fix or `ST_ASIAN_SWEEP_5R_V1` contract change (evidence: `docs/status/AGP_PR94_FOLLOWUP_S01_S02_2026-10-09.md`) | Ticket-layer fix, recorded explicitly / contract change via candidate version and admission governance | PENDING_OWNER | — |
| REG-REGEN-BOOTSTRAP | Regeneration bot: allow one empty bootstrap commit on `regen/generated-files-<sha>` before its PR exists (`docs/governance/REGENERATION_BOT_POLICY.md` E1) | Approve the narrow exception / owner opens regeneration PRs manually / waive PR-before-push for these branches | PENDING_OWNER | — |
| REG-REGEN-STALE-CLOSE | Regeneration bot: close its own superseded `regen/generated-files-<sha>` PRs with a comment (`REGENERATION_BOT_POLICY.md` E2) | Approve bot closure / comment only, owner closes | PENDING_OWNER | — |

## Resolved

| ID | Question | Status | Decision / date / source |
|---|---|---|---|
| D3 | `SESSION_TRADE_V1` demo authority | RESOLVED | `demo_authorized: false` (revoked 2026-09-30); source `strategies/registry.yaml`, recorded in `AG_V1_TWO_GOALS_OWNER_DECISIONS.md` |
| C001-PRE-RESULT-CORRECTION | Pre-result correction of frozen candidate `CRYPTO_CFD_C001` | RATIFIED | Ratified by merge of [#85](https://github.com/aungmyat1/AG-profit-trading-assit/pull/85) (2026-10-08); no C001 economic result existed. Precedent limited: any future change to a frozen candidate's rule bytes requires a new candidate ID (C002+), never an in-place correction. |
| OBJ-RATIFY-2026-10-09 | Ratification of `docs/PROJECT_OBJECTIVE.md` (rev 2026-10-08) as the project objective | RATIFIED | **YES** — owner Aung, 2026-10-09; source: explicit owner confirmation in a ChatGPT conversation, recorded by mission AGP-C2-DECIDE. Phase stays PRE-EDGE. Ratification is not execution authorization: demo/live remain disabled and no strategy, registry or safety gate changes. Approved with the 2026-10-09 amendments D1–D6 (distinct from the 2026-09-30 D1–D8 in `AG_V1_TWO_GOALS_OWNER_DECISIONS.md`), listed in `PROJECT_OBJECTIVE.md` § Owner decisions D1–D6 (2026-10-09). Their content: D1/D3 name `ST_ASIAN_SWEEP_5R_V1@1.1.2` as the intended successor for both windows, not admitted until ASW-RATIFY passes. D2 sets risk at 0.5% with cost warn at 0.10R and block at 0.25R. D4 names `ST_CRYPTO_CFD_SWEEP_RETEST_V1` as the intended crypto CFD runtime with a 10%/20% entry-to-stop spread policy, not admitted until L1–L6 pass; D2/D4 are carried in `config/v1_tickets/crypto_cfd_ticket_policy.yaml`. D5 makes demo authorization per strategy and conditional on G1–G5, which are not yet defined in a repository record. D6 requires D6 plus G1/G3 for Asian Sweep READY, which stays OFF. The canonical→broker symbol map remains PENDING AGP-C2-SYMMAP. The soak requires ≥10 clean scheduled cycles per admitted strategy. No new canonical outcomes. No broker execution authorization: `execution_authorization_changed: false`. Open rows C14 and C1 are not resolved by this entry; the owner records them separately. |
