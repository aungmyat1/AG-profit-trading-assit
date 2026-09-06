# Project Status — AG Profit Trading

AG Profit Trading is a **Trading Assistant + Strategy Execution Platform**. See
`README.md` for the folder map. The first section is the current rolling summary;
later sections preserve dated milestone evidence and may contain older test totals.

## Two-section capability model (2026-09-06)

The project is organized into two capability sections, audited in full in
`docs/PROJECT_CAPABILITY_COMPLETENESS.md` (state matrices, execution-authority matrix,
qualification counters, priorities, owner decisions — do not duplicate those matrices
here). **SECTION A — Trading Edge & Decision Core** (market data, session logic,
strategy rules, decision classification, proposals, risk/sizing, shadow/observation
evidence) and **SECTION B — Operations, Execution & Platform** (Telegram, MT5
execution infra, persistence, CLI, scheduler, release management) are governed by one
rule: Section B must never silently change Section A's direction/entry/SL/TP/risk.

Current one-liners, from actual evidence as of `main`
`651ade619c2c2df9a973d45cea37ae6599c2b9eb`:

- **FX**: Series `AG_V1_0_3_FX_SHADOW_SERIES_002` — valid=0/20, invalid=1, excluded=0,
  pending=0; next eligible trading day 2026-09-07.
- **BTC**: Bybit production market-data connectivity confirmed (HTTP 200/retCode 0) —
  data access only, not trade execution or profitability; daily-decision CLI ready;
  30-valid-observation campaign is 0/30 and **OWNER_AUTHORIZED to start** as of
  2026-09-06T06:52:42Z. No observation has been counted yet; prior diagnostics and
  missed report windows do not count retroactively. Crypto execution remains disabled.
- **Execution**: MT5 Demo infrastructure implemented and DEMO_VERIFIED generically
  (a real MT5 Demo-account order round trip, 2026-08-28; not real-money execution
  evidence); `ST_ASIAN_SWEEP_5R_V1`, the active V1.0.3 FX pilot strategy, is not
  `demo_authorized`, so it cannot use it yet (a registry gate, not a missing
  capability). `SESSION_TRADE_V1` is independently `demo_authorized: true` for its
  `ASIAN_LONDON` cycle only (`LONDON_NEWYORK` is `false`), but it is a separate
  strategy on a separate engine — this does not grant, share, or imply execution
  authority for `ST_ASIAN_SWEEP_5R_V1` or any other strategy. Strategy authorization
  and execution-channel authorization are independent gates; authority is never
  inherited across strategies. Live trading remains disabled by default.
- **Telegram**: Phases A, B, C, D1 are fully committed on feature branch
  `feature/telegram-demo-execution-gateway-v1` at commit `740512b`
  ("AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE"). The
  feature-branch working tree is clean (no uncommitted changes) as of this audit. It
  has not been merged into `main`, and development remains **paused** by owner
  directive; broker wiring absent by design.
- **Large-SMC**: `RESEARCH_DRAFT`, blocked at C10 (broker stop-loss); no proposal/
  demo/live authority.

## Current operational snapshot (2026-09-05)

This section is the rolling summary. Test totals elsewhere in this document belong to
the dated milestone that introduced the surrounding feature.

