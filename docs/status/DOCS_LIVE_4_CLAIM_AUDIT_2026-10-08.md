---
class: evidence
governance_class: STATUS_EVIDENCE
mission: DOCS-LIVE-4
date: 2026-10-08
source_head_sha: cf0ce0f3804b550b74544c769f4b979902e496e4
source_head_short: cf0ce0f
objective_authority: "https://github.com/aungmyat1/AG-profit-trading-assit/issues/47 (Operational Objective V5, owner, 2026-10-07T08:11:49Z, open; baseline main fc60cdb)"
scope:
  - PROJECT_STATUS.md
  - docs/PROJECT_ROADMAP.md
  - AGENTS.md
  - .agents/skills/**  # mapped scope for the requested "docs/agents/*", which does not exist at this SHA
  - strategies/registry.yaml  # comments only
machine_readable_companion: scripts/docs/advisory_allowlist.json
authority_granted: NONE
---

# DOCS-LIVE-4 — documentation claim audit (2026-10-08)

STATUS_EVIDENCE: read-only documentation/claim audit against `main` at
`cf0ce0f3804b550b74544c769f4b979902e496e4`. It records what each in-scope document claims,
which machine source supports or refutes it, and what the owner must decide. It authorizes
no trading, promotes no strategy, changes no gate, and establishes no economic edge.
`LOGIC_VERIFIED`, `EDGE_VERIFIED` and `DEMO_AUTHORIZED` are reported as separate states and
are never merged here.

## 1. Scope and SHA record

| item | value |
|---|---|
| Repository | `aungmyat1/AG-profit-trading-assit` |
| `main` HEAD (recorded) | `cf0ce0f3804b550b74544c769f4b979902e496e4` |
| Commit date | 2026-10-08T07:37:04Z — "Merge pull request #66 from aungmyat1/docs/agents-oss-first-rule" |
| Refs agreeing | local `main`, `origin/main`, session branch — all `cf0ce0f` |
| Tracked files | 1338 (`src/` 204, `tests/` 64, `docs/` 319, `config/` 47, `strategies/` 8) |
| Audit mode | read-only; no commits during the audit passes |

**`docs/agents/*` does not exist at this SHA.** Verified two ways: local `git ls-files`
(no `docs/agents` path, no text reference to it anywhere) and
`GET /repos/aungmyat1/AG-profit-trading-assit/contents/docs?ref=main` (no `agents` entry).
PR #66's actual file set is `AGENTS.md` + `.agents/skills/**`. The requested scope item was
therefore mapped to `AGENTS.md`, `.agents/skills/_CANONICAL_SOURCE.md`,
`.agents/skills/SKILL_REGISTRY.yaml`, `.agents/skills/*/SKILL.md`, and the `.claude/skills/`
mirror. Mirror parity machine-checked: `python scripts/check_skill_mirror_drift.py` →
`NO_DRIFT: 33 files identical`.

## 2. Objective authority used for flagging

The owner objective of 2026-10-07 is **GitHub ISSUE #47 — "AG Profit Trading — Operational
Objective V5"** (author `aungmyat1`, created 2026-10-07T08:11:49Z, state open, no labels,
own baseline stamp "main `fc60cdb`"). `docs/PROJECT_OBJECTIVE.md` (rev 2026-10-08) is an
in-repo restatement. Clauses used as the flag baseline:

- **O1 / §1** — FX + Gold daily session tickets: EURUSD, GBPUSD, USDJPY, XAUUSD;
  ASIAN_LONDON and LONDON_NEWYORK; ticket only when a registered strategy passes logic
  verification + data/freshness + geometry + spread/cost + risk gates; `NO_TRADE`/`WATCH`/
  `BLOCKED`/`DATA_ERROR` are valid; never force a daily quota.
- **O2 / §2** — crypto daily tickets: **BTCUSD and ETHUSD on the VT Markets Demo CFD venue**;
  "up to 2 qualified crypto trade tickets per day"; **"Never borrow BTCUSDT/ETHUSDT
  perpetual validation or contract authority for BTCUSD/ETHUSD CFDs."**
- **O3 / §3** — six-instrument Large-SMC watch + alerts (EURUSD, GBPUSD, USDJPY, XAUUSD,
  **BTCUSD, ETHUSD**) reported to Telegram; watch/alert authority separate from proposal and
  execution authority.
- **O4 / §3–§4, R4** — Telegram delivery of tickets, LSMC alerts and daily report; owner
  approval binds ticket/proposal ID + strategy version + code SHA + expiry; Telegram approval
  is an owner command, never automatic authorization.
- **O5 / §4, R5–R6** — owner-confirmed Demo execution only through the repository's canonical
  `assistant.commands.execute_command()` path, after strategy-specific demo authorization and
  account/venue/risk/freshness/cost/duplicate/reconciliation/order-check gates; live trading
  disabled and out of scope.
- **Label definitions (ISSUE #47)** — `LOGIC_VERIFIED` = frozen contract and deterministic
  implementation agree on all signal-producing and SL/TP rules, required inputs consumed,
  tests/replay prove determinism, ticket geometry complete; **not** profitable, **not**
  `EDGE_VERIFIED`. `EDGE_VERIFIED`/`ECONOMICALLY_QUALIFIED` = sufficient OOS/friction/
  robustness evidence. Demo authorization must state which economic standard the owner
  requires and must never be inferred from logic verification.
- **Gate order** — `R0 → R1 FX → R2 Crypto → R3 LSMC → R4 Telegram approval binding →
  R5 Demo execution → R6 host acceptance`.

**Verdict legend.** `MATCH` · `CONTRADICTS` · `NO_SOURCE` · `HISTORICAL`. Where a row mixes
clauses, the most severe verdict is recorded and the per-clause detail is kept in the claim
cell. Host-only facts (Windows Task Scheduler state, MT5 terminal, Telegram token/chat IDs,
`D:\` trees) are `NO_SOURCE`, never `CONTRADICTS`.

## 3. Claim table (40 rows)

| # | doc:line | claim_type | claim (compressed) | machine source | verdict |
|---|---|---|---|---|---|
| 1 | PROJECT_STATUS.md:3-5 | historical | first section = rolling summary; later sections "preserve dated milestone evidence and may contain older test totals" | 90 headings, 59 dated; markers at :1375, :1590, :1624, :1888 | MATCH |
| 2 | PS:7-25 | gate | stale-data gate keeps `signal_close_utc` on stale-withheld READY; both stay `INFO_ONLY_STALE`; "never `WATCH_READY`"; 18 tests | `src/v1_tickets/guards.py:59-64`; `tests/test_stale_gate_trigger_close.py` | MATCH |
| 3 | PS:26-55 | authority | R2 "verifies the candle/quote data pipeline only; does not establish a trade opportunity, strategy readiness, or execution authority"; R1 live evaluator **NOT YET HOST ACCEPTED**, both execution flags disabled | `docs/status/AG_MARKET_DATA_CONTRACT_R2_2026-10-08.md`; `src/v1_tickets/mt5_provider.py`; `scripts/host/live_eval_smoke.py`; `config/trading.yaml:17-24` | MATCH |
| 4 | PS:56-103 | authority+gate | SESSION_TRADE_V1 `MANUAL_ONLY` / `demo_order_authority NONE` / demo false since D3; loader requires demo+live present and exactly `false`; L1-L6 → zero `TICKET_READY`; `logic_status=NOT_VERIFIED`; `EDGE_VERIFIED=FALSE` | registry.yaml:36-49; `src/v1_tickets/authority.py:37,118-123`; `config/owner_ticket.yaml:8`; `tests/test_manual_ticket_logic_gate.py` | MATCH |
| 5 | PS:104-140 | authority | BTCUSD/ETHUSD `DEMO_VERIFIED` read-only observation only; `STRATEGY_CONTRACT_INCOMPLETE`; proposal/execution authority false; checklist `execution_authorized` always FALSE; 0.5 % pilot EURUSD/GBPUSD, USDJPY/XAUUSD `RISK_POLICY_AMBIGUOUS` | `config/session_scanner_v1.yaml:36-37,70-76`; `src/session_scanner/checklist_v1_1.py:16,482`; `config/pilot/*:0.5` | MATCH |
| 6 | PS:180-218 | objective+schedule | host Telegram audited (scopes `TICKET_READY`, `LSMC_OPPORTUNITY`; acceptance `HOST_VALIDATION_REQUIRED`); six-instrument objective bound, preflight 9/9; 3 tasks FX/15 m, crypto/5 m, LSMC/5 m; default delivery `ARCHIVE_ONLY` | `scripts/host/verify_objective.py:40-144`; `install_tasks.ps1:46-48`; `src/v1_tickets/fx.py:33-34`; `crypto.py:55,60`; `src/large_smc_watch/contract.py:48`; `ST_LARGE_SMC_V1_1_1_0.yaml:19`; `config/ticket_delivery.yaml:52,101` | MATCH |
| 7 | PS:871-920 | authority | "only `SESSION_TRADE_V1` is wired into `strategy_manager.manager.evaluate()`; every other strategy_id `dispatchable=False`"; frontend frozen (owner directive 2026-09-21); V2-2A/2B `VERIFIED` | `src/strategy_manager` **absent** (import fail); `src/opportunity/registry_binding.py:5-26` repeats the cite; `engine.py` + `candidate_store.py` exist | NO_SOURCE |
| 8 | PS:922-959 | gate | V2-3A `RE_AUDIT_PASS`, V2-3B, Parity #1 `PASS`, `SAFE_TO_ADVANCE_TO_V2_4=YES` via `src/opportunity/{large_smc_adapter,ssc_adapter}.py` over `large_smc_research.watch_lifecycle` + `session_sweep_continuation.replay.run_replay` | all four paths absent (`src/opportunity` = 9 files, no adapters) | CONTRADICTS |
| 9 | PS:1582-1613 | authority+gate | "owner adopted … Master Project Readiness Plan **V3** as the authoritative roadmap"; R4 STOP with `execution_eligible=false`; pointer "see *Current rolling classification (2026-09-12)* at the top of this file" | `docs/PROJECT_ROADMAP.md:1` = **V4** (RM:5 supersedes V3); actual heading PS:871 = (2026-09-21), 31 % into the file | CONTRADICTS |
| 10 | PS:1624-1674 | objective | historical owner-directed objective: 3 FX majors + gold "pending final contract freeze"; BTCUSDT/ETHUSDT preset times; "preset Large-SMC pair universe"; Major FX V1 = EURUSD/GBPUSD only | ISSUE #47 §1-§3; `docs/PROJECT_OBJECTIVE.md:19-45` (4 FX + gold, all-six watch) | HISTORICAL |
| 11 | PS:1719-1746 | schedule+authority | 2026-09-05 snapshot: LSMC v1.0.7 C10 SIGNED + FORWARD_RESEARCH; BTC window 06:30-06:45 UTC (13:00-13:15 MMT); task installed 06:35 UTC `State=Ready`; campaign `ACTIVE_0_OF_30`; "FULL REGRESSION 1356 passed" | `ST_LARGE_SMC_V1.yaml:4,28-31`; `src/btc_sweep_research/daily_report.py:50-53`; `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml:171-210`; `scripts/install_btc_daily_task.ps1` (host state unverifiable) | MATCH (dated; host rows NO_SOURCE) |
| 12 | PS:1798-1828 | authority | AUTHORITY_RECONCILIATION matrix (registry demo/live false) + Demo subsystem "Verified (`execution/executor.py`, `execution/mt5_gateway.py`)"; **:1825 "`SESSION_TRADE_V1` is separately `demo_authorized: true` for its `ASIAN_LONDON` cycle"** | registry.yaml:36 = `false` (D3 2026-09-30); `docs/governance/AG_V1_TWO_GOALS_OWNER_DECISIONS.md:16`; `execution/*` absent | **CONTRADICTS ★** |
| 13 | PS:1866-1886, 2178 | authority | Large-SMC "v1.0.6 `RESEARCH_DRAFT` → `large_smc_research` engine → fails closed to BLOCKED"; "`BLOCKED at C10`"; "C10 `UNSIGNED`" | `ST_LARGE_SMC_V1.yaml:4` = 1.0.7, `:28` `SIGNED_AND_LOCKED` 2026-09-07; registry.yaml:68; `ST_LARGE_SMC_V1_1_1_0.yaml:9-19` | **CONTRADICTS ★** |
| 14 | PS:1977-2009 | authority | demo/live false; `entry_order_type: MARKET` resolved 2026-08-31; `risk_per_trade_pct` UNSPECIFIED (real open gap); "verified from code: `execution/risk.py::size_position()` … no fallback; `trading.yaml` comment stale" | `ST_ASIAN_SWEEP_5R_V1.yaml:4,98,103` (no `risk_per_trade_pct`); `execution/risk.py` absent | MATCH (registry/YAML) / NO_SOURCE (code cites) |
| 15 | PS:2011-2065 | objective+authority | "**PAUSE further Telegram-related development, finish the core project first**"; `development_state=PAUSED`; "`main` still has zero Telegram files"; Core project objective = 10-step proposal→demo chain; "Telegram is one possible future approval interface" | ISSUE #47 §3-§4 + R4; `docs/PROJECT_OBJECTIVE.md:38-45,131`; main **has** `src/host_delivery/telegram_message.py`, `src/session_scanner/telegram_formatter.py`, `scripts/host/{enable,verify}_telegram.ps1`, `telegram_status.py`; governance D2:15 "Telegram DEFERRED" | **CONTRADICTS ★** |
| 16 | PS:2189-2248 | objective+gate | "Product objective = two deterministic decision services (Session Trade + Large-SMC **proposals**), daily decision report"; `run_daytrading_runtime.py` read-only; "execution runtime provides explicit-confirmation FX routing"; "superseding older documents that described the registry as having no caller"; `config/trading.yaml` gates fail-closed | omits O2/O4/O5; `scripts/run_daytrading_runtime.py` exists; `src/execution_runtime` = 5 crypto-feed files only; registry.yaml:1-5 still says "no caller"; `config/trading.yaml:17-41` matches | CONTRADICTS (objective) / MATCH (gate values) |
| 17 | PS:2338-2400, 2447-2469 | authority+gate | permanent authority order (`execution/executor.py` via `assistant/commands.py`; `trade_management/` → `mt5.management_gateway`); "**ORDER_SEND = ENABLED for DEMO accounts**"; `AG_DEMO_EXECUTION_V1 PASSED` (ticket 1879685149); PHASE 1-6 COMPLETE/FROZEN/BUILT | `assistant.commands`, `execution.executor`, `trade_management.*`, `mt5.management_gateway` → `ModuleNotFoundError`; `config/trading.yaml:20-24` `allow_order_send: false`; PHASE 6 package absent (`scripts/manage_trade.py:19-23` imports fail) | **CONTRADICTS ★** |
| 18 | PS:2732-2738 | authority | "`ST_ASIAN_SWEEP_5R_V1`'s `entry_order_type: MARKET_OR_LIMIT` is ambiguous (blocks `READY_FOR_ORDER_CHECK`)"; "a `config/trading.yaml` account-wide default is used instead" | `ST_ASIAN_SWEEP_5R_V1.yaml:98,103` = `MARKET`; PS:1983-1985; `config/trading.yaml:26-31` (1.0, "not read by any code yet"); real sizing authority `config/pilot/*:0.5` + `config/owner_ticket.yaml:8` `null` | **CONTRADICTS ★** |
| 19 | PS:2754-2774 | historical | Web→MT5 Vantage Demo bridge `UNIT_TESTED / CONNECTION VERIFIED — ORDER SEND NOT EXERCISED`, via `scripts/web_execute_trade.py` → `assistant.commands.execute_command()`; `config/trading.demo.yaml` | script absent; `assistant.commands` absent; `config/trading.demo.yaml` exists | HISTORICAL / NO_SOURCE |
| 20 | PROJECT_ROADMAP.md:3-11 | authority | "AUTHORITATIVE MASTER PLAN — V2 INTEGRATED 2026-09-21", supersedes V3 ordering; PS owns rolling classification, RM owns architecture/gate ordering; governance layer WP-0…WP-11 + `ST_ASIAN_SWEEP_5R_V1@1.1.1` replaces SSC as FX V2 target; "does **not** authorize broker execution, alter strategy semantics, promote a strategy, claim profitability, or grant Demo/Live authority" | `docs/governance/AG_MULTI_AGENT_EXECUTION_PROTOCOL_V1.md:7,20,34,187-201`; `ST_ASIAN_SWEEP_5R_V1.yaml:4` = 1.1.1; all registry demo/live flags false | MATCH |
| 21 | RM:113-130 | gate | readiness matrix: R0-R4 `READY`/`PASS` since 2026-09-11, R5 `PARTIAL`, economic `NOT_PASS/NOT_ESTABLISHED`, R7-R9 `BLOCKED`; "current rolling truth remains in `PROJECT_STATUS.md`" | PS:871+; registry `logic_status: NOT_VERIFIED` for both ticket strategies (platform axis ≠ strategy-admission axis) | MATCH (axis caveat) |
| 22 | RM:330-366 | gate+schedule | V2-2A/2B `VERIFIED`; V2-3A `RE_AUDIT_PASS`; V2-3B `IMPLEMENTED_AND_LOCALLY_VERIFIED`; Parity #1 `PASS` + `SAFE_TO_ADVANCE_TO_V2_4=YES`; V2-3C (WP-1) and SSC routing removal (WP-2) planned, `LEVEL B` | `engine.py`/`candidate_store.py` exist; `large_smc_adapter.py`/`ssc_adapter.py` + `session_sweep_continuation.replay` absent; governance:198-199 | CONTRADICTS (3A/3B) / MATCH (planned) |
| 23 | RM:496-575 | gate | V2-14 outcomes `QUALIFIED/VALIDATED_NEGATIVE/INSUFFICIENT_EVIDENCE/BLOCKED`; V2-15 = V2 gates + R5 + R6 + **explicit Demo authorization**; Live only after `DEMO_QUALIFIED` + explicit owner decision; "no automatic Demo authorization follows from parity alone" | `config/governance/economic_gate_contract.yaml`; `docs/svos/VD_QUALIFICATION_GATES.md`; zero `live_authorized: true` in repo | MATCH |
| 24 | RM:599-707 | authority+schedule | Part IV `strategy_readiness` 8-field per-version schema (:625 disclaims updating registry); immediate implementation order V2-2A→…→Parity #1→V2-3C→WP-2→V2-4…; final governing principle (engineering ≠ edge; economic qualification ≠ execution authority) | registry carries none of those fields; order already stamped `PASS` at PS:922-959 while adapter code is absent; principle matches `docs/PROJECT_OBJECTIVE.md:101-104` | NO_SOURCE (schema) / CONTRADICTS (order) |
| 25 | AGENTS.md:14-31 | objective | target decision products = post-Asian/post-London Session Trade tickets, preset-time BTC/ETH tickets, persistent Large-SMC funnel + entry-confirmation alerts; skills advisory, engine-only `TradeSignal`; guaranteed output = explicit decision state; "**crypto remains proposal/interface-only until a real venue integration is implemented and validated**" | `fx.py:33-34`, `crypto.py:55,60`, `large_smc_watch/contract.py:15-48`, `SKILL_REGISTRY.yaml:44-52` match; but `config/v1_tickets/crypto_ticket_v3.yaml:1-17` = VT Markets MT5 BTCUSD/ETHUSD **active**, PS:104-117 `DEMO_VERIFIED` crypto observation | CONTRADICTS (crypto clause) / MATCH (rest) |
| 26 | AG:32-49 | authority | chain `Strategy YAML → Strategy Engine → Execution Engine → MT5`; `execution/risk.py` decides sizing; "`execution/` controls MT5 orders (via `mt5/`). Entry-side OPEN **is implemented** (`execution/mt5_gateway.py`, `executor.py`) … reachable ONLY through `assistant.commands.execute_command()` with `user_confirmed=True`" | `src/strategy_engine` exists; `execution`, `execution.risk`, `execution.mt5_gateway`, `assistant.commands` → `ModuleNotFoundError`. Wording matches ISSUE #47 §4, tree does not | **NO_SOURCE ★** |
| 27 | AG:50-55 | authority | point 4: skills read/explain, no *independent* execution authority, never call executor/gateway/`order_send`, never override engine; "`.agents/skills/` canonical, `.claude/skills/` runtime-discovery mirror" | `SKILL_REGISTRY.yaml:44-52` (`may_execute_trade: false`, `may_authorize_trade: false`); drift check `NO_DRIFT: 33 files` | MATCH |
| 28 | AG:56-66 | authority | point 5: `trade_management/` (Phase 6, manual-entry only) never opens a position; only write surface `mt5.management_gateway`; gated by `config/trading.yaml trade_management:`; claimed via `scripts/manage_trade.py claim` | `config/trading.yaml:39-41` matches (`DRY_RUN`, `allow_live_management: false`); `trade_management.*`, `mt5.management_gateway`, `mt5.account` absent; `scripts/manage_trade.py:19-23` imports fail | **NO_SOURCE ★** |
| 29 | AG:67-116 | gate+authority | LIVE disabled unless `account.allow_live_trading`; never override `NO_TRADE`; "never edit files in `D:/wp3-main-integ`"; frozen strategy version preservation (new candidate version + explicit promotion, evidence never reattributed); OSS-FIRST standing rule (OSS = ORACLE/REFERENCE never authority; LIVE cohorts VT Markets MT5 only; no OSS path may import broker/order modules; fail closed `OSS_BLOCKED`) | `config/trading.yaml:24` false; `ST_LARGE_SMC_V1_1_1_0.yaml` (1.1.0 added, 1.0.7 preserved); `STRATEGY_LEDGER.md:104-106`; `tests/test_opportunity_import_boundaries.py`, `tests/test_v1_large_smc_import_boundary.py`; PR #66 file set = `AGENTS.md` + `.agents/skills/**` | MATCH (`D:/wp3-main-integ` = NO_SOURCE, host path) |
| 30 | AG:159-176 | authority | "Registration, advisory analysis, proposal authority, demo authorization, and live authorization are separate states"; "Never use a generic analysis skill to fill an `UNSIGNED` strategy rule"; "`ST_LARGE_SMC_V1`, currently `RESEARCH_DRAFT` … cannot emit an actionable `READY` proposal" | `strategy-management/SKILL.md:52-56,71` matches, but `:47` names `strategy_manager/manager.py` (absent); `ST_LARGE_SMC_V1.yaml:5` = `RESEARCH_DRAFT` true for v1.0.7 — omits delivered `src/large_smc_watch` v1.1.0 `SHADOW_ALERTS_ONLY` six-instrument watch (O3) | CONTRADICTS (omission + skill path) |
| 31 | AG:230-269 | authority | live-status maintenance (registry + ledger together; "never infer authorization from code availability"; "Never label a unit-tested path as live-verified"); BOOTSTRAP: read `config/agent_context.json`; budget 5 files/2 skills; "A HEAD mismatch alone does not invalidate the manifest" | `docs/status/LIVE_STATUS_MAINTENANCE.md` exists; `config/agent_context.json:4-5` `generated_from_head 933921fa` ≠ `cf0ce0f`, `last_verified_utc 2026-09-20`; its routes `src/session_sweep_continuation`(:20), `src/proposals`(:33), `src/execution`(:46), `src/scheduling`(:57) **all absent** | **CONTRADICTS ★** |
| 32 | registry.yaml:1-5 | authority | header "data only (2026-08-27) … **nothing in this repo currently calls a strategy-manager runtime**, and building one with no caller would be speculative infrastructure" | literally true at cf0ce0f (no `strategy_manager`), but contradicted in-file by registry.yaml:120-129 and by PS:2198-2203 ("superseding older documents that described the registry as having no caller") | CONTRADICTS (internal) |
| 33 | RG:7-10 | authority | legend: `registered`/`active`/`research` defined; "`demo_authorized` / `live_authorized` — set independently; never conflate registration with permission" | `src/v1_tickets/authority.py:29-39`; `docs/PROJECT_OBJECTIVE.md:101-104` | MATCH |
| 34 | RG:17-20 | authority | ST_ASIAN_SWEEP_5R_V1 demo/live `false`; "explicit-command demo execution **exists project-wide**, but this strategy remains independently blocked by its own open contract gaps (`entry_order_type` undefined, `risk_per_trade_pct` unspecified)" | flags match `authority.py:37`; no project-wide demo execution code exists (cf. ISSUE #47 readiness block, same wording); `entry_order_type: MARKET` (`ST_ASIAN_SWEEP_5R_V1.yaml:98,103`); `risk_per_trade_pct` genuinely absent | CONTRADICTS (2 of 3 clauses) |
| 35 | RG:23-30 | authority+gate | Manual Trade Ticket V1 block: `ticket_authority: MANUAL_ONLY`, `logic_status: NOT_VERIFIED` ("LOGIC_VERIFIED only with a matching `logic_verified_identity`"), identity `null`, `economic_status: NOT_EVALUATED`, `demo_order_authority: NONE`, read by `src/v1_tickets/authority.py`, unknown/missing fail closed, "a manual ticket is never an order" | `authority.py:29-39,113-123`; `tests/test_manual_ticket_authority.py` | MATCH |
| 36 | RG:36-49 | authority | SESSION_TRADE_V1 `demo_authorized: false` — "AG V1 owner decision D3 (2026-09-30): demo authority withdrawn; was true (ASIAN_LONDON only)"; engine in separate repo (`D:\ddev\Session Trade Codex`), tickets fail closed `STRATEGY_ADAPTER_NOT_IMPLEMENTED` | `AG_V1_TWO_GOALS_OWNER_DECISIONS.md:16` (D3) confirms; **contradicted by** PS:1825 and `docs/v2/AG_V2_BASELINE_MANIFEST_V1.json:50` (`demo_authorized: true`, `manager_dispatchable: true`) | MATCH (registry authoritative) ★cross-contradicted |
| 37 | RG:61-68 | authority | ST_LARGE_SMC_V1 engine "`src/large_smc_research/engine.py` (RESEARCH_ONLY …)"; "C10 stop-loss SIGNED and implemented as of v1.0.7 (`c10_stop_policy.py`, 2026-09-07), `RESEARCH_QUALIFIED` now reachable"; lifecycle "recorded only in `src/validation_framework/adapters/large_smc_adapter.py`"; FORWARD_RESEARCH 2026-09-07 | values MATCH (`ST_LARGE_SMC_V1.yaml:4,28-31`; `config/governance/strategy_lifecycle.yaml:31-33`) but **both cited module paths absent** (`src/large_smc_core` is a byte-copy successor) | **CONTRADICTS ★** (paths) |
| 38 | RG:69-77 | objective+authority | "NEW version 1.1.0 registered alongside, v1.0.7 unchanged — engine `src/large_smc_watch/` (watch/alerts only, status `SHADOW_ALERTS_ONLY`, instruments EURUSD GBPUSD USDJPY XAUUSD BTCUSDT ETHUSDT, `proposal_generation_authorized=false`, alerts `ARCHIVE_ONLY`). No demo/live authority for either version." | `ST_LARGE_SMC_V1_1_1_0.yaml:9,10,14,19,41-42`; `large_smc_watch/contract.py:15-16,48`; `tests/test_v1_large_smc_110_watch.py`; `verify_objective.py:98-105` | MATCH ← O3's machine binding (universe-complete; see A3/A4 for identity + gate gaps) |
| 39 | RG:79-105 | authority+schedule | ST_LIQUIDITY_SWEEP_RETEST_V1 `active:false` rationale; engine `src/strategy_engine/sweep_retest/` (FOREX + CRYPTO_PERP) + `src/btc_sweep_research/` + Bybit V5 feed (owner-approved exception) + Binance (HTTP 451); "v2.0.0 `ACTIVE_INCUBATION` … verified `tests/test_btc_proposal_execution_boundary.py`"; 2026-09-30 crypto ticket config **V2**; D4 ETHUSDT `SHADOW` | engines/feeds exist; `AG_TRADE_ASSISTANT_V1_0_3.yaml:152,171-173` `APPROVED_READ_ONLY_ONLY`; **`tests/test_btc_proposal_execution_boundary.py` absent** (nearest `tests/test_btc_research_runner_boundary.py`); active config is `crypto_ticket_v3.yaml` (`crypto.py:60`) | HISTORICAL (V2 note) / CONTRADICTS (test pointer) |
| 40 | RG:107-152 | authority+historical | SSC `active:false` `OFFLINE_RESEARCH`; engine `src/session_sweep_continuation/` + adapter `src/validation_framework/adapters/…`; "`strategy_manager.manager.evaluate()` … `GET /api/strategies`"; identity note "real identity is … **v1.0.0**"; R8_OBM_V1 "`.ex5`/`.mq5` removed by the owner (2026-08-27) … see **chat history**, not tracked by this registry" | lifecycle MATCH (`strategy_lifecycle.yaml:35-37`); all three module paths absent; `src/api/app.py` exposes only `GET /api/opportunities` (PS:171-174); real version **1.0.1** (`ST_SESSION_SWEEP_CONTINUATION_V1.yaml:22`); `config/ag_scheduler_v2.yaml:84-91` asserts SSC has "no registry entry, no contract"; R8_OBM_V1 has no repo source | **CONTRADICTS ★** (+ HISTORICAL for RG:142-152) |

## 4. Addendum rows A1-A12 (owner-objective and PR/issue state)

| # | doc:line / source | claim_type | claim (compressed) | machine source | verdict |
|---|---|---|---|---|---|
| A1 | ISSUE #47 (owner, 2026-10-07, open) | objective | Operational Objective V5 §1-§4 + R0-R6 order; own baseline "main `fc60cdb`" | reference source; `fc60cdb` ≠ `cf0ce0f` (delta = PR #66, docs-only) | MATCH (baseline) |
| A2 | ISSUE #47 readiness classification | authority | "Demo execution framework: **exists project-wide** but current target strategies are not Demo-authorized" | `execution/`, `assistant/`, `trade_management/`, `mt5.management_gateway` absent; `.gitignore:1-47` does **not** exclude them; `pyproject.toml:10-11,14` (`where=["src"]`, `pythonpath=["src"]`) would discover them; import probe 8/8 `ModuleNotFoundError`; `tests/test_import_integrity.py` asserts none of them | **CONTRADICTS ★** |
| A3 | ISSUE #47 §2 + R2 | objective | crypto identity = **BTCUSD/ETHUSD CFD**; never borrow BTCUSDT/ETHUSDT perp authority | `config/v1_tickets/crypto_ticket_v3.yaml:4,17` (perp engine `CRYPTO_PERP` mapped `BTCUSDT→BTCUSD`); registry.yaml:99-105; `ST_LARGE_SMC_V1_1_1_0.yaml:19` (BTCUSDT/ETHUSDT); `verify_objective.py:40-41` `WATCH_UNIVERSE` uses perp names; `crypto_symbols.py:22` BTCUSDT `point=0.1` vs host-captured `BTCUSD.json point=0.01` (**10× divergence**) | **CONTRADICTS ★** |
| A4 | ISSUE #47 R3 | gate | LSMC gaps resolved "for **all six** instruments"; WATCH→OPPORTUNITY/CONFIRMED/EXPIRED/BLOCKED deterministic | `ST_LARGE_SMC_V1_1_1_0.yaml:63-64` `USDJPY/XAUUSD {point: null, status: FIXTURE_ONLY}` → contract's own flagged choice `:50` yields `C10_PIP_SIZE_NOT_EVIDENCED`; yet `config/symbol_metadata/host_captured/USDJPY.json` (`point=0.001`) and `XAUUSD.json` (`point=0.01`), both `VTMarkets-Demo`/`trade_mode=FULL`, already exist and are validated by `verify_objective.py:79-87` | CONTRADICTS (gate open; unblock data already in repo) |
| A5 | ISSUE #47 R4 | gate | owner approval must bind ticket/proposal ID + strategy version + **code SHA** + expiry; stale/expired cannot execute | `src/v1_tickets/code_identity.py:18-31` (`git rev-parse HEAD`, failure → `UNKNOWN`); `manual_ticket.py:343-344` stamps `code_sha` outside `content_hash`; `owner_decision.py` append-only | MATCH (stamping) / NO_SOURCE (approval binding lives in unmerged PR #60) |
| A6 | ISSUE #47 R5/R6 vs `docs/PROJECT_OBJECTIVE.md:88-95,139` | schedule+gate | V5: a real "explicit owner-confirmed Demo order on an eligible test ticket" **inside** R6 host acceptance; no soak gate. PROJECT_OBJECTIVE: "≥10 clean scheduled cycles … `broker_mutations = 0` throughout the PRE-EDGE soak", demo authorization = "separate **post-soak** governance decision" (critical path #9) | both texts; registry all `demo_authorized: false` | **CONTRADICTS ★** (demo-gate sequencing) |
| A7 | PS:66 | schedule | "**Next open item:** owner choices on the Phase B reconciliation table for `ST_ASIAN_SWEEP_5R_V1@1.1.1` (**PR #40**)" | PR #40 `state=closed, merged=true`, head `readiness/trade-ticket-watch-r2@67c5620` | **CONTRADICTS ★** |
| A8 | `docs/PROJECT_OBJECTIVE.md:131` | schedule | critical path #1 "**#60 Telegram delivery** — rebase onto current `main`, reconcile, run focused + full regression suite, review and merge" | PR #60 **open**, head `feat/telegram-delivery@63478c4`, `mergeable_state=clean`, updated 2026-10-07T22:58:54Z, 3 commits / 20 files | MATCH |
| A9 | PR #60 body vs PS:182-186 / PS:14-16 | gate | #60: "`WATCH_READY` and **every canonical `INFO_ONLY_*`** decision send". PS:182-186: only newly archived `READY` under `TICKET_READY`, LSMC only `OPPORTUNITY`; "`NO_TRADE`, `BLOCKED`, `STALE`, `DATA_ERROR`, `WATCH`, and `INFO` remain archive-only". PS:14-16: stale-withheld tickets "never `WATCH_READY`" | `src/host_delivery/telegram_message.py` `SCOPES=(TICKET_READY, LSMC_OPPORTUNITY)`; `verify_objective.py:135-142`; `config/ticket_delivery.yaml:52,101` | **CONTRADICTS on merge ★** |
| A10 | PS:77-79 + registry.yaml:27 vs PR #62 | gate | FX L2 spec/engine divergences → zero `TICKET_READY`, `logic_status=NOT_VERIFIED` (V5 R1 open) | PR #62 **open**: `strategies/ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml` "closes Logic Gate L2 … v1.1.1 is not edited in place" = exactly V5 R1's promotion rule; **no in-scope doc mentions v1.1.2** | MATCH (current truth) + stale pointer |
| A11 | AGENTS.md:16-23, 48 | objective | the mandatory bootstrap file names **no instrument universe** (only "BTC/ETH" at :18; "EURUSD" inside an example execution command at :48) and contains **0** occurrences of `LOGIC_VERIFIED`/`EDGE_VERIFIED`/`DEMO_AUTHORIZED`; ROADMAP: 0 of each label and 0 crypto symbols | ISSUE #47 §1-§3 names all six; labels live only in registry.yaml:27,46 + `docs/PROJECT_OBJECTIVE.md:14,50,101-104` | NO_SOURCE (coverage gap) |
| A12 | PS:242-870, PS:1297-1581 | historical | dated bodies contain **zero** `LOGIC_VERIFIED`/`EDGE_VERIFIED`/`DEMO_AUTHORIZED`/`LIVE_AUTHORIZED` assertions; `AUTHORIZED` at :562, :616, :741-742, :784 is proposal-approval lifecycle vocabulary (`PREPARED→AUTHORIZED→SUBMISSION_PENDING`); :816 is `BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED`; :1463 is Telegram-failure isolation | range scan of both allowlisted blocks | MATCH → allowlist confirmed safe |

## 5. Objective text ≠ owner objective 2026-10-07 (ISSUE #47) — flags

1. **PS:2011-2054 + PS:2064-2065** — Telegram **PAUSE** directive, `development_state=PAUSED`,
   "Telegram is not a core-completion dependency", "`main` has zero Telegram files" (false at
   cf0ce0f). Opposes **O4**, ISSUE #47 §3/R4 and `docs/PROJECT_OBJECTIVE.md:38-45,131`
   (critical path #1 = PR #60, still open). No supersession marker on the section.
2. **PS:2056-2065 "Core project objective"** — a 10-step proposal→authorization→execute-once→
   demo objective. No six-instrument ticket scope, no Telegram delivery requirement; demo
   framed as the goal rather than a separately authorized boundary (**O5** emphasis inverted).
3. **PS:2189-2196 "Product objective"** — "two deterministic decision services": omits **O2**
   (crypto tickets) and **O4**; frames Large-SMC as *proposals* while **O3** and the machine
   source are watch/alerts only (`proposal_generation_authorized=false`).
4. **PS:1624-1648** — 3 FX majors + gold "pending final contract freeze", "preset Large-SMC
   pair universe" (not all six). Marked *superseded* → HISTORICAL, allowlisted.
5. **PS:1662-1669** — Major FX V1 = **EURUSD/GBPUSD only**; XAUUSD only after a reliability
   gate; USDJPY/XAUUSD/ETHUSDT candidate/shadow only → ≠ **O1/O2**.
6. **AG:27-31** — "crypto remains proposal/interface-only until a real venue integration is
   implemented and validated" → ≠ **O2** as built (`crypto_ticket_v3.yaml` active on VT Markets
   MT5 BTCUSD/ETHUSD; PS:104-117 `DEMO_VERIFIED` observation).
7. **AG:173-178** — Large-SMC described only as `RESEARCH_DRAFT` that "cannot emit an
   actionable `READY` proposal"; omits the delivered v1.1.0 six-instrument watch → an agent
   reading AGENTS.md alone would report **O3** as unimplemented.
8. **`config/ag_scheduler_v2.yaml:82-96`** (the scheduler authority that AG:255 and
   `config/agent_context.json:51-59` route every agent to) — `symbols: [EURUSD, GBPUSD]`,
   target `SESSION_TRADE_V1`, `status: RESEARCH`, `lifecycle: OFFLINE_RESEARCH` → ≠ **O1**
   (4 FX + gold) and names an out-of-repo engine.
9. **`docs/v2/AG_V2_BASELINE_MANIFEST_V1.json:50`** — `SESSION_TRADE_V1 demo_authorized: true`
   → ≠ **O5**.
10. **Instrument identity** — ISSUE #47 §2/§3 name **BTCUSD/ETHUSD (CFD)**; registry.yaml:99-105,
    `ST_LARGE_SMC_V1_1_1_0.yaml:19` and `verify_objective.py:40-41` encode **BTCUSDT/ETHUSDT**
    (perp) → ≠ **O2/O3** identity (see A3, C12).
11. **Demo-gate sequencing** — ISSUE #47 R5/R6 vs `docs/PROJECT_OBJECTIVE.md:88-95,139`
    (see A6, C14).
12. **Upheld everywhere:** no in-scope document claims live/real-money authority; zero
    `live_authorized: true` in the repository. **O5's live exclusion is consistently upheld.**

## 6. LOGIC_VERIFIED / EDGE_VERIFIED / DEMO_AUTHORIZED — kept separate

| label | where claimed in scope | machine truth at cf0ce0f |
|---|---|---|
| **LOGIC_VERIFIED** | registry.yaml:27, :46 (*rule only*: "LOGIC_VERIFIED only with a matching `logic_verified_identity`"); PS:77 (`logic_status = NOT_VERIFIED`); `docs/PROJECT_OBJECTIVE.md:14,50,101`; definition only in ISSUE #47 | **0 strategies LOGIC_VERIFIED.** `authority.py:113-123` requires a non-null identity; both ticket strategies carry `logic_verified_identity: null`. FX remedy pending unmerged PR #62 (v1.1.2) |
| **EDGE_VERIFIED** | PS:77 (`EDGE_VERIFIED = FALSE`); registry.yaml:29, :48 (`economic_status: NOT_EVALUATED`); RM:125 (`NOT_PASS / NOT_ESTABLISHED`), RM:216-249 (R5/R6) | **0 strategies EDGE_VERIFIED.** `config/governance/economic_gate_contract.yaml`; RM:498 "not the beginning of strategy validation" |
| **DEMO_AUTHORIZED** | registry.yaml:17, :36, :55, :65, :85, :113, :146 (all `false`); PS:56-66 (D3 withdrawal, loader fail-closed); RM:243, :251-277 (three-gate chain) | **0 strategies DEMO_AUTHORIZED.** `authority.py:37 NO_ORDER_FLAGS` requires present-and-exactly-`false`. Contradicting sources: PS:1825; `docs/v2/AG_V2_BASELINE_MANIFEST_V1.json:50` |

**Merge-risk hotspots an advisory scanner must not collapse** (distinct labels, all in scope):
`DEMO_VERIFIED` = infrastructure/market-data proof — 9 occurrences (PS:110 crypto observation;
PS:1805, 1806, 1881, 1882, 2092, 2097; PS:2399 2026-08-28 round trip) — **not** demo
authorization; `DEMO_ELIGIBILITY/AUTHORIZATION/EXECUTION` gates (RM:255-261) and
`DEMO_QUALIFIED` (RM:108, 279-287, 560) — **not** `LIVE_AUTHORIZED`; PS:1881 "ENABLED,
explicit-command-gated" and PS:2368 "ORDER_SEND = ENABLED for DEMO accounts" vs
`config/trading.yaml:20-21` `allow_order_send: false`; RM:122 "Canonical strategy decisions
`READY`" (platform axis) vs registry `logic_status: NOT_VERIFIED` (strategy-admission axis);
`TICKET_READY`/`WATCH_READY`/`ACTIONABLE` ≠ order (registry.yaml:25, :44; PS:14-16);
`AUTHORIZED` in PS:562/616/741-742/784 = proposal-approval lifecycle state, **not** strategy
demo authorization.

## 7. HISTORICAL / example locations → advisory-scan allowlist

Machine-readable form: **`scripts/docs/advisory_allowlist.json`** (same content, with
carve-outs that must never be suppressed).

**PROJECT_STATUS.md** (dated evidence, per its own rule at :3-5): `:40-55` ("historical
offline evidence"); `:104-178` (dated 2026-10-01…03 milestones — evidence, not current
authority); `:242-357` (host kit + MCP/workspace, 2026-09-27…30); `:358-870` (dated
candidate/branch records incl. all `PANEL_*` "worktree branch, not merged"); `:1297-1374`
(SSC v1.0.1 SVOS G2, 2026-09-19/21); `:1375-1581` "Historical rolling classification
(2026-09-14, superseded)"; `:1590-1598` ("Classification as recorded on 2026-09-10
(**superseded**) … preserved here as dated historical context"); `:1624-1674` "Historical
owner-directed profit-seeking objective (regenerated 2026-09-07; superseded as master
ordering)"; `:1719-1770` "Current operational snapshot (2026-09-05)" incl. the multi-KB
single-line ledger entries `:1745-1769`; `:1772-2321` "Capability & Roadmap Reconciliation
(dated 2026-09-06)"; `:2322-2337` (repo reorg 2026-08-28); `:2362-2446` (execution
restructure 2026-08-28 + ASSISTANT_RUNTIME_V1 + SMC skills 2026-08-27); `:2447-2731`
(PHASE 1-6 roadmap, 2026-08-26…28); `:2732-2753` (Phase-B config gaps + "Next owner
decision"); `:2754-2774` (Vantage bridge 2026-09-10).

**strategies/registry.yaml**: `:1-5` ("data only (2026-08-27)"); `:59` (SMC_3R_V1
independence note); `:73-77` (AG V1 Goal 2, 2026-09-30); `:94-98` (2026-09-05
reconciliation-only note); `:99-105` (2026-09-30 crypto config **V2** — superseded by V3);
`:130-140` (2026-09-10 identity note); `:142-152` **R8_OBM_V1 — explicit example/non-repo
provenance** ("see chat history, not tracked by this registry"); `:40, :57, :58, :151`
(`D:\ddev\…` external-repo paths = examples of out-of-repo authority).

**docs/PROJECT_ROADMAP.md**: `:5` (V3 superseded); `:130` ("reached READY/PASS on
2026-09-11"); `:330, :342, :346, :350, :354` (dated `VERIFIED`/`RE_AUDIT_PASS`/`PASS` stamps
2026-09-21/22); `:535` ("Replace the earlier concept of automatic `AUTO_DEMO`");
`:27-52, :64-91, :97-109, :144-150` and other ASCII diagrams (illustrative target
architecture, not state).

**AGENTS.md**: `:5-13` (owner token policy — rules, not project state); `:41-49` ("as of the
2026-08-28 Execution authority restructure" + example commands `"execute it"`,
`"sell EURUSD 0.31 lots…"`); `:56` ("Phase 6"); `:75` (`D:/wp3-main-integ` host path);
`:118-158` (token-efficiency rules); `:159-215` (skill load-order guidance, not capability
claims); `:203-229` (branch/push discipline + example SHA placeholders `<PR head SHA>`).

**`.agents/skills/**`**: `SKILL_REGISTRY.yaml:1-34` (dated header notes 2026-08-27/28,
2026-09-07); `strategy-management/SKILL.md:47` (`strategy_manager/manager.py` — stale path,
treat as example); `.agents/reports/workflow_skill_audit/*_2026-09-01_143835.{json,md}`
(35 files, dated audit snapshot); `.agents/skills/_CANONICAL_SOURCE.md` and
`.claude/skills/_MIRROR_NOTICE.md` (mirror-contract examples).

**Disambiguation notes (token collisions, not authority):** PS:562, PS:616, PS:741-742,
PS:784 — `AUTHORIZED` / `REJECT` / `SUBMISSION_PENDING` are demo-execution-bridge
**proposal-approval states** (2026-09-23…25 `feat/demo-execution-bridge` records), not
strategy `DEMO_AUTHORIZED`. PS:470 "are not AUTHORIZED"; PS:266 and PS:287 "No … Telegram
calls"; PS:816 `BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED`; PS:1463 Telegram-failure isolation.

**Verified safe:** PS:242-870 and PS:1297-1581 assert **no** `LOGIC_VERIFIED`,
`EDGE_VERIFIED`, `DEMO_AUTHORIZED` or `LIVE_AUTHORIZED` state (row A12), so both ranges may
be allowlisted for those four labels.

## 8. Critical contradictions for owner (C1-C17)

**C1 — Telegram: three live sources disagree; O4 has no single authority.** ISSUE #47 §3/R4
and `docs/PROJECT_OBJECTIVE.md:38-45,131` (critical path #1 = PR #60) require Telegram
delivery, vs **PS:2011-2054** ("PAUSE further Telegram development … `development_state=
PAUSED`", "`main` still has zero Telegram files" — false at cf0ce0f) vs governance **D2**
("Telegram is **DEFERRED**. Do not change the ticket-delivery `mode` or transport") vs the
shipped host opt-in (`config/ticket_delivery.yaml:52` `ARCHIVE_ONLY`, `:101`
`authorized_chat_ids: []`, with `scripts/host/enable_telegram.ps1` / `verify_telegram.ps1` /
`verify_objective.py:118-144` implementing and testing `TICKET_READY` + `LSMC_OPPORTUNITY`).
**Decision needed:** is D2/PAUSE formally rescinded by the 2026-10-07 objective, and is
host-local `MESSAGE_DELIVERY` opt-in the authorized path?

**C2 — A machine-readable manifest still asserts demo authorization.**
`docs/v2/AG_V2_BASELINE_MANIFEST_V1.json:50` → `SESSION_TRADE_V1: demo_authorized: true,
manager_dispatchable: true` (frozen 2026-09-21, baseline `1e75e36`, i.e. **before** D3 on
2026-09-30), echoed in prose at **PS:1825**. Registry (RG:36) and `authority.py:37` say
`false` and fail closed. Risk: any script/agent that reads JSON before prose concludes demo
is authorized. **Fix:** dated supersession stamp on that block, or regenerate the authority
summary; correct PS:1825.

**C3 — The execution / trade-management authority chain described by the docs is absent from
`main` at cf0ce0f.** Cited by AG:40-49, AG:56-66, PS:2338-2360, PS:2362-2378, PS:1805-1806,
RG:17-20, `config/trading.yaml:1-6,33-38`, `scripts/manage_trade.py:19-23`,
`.agents/skills/strategy-management/SKILL.md:47`, `docs/REPO_STRUCTURE_AUDIT.md:10`:
`execution/{risk,executor,mt5_gateway,validator,intent_builder,journal,models,adapter}.py`,
`assistant/commands.py`, `trade_management/*`, `mt5/{management_gateway,account,deals}.py`.
Import probe: **8/8 `ModuleNotFoundError`**; `scripts/web_execute_trade.py` and
`tests/test_btc_proposal_execution_boundary.py` (cited at PS:2757, RG:93) also absent.
Consequences: RG:17's "explicit-command demo execution exists project-wide", PS:2368's
"ORDER_SEND = ENABLED for DEMO accounts" and PHASE 6 "BUILT" are unverifiable/false **in this
tree**. See C11 for the owner-level framing.

**C4 — The mandatory bootstrap manifest routes agents to four nonexistent modules.**
AG:253-269 requires reading `config/agent_context.json`, and AG:267 states "A HEAD mismatch
alone does not invalidate the manifest". That manifest (`generated_from_head 933921fa` ≠
`cf0ce0f`, `last_verified_utc 2026-09-20`) routes to `src/session_sweep_continuation`,
`src/proposals`, `src/execution`, `src/scheduling` — **all absent**. Also absent but cited as
authority: `src/large_smc_research` (RG:68, `ST_LARGE_SMC_V1.yaml:31`, PS:1866, RM:348),
`src/validation_framework/adapters/` (RG:68, RG:119), `src/strategy_manager` (RG:120-129,
PS:883, `ag_scheduler_v2.yaml:88`), `src/opportunity/{large_smc_adapter,ssc_adapter}.py`
(PS:923-925, RM:348-352), `GET /api/strategies` (RG:124 — real API exposes only
`GET /api/opportunities`). **Fix:** refresh `config/agent_context.json`, or add a
"routes may be stale" guard, before the next runtime/strategy mission.

**C5 — The scheduler authority asserts a registered strategy does not exist.**
`config/ag_scheduler_v2.yaml:84-91`: "ST_SESSION_SWEEP_CONTINUATION_V1 **does not exist
anywhere in this repository** (no registry entry, no adapter, no contract, no tests …
confirmed 2026-09-10)", aliasing it to `SESSION_TRADE_V1`. Contradicted by RG:107-140,
`strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` (v**1.0.1**, while RG:134 says v1.0.0),
`config/governance/strategy_lifecycle.yaml:35-37`, `docs/v2/AG_V2_BASELINE_MANIFEST_V1.json:55`
and `config/historical_datasets/ST_SESSION_SWEEP_CONTINUATION_V1_EURUSD_PACKAGE.yaml`. The
same config caps `symbols: [EURUSD, GBPUSD]` (≠ O1) and is `status: RESEARCH` /
`OFFLINE_RESEARCH` while `config/agent_context.json:53` names it *the* scheduler authority.

**C6 — Large-SMC C10 status is a four-way disagreement.** `SIGNED_AND_LOCKED` 2026-09-07
(RG:68, `ST_LARGE_SMC_V1.yaml:28-31`) vs "BLOCKED at C10 / C10 UNSIGNED / v1.0.6
RESEARCH_DRAFT" (PS:1814, 1866-1868, 1886, 2178 — inside tables titled *current*) vs
`engine_runtime_status: UNSIGNED_BLOCKED`, `implementation_status: PENDING`
(`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml:301-304`) vs the inline changelog comment
`ST_LARGE_SMC_V1.yaml:81-82` ("C10 … remain UNSIGNED by explicit owner decision
(2026-09-01)"). PS:1877-1886 "Current capability classification table" is the most quotable
and the most wrong.

**C7 — Risk-sizing authority is described three incompatible ways.** PS:2732-2738 + RG:19-20:
`entry_order_type` ambiguous/undefined and "a `config/trading.yaml` account-wide default is
used instead" (1.0 %). Machine truth: `entry_order_type: MARKET`
(`ST_ASIAN_SWEEP_5R_V1.yaml:98,103`); no `risk_per_trade_pct` in the strategy YAML;
`config/trading.yaml:29` says its own 1.0 % is "Not read by any code yet except
`execution/risk.py`" (which does not exist); PS:1991-2009 states no fallback exists; pilot
configs carry **0.5 %**; the manual-ticket path uses `config/owner_ticket.yaml:8
risk_pct: null` → `RISK_CONFIG_MISSING`. Owner risk: someone sizes a ticket at 1.0 % on the
strength of a documented fallback no code implements.

**C8 — Roadmap version and pointer drift at the top of the authority hierarchy.** PS:1584
"owner adopted … **V3** as the authoritative roadmap" vs RM:1 "**V4**" + RM:5 "supersedes the
V3 implementation ordering"; PS:1590-1591 points to "*Current rolling classification
(2026-09-12)* at the top of this file" — the real heading is PS:871 "**(2026-09-21)**", 871
lines into a 2774-line file. RM:655-701's "immediate implementation order" still begins at
V2-2A/3A/3B/Parity #1 as pending, which PS:922-959 stamps `PASS` and whose code is missing.

**C9 — Test totals and suite names are unquoted-date hazards.** PS:1741 "1356 passed"
(2026-09-02/03) vs PS:177 "770 passed" (2026-10-02) vs PS:65 "1050 passed" (2026-10-06) vs
PS:52 "1120 tests" (2026-10-07) — against 204 tracked `src/` files and 64 test files at
cf0ce0f, with at least one cited suite (`tests/test_btc_proposal_execution_boundary.py`,
RG:93) nonexistent. Any advisory claim quoting a total or suite must be date- and SHA-bound.

**C10 — Dated sections carry un-marked "current" wording.** PS:1772-2321 is headed
"Capability & Roadmap Reconciliation (**dated 2026-09-06**)" but contains subsections titled
"*Current* capability classification table" (PS:1877), "*Current* operational snapshot"
(PS:1719), "Telegram — **current** owner directive" (PS:2011) and "**Core** project
objective" (PS:2056). An advisory scanner or a new agent cannot tell currency from date
without reading the parent heading. **Fix:** add an explicit superseded banner per
`docs/DOCUMENTATION_GOVERNANCE.md:62-73` (dated addendum, no rewrite of history).

**C11 — `main` does not contain the execution path the owner objective mandates (highest
priority).** ISSUE #47 §4 requires routing "only through the repository's canonical
`assistant.commands.execute_command()`", and its readiness block states the demo framework
"exists project-wide". At `cf0ce0f` that framework is **not in the repository**:
`.gitignore:1-47` does not exclude it (only caches, `node_modules`, `/logs/`, `/journal/`,
`/artifacts/diagnostics/`, `/config/local/`), `pyproject.toml:10-11,14` would auto-discover
it under `src/`, the import probe fails for all 8 modules, and no test asserts its presence
(`tests/test_import_integrity.py` has no such expectation). Therefore R5/R6 cannot be
evidenced from `main`, and PS:2322-2336 ("All 11 Python packages … moved into `src/`")
describes a tree that no longer matches. **Decision needed:** commit the
execution/trade-management/assistant packages to `main`, **or** amend V5 §4 to name the
host-only tree (`D:/wp3-main-integ`, AG:75) as the execution authority and mark `main`
explicitly as non-buildable for execution.

**C12 — Crypto identity conflict: perp contract authority is being used for CFD tickets.**
V5 §2 forbids borrowing BTCUSDT/ETHUSDT perp authority for BTCUSD/ETHUSD CFDs; the *active*
path does exactly that by mapping (`crypto_ticket_v3.yaml:4,17`, endorsed by RG:99-105), the
LSMC 1.1.0 contract lists the perp names (`:19`), and the objective preflight enforces the
perp universe (`verify_objective.py:40-41`). Concrete consequence: `crypto_symbols.py:22`
BTCUSDT `point=0.1` vs host-captured `BTCUSD.json point=0.01` — a **10× point/pip
divergence** feeding BTC stop-distance math in the six-instrument watch (ETH: 0.01 both).
PS:119-123 already matches V5 R2's "not yet qualified"; what no in-scope doc flags is the
identity borrow itself.

**C13 — O3 "all six" is universe-complete but gate-incomplete, and the fix is already in the
repo.** `ST_LARGE_SMC_V1_1_1_0.yaml:63-64` leaves USDJPY/XAUUSD `point: null /
FIXTURE_ONLY` ("host must capture MT5 `symbol_info()`"), which per the contract's own flagged
choice (`:50`) degrades those instruments to `C10_PIP_SIZE_NOT_EVIDENCED`. The captures
**exist** (`USDJPY.json point=0.001 digits=3`, `XAUUSD.json point=0.01 digits=2`, both
`broker_symbol=*-VIP`, `server=VTMarkets-Demo`, `trade_mode=FULL`) and are already validated
by `verify_objective.py:79-87`. RG:69-77 states the six-instrument watch without this caveat
→ V5 R3 acceptance is not met for 2 of 6 (4 of 6 counting BTCUSD/ETHUSD per C12).

**C14 — Demo-gate sequencing conflict between the two objective documents.** V5 puts an
explicit owner-confirmed Demo order inside R6 host acceptance with no soak;
`docs/PROJECT_OBJECTIVE.md:88-95,139` requires a ≥10-cycle `broker_mutations = 0` soak
*before* the demo-authorization decision. Both are live; neither references the other. One
must be declared authoritative before any R5/R6 work is scheduled.

**C15 — Stale and mis-pointed "next open item" in the top rolling summary.** PS:66 points at
PR #40 (**merged**) as the open item; the real pending FX remedy is **PR #62** (v1.1.2
candidate closing L2 without editing frozen v1.1.1 — precisely V5 R1), and no in-scope doc
mentions v1.1.2. Also open and unreflected in scope: PR #63 (CFD ticket contract + LSMC 1.1.0
audit / 1.1.1 candidate), #64 (`TICKET_STORE_V1`), #67 (M1 replay outcome grading), #69 (docs
live facts/drift), #70 (host heartbeat).

**C16 — Merging PR #60 silently changes the Telegram scope contract.** PR #60 (open,
`mergeable_state=clean`, 20 files) sends `WATCH_READY` **and every `INFO_ONLY_*`** decision;
main's documented contract sends only newly archived `READY` under `TICKET_READY` plus LSMC
`OPPORTUNITY`, with WATCH/INFO/STALE/BLOCKED/DATA_ERROR archive-only (PS:182-186) and
stale-withheld tickets "never `WATCH_READY`" (PS:14-16). Owner-visible message volume changes
on merge, and `verify_objective.py:135-142`'s `telegram_report_scope` check would need to move
with it. Recommend the merge decision state which scope contract wins, and record V5 R4's
approval-binding requirement (ticket ID + strategy version + code SHA + expiry) — `code_sha()`
stamping already exists (`manual_ticket.py:343-344`); the binding path does not.

**C17 — The two files every agent reads first carry neither the instrument universe nor the
three protected labels.** AGENTS.md names no instruments and has 0 occurrences of
`LOGIC_VERIFIED`/`EDGE_VERIFIED`/`DEMO_AUTHORIZED`; ROADMAP has 0 of each label and 0 crypto
symbols. The definitions live only in ISSUE #47, registry comments and
`docs/PROJECT_OBJECTIVE.md` — none of which AGENTS.md's bootstrap (AG:253-269) routes to (it
routes to `config/agent_context.json`, itself stale per C4). Cheapest fix: a short pointer
block in AGENTS.md to ISSUE #47 / `docs/PROJECT_OBJECTIVE.md` plus the three label
definitions. Owner decision; no code change.

## 9. Method, evidence and limits

- **Read-only audit.** `git status --porcelain` empty and `HEAD` = `cf0ce0f` before and after
  every audit pass; no commits, pushes, or file writes during the audit. This document and
  `scripts/docs/advisory_allowlist.json` are the only artifacts produced, in the close-out
  docs-only change set.
- **Evidence gathered by:** targeted `grep`/`awk` line reads (no repo-wide dumps); file and
  directory existence checks; YAML/JSON field reads; one `PYTHONPATH=src` import probe of 8
  modules (all `ModuleNotFoundError`); `scripts/check_skill_mirror_drift.py`
  (`NO_DRIFT: 33 files`); `diff -rq .agents/skills .claude/skills`; `.gitignore` +
  `pyproject.toml` inspection to prove the missing packages are not ignored; host-captured
  symbol-metadata field reads; range scans of PS:242-870 and PS:1297-1581 for the four
  protected labels.
- **GitHub API (read-only):** `main` HEAD SHA/date; `contents/docs?ref=main`; PR #66 file
  list; PR #28/#40/#60/#62/#63/#66 state; open PR and issue lists; ISSUE #47 body.
- **Not verifiable here (`NO_SOURCE`, not `CONTRADICTS`):** Windows Task Scheduler state, MT5
  terminal/broker facts, Telegram bot token and chat IDs, `D:\` trees, host-local
  `config/local/` overrides (gitignored by design).
- **Not scanned line-by-line (allowlisted in §7, outside requested scope):** PS:242-870 and
  PS:1297-1581 dated bodies; `docs/status/**`; `docs/PROJECT_CAPABILITY_COMPLETENESS.md`;
  `README.md`; `docs/README.md`.
- **Deferred by explicit owner instruction ("No other edits"):** `docs/README.md` /
  `docs/status` navigation link for this record, which AG:230-245 and
  `docs/DOCUMENTATION_GOVERNANCE.md:54-60` would normally require when a document is added.
  No `PROJECT_STATUS.md` rolling-snapshot entry was added either, since this audit changes no
  implemented capability, runtime reachability, execution authority, safety gate, strategy
  authorization, or regression baseline.
