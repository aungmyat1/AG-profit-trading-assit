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
| OD1010-C6-RISK | Initial DEMO-only numerical risk limits for FX/Gold, Crypto CFD, and Large-SMC | APPROVED_LIMITS_ONLY | Aung, 2026-10-10, owner chat: risk per trade 0.5% of demo account equity; maximum 1 open position per instrument across all strategies; maximum 5 trades per day per strategy; daily loss limit 1% per strategy; account-wide daily loss limit 2%. Limits are ceilings, not targets or an instruction to place trades. This numerical approval grants no strategy execution authorization: `demo_authorized=false`, `live_authorized=false`; separate per-strategy DEMO_AUTHORIZED approval and applicable evidence/gates remain mandatory. Daily reset timezone and notification-failure behavior remain pending owner policy. |
| C11 | Untracked host execution layer | RESOLVED | Bring the host execution layer into the repository through a reviewed PR before G6. Aung, 2026-10-09 (OD1009 owner chat). Record-only; no runtime or execution-authority change. Host-side files remain `UNTRACKED_HOST` until reviewed and merged. |
| OD1009-D1 | Asian Sweep Phase B owner decisions | CONFIRMED | Aung, 2026-10-09; owner chat. Every Phase B row `CONFIRMED_AS_RECOMMENDED`; fixed UTC anchoring; accept packet proposal `SETUP_WINDOW_OPEN`; successor v1.1.2. Candidate confirmation only; no runtime promotion. |
| OD1009-D2 | FX/gold manual-ticket risk and cost policy | CONFIRMED | Aung, 2026-10-09; owner chat. `risk_pct: 0.5`, `cost_warn_R: 0.10`, `cost_block_R: 0.25`; cost at or above 0.25R blocks and absent required risk/cost keys fail closed. |
| OD1009-D3 | Crypto ticket strategy path | CONFIRMED | Aung, 2026-10-09; owner chat. Use `ST_CRYPTO_CFD_SWEEP_RETEST_V1` after L1–L6; keep `ST_LIQUIDITY_SWEEP_RETEST_V1` research. No runtime binding or admission change now. |
| OD1009-D4 | LSMC watch schedule target | CONFIRMED | Aung, 2026-10-09; owner chat. `AG-V1-LSMC-Watch` daily at 00:04:15 UTC; retire `AG-V1-LSMC-Crypto-Weekend`. Register-only; no host task change. |
| OD1009-D5 | Per-strategy demo gate | CONFIRMED | Aung, 2026-10-09; owner chat. Demo follows G1–G5 and remains separately authorized per strategy; all demo flags remain `false`. See `PROJECT_OBJECTIVE.md` G1–G6. |
| OD1009-D5-ECONOMIC-STANDARD | Economic evidence required for demo | CONFIRMED | Linked to OD1009-D5: none is required for demo authorization in PRE-EDGE; `EDGE_VERIFIED=false` is accepted for demo; live remains out of scope. Aung, 2026-10-09. |
| OD1009-D6 | Asian Sweep READY gate | CONFIRMED | Aung, 2026-10-09; owner chat. READY may be ON for `ST_ASIAN_SWEEP_5R_V1` after G1+G3; readiness remains unchanged/OFF until gates pass. See `PROJECT_OBJECTIVE.md`. |
| CRYPTO-RUNTIME | Intended crypto ticket strategy | RECORDED | Aung, 2026-10-09 (OD1009-D3); `ST_CRYPTO_CFD_SWEEP_RETEST_V1` after L1–L6; `ST_LIQUIDITY_SWEEP_RETEST_V1` remains research. No runtime change. |
| LSMC-SCHED | LSMC scheduler target | RECORDED | Aung, 2026-10-09 (OD1009-D4); `AG-V1-LSMC-Watch` daily 00:04:15 UTC; retire `AG-V1-LSMC-Crypto-Weekend`. No host task change. |
| D3 | `SESSION_TRADE_V1` demo authority | RESOLVED | `demo_authorized: false` (revoked 2026-09-30); source `strategies/registry.yaml`, recorded in `AG_V1_TWO_GOALS_OWNER_DECISIONS.md` |
| C001-PRE-RESULT-CORRECTION | Pre-result correction of frozen candidate `CRYPTO_CFD_C001` | RATIFIED | Ratified by merge of [#85](https://github.com/aungmyat1/AG-profit-trading-assit/pull/85) (2026-10-08); no C001 economic result existed. Precedent limited: any future change to a frozen candidate's rule bytes requires a new candidate ID (C002+), never an in-place correction. |
| OBJ-RATIFY-2026-10-09 | Ratification of `docs/PROJECT_OBJECTIVE.md` as the project objective | RATIFIED | Owner Aung, 2026-10-09. Phase remains PRE-EDGE. The objective amendments are recorded separately as OD1009-D1–OD1009-D6. Ratification does not change strategy authorization or demo/live flags; `execution_authorization_changed: false`. Open rows C14 and C1 remain unresolved. |
| OD1011-COMMISSION | VT demo commission source | APPROVED | Aung, 2026-10-11, owner chat: VT Markets demo account is Standard STP, zero commission; cost is carried in the spread. Applies to all symbols on this demo account (FX, gold, crypto CFD). Commission = 0 is an owner-stated account fact, not a default: it is bound to this account and must be re-confirmed for any other account. It is verified against the commission field of the first demo deals once any exist; a non-zero value there invalidates this entry and blocks L5. Note (2026-10-11): commission_R valid only at 0; a non-zero commission requires a per-lot field (future), never R units. Config schema (runtime reader, #132): `decision_id`, `account_login_suffix` committed, full `account_login` only in gitignored `config/local/owner_ticket.yaml`, `commission_R`. |
| OD1011-ROUNDING | Price rounding mode for ST_ASIAN_SWEEP_5R_V1 v1.1.2 levels | APPROVED | APPROVED (amended 2026-10-11): For ST_ASIAN_SWEEP_5R_V1 v1.1.2 the frozen rounding rule is the engine's fx._r (Python round() on IEEE floats, tie results as stored). Verification gates must replicate it exactly. Any next candidate version (≥1.1.3) must use Decimal ROUND_HALF_UP to the point grid; that change requires re-verification. Original premise corrected per Codex review on #149. |
| OD1011-SCOPE | Branch-scoped logic verification | APPROVED | Aung, 2026-10-11: a lane may be LOGIC_VERIFIED per strategy branch. GBPUSD×ASIAN_LONDON verification covers SWEEP only; RANGE_REJECTION (never exercised on recorded VT days) and TREND (spec-blocked) stay fail-closed for tickets until separately verified. A branch can't be verified without exercise on VT data. |
| OD1011-L5 | Meaning of L5 for logic verification | APPROVED | Aung, 2026-10-11: L5 PASS = cost evidence (spread + commission) exists from an accepted source and the cost gate applies it correctly, including the 0.10R warn / 0.25R block per OD1009-D2. A ticket blocked by cost is an actionability outcome, not a verification failure. Missing cost evidence stays INSUFFICIENT. No demo authorization is implied. |