```text
ANALYSIS                      AVAILABLE
DAILY SESSION/SMC RUNTIME     READ-ONLY, restart-persistent
DEMO OPEN/CLOSE EXECUTION     IMPLEMENTED, explicit-command-gated
LIVE TRADING                  DISABLED BY DEFAULT
MANUAL TRADE MANAGEMENT       BUILT, independently gated, live validation deferred
FX LONDON->NEW YORK CYCLE     UNIT_TESTED, ST_ASIAN_SWEEP_5R_V1 LONDON_NEWYORK pilot (AG_POST_LONDON_NEWYORK_PILOT_V1_0_1), proposal-only, isolated ledger from ASIAN_LONDON, no live/demo verification yet
CRYPTO SIGNAL CONTRACT        IMPLEMENTED (incubation)
CRYPTO DATA ADAPTER           LIVE-VALIDATED, Bybit production public/read-only BTCUSDT linear perpetual: server time/instrument/M5 endpoints HTTP 200 retCode=0; frozen adapter validated complete closed H1/M5 evidence on 2026-09-05. No credentials/private endpoints.
CRYPTO DAILY DECISION         OPERATIONAL CLI READY, scripts/run_btc_daily_report.py enforces 00:05-00:15 UTC next-day window, previous-UTC-date evaluation, complete 24 H1 reference + 288 M5 observation audit, immutable archive, and informational proposal ticket on READY. First in-window scheduled archive pending; observation campaign remains 0/30 and not separately authorized.
CRYPTO RESEARCH RUNTIME       LIVE-DATA-VALIDATED, RESEARCH_ONLY/PROPOSAL_ONLY, execution_domain=CRYPTO_RESEARCH/execution_authority=DISABLED, statically and behaviorally verified never to reach execution.executor/mt5.management_gateway
CRYPTO EXECUTION              NOT IMPLEMENTED, fail-closed (execution.adapter.CryptoExecutionAdapter remains NOT_IMPLEMENTED; execution.executor now explicitly rejects any non-TradeCommand object, not just BTC proposals)
LARGE SMC STRATEGY            RESEARCH_DRAFT v1.0.6, research-only funnel + replay infra fixed, C10 remains sole blocker, no execution authority
SMC SEMANTIC TRAP GUARD       UNIT_TESTED, additive evidence validation for Asian Sweep + Large SMC
HISTORICAL REPLAY             LIVE-MT5 ACCESS BLOCKED
FULL REGRESSION               1356 passed / 1 skipped / 0 failed (2026-09-02/03, `python -m pytest -q`, AG_COMPLETE_TRADE_OPPORTUNITY_V1 remediation milestone -- see docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md); previous dated milestone baseline: 979 passed / 5 skipped / 0 failed, 2026-08-30 -- see dated sections below
RELEASE MANIFEST               AG_TRADE_ASSISTANT_V1_0_3 frozen as RELEASE_CANDIDATE (2026-09-03, config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml) -- pins the source baseline described above; V1.0.2 remains the current documented/operational release (config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml is still the default consumed by src/post_asian_pilot/pilot_config.py and preflight.py). Owner decisions recorded 2026-09-03: credential rotation OWNER_CONFIRMED_COMPLETE (Binance/MEXC/Bybit); withdrawal permission OWNER_CONFIRMED_RESTRICTED (2026-09-03); IP-restriction status still UNRESOLVED; BTC production market-data authority FROZEN as Bybit (adapter NOT_IMPLEMENTED, environment-blocked HTTP 403 from here, same class as Binance's HTTP 451); Large-SMC C10 conceptual stop model FROZEN as AG_NATIVE_INVALIDATION (implementation/contract-freeze still PENDING, engine unchanged/still BLOCKED). Release qualification (20-day FX shadow, 30-day BTC observation) remains pending, not started -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md.
OPERATIONAL PREFLIGHT          AG_TRADE_ASSISTANT_V1_0_3 preflight: PREFLIGHT_PASS_SHADOW_READY (closed 2026-09-03). Initial run (same date, prior environment) returned HOLD solely on MT5 connectivity ("No IPC connection" -- no terminal reachable from that tool environment; all other categories PASS'd there already, see docs/status/AG_TRADE_ASSISTANT_V1_0_3_OPERATIONAL_PREFLIGHT_STATUS.md, preserved as historically accurate for that environment). Re-run from the intended operator environment (MT5 terminal connected, demo account confirmed) closed that blocker: EURUSD/GBPUSD both resolve with exchange-verified metadata and 24 well-formed, correctly-ordered M15 closed bars each (the pipeline's only required timeframe -- strategies/ST_ASIAN_SWEEP_5R_V1.yaml, src/post_asian_pilot/pipeline.py), session/clock contract validates, no broker mutation performed -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md. Release remains RELEASE_CANDIDATE, not RELEASED; FX shadow/BTC observation collection not started (0/20, 0/30).
FX SHADOW EVIDENCE CONTRACT    AG_TRADE_ASSISTANT_V1_0_3 FX shadow-validation evidence contract frozen 2026-09-03: SHADOW_EVIDENCE_CONTRACT_READY (series AG_V1_0_3_FX_SHADOW_SERIES_001, contract AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1). Freezes VALID_DAY/EXCLUDED_DAY/INVALID_DAY/PENDING_RECONCILIATION definitions, per-unit evidence fields (trading_date x cycle x symbol), immutable-evidence, duplicate, cross-cycle-isolation, restart, and data-error contracts -- every field mapped onto existing, already-tested components (governor.DailyTradeLedger, report.cycle_to_dict, store.py idempotent writes/immutable snapshots); no new shadow runtime built. Large-SMC/C10 remain independent: PARTIALLY_RESOLVED_REQUIREMENTS, three owner decisions (exact buffer, spread/bid-ask policy, broker minimum-distance policy) still UNSIGNED, engine still BLOCKED.
FX SHADOW DAY 001 (2026-09-02)  EXCLUDED_DAY. Shadow-validation authorization for AG_V1_0_3_FX_SHADOW_SERIES_001 arrived after both ASIAN_LONDON (07:00-11:00 UTC) and LONDON_NEWYORK (12:00-15:00 UTC) execution windows for 2026-09-02 had already closed, and after both cycles' ledgers already held real pre-existing claimed slots (4/4) from ordinary V1.0.2-labeled operation predating this series -- no uncontaminated window remained to fairly test the frozen runtime today. Not a strategy/runtime defect. One read-only --once probe was run to confirm live state (proposal-only, order_send unreachable, confirmed). Counters after this entry: valid_days=0/20, excluded_days=1, invalid_days=0, pending_days=0 -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_001_STATUS.md.
FX SHADOW DAY 002 (2026-09-03 attempt)  PENDING_RECONCILIATION. Authorized re-run attempted for trading_date 2026-09-03, but at time of run (2026-09-02T22:51Z system / 2026-09-03T01:51Z broker) Thursday's asian reference session (00:00-06:00 UTC) had not yet started and both execution windows were 8+ hours away -- no unit was yet eligible for evaluation (not a failure, not an exclusion of the day itself, just premature timing). One read-only probe confirmed this returns the same already-excluded 2026-09-02 state, not new evidence. Not resolved to VALID/INVALID; re-run required at/after 11:00 UTC (ASIAN_LONDON) and 15:00 UTC (LONDON_NEWYORK) on 2026-09-03, under separate authorization. Counters: valid_days=0/20, excluded_days=1, invalid_days=0, pending_reconciliation=1 -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_002_STATUS.md. Continuation same day (10:36 UTC): a further read-only probe produced a real, non-synthesized GBPUSD ASIAN_LONDON proposal (SHORT, reason UPPER_SWEEP_STRICT_PENETRATION); EURUSD stayed WATCH. Confirmed FX_SESSION_GATE = VERIFIED_CORRECT (10:36 UTC is legally inside the 07:00-11:00 UTC window, not an early-evaluation defect) and FX_RELEASE_IDENTITY = PRESENTATION_ONLY_METADATA_DRIFT (pilot_config.DEFAULT_RELEASE_CONFIG_PATH is hardcoded to V1.0.2; release_id is metadata-only, never selects strategy/pilot/risk/session behavior) -- remediation diff fully defined but held, not applied, pending explicit owner go-ahead. Day 002 still does not count toward 20/20 pending that reconciliation. BTC's Bybit-adapter release-qualification gate conflicts with V1.0.3's own scope-freeze invariant -- classified QUALIFICATION_REMEDIATION_REQUIRES_OWNER_AUTHORIZATION, no Bybit code written. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_QUALIFICATION_BLOCKERS_STATUS.md.
FX DAILY REPORTING INFRASTRUCTURE (2026-09-03)  PARTIAL_REPORTING_INFRASTRUCTURE_READY. Added a combined FX daily decision-report builder (src/post_asian_pilot/daily_fx_report.py) that aggregates the existing, unchanged per-cycle report.render_pilot_end_report() for ASIAN_LONDON and LONDON_NEWYORK into one canonical JSON artifact, plus a generic append-only/immutable archive (src/post_asian_pilot/report_archive.py, idempotent re-generation, numbered correction records on genuine change, original never overwritten) and a scheduler-ready CLI (scripts/run_fx_daily_report.py -- no OS scheduler job installed). No strategy/risk/execution semantics changed; 6 new focused tests plus the existing 66 FX pilot tests all pass. BTC daily reporting, a scheduler install, READY notifications, and outcome/broker-trade history remain not built (out of this narrowed slice's scope). Still blocked on the same FX release-identity and BTC Bybit-scope items above. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_DAILY_REPORTING_HISTORY_AND_SCHEDULER_STATUS.md.
FX RELEASE-IDENTITY REMEDIATION (2026-09-04)  FX_RELEASE_IDENTITY_REMEDIATION_COMPLETE. Applied the previously-defined, now owner-authorized 5-file metadata-only fix so active FX pilot/reporting output self-identifies as AG_TRADE_ASSISTANT_V1_0_3 instead of V1.0.2 (pilot_config.DEFAULT_RELEASE_CONFIG_PATH, preflight.py's default/assertion, report.py's label/docstring, run_post_asian_pilot.py's CLI strings, 2 of the 5 originally-flagged test assertions -- config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml itself untouched). No strategy/risk/session/quota/execution semantics changed; affected suite 72 passed / 0 failed. Re-ran the FX daily-report CLI read-only against 2026-09-03: decisions/proposals byte-identical to the pre-remediation run, only the release label changed -- the archive correctly preserved the original V1.0.2-labeled record and wrote a numbered correction (journal/reports/fx/2026/2026-09-03.correction-001.json) rather than overwriting it, confirming the immutability policy works with real evidence. Day 001/Day 002 (Series 001) preserved unchanged, still non-counting; recommend a clean AG_V1_0_3_FX_SHADOW_SERIES_002 (0/20) for future collection -- not started. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_REMEDIATION_STATUS.md.
BASELINE FREEZE BEFORE FX SERIES 002 (2026-09-04)  BASELINE_FROZEN_SERIES_002_READY. Series 002 was blocked (BASELINE_NOT_READY) because the release-identity remediation and daily-reporting infrastructure existed only in the uncommitted working tree -- owner authorized commit-and-freeze (not an uncommitted-tree exception). Reviewed and classified every dirty path (5 remediation files, 4 new reporting files, 7 status docs, PROJECT_STATUS.md as intended; journal/reports/ runtime evidence explicitly excluded, left untracked); confirmed no strategy/session/risk/quota/proposal/execution semantic change; ran the affected suite fresh (72 passed/0 failed) before staging explicit paths only (no `git add -A`). Committed as SOURCE_BASELINE_COMMIT 68d76f6b1982f2b2936e12128151a308ba153a13 ("Freeze V1.0.3 FX identity and daily reporting baseline"). config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml's own frozen source_baseline.git_head (be5d31a, from the earlier manifest-freeze milestone) was deliberately left untouched -- it describes when the manifest itself was frozen, not a live pointer; this new hash is recorded only in status docs/PROJECT_STATUS.md instead. SERIES_002_COUNTING_READY = YES; AG_V1_0_3_FX_SHADOW_SERIES_002 (0/20) was not initialized or started this milestone. Not pushed. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_BASELINE_FREEZE_BEFORE_FX_SERIES_002_STATUS.md.
FX SHADOW SERIES 002 DAY 001 (2026-09-04)  INVALID_DAY. First Series 002 evaluation attempt under SOURCE_BASELINE_COMMIT 68d76f6, read-only (no strategy cycle re-run, no order sent). Discovered a real, pre-existing material defect: report.render_pilot_end_report() looks up decisions using the pilot config's reference_session_name ("asian"/"london_am", lowercase), but a real post-close decision from the strategy engine is saved under TradeSignal.reference_session ("Asian"/"London", capitalized, from strategies/ST_ASIAN_SWEEP_5R_V1.yaml's session_pairs) -- a key-casing mismatch that made today's canonical report falsely show NO_RECORD for both ASIAN_LONDON symbols despite two real, legitimately-claimed READY proposals (EURUSD, GBPUSD, ready_at 07:45 UTC) actually existing in the ledger/decision journal. Confirmed by reading the raw journal files directly, not inferred. Preserved all evidence, made no source changes (defect not fixed inside the countable day, per instruction), classified INVALID_DAY. Counters: valid_days=0/20, excluded_days=0, invalid_days=1, pending_days=0. Next step: a separate owner-authorized remediation milestone must fix the reference_session key-casing mismatch before Series 002 can produce trustworthy daily evidence. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md.
FX REPORT DECISION-KEY REMEDIATION (2026-09-04)  REPORT_KEY_REMEDIATION_COMPLETE. Fixed the Day 001 defect: render_pilot_end_report() now looks up decisions via a new post_asian_pilot.store.find_decision() helper matching on (strategy_id, symbol, trading_date) within each already-isolated per-cycle decision store, picking the latest-evaluated record when more than one candidate exists, instead of building a reference_session-cased dict key. Also found and fixed a second instance while reproducing: LONDON_NEWYORK's mismatch is not mere casing ("London" vs "london_am" differ by more than case), so the initial case-insensitive-only approach was replaced with this cycle-isolation-based fix. No persisted journal file was rewritten; no strategy/session/risk/quota/execution semantics changed. 6 new/updated focused tests; affected suite 78 passed/0 failed. Re-ran the existing report against the same 2026-09-04 journals: ASIAN_LONDON EURUSD/GBPUSD now correctly show READY with their real proposal IDs, LONDON_NEWYORK correctly shows WATCH -- archived as a numbered correction, original preserved, per the append-only archive's own design. Day 001 remains INVALID_DAY (not retroactively counted); counters unchanged: valid_days=0/20, invalid_days=1. Series 002 continues (no new series required by the frozen evidence contract). See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md.
FX SHADOW SERIES 002 DAY 002 (checked 2026-09-04, re-checked 2026-09-05)  BASELINE_VERIFIED_AWAITING_NEXT_ELIGIBLE_DAY. Verified HEAD matches validation_source_baseline 3b2eeed (updated from 30b63f8 after the Entry Ticket wiring commit), no source drift (only journal/reports/ dirty), fresh affected-suite run 92 passed/0 failed. 2026-09-04/05/06 cannot be Day 002 -- 09-04 is already Day 001's (INVALID_DAY) trading date, 09-05/06 are weekend; next eligible trading date is Monday 2026-09-07. No FX cycle invoked, no report generated, no source touched -- pure verify-and-stop, twice now. Counters unchanged: valid_days=0/20, invalid_days=1. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_002_STATUS.md.
FX COMPLETE ENTRY TICKET WIRING (2026-09-04)  FX_COMPLETE_ENTRY_TICKET_WIRING_COMPLETE. Wired the existing, unchanged report.render_entry_ticket() into the per-cycle operational output of scripts/run_post_asian_pilot.py (--once/--status/--watch): a READY proposal now gets an additive `entry_ticket` JSON field / "ENTRY TICKET" human-readable section, sourced verbatim from the same decision/proposal/ledger already produced by run_pilot_cycle() (pipeline.py untouched). Non-READY states get no ticket (entry_ticket=null, status=NOT_APPLICABLE); a render failure degrades to entry_ticket=null/status=RENDER_ERROR with a safe error code without changing the underlying decision/proposal/ledger claim. The canonical AG_FX_DAILY_REPORT_V1 schema is explicitly untouched (verified by test). 14 new focused tests (JSON, human-output, render-error, both cycles, both symbols, execution firewall, daily-schema compatibility); affected suite 92 passed/0 failed. No strategy/session/risk/quota/proposal-generation/execution-authority change. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_COMPLETE_ENTRY_TICKET_WIRING_STATUS.md.
AG_BYBIT_BTC_MARKET_DATA_AND_DAILY_DECISION_V1 (2026-09-05)  OWNER_APPROVAL_REQUIRED. Stopped at the milestone's own governance gate before any implementation: searched the manifest and every V1.0.3 status document and found only forward-references ("next milestone: AG_BYBIT_BTC_MARKET_DATA_V1") to this work, never an actual owner sign-off on the read-only Bybit scope exception the V1.0.3 scope freeze requires -- consistent with the earlier release-qualification-blockers finding (QUALIFICATION_REMEDIATION_REQUIRES_OWNER_AUTHORIZATION). No branch/worktree created, no adapter/registry/test code written, FX baseline (3b2eeed) and all protected FX surfaces untouched (confirmed by git status). Also confirmed, read-only: ST_LIQUIDITY_SWEEP_RETEST_V1 is documented in strategies/STRATEGY_LEDGER.md but has no real entry in strategies/registry.yaml (comment-only mention) -- a real inconsistency, not fixed. BTC evidence remains 0/30. See docs/status/AG_BYBIT_BTC_MARKET_DATA_AND_DAILY_DECISION_V1_STATUS.md.
AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1 (2026-09-05)  BTC_OBSERVATION_TIME_CONTRACT_FROZEN. Owner approved the read-only Bybit qualification exception (explicit direct instruction, this session); work proceeds on isolated branch/worktree btc/bybit-qualification-v3 (source_HEAD 759e2cb), never touching the active FX workspace. Froze docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md: UTC calendar day, half-open [00:00:00Z, next-day 00:00:00Z), daily report target 00:05-00:15 UTC next day (06:35-06:45 MMT), late-data/correction policy (fail-closed DATA_ERROR at cutoff, additive-correction-only, no overwrite, no automatic retroactive VALID_DAY counting). Verified against strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml's own CRYPTO_PERP profile (PREVIOUS_DAY reference already documented as "strict UTC midnight-to-midnight"; execution_windows 13:30-16:00 UTC) -- no strategy timing conflict, 8+ hour margin before the report target. FX timing/protected surfaces confirmed unchanged. BTC evidence remains 0/30, campaign not started. See docs/status/AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1_STATUS.md and docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md.
AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3 -- GOVERNANCE (2026-09-05)  Owner explicitly approved V1_0_3_BYBIT_QUALIFICATION_EXCEPTION=APPROVED_READ_ONLY_ONLY (direct instruction, this session, exact scope list recorded in config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml's new qualification_exception block). Reconciled the known ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0 registration inconsistency: added its entry to strategies/registry.yaml using the existing schema exactly (registered/research=true, demo_authorized/live_authorized=false, no unsupported fields) -- registration only, no authority change (STRATEGY_LEDGER.md already documented ACTIVE_INCUBATION/RESEARCH_ONLY since 2026-08-30). Updated the manifest's btc_market_data_authority/release_qualification_gates.btc fields to reflect the now-implemented adapter (see IMPLEMENTATION entry below) without touching unrelated FX gates or the scope_freeze block. 6 focused tests (registration/ledger identity, no-unsupported-fields, no-execution-authority) pass. FX protected surfaces confirmed unchanged. Work isolated on branch/worktree btc/bybit-qualification-v3. See docs/status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md.
AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3 -- IMPLEMENTATION + PROVENANCE (2026-09-05)  BTC_IMPLEMENTED_PRODUCTION_VALIDATION_BLOCKED. Implemented BybitLinearPerpFeed (src/execution_runtime/bybit_linear_perp_feed.py) against Bybit's official V5 API (verified via WebFetch, not memory): category=linear BTCUSDT, public/unauthenticated only, handles Bybit's descending kline order and retCode envelope, mirrors the existing Binance adapter's fail-closed validation contract exactly. Added additive exchange_id/symbol_meta parameters to btc_sweep_research.pipeline.run_research_cycle (72 pre-existing BTC tests unaffected) and a new btc_sweep_research.daily_report module (AG_BTC_DAILY_REPORT_V1: READY/WATCH/NO_TRADE/DATA_ERROR, reusing post_asian_pilot.report_archive unchanged for immutable/idempotent/correction archiving). 33 new focused tests; combined BTC suite 111 passed/1 pre-existing skip/0 failed. Freshly re-tested Bybit connectivity from this environment post-implementation: still HTTP 403 (CloudFront country-block, unchanged from 2026-09-03) -- BTC_PRODUCTION_VALIDATION=BLOCKED_ENVIRONMENT, no circumvention attempted. Code ready (BTC_DAILY_DECISION_CODE_READY=YES) but not operational; observation NOT started, BTC evidence remains 0/30. FX protected surfaces confirmed unchanged at every stage. Three commits on isolated branch btc/bybit-qualification-v3 (governance 705a790, implementation 0c5cda1, provenance freeze this commit), none pushed. Next: VALIDATE_BYBIT_BTC_PATH_IN_PERMITTED_ENVIRONMENT. See docs/status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md.
AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1 (2026-09-05)  BTC_PRODUCTION_DATA_PATH_PASS_SCHEDULER_READY. Merged the frozen BTC qualification lineage into main without changing the seven protected FX behavioral paths. Bybit production public endpoints recovered from the earlier environment-specific HTTP 403 and returned HTTP 200/retCode 0. Added strict scheduler-ready CLI scripts/run_btc_daily_report.py, complete closed-candle audit (24 prior-day H1 + 288 observation-day M5), observation-date/future-candle guards, clean machine JSON, immutable archive, and human READY proposal ticket explicitly labeled NOT A BROKER TICKET. Live diagnostic against observation date 2026-09-04 returned WATCH/NO_QUALIFIED_SWEEP_YET with complete data-quality PASS; deliberately outside the report window, unarchived, disposable state, and non-counting. Local Task Scheduler installer added for 06:37 MMT. Crypto execution remains unimplemented/disabled; campaign remains not started at 0/30 pending separate owner authorization. See docs/status/AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1_STATUS.md.
```

## Capability & Roadmap Reconciliation (dated 2026-09-06)

This section is additive — it does not replace or rewrite the rolling summary above or
any dated evidence below. It exists to answer, from current evidence, seven standing
questions: what AG can do now; what is implemented but not integrated; what is
verified; what is actually enabled/authorized; what is research-only; the current
core-completion path; and where Telegram, MT5 Demo, BTC/Bybit, and Large-SMC sit
relative to that path. No strategy semantics, risk settings, execution authority,
broker routing, or release state were changed while writing this section.

**Core principle.** `IMPLEMENTED ≠ VERIFIED ≠ ENABLED ≠ AUTHORIZED`. Historical release
state (`docs/VERSION_HISTORY.md`) is distinct from current project state (this
document). Execution infrastructure (can a component send an order) is distinct from
strategy execution authority (is a specific strategy allowed to use it). A component
being able to place an MT5 order does not mean a strategy is authorized to use it.

**Authority sources used to build this section** (verified, not assumed):
`docs/VERSION_HISTORY.md` = historical application/version authority.
`PROJECT_STATUS.md` (this file, rolling summary above) = current operational
authority. `strategies/registry.yaml` + `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` +
`strategies/STRATEGY_LEDGER.md` = strategy authorization authority. `AGENTS.md`'s
"Authority order" section = execution authority — confirmed the sole approved
execution funnel is `assistant.commands.execute_command(command, user_confirmed=True)`
(`AGENTS.md`, "Authority order" / PROJECT_STATUS.md "Execution authority restructure
(2026-08-28)" below).

### AUTHORITY_RECONCILIATION matrix

| Capability | Historical (VERSION_HISTORY, 2026-09-03) | Current (PROJECT_STATUS, 2026-09-05/06) | Registry authority | Implemented | Verified | Enabled | Notes |
|---|---|---|---|---|---|---|---|
| EURUSD/GBPUSD Asian→London proposals | IMPLEMENTED, PROPOSAL_ONLY | unchanged, PROPOSAL_ONLY, Series 002 in progress | `ST_ASIAN_SWEEP_5R_V1` demo_authorized=false | Yes | Runtime evidence exists | PROPOSAL_ONLY |  |
| EURUSD/GBPUSD London→New York proposals | IMPLEMENTED, unit-tested only, shadow pending | unchanged, PROPOSAL_ONLY, still no live/demo verification | same strategy, `LONDON_NEWYORK` pair | Yes | Unit-tested only | PROPOSAL_ONLY |  |
| `ST_ASIAN_SWEEP_5R_V1` | v1.1.1 ACTIVE, SOLE_DAY_TRADING_AUTHORITY (pilot-scoped) | unchanged | registered=true active=true research=true demo_authorized=false live_authorized=false | Yes (signal engine) | Live runtime evidence exists | PROPOSAL_ONLY only | `entry_order_type` resolved to MARKET (2026-08-31); `risk_per_trade_pct` still absent from the strategy YAML itself |
| MT5 Demo execution subsystem | IMPLEMENTED, disabled by default, every send requires a fresh explicit user command | unchanged | N/A — application infrastructure, not strategy-scoped | Yes (`execution/executor.py`, `execution/mt5_gateway.py`) | DEMO_VERIFIED 2026-08-28 (ticket 1879685149; a real MT5 Demo-account round trip, not real-money execution evidence) | Disabled by default; explicit-command-gated |  |
| FX proposal→MT5 integration | not separately called out | Generic `ASSISTANT_PROPOSAL` plumbing exists and was DEMO_VERIFIED 2026-08-28 (ticket 1880212783); see architecture note below | not strategy-scoped by itself | Yes, generically | DEMO_VERIFIED, but from the assistant's own analysis-derived `TradeProposal`, not from an `ST_ASIAN_SWEEP_5R_V1` pilot-cycle proposal | Requires fresh explicit command AND the specific strategy to be `demo_authorized` | `ST_ASIAN_SWEEP_5R_V1` is not `demo_authorized`, so its pilot proposals cannot use this path as of 2026-09-06 even though the generic plumbing works |
| MT5 live execution | IMPLEMENTED behind gates, not authorized as a live service | unchanged | N/A | Yes (behind gates) | Not exercised live | DISABLED (`config/trading.yaml` `account.allow_live_trading: false`) |  |
| BTC market-data runtime | IMPLEMENTED (Binance adapter), production blocked (HTTP 451/403) | Bybit adapter IMPLEMENTED and production market-data connectivity confirmed (HTTP 200/retCode 0, 2026-09-05) — data access only, not trade execution; supersedes 2026-09-03 blocked claim | `ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0 registry entry, research=true | Yes | Production-data-verified 2026-09-05 | Read-only market data only |  |
| Bybit production market-data connectivity | BLOCKED (HTTP 403, CloudFront country-block, 2026-09-03) | RECOVERED — HTTP 200/retCode=0 confirmed 2026-09-05 (`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`, `qualification_exception`/`btc_market_data_authority` blocks) | N/A (infrastructure) | Yes | Production-data-verified 2026-09-05 — data access only, not trade execution | Read-only public endpoint only, no credentials |  |
| BTC sweep/retest proposals | IMPLEMENTED, unit-tested, RESEARCH_ONLY | unchanged, RESEARCH_ONLY, `execution_domain=CRYPTO_RESEARCH`/`execution_authority=DISABLED`, statically+behaviorally verified never to reach `execution.executor`/`mt5.management_gateway` | `ST_LIQUIDITY_SWEEP_RETEST_V1` registered=true active=false research=true demo_authorized=false live_authorized=false | Yes | Unit-tested + production-data-verified | RESEARCH_ONLY |  |
| BTC daily report | not present (predates 2026-09-05 milestone) | OPERATIONAL CLI READY (`scripts/run_btc_daily_report.py`), immutable archive, informational proposal ticket labeled NOT A BROKER TICKET | inherits `ST_LIQUIDITY_SWEEP_RETEST_V1`'s RESEARCH_ONLY authority | Yes | Diagnostic run against production data 2026-09-05, evaluated 2026-09-04 (WATCH, disposable, non-counting) | Scheduler-ready, not yet scheduled to run in-window |  |
| BTC scheduler | not present | Task Scheduler installer added (`scripts/install_btc_daily_task.ps1`), 06:37 MMT | same | Yes | Installer exists; no confirmed installed/running scheduled task recorded yet | Not started |  |
| BTC execution | NOT IMPLEMENTED, DISABLED | unchanged | `execution_authority=DISABLED`, `crypto_execution_adapter: NOT_IMPLEMENTED` | No | N/A | DISABLED |  |
| Large-SMC research | IMPLEMENTED (research funnel + replay infra), RESEARCH_ONLY, C10 blocked | unchanged, v1.0.6 RESEARCH_DRAFT, C10 sole blocker | `ST_LARGE_SMC_V1` research=true, no demo/live | Yes (research engine) | Corrected replay baseline recorded | RESEARCH_ONLY; engine fails closed to BLOCKED |  |
| Large-SMC proposal authority | none | unchanged, none | `proposal_generation_authorized: false` | No | N/A | NONE |  |
| Telegram approval module | not covered by VERSION_HISTORY (VERSION_HISTORY never mentions Telegram) | Committed as a frozen baseline in an isolated worktree only (`.claude/worktrees/telegram-execution-gateway-v1`, branch `feature/telegram-demo-execution-gateway-v1`, commit `740512b` "AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE", branched from `main` at `63938cc`); not merged into `main`, not pushed; `src/authorization/`, `src/notifications/` still do not exist on `main` | not registered as a strategy; not a strategy-authority concept | Phases A/B/C/D1 all present and committed on the feature branch (`authorization/{store,models,config,integrity,strategy_authority,proposal_source,telegram_gateway}.py`, `notifications/{telegram_client,trade_ticket_formatter}.py`, matching tests) | 117 focused tests passing (all HTTP mocked); not verified against `main` — none of it is part of the current operational codebase | PAUSED (owner directive) | See `docs/status/AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_FROZEN_STATUS.md` (on the feature branch) and Telegram section below |
| Telegram→real proposal integration | not covered | COMPLETE and committed, worktree-only (`proposal_source.py` reads real `post_asian_pilot` proposal journals read-only) — not merged, not part of current operational state | N/A | Complete, committed on feature branch | Verified (8 focused tests) | Not integrated into `main` | Do not treat as core-project evidence |
| Telegram→MT5 execution integration | not covered | Not present anywhere in the branch's file set (no code calls `execution.executor` or `assistant.commands.execute_command`) | N/A | No | N/A | Not integrated | |

### Corrected architecture description

Do **not** publish "FX Trade Proposal → Risk/Safety Gates → Execution System → MT5
Demo" as one seamless, strategy-authorized pipeline for `ST_ASIAN_SWEEP_5R_V1` — the
repository does not prove that exact integration exists for it (`demo_authorized:
false`). `SESSION_TRADE_V1` is separately `demo_authorized: true` for its
`ASIAN_LONDON` cycle, but it runs on a different engine in a different repository and
does not use this repository's FX proposal/execution pipeline — its authorization does
not extend to `ST_ASIAN_SWEEP_5R_V1` or vice versa; strategy authority is never
inherited across strategies. The accurate picture for this repository's own pipeline is
two separated domains plus a documented, narrower bridge:

```text
CORE FX PROPOSAL RUNTIME (proposal-only, strategy-scoped)
  FX deterministic runtime (strategy_engine/, ST_ASIAN_SWEEP_5R_V1)
    -> TradeIntent / TradeProposal (execution/intent_builder.py, post_asian_pilot/proposal.py)
    -> proposal persistence + reporting (journal/post_asian_pilot/, journal/post_london_newyork_pilot/,
       report_archive.py, AG_FX_DAILY_REPORT_V1)
    -> PROPOSAL-ONLY OPERATIONAL OUTPUT (CLI --once/--status/--watch, Entry Ticket)
  ST_ASIAN_SWEEP_5R_V1 stops here as of 2026-09-06: demo_authorized=false, live_authorized=false.

SEPARATE EXECUTION SUBSYSTEM (application infrastructure, not strategy-scoped)
  explicit fresh user command
    -> execution safety gates (execution/validator.py, execution/risk.py, journal.py atomic claim)
    -> assistant.commands.execute_command(command, user_confirmed=True)
    -> MT5 Demo (execution/executor.py, execution/mt5_gateway.py)
    -> journal / reconciliation

DOCUMENTED BRIDGE BETWEEN THEM (generic, infrastructure-level, demo-verified once)
  A TradeProposal built from the assistant's own ASSISTANT_PROPOSAL analysis path CAN
  be resolved ("execute it") into a TradeCommand and sent through the execution
  subsystem above — AG_ASSISTANT_PROPOSAL_EXECUTION_V1, 2026-08-28, ticket 1880212783,
  a real MT5 Demo-account order_send -> real close, fully verified (not real-money
  execution evidence). This bridge is strategy-agnostic
  infrastructure: it does not, by itself, authorize any specific strategy. No evidence
  was found of this bridge ever being exercised specifically with an
  ST_ASIAN_SWEEP_5R_V1 pilot-cycle-origin proposal — the 2026-08-28 evidence describes
  a proposal from the assistant's own live analysis, not a post_asian_pilot journal
  entry. ST_ASIAN_SWEEP_5R_V1 proposals cannot use this bridge as of 2026-09-06 because
  the strategy itself is not demo_authorized (a registry-level gate, independent of
  whether the bridge code works).

PARALLEL RESEARCH DOMAINS (independent strategy families, no execution authority)
  BTC:        Bybit market data (production connectivity confirmed, data access only) -> ST_LIQUIDITY_SWEEP_RETEST_V1 research
              engine -> btc_sweep_research proposals -> RESEARCH_ONLY, never reaches
              execution.executor / mt5.management_gateway (verified statically+behaviorally)
  Large-SMC:  ST_LARGE_SMC_V1 v1.0.6 RESEARCH_DRAFT -> large_smc_research engine ->
              fails closed to BLOCKED on any C10-dependent candidate; no proposal
              authority

PAUSED OPTIONAL INTERFACE (not part of the core path, not merged)
  Telegram approval module (Phases A/B/C/D1 all built and committed as a frozen
  baseline, commit 740512b) lives only in an isolated feature-branch worktree; it is
  not connected to MT5 execution anywhere in its own file set, and it is not part of
  main. Development is PAUSED by owner directive.
```

### Current capability classification table

| Capability | Implementation | Verification | Integration | Authority | Current operational state |
|---|---|---|---|---|---|
| MT5 Demo execution subsystem | IMPLEMENTED | DEMO_VERIFIED (2026-08-28; a real MT5 Demo-account round trip, not real-money execution evidence) | Standalone, explicit-command-only | Application infrastructure, not strategy-gated | ENABLED, explicit-command-gated, disabled by default absent a fresh command |
| FX proposal→MT5 execution (generic bridge) | IMPLEMENTED | DEMO_VERIFIED (2026-08-28), generically, not for `ST_ASIAN_SWEEP_5R_V1` specifically | NOT_GENERALLY_WIRED to any pilot-cycle proposal | Requires per-strategy `demo_authorized` in addition | PARTIAL — infrastructure works, no strategy authorized to use this repository's execution path can use it (`SESSION_TRADE_V1`'s separate `demo_authorized: true` is on a different engine and does not apply here) |
| `ST_ASIAN_SWEEP_5R_V1` Demo authority | N/A (strategy has no execution code of its own) | N/A | N/A | `demo_authorized: false`, `live_authorized: false` (registry) | BLOCKED — proposal-only by explicit authorization gate, independent of infrastructure readiness |
| BTC execution | NOT_IMPLEMENTED (`CryptoExecutionAdapter`) | N/A | N/A | `execution_authority: DISABLED` | NOT_OPERATIONAL, fail-closed |
| BTC market data | IMPLEMENTED (Bybit adapter) | PRODUCTION_DATA_VERIFIED (2026-09-05, HTTP 200/retCode 0) — data access confirmed only, not trade execution or profitability | Wired into `btc_sweep_research` and `run_btc_daily_report.py` | Read-only, no execution implication | OPERATIONAL for data/reporting only |
| Large-SMC | IMPLEMENTED (research engine) | Corrected replay baseline recorded | Standalone research pipeline, no execution/broker call anywhere | `proposal_generation_authorized: false`, C10 UNSIGNED | RESEARCH_ONLY, BLOCKED at C10 for any candidate needing it |

### Historical vs. current — stale-claim correction

`docs/VERSION_HISTORY.md`'s "Current Capability and Upgrade Report (2026-09-03)" is
preserved unchanged as historical record — it was accurate for that date. Two of its
claims are now superseded by later evidence in this file's rolling summary and by
`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s `qualification_exception` block:

- "BTC ... production market-data authority is owner-frozen as Bybit (2026-09-03),
  adapter not yet implemented, environment-blocked (HTTP 403)" — **superseded**: the
  adapter is now implemented (`src/execution_runtime/bybit_linear_perp_feed.py`) and
  production market-data connectivity is confirmed (HTTP 200/retCode 0, 2026-09-05) —
  data access only, not trade execution or profitability. Historical
  state as of 2026-09-03; see this file's rolling summary (`CRYPTO DATA ADAPTER` line,
  2026-09-05) for current operational status.
- "Shadow-day/observation-day collection has not started" — **superseded** for FX:
  Series 002 has one classified day (Day 001, INVALID_DAY, defect found+fixed, not
  counted) and one verified-baseline pending day (Day 002, next eligible trading date
  2026-09-07). See `FX_VALIDATION` below for the current counters. BTC observation
  (0/30) genuinely has not started and that portion of the historical claim still holds.

`README.md` and `docs/README.md` are reconciled against this same current state (see
their own edits, dated 2026-09-06).

### BTC/Bybit current status (verify market data ≠ execution)

Market-data connectivity and trade-execution capability are independent facts. Current
truth, from `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s `qualification_exception`
and `btc_market_data_authority` blocks (owner-approved 2026-09-05,
`V1_0_3_BYBIT_QUALIFICATION_EXCEPTION`, `APPROVED_READ_ONLY_ONLY`):

- Feed: `BybitLinearPerpFeed` (`src/execution_runtime/bybit_linear_perp_feed.py`),
  public/read-only only, no authenticated or order/wallet endpoint anywhere in it;
  111 BTC tests passing.
- Production connectivity: `PRODUCTION_PUBLIC_READ_PASS` (HTTP 200/retCode 0, verified
  2026-09-05) — supersedes the 2026-09-03 HTTP 403 CloudFront country-block finding,
  which is preserved as historical evidence in the same manifest, not deleted.
- Reporting: `scripts/run_btc_daily_report.py`, scheduler-ready, one disposable/
  non-counting diagnostic run completed 2026-09-05 (WATCH/NO_QUALIFIED_SWEEP_YET
  against 2026-09-04).
- Scheduler: `scripts/install_btc_daily_task.ps1` (06:37 MMT), added but not confirmed
  installed/running as a live scheduled task in this environment.
- Observation campaign: 0/30, forbidden_scope explicitly excludes starting it —
  requires separate owner authorization after production validation passes.
- Execution: forbidden_scope explicitly excludes order creation/checking/submission/
  modification/cancellation and wallet operations. `BTC_EXECUTION: NOT_IMPLEMENTED`.
  BTC research proposal capability never implies BTC execution authorization.

### FX validation current status

Do not report "shadow validation pending" or "collection has not started" without
citing the actual counters. Current series is `AG_V1_0_3_FX_SHADOW_SERIES_002`
(Series 001 — Day 001 EXCLUDED_DAY, Day 002 PENDING_RECONCILIATION — was left
unresolved and superseded by a fresh series, not retroactively fixed):

- `valid_days = 0/20`, `invalid_days = 1`, `excluded_days = 0`, `pending_days = 0`.
- Day 001 (2026-09-04): `INVALID_DAY` — a real reference-session key-casing defect was
  found and fixed (not retroactively counted as valid).
- Day 002: checked 2026-09-04, re-checked 2026-09-05 —
  `BASELINE_VERIFIED_AWAITING_NEXT_ELIGIBLE_DAY`. 2026-09-05/06 are weekend; next
  eligible trading date is Monday 2026-09-07.
- Baseline: source HEAD `3b2eeed` (validation_source_baseline), affected suite 92
  passed/0 failed at last verification.

### Strategy authority correction — `ST_ASIAN_SWEEP_5R_V1`

Values below are read as-is from `strategies/registry.yaml` and
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`; none were changed while writing this section.

- `demo_authorized: false`, `live_authorized: false` (registry).
- `entry_order_type: MARKET` for both `long_setup`/`short_setup` — resolved
  2026-08-31 (`AG_EXECUTION_RUNTIME_READINESS_V1`, strategy v1.1.1); the prior
  "dual-mode ambiguity" was determined to have never been a genuine two-case choice.
- `risk_per_trade_pct`: **UNSPECIFIED in the strategy YAML** — the
  `risk_and_money_management` block only declares `risk_mode:
  FIXED_PERCENT_OR_CONTRACT`, `stop_loss_mode: PERCENT_OF_SESSION_RANGE`,
  `stop_loss_range_pct: 0.25`. This is a real, current, unresolved gap, not a stale
  historical claim.
- **Account-level risk fallback — verified from code, not assumed.** Contrary to
  `strategies/STRATEGY_LEDGER.md`'s comment ("`execution/risk.py` currently falls back
  to `config/trading.yaml`'s account-wide `risk.risk_per_trade_pct: 1.0` default"),
  reading the actual call chain shows no code path performs that fallback as of 2026-09-06:
  `execution/risk.py::size_position()` and `execution/intent_builder.py::build_intent()`
  both take `risk_per_trade_pct` as a required parameter with no default and never read
  `config/trading.yaml` themselves; `execution/validator.py::validate_account_and_config()`
  only checks that whatever value it is handed is a finite number in `(0, 100]` — it
  does not supply one. `config/trading.yaml`'s own comment ("Not read by any code yet
  except execution/risk.py") is itself stale — `risk.py` does not read the file. The
  value that actually reaches the FX proposal path as of 2026-09-06 comes from the pilot-config
  layer (`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml` /
  `..._LONDON_NEWYORK_PILOT_V1_0_1.yaml`'s own `risk_per_trade_pct`), deliberately kept
  outside the strategy YAML (`post_asian_pilot/pilot_config.py`'s own docstring). There
  is currently no automatic code-level fallback from an unset strategy
  `risk_per_trade_pct` to `config/trading.yaml`'s account-wide default for the direct
  `execution.executor` path (`ASSISTANT_PROPOSAL`/`USER_EXPLICIT_ORDER`) — a caller must
  supply an explicit value every time. This is reported as a finding, not resolved; no
  risk value was changed.

### Telegram — current owner directive

The owner has explicitly decided: **PAUSE further Telegram-related development,
finish the core project first.** This is a current project-management directive from
this session, not derived from `docs/VERSION_HISTORY.md` (which never mentions
Telegram at all). Verified against the actual worktree, not assumed:

- `implemented_phases`: A+B+C+D1 all committed as a frozen, broker-unreachable
  baseline in `.claude/worktrees/telegram-execution-gateway-v1` (branch
  `feature/telegram-demo-execution-gateway-v1`, commit `740512b`
  "AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE",
  branched from `main` at `63938cc` — this is the branch's only Telegram-related
  commit; `main` itself remains at `63938cc`, unchanged). Not merged into `main`, not
  pushed. `authorization_core` (`src/authorization/{store,models,config,integrity,strategy_authority,proposal_source,telegram_gateway}.py`)
  and the transport/callback gateway (`src/notifications/{telegram_client,trade_ticket_formatter}.py`)
  are present with matching tests (`tests/test_authorization_core.py`,
  `tests/test_telegram_client.py`, `tests/test_telegram_gateway.py`,
  `tests/test_trade_ticket_formatter.py`, `tests/test_phase_d1_proposal_and_authority.py`,
  `tests/test_phase_d1_gateway_execution_flow.py` — 117 tests, all passing, all
  Telegram HTTP mocked).
- Phase D1 (real proposal integration) is **complete and committed**:
  `src/authorization/proposal_source.py` (its own docstring: "Phase D1: the real,
  authoritative TradeProposal source ... replaces Phase C's placeholder JSON-file
  lookup") reads real `post_asian_pilot` proposal journals read-only; a live strategy
  demo-authorization recheck (`src/authorization/strategy_authority.py`, reads
  `strategies/registry.yaml` directly on every Execute Demo click) blocks execution
  with `BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED` for `ST_ASIAN_SWEEP_5R_V1`
  (`demo_authorized: false`, verified from the registry file, unchanged). `main` still
  has zero Telegram files (`src/authorization/`, `src/notifications/` do not exist
  there) — this is a preservation commit on an isolated branch, not an integration.
- MT5/Bybit broker wiring: not present anywhere in the branch's file set — no
  Telegram module calls `execution.executor`, `execution.coordinator`, or
  `assistant.commands.execute_command`; verified by an AST-based import scan plus
  grep, both clean. See `docs/status/AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_FROZEN_STATUS.md`
  (on the feature branch) for full detail, including a known pre-existing Windows
  `JsonKeyValueStore` concurrency race under heavy combined-suite parallel test load
  (`WINDOWS_APPROVAL_STORE_CONCURRENCY = MUST_FIX_BEFORE_EXECUTION_AUTHORIZATION`) —
  does not affect FX/BTC qualification, which never touches this store; must be fixed
  before any future Telegram/MT5/Bybit execution work resumes.
- `development_state = PAUSED`. `reason = core-project (V1.0.3) qualification
  prioritized`. `resume_condition = explicit owner authorization after the V1.0.3
  release qualification decision`.
- No Telegram feature work was added, refactored, or continued this milestone beyond
  the preservation commit itself. Telegram is not a core-completion dependency.

### Core project objective

AG Profit Trading should become a deterministic trading assistant that can: (1)
produce an immutable deterministic `TradeProposal`; (2) persist it; (3) obtain fresh
explicit owner authorization through an approved interface; (4) enforce strategy
authority; (5) execute exactly once through the canonical command funnel; (6) operate
only against a positively verified MT5 Demo environment; (7) journal broker actions;
(8) reconcile against broker truth; (9) survive restart/crash boundaries safely; (10)
keep live trading disabled unless separately authorized. Telegram is one possible
future approval interface, not the definition of the core system.

### CORE-FIRST roadmap (replaces the old Telegram-centric Phase D roadmap)

- **CORE-D1 — Real deterministic proposal persistence.** Status: **substantially
  already implemented for FX**, not NOT_STARTED. `strategy_engine` → `TradeIntent` →
  `TradeProposal` (`execution/intent_builder.py`, `post_asian_pilot/proposal.py`) →
  durable per-cycle journal (`journal/post_asian_pilot/`,
  `journal/post_london_newyork_pilot/`) → append-only immutable archive
  (`post_asian_pilot/report_archive.py`, `AG_FX_DAILY_REPORT_V1`) → CLI inspection
  (`--once`/`--status`/`--watch`, Entry Ticket). Deterministic identity, strategy/
  version recording, restart-safe lookup, and no-broker-call are already evidenced by
  the FX shadow-series work above. Not yet formally re-verified against this
  milestone's exact acceptance-criteria wording (immutable execution fields, expiry
  recorded) — that re-verification, not the underlying capability, is what remains
  open.
- **CORE-D2 — Strategy execution contract.** OPEN, unresolved by design. Before
  connecting `ST_ASIAN_SWEEP_5R_V1` to MT5 Demo, an explicit owner decision is required
  among: (A) add a strategy-specific `risk_per_trade_pct` to the strategy YAML; (B)
  explicitly authorize the pilot-config/account-level risk value as the strategy's
  real contract; (C) remain proposal-only. This task reports the gap (see "Strategy
  authority correction" above) and does not choose for the owner.
- **CORE-D3 — Approved command funnel.** Status: **substantially already implemented**
  at the infrastructure level (see "Corrected architecture description" bridge above) —
  stored `TradeProposal` → "execute it" resolution
  (`assistant.commands.resolve_active_proposal()`) → freshness/integrity revalidation →
  `TradeCommand` → `assistant.commands.execute_command(command, user_confirmed=True)`
  → execution subsystem, DEMO_VERIFIED 2026-08-28 (a real MT5 Demo-account round trip,
  not real-money execution evidence). What remains open is strategy-level
  gating: `ST_ASIAN_SWEEP_5R_V1` pilot proposals cannot reach this funnel as of
  2026-09-06 because the strategy is not `demo_authorized` — that is CORE-D2's
  decision, not a missing funnel capability.
- **CORE-D4 — MT5 Demo firewall.** Status: implemented and DEMO_VERIFIED for the
  existing OPEN/CLOSE path (`config/trading.yaml` `account.allow_live_trading: false`,
  explicit `user_confirmed=True` required every call, DEMO round trip verified
  2026-08-28). Not independently re-audited in this task against every firewall
  condition listed in the task protocol (unknown environment, analysis-mode leakage,
  etc.) — flagged for a dedicated review, not claimed complete here.
- **CORE-D5 — Controlled Demo verification gate.** Defined by this task only (offline
  tests → mocked end-to-end → real `order_check` → one minimum-size Demo order →
  verify broker ticket/journal/reconciliation; one authorization = one command = at
  most one broker submission = one reconciled broker result). No broker smoke test was
  performed by this task.
- **CORE-D6 — Recovery/concurrency hardening.** `execution/journal.py` already
  implements its own independent atomic-claim mechanism (O_EXCL exclusive-create,
  restart-safe, cross-process/cross-thread safe per the 2026-08-30 hardening notes
  referenced in this file's "Authority order" section) — separate from, and not
  affected by, the Telegram approval store's own concurrency implementation. The
  Telegram-specific approval store (`.claude/worktrees/telegram-execution-gateway-v1/
  src/authorization/store.py`) reuses the same O_EXCL idiom by its own docstring; no
  Windows-specific concurrency-race defect document was found under `docs/status/` for
  it in this pass. Flag clearly: **this pattern must not be re-implemented or weakened
  when Telegram resumes** — the core execution path's own atomic claim in
  `execution/journal.py` must remain the reference implementation.
- **CORE-D7 — Release/validation closure.** FX Series 002 in progress (0/20 valid, 1
  invalid, next eligible day 2026-09-07); BTC observation not started (0/30). Execution
  capability (MT5 Demo works) and evidence qualification (shadow/observation days) are
  separate — MT5 Demo working does not imply release completion.

```text
AG PROFIT TRADING -- CORE COMPLETION ROADMAP

CURRENT (2026-09-06)
  |
  v
CORE-D1  Real deterministic proposal persistence  [substantially already done for FX]
  |
  v
CORE-D2  Strategy execution contract (risk_per_trade_pct decision)  [OPEN -- owner decision required]
  |
  v
CORE-D3  Approved command funnel  [infrastructure already done; strategy-gate blocked on D2]
  |
  v
CORE-D4  MT5 Demo firewall  [implemented; not independently re-audited this pass]
  |
  v
CORE-D5  Controlled Demo verification gate  [DEFINED only, not run]
  |
  v
CORE-D6  Recovery/concurrency hardening  [core path already has its own atomic claim]
  |
  v
CORE-D7  Release/validation closure  [FX Series 002 0/20, BTC 0/30, in progress]
  |
  v
CORE PROJECT OPERATIONALLY READY
  |
  +--> OPTIONAL: Telegram integration resumes (resume_condition: core ready or owner reactivation)
  +--> OPTIONAL: Bybit Demo execution work (BYBIT-DEMO-1..6, not started)
  +--> OPTIONAL: Large-SMC evidence progression (C10 -> causal outcomes -> robustness -> proposal-authority decision)
```

**Large-SMC roadmap** (unchanged, preserved): research → C10 contract resolution
(owner-selected `AG_NATIVE_INVALIDATION` conceptual model, implementation still
`PENDING`) → causal outcomes → wider robustness → evidence review → separate
proposal-authorization decision. Demo/live execution remains independently
authorized and is not implied by any research progress. `ST_LARGE_SMC_V1` stays
`RESEARCH_DRAFT` — not promoted by this section.

### Current-state summary

```text
FX_SESSION_ANALYSIS             IMPLEMENTED, VERIFIED
FX_PROPOSALS                    PROPOSAL_ONLY (ASIAN_LONDON verified runtime evidence; LONDON_NEWYORK unit-tested, shadow pending)
FX_PROPOSAL_TO_MT5               PARTIAL (generic bridge IMPLEMENTED + VERIFIED 2026-08-28; NOT_WIRED for ST_ASIAN_SWEEP_5R_V1 specifically -- strategy not demo_authorized)
ST_ASIAN_SWEEP_DEMO_AUTHORITY    DISABLED (registry: demo_authorized=false)
ST_ASIAN_SWEEP_LIVE_AUTHORITY    DISABLED (registry: live_authorized=false)
MT5_DEMO_SUBSYSTEM               IMPLEMENTED, VERIFIED, explicit-command-gated
MT5_LIVE_SERVICE                 IMPLEMENTED behind gates, DISABLED
BTC_MARKET_DATA                  IMPLEMENTED, VERIFIED (Bybit, HTTP 200/retCode 0, 2026-09-05)
BTC_PROPOSALS                    RESEARCH_ONLY
BTC_EXECUTION                    NOT_IMPLEMENTED, DISABLED
LARGE_SMC_RESEARCH                IMPLEMENTED, RESEARCH_ONLY, BLOCKED at C10
LARGE_SMC_PROPOSALS               NOT_AUTHORIZED
LARGE_SMC_EXECUTION               NOT_IMPLEMENTED, NONE
TELEGRAM_INTERFACE                Phases A+B+C+D1 all committed on feature branch
                                   feature/telegram-demo-execution-gateway-v1 @ 740512b;
                                   feature-branch working tree clean; not merged to main
TELEGRAM_REAL_PROPOSAL_INTEGRATION  COMPLETE and committed on feature branch (not merged)
TELEGRAM_MT5_INTEGRATION          NOT_WIRED, not present anywhere in the feature branch
TELEGRAM_DEVELOPMENT_STATE        PAUSED (owner directive, 2026-09-06)
```

### Product objective

The target product produces two deterministic decision services: recurring intraday
**Session Trade** proposals and selective higher-timeframe **Large-SMC Trade** proposals.
Each evaluation must end in an explicit actionable or non-actionable state; the system
guarantees a daily decision report, not a forced trade. A proposal is not a broker
ticket. Broker execution remains a separate, freshly validated, explicitly
human-authorized action.

The current implementation is FX/MT5-first. `scripts/run_daytrading_runtime.py` provides
a read-only, closed-bar runtime for completed-session evaluation and SMC conditional
surveillance with restart-persistent state and idempotent alert records. The execution
runtime provides explicit-confirmation FX routing and restart reconciliation. These are
real runtime paths, superseding older documents that described the registry as having
no caller or orchestrator.

`ST_LIQUIDITY_SWEEP_RETEST_V1` contains parameterized Forex and crypto-perpetual signal
profiles. Crypto remains research/proposal-only: `execution_runtime.binance_usdtm_feed`
(added 2026-09-02) implements `execution_runtime.crypto_feed.CryptoCandleFeed` for
Binance USDT-M perpetual BTCUSDT public market data (fail-closed candle validation,
UNIT_TESTED offline; live connectivity from this environment is currently BLOCKED --
Binance returns HTTP 451 -- see the dated status document below), and
`execution.adapter.CryptoExecutionAdapter` still cannot send orders. The BTC research
runtime (`src/btc_sweep_research/`) enumerates every qualifying same-day occurrence (not
capped at one), separates strategy qualification from tradability-guard state, and builds
a `BTCSweepResearchProposal` explicitly tagged `execution_domain=CRYPTO_RESEARCH` /
`execution_authority=DISABLED`; `execution.executor.execute()` now rejects any object
that is not `execution.models.TradeCommand` before reading any of its fields, so this
proposal type cannot reach the FX order path even by accident. Its own exchange-specific
metadata (tick size, quantity step, minimum quantity) is sourced from the Binance adapter,
not the crypto_symbols.py synthetic defaults.

Documentation live-status changes follow
`docs/status/LIVE_STATUS_MAINTENANCE.md`. Dated milestone documents remain evidence of
their date and are not rewritten merely because later implementation superseded them.
The 2026-08-31 documentation refresh started a new full regression run, but it was
operator-interrupted after passing 64% with no reported failures because
environment-sensitive checks were taking an extended time; it therefore does not
replace the last completed baseline above.

Execution safety was reverified and hardened on 2026-08-30:

- OPEN and CLOSE share duplicate-command protection.
- An atomic, restart-persistent command claim permits only one worker to own a
  `command_id`; crash recovery fails closed rather than risking a duplicate send.
- Journal filenames use a deterministic hash of `command_id`, while entries retain the
  original ID. Existing safe legacy journal filenames remain readable.
- CLOSE volume rejects non-finite, non-positive, excessive, below-minimum, above-maximum,
  and unsafe remainder cases; off-step requests are floored to the broker step and are
  never rounded upward.
- Missing or malformed Session Trade adapter analysis fails closed.
- Historical replay explicitly blocks live MT5 candle/tick access even if a terminal
  was initialized earlier in the test or process. Historical session-box reconstruction
  remains a completeness gap and reports `HISTORICAL_SESSION_DATA_UNAVAILABLE`.
- Live FX tests skip closed-market days instead of weakening stale-data protection or
  fabricating candles.

Current default gates remain safe in `config/trading.yaml`: `mode: ANALYSIS`,
`allow_order_check: false`, `allow_order_send: false`, `allow_live_trading: false`, and
manual trade management in `DRY_RUN` with `allow_live_management: false`.

`SMC_TRAP_GUARD_V1` is an additive, deterministic evidence validator shared by
`ST_ASIAN_SWEEP_5R_V1` and `ST_LARGE_SMC_V1`. It rejects future/retrospective evidence,
direction claims made below strategy authority, and lower-timeframe attempts to
override higher-timeframe context. Strategy contracts also pin existing invariants
such as liquidity-event != trade-signal, penetration-without-reclaim = no trade, and
E3 sweep-without-reclaim = not eligible. It adds no entry filter, changes no strategy
version, and grants no proposal/demo/live authority. See
`docs/status/SMC_TRAP_GUARD_V1_STATUS.md`.

`ST_LARGE_SMC_V1 v1.0.6` is registered as an independent `RESEARCH_DRAFT` strategy
contract. It shares advisory Market Structure, Supply/Demand, Liquidity, Entry
Confirmation, and Trade Management capabilities, but shares no strategy authority or
validation evidence with `ST_ASIAN_SWEEP_5R_V1`. UC-001 (timeframe roles: D1/H1/M5),
C11 (target model: `HYBRID_WITH_STRUCTURAL_FALLBACK`), and C12 (candidate expiry:
shared `is_eligible_at()` window, no independent M1/M2/M3 timer) are resolved. C14
(duplicate/re-entry) is `PARTIALLY_RESOLVED`: setup-family identity reuses
`proposals/`'s existing `setup_id`, and candidate-occurrence/M-candidate identity is
deterministic and unit-tested via additive `source_id` fields on `M1Result`/
`M2Result`/`M3Result` and `proposals/occurrence_identity.py` — not wired into
`proposals/lifecycle.py`'s live store (shared with the live `SMC_CONDITIONAL_ENTRY_V2`
watcher; migration `SHARED_CHANGE_REQUIRED`); post-fill re-entry separately `DEFERRED`.

As of v1.0.5 (2026-09-02, `RESEARCH_ONLY_FUNNEL_V1`), a research-only engine exists:
`src/large_smc_research/` composes the already-frozen E1/E2/E3 + M1/M2/M3 pipeline
(`historical_replay.stage2`, zero redetection) into explicit
`LargeSMCResearchDecision`s. C01 (instruments → `[EURUSD]` only), C16 (warmup → reuse
of `D1=60/H1=50/M5=200`), the C11 target-model adapter (formula unchanged, now
`IMPLEMENTED`), and C18 (simultaneous-combination selection →
`RECORD_ALL_INDEPENDENTLY`, reuse of C14) are resolved. `decision_states` dropped the
placeholder `READY` for `RESEARCH_QUALIFIED`/`INVALIDATED`. **C10 (broker stop-loss)
remains deliberately `UNSIGNED`** — an explicit owner decision to block outcome
simulation rather than guess; the engine fails closed to `BLOCKED` for any candidate
that would otherwise need it, with a decision-packet document. No proposal, demo,
live, execution, or risk-sizing authority was added. See
`docs/status/LARGE_SMC_V1_REGISTRATION_STATUS.md`,
`docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`, and
`docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`.

As of v1.0.6 (2026-09-02, `OUTCOME_LIFECYCLE_V1`), post-READY pending-entry expiry is
`RESOLVED_BY_REUSE`: `historical_replay/fill_simulator.py` (pre-existing, tested, never
previously wired here) already establishes no time-based expiry exists for this
pipeline — a pending entry terminates only via fill or structural invalidation, reused
verbatim by new `src/large_smc_research/pending_entry.py`. This phase also **discovered
and disclosed** (not fixed) a separate, pre-existing gap: C11's target-model adapter
and the project's own M1 inducement-candidate detection both silently fail during
historical replay because `market_structure.tiers.analyze_structure_tiers` requires a
live MT5 terminal for symbol metadata that `historical_replay/data_source_patch.py`
never patches — this likely explains the long-standing "M1 forms zero entry arrays"
finding as at least partly a data-source-patching artifact, not purely a strategy
result. The engine now fails closed to `DATA_ERROR` in this case rather than a
misleading `NO_TRADE`. See `docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`.

**Resolved same day (`REPLAY_METADATA_DECOUPLING_V1`):** the owner authorized a
dataset-fingerprint-bound historical `tick_size=0.00001` for
`EURUSD_M5_202504211715_202607310000` only (`HISTORICAL_ANALYSIS_ONLY` scope, tagged
`SYNTHETIC_RESEARCH`, never usable for execution — `config/historical_datasets/`,
`historical_replay/symbol_metadata_manifest.py`). Wired as an opt-in parameter into
`historical_data_context`, fixing both C11's target adapter and M1's inducement
detection at their one shared call site, with no live-behavior change (verified) and
no formula change. A corrected September 2025 replay isolates the effect to exactly
one combination cell (E1M1, previously starved) — every other cell byte-identical to
the pre-fix run. C10 (broker stop-loss) remains the sole open blocker.
Recommendation: `GO_TO_C10_DECISION`. See
`docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md` and
`docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`.

The strategy/skill workflow is organized conceptually in
`docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md`: local contracts and engines retain
authority; D-drive SMC repositories are classified as separate authorities, research
references, locked work, or historical safety evidence. `.agents/skills` and
`.claude/skills` remain path-for-path mirrors; no skill or strategy code was moved.

## Repository reorganization (2026-08-28)

All 11 Python packages + `session_clock.py` moved from repo root into `src/` (flat --
package names unchanged, so no import statement anywhere needed to change; see
`pyproject.toml`'s `pythonpath`/packaging config). 14 of 17 root-level `.md` docs moved
into `docs/{architecture,specs,status,setup}/`; `README.md`/`AGENTS.md`/
`PROJECT_STATUS.md` stay at root. `cleanup_mbt.ps1`/`setup_mbt.ps1` moved into
`scripts/`. Fixed three real `__file__`-relative config-path bugs this move exposed
(`execution/mt5_gateway.py`, `mt5/management_gateway.py`, `session_clock.py` all
assumed a fixed distance to repo root that changed by one level) plus five hardcoded
test-fixture paths (`tests/test_five_skill_runtime.py`,
`tests/test_entry_confirmation.py`, `tests/test_trade_management_pretrade.py`).
`config/`, `scripts/`, `tests/`, `strategies/`, `journal/`, `.claude/`, `.agents/` are
unchanged in place. First-ever git commits made as part of this pass (repo previously
had zero history). 448 passed / 0 failed, unchanged from pre-move baseline.

## Authority order (permanent project principle)

```
Strategy YAML -> Strategy Engine -> Execution Engine -> MT5
Agent skills / Trading Assistant capabilities -> ADVISORY ONLY
```

Trading Assistant capabilities (market-data, structure, supply/demand, liquidity,
entry-confirmation, trade-management) advise, inspect, explain. They have no
*independent* execution authority and never call `execution.executor`/
`execution.mt5_gateway`/`order_check`/`order_send` directly, and never override a
`strategy_engine.evaluate()` result — if a capability's read disagrees with the engine,
the engine's result stands; the capability may explain the disagreement, not act on it.
Actual broker execution is delegated to the central Trade Assistant execution layer
(`execution/executor.py`, reached only via `assistant/commands.py`) and requires
explicit user authorization every time — see "Execution authority restructure" below.

Exception, added 2026-08-27: `trade_management/` (Phase 6, manual-entry only) is a
third pathway, independent of both the above. It manages a position a human already
opened by hand and explicitly claimed by ticket — it never opens a position itself, and
its writes go only through `mt5.management_gateway` (modify SL / partial close / close),
gated by `config/trading.yaml`'s own `trade_management:` block, separate from
`execution/`'s gates.

## Execution authority restructure (2026-08-28)

```
EXECUTION DEVELOPMENT   = ACTIVE (entry-side OPEN, explicit-command-gated)
ANALYSIS                = AVAILABLE
ORDER_CHECK              = IMPLEMENTED (execution/mt5_gateway.py)
ORDER_SEND               = ENABLED for DEMO accounts, gated by config/trading.yaml AND
                            a required, non-defaulted user_confirmed=True per call
LIVE TRADING             = DISABLED (config/trading.yaml account.allow_live_trading: false)
```

`execution/mt5_gateway.py` and `execution/executor.py` (previously `NotImplementedError`
stubs) now implement OPEN for a new position, modeled directly on
`mt5.management_gateway.py`'s existing dry-run/live pattern. `execution/intent_builder.py`,
`risk.py`, `validator.py` are unchanged (still the strategy-signal path). CLOSE routes
through the existing, unmodified `mt5.management_gateway.close_position()` — no second
MT5 gateway.

Two `ExecutionSource`s (`execution/models.py`):
- `USER_EXPLICIT_ORDER` — a fully user-specified order (e.g. "sell EURUSD 0.31 lots SL
  ... TP ..."). Validated for geometry/sizing/broker constraints only
  (`trade_management.pretrade_engine.evaluate_trade_management()`) — never blocked for
  lacking a strategy signal or entry-confirmation.
- `ASSISTANT_PROPOSAL` — a `TradeProposal` the assistant generated from its own
  analysis, executed only on a later, separate explicit user command; refreshed and
  re-validated against live price at execution time, rejected as `PROPOSAL_STALE` if
  price/age has drifted past a documented tolerance rather than silently reused.

Both paths require `execution.executor.execute(command, user_confirmed=True)` — a
Python-level invariant, not a config flag: no code path reaches `order_send` without the
caller having just received an explicit user instruction that turn. Duplicate protection
via `execution/journal.py` uses an atomic persistent claim plus append-only hashed
journal files. It blocks concurrent workers, process-restart retries, and re-sending an
already-`EXECUTED` `command_id` without putting caller-controlled IDs into paths. CLI:
`scripts/execute_trade.py open|close ... [--confirm]`
(omit `--confirm` for a dry-run report of the exact broker request).

**AG_DEMO_EXECUTION_V1 (2026-08-28): PASSED.** One real, explicit-user-command DEMO
round trip verified live: order_check -> order_send -> broker-confirmed open (ticket
1879685149) -> live duplicate-command rejection -> close -> broker/deal-history-confirmed
closure -> config restored to safe defaults. Found and fixed one real defect during this
pass: MARKET-order geometry validation was defaulting `entry_price` to `0.0` instead of
resolving a fresh tick when `--entry` was omitted (`execution/executor.py::
_resolve_entry_price`). Full suite: 412 passed, 0 failed, unchanged count (bugfix, not
new functionality).

**AG_ASSISTANT_PROPOSAL_EXECUTION_V1 + AG_RISK_PERCENT_SIZING_LIVE_V1 (2026-08-28):
PASSED.** `TradeProposal` (`assistant/analysis_models.py`) is now execution-linked: an
`ASSISTANT_PROPOSAL` `TradeCommand` resolves side/SL/TP/risk_percent FROM the stored
proposal (never re-typed by the caller), and `assistant.commands.resolve_active_proposal()`
gives deterministic "execute it" resolution (`NO_ACTIVE_PROPOSAL` / `AMBIGUOUS_PROPOSAL`
/ resolved). Risk-percent sizing now actually works end-to-end: `execution/executor.py`
fetches fresh equity + symbol_meta at execution time (previously never populated at all --
every risk_percent order would have failed `ACCOUNT_DATA_MISSING`) and adds a defensive
final-risk-revalidation check before `order_open`. An already-`EXECUTED` proposal now
blocks re-execution by proposal identity, independent of `command_id` — closes a real gap
where a fresh CLI invocation ("execute it again") would have bypassed the command_id-keyed
journal check and sent a genuine second order. Also fixed: the default order comment
(`f"AG_TRADE_ASSISTANT:{source}"`, 38 chars) exceeded MT5's ~31-char comment limit and
would have rejected every unlabeled order — found live via a real `order_check` failure.
Live-verified: real analysis -> proposal -> "Execute it" -> risk-percent-derived volume
(0.5% of $997.06 equity -> raw 0.0997 lots -> floored to 0.09, actual risk 0.4513%) ->
real order_send (ticket 1880212783) -> live duplicate-proposal rejection -> real close ->
deal-history-confirmed -> config restored. Full suite: 427 passed (412 + 15 new), 0 failed.

## ASSISTANT_RUNTIME_V1 (2026-08-27)

`strategy_manager/` + `assistant/runtime.py` now let the Trade Assistant coordinate
`SESSION_TRADE_V1` / `ASIAN_LONDON` end-to-end in three explicit modes (`ANALYZE_ONLY`
live-verified; `SHADOW_DEMO`/`DEMO_EXECUTION` gating unit-tested, not yet exercised
live). `LONDON_NEWYORK` and `LIVE` both hard-blocked, independent of any flag. Full
architecture: `docs/status/ASSISTANT_RUNTIME_V1.md`; live evidence: `docs/status/ASSISTANT_RUNTIME_V1_STATUS.md`.
278 passed / 0 failed (was 252 before this pass).

## SMC foundational skills validation pass (2026-08-27)

A dedicated validation pass added external/internal structure tiers
(`market_structure/tiers.py`, `swing_length` 5/50), HH/HL/LH/LL labeling, a matplotlib
`chart_renderer/` package, external/internal liquidity scoping + Inducement Candidate
detection (`liquidity/hierarchy.py`), and engineered/retail liquidity classification
(`liquidity/proxies.py`) on top of Phases 2-4 below — all additive, nothing here changed
or broke the frozen `analyze_structure()`/`AG_ORDER_BLOCK_V1`/existing `liquidity/`
behavior. Full results, capability matrix, and verdicts: `docs/status/SMC_SKILL_VALIDATION.md`.
252 passed / 0 failed (was 213 before this pass).

## Trading Assistant capability roadmap

```
PHASE 1 — MARKET DATA          COMPLETE / VERIFIED (AG_TIME_NORMALIZATION_V1, 2026-08-27)
PHASE 2 — STRUCTURE            COMPLETE / FROZEN
PHASE 3 — SUPPLY & DEMAND      COMPLETE / FROZEN (AG_ORDER_BLOCK_V1, frozen 2026-08-26, verified 2026-08-27)
ORDER BLOCK CONTRACT           AG_ORDER_BLOCK_V1 FROZEN -- L1/L2 + inside-bar still UNSIGNED
PHASE 4 — LIQUIDITY            COMPLETE / FROZEN (AG_LIQUIDITY_V1, frozen 2026-08-27)
PHASE 5 — ENTRY & CONFIRMATION VERIFIED / FROZEN (AG_ENTRY_CONFIRMATION_V1, frozen 2026-08-28)
PHASE 6 — TRADE MANAGEMENT     BUILT (manual-entry only, 2026-08-27) -- see below
```

### PHASE 6 — TRADE MANAGEMENT (manual-entry only): BUILT (2026-08-27)

Owner-requested, out of the bottom-up phase order above: manages *already open,
manually entered* MT5 positions. It was implemented independently of Phase 5 and
remains separate from the later entry-side `execution/` pathway. New top-level
`trade_management/` package
(`models.py`, `claims.py`, `state.py`, `risk.py`, `rules.py`, `validator.py`,
`journal.py`, `manager.py`, `position_monitor.py`), plus `mt5.account.positions()`
(implemented; was `NotImplementedError`), `mt5/deals.py` (new), and
`mt5/management_gateway.py` (new -- the only module allowed to call
order_check/order_send for modify/partial-close/close on an existing position).

**Authority addendum (extends, does not replace, the section below):** this subsystem
is a third, independently-gated pathway -- distinct from both the advisory-only skills
and entry-side `execution/`. It never opens a position (structurally: every
gateway function requires an existing ticket) and is gated by
`config/trading.yaml`'s own `trade_management: {mode, allow_live_management}` block,
default `DRY_RUN`/`false`. `.claude/skills/trade_management/*` /
`.agents/skills/trade_management/*` (`position-monitor`, `risk-manager`,
`partial-profit-manager`, `breakeven-manager`, `exit-manager`) are thin advisory
wrappers that delegate to `trade_management.rules`, not reimplementations.

Baseline V1 rules (frozen, not user-configurable without a new owner-signed rule): 75%
partial close at an explicitly-supplied TP1, breakeven only after that partial is
broker-confirmed, 25% runner closed at 5R from the frozen initial risk distance. Never
enlarges risk or volume; fails closed (`MANAGEMENT_BLOCKED`) on any ambiguity,
including a manual SL/volume change made outside this system.

Workflow: `python scripts/manage_trade.py claim <ticket> --tp1 X --final-r 5`, then
`python scripts/manage_positions.py --once` or `--watch`.

Tests: `tests/test_trade_management_*.py`, `tests/test_management_gateway.py` -- 56
passed, all offline (mocked MT5 positions/ticks, no live connection needed except the
gateway's own live-mode integration is monkeypatched too). Full suite: 211 passed, 0
failed (155 prior + 56 new).

**Not done in this pass (deferred, needs an explicit follow-up request):** live DEMO
validation against a real manually-opened position (spec's own "one intentionally small
DEMO trade" controlled-progression requirement) -- `allow_live_management` stays `false`
until that's explicitly run. Netting-vs-hedging broker mechanics
(`mt5.account.Account.is_hedging_account`) is wired but not yet exercised live.

See `docs/status/PHASE_1_4_FREEZE_STATUS.md` for the 2026-08-27 stabilization pass: root-caused and
fixed a generic (not symbol-specific) tie-break defect in `mt5.broker_time`'s weekly-
reopen-gap detection, established `AG_TIME_NORMALIZATION_V1` (`mt5/time_contract.py`),
and validated all four phases as a regression baseline (154 passed / 1 skipped / 0
failed) before Phase 5 begins. `FROZEN` means no silent semantic changes to
`AG_ORDER_BLOCK_V1` / `AG_LIQUIDITY_V1` going forward -- a behavior change requires a new
contract version or explicit owner instruction.

Each phase implemented bottom-up; owner approves before the next one starts.

### PHASE 5 — ENTRY & CONFIRMATION: VERIFIED / FROZEN (2026-08-28)

`AG_ENTRY_CONFIRMATION_V1` (`entry_confirmation/`) consumes `market_structure.StructureResult`
and `liquidity.LiquidityResult` verbatim -- no redetection of pivots, CHoCH, BOS, sweeps,
or reclaims. Canonical chain: `LIQUIDITY EVENT -> STRUCTURE_SHIFT (CHoCH) -> DISPLACEMENT
-> EVENT_SEQUENCE -> CONFIRMATION_STATE` (`CONFIRMED` / `PARTIAL` / `NOT_CONFIRMED` /
`INDETERMINATE`, no numeric score). Displacement is now signed as
`AG_ENTRY_DISPLACEMENT_V1`: `body_ratio >= 0.60 AND body >= 1.30 x median_body_20 AND`
direction matches the candidate. `event_sequence` enforces
`liquidity_time < structure_time <= displacement_time` (same-candle structure/displacement
allowed). `rejection` qualification, POI alignment, FVG-as-entry-trigger, and
BOS-as-structure_shift remain explicitly DEFERRED, not missing. See
`docs/status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md` for full evidence: fixed a
circular import (`entry_confirmation <-> liquidity <-> supply_demand <-> assistant`,
rooted in `supply_demand/native_zones.py` importing `assistant.market_data`), added 19
focused tests, ran read-only live MT5 validation on EURUSD (both examples correctly
resolved to `INDETERMINATE`/`NOT_CONFIRMED`-shaped evidence, not manufactured). Full
suite: 467 passed, 0 failed. `order_send` not used; `REAL_MONEY_TRADING` /
`AUTONOMOUS_TRADING` remain `DISABLED`, untouched by this phase.

### PHASE 1 — MARKET DATA: COMPLETE

Implemented in `mt5/`:
- `connection.py` — `connect()`/`is_connected()`, real, live-tested
- `broker_time.py` — UTC-offset detection via weekly-reopen-gap
- `market_data.py` — `get_candles()` (range), `get_latest_candles()` (position-based),
  `get_tick()` (Bid/Ask), `check_freshness()`; canonical `Candle` now carries `volume`
- `account.py` — `account()` (login/server/equity/demo flag)
- `symbol_resolver.py` — `get_symbol_meta()` (tick/contract/volume-step, generic across
  symbol types), `available_symbols()`

Fail-closed reason codes in use: `MT5_NOT_CONNECTED`, `SYMBOL_NOT_FOUND`, `DATA_MISSING`,
`INSUFFICIENT_CANDLES`, `STALE_DATA`, `DUPLICATE_TIMESTAMPS`, `NON_MONOTONIC_TIMESTAMPS`,
`SESSION_INCOMPLETE`, `TIME_NORMALIZATION_ERROR`, `UNSUPPORTED_TIMEFRAME`.

Report tool: `scripts/check_mt5.py --symbol X [--candles N] [--session asian] [--json]`.

Tests: `tests/test_broker_time.py` (7), `tests/test_market_data.py` (7, live-guarded).

**Fixed a real bug found live:** `get_candles()` passed naive datetimes to
`copy_rates_range`; MT5 silently reinterpreted them via this host's own system timezone
(UTC+6:30), shifting every session query by 6.5h. Fixed by passing epoch integers
instead — see `market_data.py`'s `_to_broker_epoch()`.

**Live examples (2026-08-26, VantageMarkets-Demo):**
- EURUSD: tick 1.16499/1.16512, 24/24 Asian bars, session high/low correct, freshness OK
- XAUUSD: tick 4592.92/4593.21, 24/24 Asian bars, freshness correctly flagged `STALE_DATA`

**Known gap:** `symbol_resolver.resolve()` (broker-suffix resolution, e.g.
`XAUUSD.crp`) still `NotImplementedError` — not hit yet since the connected account's
symbols are unsuffixed; revisit if a broker/symbol needs it.

### PHASE 2 — MARKET STRUCTURE: COMPLETE

`market_structure/` (new top-level package): `analyzer.py` (`analyze_structure()`,
public entry point), `smc_adapter.py` (the ONLY module allowed to import
`smartmoneyconcepts`; verified against installed v0.0.27's actual API, not an assumed
one), `models.py` (`StructureResult`, `StructurePoint`), `config.py` (reads
`config/market_structure.yaml`: `swing_length: 5`, `close_break: true`).

Capabilities: swing highs/lows, BOS, CHoCH, previous high/low, and a deterministic
`state` (`BULLISH`/`BEARISH`/`STRUCTURE_STATE_UNDEFINED` — no invented `RANGE`; see
`analyzer._structure_state()`'s docstring for why). Explicit per-call timeframe
(M1/M5/M15/M30/H1/H4/D1 — `mt5/market_data.py`'s `_TIMEFRAMES` extended beyond M1/M5/M15
for this). Closed candles only (`get_latest_candles` excludes the forming bar).
Warm-up (`max(swing_length*20, 100)` extra candles) fetched but not exposed as separate
"requested vs. total" ranges — reported provenance is the full fetched range.

**Dependency verification (required before coding against it):** `smartmoneyconcepts`
0.0.27's `swing_highs_lows`/`bos_choch` ignore the input DataFrame's own index and
return a fresh positional `RangeIndex`; `previous_high_low` instead calls
`pd.to_datetime(ohlc.index)` internally, so a positional `RangeIndex` there would be
silently reinterpreted as epoch-nanosecond garbage. Resolved by standardizing on one
canonical DataFrame (real UTC `DatetimeIndex`) for all three calls — verified live that
all three tolerate it correctly. Documented in `smc_adapter.py`'s module docstring.

Report tool: `scripts/analyze_structure.py --symbol X --timeframe Y [--count N] [--json]`.

Tests: `tests/test_market_structure.py` — 3 synthetic fixtures (ascending zigzag ->
BULLISH, descending -> BEARISH, range oscillation -> swings present but
`STRUCTURE_STATE_UNDEFINED`, no invented break), 1 adapter-shape test, 2 live EURUSD
(H1, M15) — all real data, both returned `BEARISH` with a live-confirmed BOS.

Added `requirements.txt` (didn't exist before) pinning the verified versions.

### Market Data Assistant layer: COMPLETE

`assistant/market_data.py` — the five user-facing capabilities on top of `mt5/` and
`market_structure/`, each returning a compact dataclass (never raw candle dumps to an
LLM): `market_snapshot()`, `historical_candles()` (UTC range or count), `session_snapshot()`
(open/high/low/close/range/midpoint/completeness), `data_health()` (per-check reason
codes, including new gap detection — `UNEXPECTED_DATA_GAP` vs. weekend closures, which
are not flagged), `multi_timeframe_snapshot()` (reuses `StructureResult` per timeframe).

Tests: `tests/test_assistant_market_data.py` — 10 passed (4 pure gap-logic, 6 live).

### PHASE 3 — SUPPLY & DEMAND: COMPLETE

New top-level package `supply_demand/`: `smc_adapter.py` (ONLY module here allowed to
import `smartmoneyconcepts`; reuses `market_structure.smc_adapter.candles_to_dataframe`),
`native_zones.py` (no smc import), `analyzer.py` (fail-closed batch entry points),
`models.py` (`ZoneResult`, `ZoneQueryResult`).

- **Order Blocks / FVG** (`order_blocks_for()`, `fair_value_gaps_for()`): bullish →
  `ZoneRole.DEMAND`, bearish → `ZoneRole.SUPPLY`. `MitigatedIndex == 0` verified from
  `smc` 0.0.27's own source to be an unambiguous "not mitigated" sentinel (never a real
  position) → `FRESH`; nonzero → `MITIGATED`. A fully invalidated OB is *deleted* from
  the library's internal state and never appears as an output row at all — this adapter
  therefore never reports `INVALIDATED` for these two families (not guessed). `Percentage`
  (OB) exposed only as `raw_strength_metric`, documented as a volume-symmetry ratio, not
  a probability/confidence.
- **Native session zones** (`session_zone()`): wraps `assistant.market_data.session_snapshot()`
  — no new session math. `status` is always `UNKNOWN` here (reason code
  `STATUS_LIFECYCLE_NOT_MODELED_IN_SUPPLY_DEMAND_PHASE`) — sweep/reclaim is a Liquidity-
  phase question.
- **Previous Day High/Low** (`previous_day_high_low()`): project-owned, no smc — the
  last CLOSED D1 bar via `mt5.market_data.get_latest_candles(symbol, "D1", 1)`.
  `TOUCHED` only reflects the *current* tick vs. the level, not the whole day's path
  (reason code names this limitation explicitly).
- **Premium/Equilibrium/Discount** (`dealing_range_zones()`): pure function, takes an
  **explicit** low/high + a caller-named `source` string — never picks a range itself.
  `premium_discount_from_previous_day()` / `premium_discount_from_session()` are the
  only two named convenience sources wired up so far.

Tests: `tests/test_supply_demand.py` — 8 passed (2 real-`smc.fvg()` fixtures for
bullish-fresh/bearish-mitigated, 1 mocked-`smc.ob()` fixture for OB mapping — `smc.ob()`'s
own trigger conditions are too stateful to hand-construct reliably, so its *output* is
mocked to test our mapping, which is the boundary we own; 1 pure premium/discount test;
4 live).

**Live examples (EURUSD, 2026-08-26):** H1 — 9 order blocks (mix of FRESH/MITIGATED),
36 FVGs; M15 — 3 order blocks, 28 FVGs; previous-day H/L 1.16506/1.16790 (`FRESH`);
premium/discount from both previous-day and Asian-session ranges classified current
price as `DISCOUNT`.

### PHASE 4 — LIQUIDITY: BUILT, PAUSED (2026-08-26)

Built and tested (below), then paused by owner request — no further liquidity work
until Order Blocks are resolved. Nothing here changed or broken; simply not being
extended further right now.

New top-level package `liquidity/`: `status.py` (pure sweep/reclaim state machine, no
MT5/smc import — see its module docstring for exact UNSWEPT/SWEPT/RECLAIMED/CONSUMED
semantics, deliberately independent of `strategy_engine.session.setups.entry_2_sweep`'s
strategy-specific strict-penetration contract), `equal_levels.py` (own local-extreme +
tolerance-clustering method, independent of `market_structure`'s smc-swing detection),
`analyzer.py` (`liquidity_result()`, reuses `market_structure.analyze_structure()`,
`supply_demand.session_zone()`, `supply_demand.previous_day_high_low()` rather than
recalculating any of them), `models.py` (`LiquidityLevel`, `LiquidityResult`).

Sources: structural swings (from `StructureResult`), session highs/lows (Asian/London/
New York), PDH/PDL, equal highs/lows (`config/liquidity.yaml`:
`equal_level_tolerance_points: 5`, symbol-tick-size-based, explicit default — no prior
project authority defined one). `SWEPT` is reported only for a live-tick penetration not
yet confirmed by a closed candle; closed-candle history always resolves to `RECLAIMED`
or `CONSUMED`.

Tests: `tests/test_liquidity.py` — 12 passed (7 pure state-machine, 3 pure equal-level
clustering, 2 live).

**Live examples (EURUSD, 2026-08-26):** H1 — 13 levels across all 4 sources; swing high
UNSWEPT, Asian High RECLAIMED, Asian Low CONSUMED, PDH UNSWEPT, PDL CONSUMED, one
EQUAL_HIGHS cluster. M15 — swing high caught mid-sweep as `SWEPT` (live tick trading
through it, not yet closed-candle-confirmed) — a real, not simulated, demonstration of
that status.

### ORDER BLOCK CONTRACT: AG_ORDER_BLOCK_V1 FROZEN AND IMPLEMENTED (2026-08-27)

The owner froze the baseline contract `AG_ORDER_BLOCK_V1` (superseding the prior
"everything stays CANDIDATE forever" placeholder from 2026-08-26). `supply_demand/ob_contract.py`
now implements it fully:

- **PIVOT_OB** (zone = full candle high/low) vs. **SHADOW_OB** (zone = wick tip to body
  edge): split by the origin candle's body-to-range ratio (≥0.5 → PIVOT, <0.5 → SHADOW)
  — an explicit, documented interpretation of the owner's wording, not a frozen number;
  flagged in `ob_contract.py`'s module docstring for confirmation.
- **FLIP_OB** (zone = full candle) is frozen but **never assigned** — its identification
  rule needs a lookback/proximity definition the contract doesn't give (unlike FVG's
  explicit `MAX_CANDLES_TO_FVG=3`). Every candidate resolves to PIVOT_OB or SHADOW_OB.
- **STRUCTURE**: requires a matching-direction BOS or CHoCH confirmed at/after the OB's
  origin — reuses `market_structure`'s real `bos_choch` output via a new
  `market_structure.structural_breaks_for_candles()` (exposes ALL confirmed breaks, not
  just the latest, so a batch of historical OB candidates can each find their own).
  `source=INTERNAL_OR_EXTERNAL` preserved as a placeholder field (`structure_source`) —
  `market_structure/` has one swing-length classifier, no internal/external tiering yet.
- **FVG**: requires a same-direction FVG within `MAX_CANDLES_TO_FVG=3` candles of the OB
  (positional distance, computed from the same fetched candle set as the OB — added
  `validated_order_blocks_for()` fetches OB+FVG candidates together for this reason). No
  literal price overlap required, per the frozen contract.
- **MITIGATION** (`WICK_TOUCH_BOUNDARY`) and **INVALIDATION** (close beyond the zone,
  bullish=below-low / bearish=above-high) scanned forward candle-by-candle; a wick that
  pierces the whole zone but closes back on the original side is `MITIGATED`, not
  `INVALIDATED` — verified live and by a dedicated test.

Lifecycle now real: `CANDIDATE` / `VALID` / `MITIGATED` / `INVALIDATED` / `REJECTED`, all
reachable. Reason codes: `VALID_OB`, `REQUIRED_STRUCTURE_MISSING`, `REQUIRED_FVG_MISSING`,
`FVG_DIRECTION_MISMATCH`, `FVG_TOO_LATE`, `INVALID_OB_GEOMETRY`, `OB_MITIGATED`,
`OB_INVALIDATED`.

**Still explicitly UNSIGNED** (owner instruction — not inferred from the reference
image): `supply_demand.L1_L2_CLASSIFICATION`, `supply_demand.INSIDE_BAR_FLIP_RULE`. See
`supply_demand.ORDER_BLOCK_CONTRACT_GAPS` for the remaining open items (FLIP_OB
identification, the PIVOT/SHADOW split interpretation, structure internal/external
tiering).

Existing generic OB/FVG functionality (`order_blocks_for()`, `fair_value_gaps_for()`) is
unchanged — `validated_order_blocks_for()` is additive.

Tests: `tests/test_ob_contract.py` — 13 passed (valid bullish/bearish PIVOT+FVG, missing
FVG, opposite-direction FVG, FVG too late, missing structure, SHADOW_OB wick-zone
geometry, mitigation by touch, bullish/bearish invalidation, wick-without-invalidation,
contract-gap coverage, 1 live). Full suite: 122 passed.

**Live examples (EURUSD, 2026-08-27):** H1 — 9 candidates, real mix of `VALID`
(2×SHADOW_OB bullish), `MITIGATED` (4), `INVALIDATED` (3, all SHADOW_OB); M15 — 3
candidates, all `MITIGATED` (2×PIVOT_OB, 1×SHADOW_OB). No `FLIP_OB` ever assigned, as
designed.

`supply-demand-analysis` skill updated for `SMC_CANDIDATE_OB` vs. `AG_VALID_ORDER_BLOCK`
terminology and the full lifecycle — see that skill's revised section.

## Strategy-config gaps (found building Phase B, still open)

See `strategies/STRATEGY_LEDGER.md`: `ST_ASIAN_SWEEP_5R_V1`'s `entry_order_type:
MARKET_OR_LIMIT` is ambiguous (blocks `READY_FOR_ORDER_CHECK`) and
`risk_and_money_management` never states an actual risk-per-trade percentage (a
`config/trading.yaml` account-wide default is used instead). Strategy-authorship
decisions, not something to invent while building the Assistant.

## Next owner decision

AG_ORDER_BLOCK_V1 and AG_LIQUIDITY_V1 are both implemented, validated, and now FROZEN
(see `docs/status/PHASE_1_4_FREEZE_STATUS.md`, 2026-08-27). Remaining open items (not blocking, but
unresolved): confirm/replace the PIVOT/SHADOW body-ratio split interpretation; decide
FLIP_OB's identification rule (lookback + proximity to a prior failed zone); L1/L2 and
inside-bar D2S/S2D remain explicitly UNSIGNED, not to be inferred; liquidity's
SWING_HIGH/SWING_LOW scope (latest-only) and its reuse of `equal_level_tolerance_points`
as the cross-source dedup tolerance are documented, non-blocking V1 gaps. Phase 5 — Entry
& Confirmation is now `VERIFIED` / `FROZEN` (`AG_ENTRY_CONFIRMATION_V1`, 2026-08-28; see
`docs/status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md`). Next phase:
`AG_TRADE_MANAGEMENT_V1`'s entry-side dependency on Phase 5 (Phase 6's manual-entry-only
subsystem already ships independently of Phase 5 -- see PHASE 6 above) -- not started
in this pass.
