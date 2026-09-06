# AG Profit Trading — Project Capability Completeness

**Last verified:** 2026-09-06, `main` @ `651ade619c2c2df9a973d45cea37ae6599c2b9eb`
("Reconcile V1.0.3 evidence and pause Telegram development for qualification").
Audit type: `AG_PROJECT_TWO_SECTION_CAPABILITY_COMPLETENESS_AUDIT_V1` —
documentation-only. No strategy, risk, session, execution, or authorization code was
changed to produce this document.

**This document is NON-AUTHORIZING.** It is a capability audit / navigation matrix
derived from the authoritative sources listed below. It classifies and cross-references
evidence; it does not grant, imply, or supersede any strategy, execution, or release
authority. Where this document and an authoritative source disagree, the authoritative
source always wins and this document must be re-verified, not assumed correct:

| Claim type | Authoritative source |
|---|---|
| Strategy authorization (`demo_authorized`, `live_authorized`, registration) | `strategies/registry.yaml`, `strategies/STRATEGY_LEDGER.md` |
| Release state / version identity | `docs/VERSION_HISTORY.md`, `config/releases/*.yaml` release manifests |
| Current rolling operational state | `PROJECT_STATUS.md` |
| Qualification / observation evidence | dated `docs/status/*.md` and campaign/archive artifacts |

This document does not replace any of the above.

---

## 1. Purpose

Answer, from current repository evidence only, what is implemented, verified,
operational, under qualification, ready-but-not-authorized, deliberately disabled, or
genuinely missing — for both the trading-edge/decision logic and the surrounding
operations/execution/platform layer — so that future work is prioritized by evidence
rather than by assumption. This is an audit artifact: it classifies, it does not
authorize anything.

## 2. Completeness methodology

`IMPLEMENTED ≠ VERIFIED ≠ OPERATIONAL ≠ QUALIFYING ≠ QUALIFIED ≠ ENABLED ≠ AUTHORIZED ≠
RELEASED`. These are never used as synonyms in this document. Every capability below is
recorded across five independent dimensions, never averaged into one score:

- **IMPLEMENTATION**: `NOT_STARTED` / `PARTIAL` / `IMPLEMENTED`
- **VERIFICATION**: `UNVERIFIED` / `FOCUSED_VERIFIED` / `INTEGRATION_VERIFIED` /
  `PRODUCTION_DATA_VERIFIED` (real production market/runtime data confirmed access or
  correctness — never implies a broker order or trade execution) / `DEMO_VERIFIED`
  (an actual MT5 Demo-account order round trip confirmed, e.g. order_send→order_close)
  / `LIVE_VERIFIED` (reserved strictly for evidence from a real live trading account —
  searched for and confirmed **none exists** anywhere in this repository as of this
  audit). `DEMO_VERIFIED` is never described as "live validated" or "live-validated"
  in this document, to avoid implying real-money execution evidence.
- **AUTHORITY**: `NOT_APPLICABLE` / `RESEARCH_ONLY` / `PROPOSAL_ONLY` / `DEMO_AUTHORIZED` / `LIVE_AUTHORIZED` / `DISABLED`
- **QUALIFICATION**: `NOT_REQUIRED` / `NOT_STARTED` / `IN_PROGRESS` / `BLOCKED` / `QUALIFIED`
- **CURRENT_USE**: `INACTIVE` / `READY` / `ACTIVE` / `PAUSED` / `DISABLED`

Percentages are never repository-defined truth. Where offered (Section 20-equivalent /
final assessment), they are explicitly labeled `PLANNING ESTIMATE`, with the
calculation shown, and are never a blind average across these five dimensions.

## 3. Section A definition — Trading Edge & Decision Core

Capabilities that directly determine: opportunity existence, direction, setup
qualification, entry, invalidation/stop, target, risk, position sizing,
trade-management semantics, strategy performance/expectancy, and promotion evidence.
Categories: Market Data, Session Logic, Market Structure, Liquidity, Supply/Demand,
SMC Context, Strategy Rules, Entry Confirmation, Risk/Position Sizing, Decision
Classification, Trade Proposal, Trade Ticket semantics, Trade Management rules,
Backtest/Replay, Shadow Validation, Observation Campaigns, Performance Measurement,
Strategy Research.

## 4. Section B definition — Operations, Execution & Platform

Capabilities that deliver, protect, persist, authorize, execute, monitor, schedule,
recover, or communicate a Section A decision, without themselves owning trading edge.
Categories: Telegram, MT5 execution infra, future Bybit execution, authorization,
execution journals, reconciliation, persistence infra, CLI, scheduler, notifications,
report transport, monitoring, release management, documentation, security,
credentials, deployment, recovery, operational controls.

## 5. Architecture boundary rule (binding)

**Section B must not silently change Section A.** Telegram may approve/reject a
proposal but must not change strategy direction/entry/SL/TP/risk. A scheduler may
trigger evaluation but must not change session semantics. MT5 may normalize
broker-required execution values per already-authorized rules but must not invent a
new setup. Reporting may render a decision but must not reclassify the strategy.
Reconciliation may recover execution state but must not alter historical strategy
evidence. Any future change must be explicitly classified `TRADING_EDGE_CHANGE` or
`PLATFORM_OPERATION_CHANGE` before being made.

Verified current instances of this boundary holding:
- FX: `execution.executor.execute()` rejects any object that is not
  `execution.models.TradeCommand` before reading any field
  (`src/execution/executor.py`) — a proposal/report render can never mutate strategy
  output.
- BTC: `BTCSweepResearchProposal` is tagged `execution_domain=CRYPTO_RESEARCH` /
  `execution_authority=DISABLED` and is statically+behaviorally verified
  (`tests/test_btc_proposal_execution_boundary.py`) never to reach
  `execution.executor` / `mt5.management_gateway`.
- Telegram (feature branch, not on `main`): AST-based import scan confirms no module
  under `src/authorization/` or `src/notifications/` imports `mt5`,
  `assistant.commands`, or `execution.executor`; the only wired execution handler,
  `phase_d1_broker_disabled_handler`, unconditionally returns `success=False`.

---

## 6. Section A capability matrix

| CAPABILITY | SECTION | PROFIT_ROLE | IMPLEMENTATION | VERIFICATION | AUTHORITY | QUALIFICATION | CURRENT_USE | EVIDENCE | GAP | NEXT_GATE |
|---|---|---|---|---|---|---|---|---|---|---|
| FX market data (MT5 EURUSD/GBPUSD M15) | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md` — 24 well-formed closed M15 bars/symbol, exchange-verified metadata | none material | maintain |
| FX session definitions (Asian/London/NY) | A | DIRECT_EDGE | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `config/canonical_sessions.yaml`, `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` session_pairs | ASIAN_LONDON trade window (07:00-11:00) intentionally deviates from canonical `london_am` by 1h — documented, not a defect | none |
| FX session/reference snapshots (frozen Asian/London box) | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `immutable_asian_snapshots: true` (release manifest), pipeline.py | none | maintain |
| `ST_ASIAN_SWEEP_5R_V1` strategy engine (evaluation) | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED (real runtime decisions) | PROPOSAL_ONLY | IN_PROGRESS (Series 002) | ACTIVE | `strategy_engine/session/setups.py`, registry `active=true` | none in engine logic itself | Series 002 continuation |
| FX decision classification | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `src/post_asian_pilot/decision.py`: `STATUS_WATCH/READY/NO_TRADE/DATA_ERROR/EXPIRED/BLOCKED` (matches expected 6-state contract exactly) | none | maintain |
| FX READY proposal construction | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED (real GBPUSD SHORT proposal, Series 002 Day 001, 2026-09-04) | PROPOSAL_ONLY | IN_PROGRESS | ACTIVE | `post_asian_pilot/proposal.py`, `execution/intent_builder.py` | none in construction logic | maintain |
| FX entry semantics | A | DIRECT_EDGE | IMPLEMENTED | FOCUSED_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `entry_level: Sweep_Candle_Body_Close`; `entry_order_type: MARKET` resolved v1.1.1 (2026-08-31) | none | maintain |
| FX stop/invalidation semantics | A | RISK_CONTROL | IMPLEMENTED | FOCUSED_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `stop_loss_mode: PERCENT_OF_SESSION_RANGE`, `stop_loss_range_pct: 0.25` | none | maintain |
| FX target semantics | A | DIRECT_EDGE | IMPLEMENTED | FOCUSED_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `position_split_and_targets` block, `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` | not independently re-audited this pass | maintain |
| FX risk policy (pilot-level) | A | RISK_CONTROL | IMPLEMENTED | FOCUSED_VERIFIED | PROPOSAL_ONLY | NOT_REQUIRED | ACTIVE | pilot configs: `risk_per_trade_pct: 0.5` (both cycles) | strategy YAML itself declares no numeric `risk_per_trade_pct` | CORE-D2 owner decision |
| FX strategy-level numeric risk contract | A | RISK_CONTROL | NOT_STARTED (numeric value) | UNVERIFIED | NOT_APPLICABLE | BLOCKED | INACTIVE | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` `risk_mode: FIXED_PERCENT_OR_CONTRACT` with no percentage; verified no code fallback exists (`execution/risk.py::size_position()` requires the value as a mandatory param) | UNSPECIFIED — real, current, unresolved | owner decision (CORE-D2) before any Demo authorization; does NOT block proposal-only qualification |
| FX position sizing | A | RISK_CONTROL | IMPLEMENTED | FOCUSED_VERIFIED | PROPOSAL_ONLY | NOT_REQUIRED | ACTIVE | `execution/risk.py::size_position()` | depends on caller supplying `risk_per_trade_pct` (pilot value used as of 2026-09-06) | maintain |
| FX ticket semantics (Entry Ticket) | A | DIRECT_EDGE / CONVENIENCE-adjacent | IMPLEMENTED | FOCUSED_VERIFIED (14 tests) | PROPOSAL_ONLY | NOT_REQUIRED | ACTIVE | `report.render_entry_ticket()`, wired into `run_post_asian_pilot.py` 2026-09-04 | none | maintain |
| FX Trade Management rules (manual-entry) | A | RISK_CONTROL | IMPLEMENTED | FOCUSED_VERIFIED | DEMO_AUTHORIZED (independently gated) | NOT_REQUIRED | READY | `trade_management/`, `config/trading.yaml` `trade_management.mode: DRY_RUN` | live validation deferred | owner Demo trial |
| Backtest/replay (historical) | A | EDGE_VALIDATION | PARTIAL | UNVERIFIED (live) | NOT_APPLICABLE | NOT_STARTED | INACTIVE | `HISTORICAL REPLAY LIVE-MT5 ACCESS BLOCKED` (PROJECT_STATUS.md); Large-SMC replay infra exists separately | live MT5 historical access blocked | not prioritized (see Section 18) |
| FX Shadow Validation (evidence collection) | A | EDGE_VALIDATION | IMPLEMENTED | PRODUCTION_DATA_VERIFIED (real runtime data) | NOT_APPLICABLE | IN_PROGRESS | ACTIVE | Series `AG_V1_0_3_FX_SHADOW_SERIES_002`: valid=0/20, invalid=1, excluded=0, pending=0 | 19 more valid days needed | next eligible day 2026-09-07 |
| FX Outcome/performance evidence | A | EDGE_VALIDATION | NOT_STARTED | NOT_STARTED | NOT_APPLICABLE | NOT_STARTED | INACTIVE | no broker fills exist yet (proposal-only) | no trade outcomes to measure | after Demo authorization (CORE-D2/D5) |
| FX qualification status | A | EDGE_VALIDATION | N/A | N/A | N/A | IN_PROGRESS | ACTIVE | 0/20 valid days | 19 more valid days | continue Series 002 |
| BTC market data (Bybit adapter) | A | DIRECT_EDGE (data correctness) | IMPLEMENTED | PRODUCTION_DATA_VERIFIED (HTTP 200/retCode 0, 2026-09-05) | N/A (read-only) | NOT_REQUIRED | READY | `src/execution_runtime/bybit_linear_perp_feed.py`, 111 BTC tests | none material | maintain |
| BTC production data validation | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | READY | complete closed 24×H1 + 288×M5 audit (`scripts/run_btc_daily_report.py`) | none | maintain |
| BTC data provenance | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | READY | Bybit V5 official docs verified; public/unauthenticated only | none | maintain |
| BTC strategy (`ST_LIQUIDITY_SWEEP_RETEST_V1`, CRYPTO_PERP profile) | A | DIRECT_EDGE | IMPLEMENTED | UNIT_TESTED + PRODUCTION_DATA_VERIFIED | RESEARCH_ONLY | NOT_STARTED (observation) | READY | `src/strategy_engine/sweep_retest/`, registry v2.0.0 `ACTIVE_INCUBATION`; campaign start owner-authorized 2026-09-06 | no counted observation evidence yet | first eligible in-window observation |
| BTC daily classification | A | DIRECT_EDGE | IMPLEMENTED | PRODUCTION_DATA_VERIFIED (diagnostic run 2026-09-05, WATCH) | RESEARCH_ONLY | NOT_REQUIRED | READY | `src/btc_sweep_research/daily_report.py`, reuses READY/WATCH/NO_TRADE/DATA_ERROR | none | maintain |
| BTC research proposal | A | DIRECT_EDGE | IMPLEMENTED | FOCUSED_VERIFIED | RESEARCH_ONLY | NOT_REQUIRED | READY | `BTCSweepResearchProposal`, `execution_authority=DISABLED` | none | maintain |
| BTC evidence ledger | A | EDGE_VALIDATION | IMPLEMENTED | FOCUSED_VERIFIED | N/A | NOT_STARTED | READY | `journal/btc_sweep_research/occurrences.json` | 0 observations recorded | first eligible in-window observation |
| BTC daily report semantics | A | DIRECT_EDGE / supports EDGE_VALIDATION | IMPLEMENTED | PRODUCTION_DATA_VERIFIED (diagnostic, disposable/non-counting) | RESEARCH_ONLY | NOT_REQUIRED | READY | labeled "NOT A BROKER TICKET" | first in-window scheduled archive still pending | scheduler run in-window |
| BTC observation contract | A | EDGE_VALIDATION | IMPLEMENTED | FOCUSED_VERIFIED | NOT_APPLICABLE | NOT_REQUIRED | READY | `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md` — UTC half-open day, 00:05-00:15 UTC report target, no strategy timing conflict found | none | maintain |
| BTC scheduler readiness | B (supports A) | OPERATIONAL_SUPPORT | IMPLEMENTED (installer) | UNVERIFIED (not confirmed installed/running) | N/A | NOT_STARTED | READY | `scripts/install_btc_daily_task.ps1` (06:37 MMT) | installed ≠ confirmed running | confirm scheduled task active |
| BTC observation evidence (30 valid observations) | A | EDGE_VALIDATION | IMPLEMENTED (tooling) | N/A (0 collected) | OWNER_AUTHORIZED_READ_ONLY | NOT_STARTED | READY | release manifest: `observation_campaign_authorized: true`, `observation_days_completed: 0`, `observation_campaign_started: false` | 0/30; no retroactive counting | first eligible in-window observation |
| BTC performance evidence | A | EDGE_VALIDATION | NOT_STARTED | NOT_STARTED | NOT_APPLICABLE | NOT_STARTED | INACTIVE | no observations exist | none exist | after campaign starts |
| BTC qualification status | A | EDGE_VALIDATION | N/A | N/A | OWNER_AUTHORIZED_READ_ONLY | NOT_STARTED | READY | 0/30; authorization recorded 2026-09-06 | no counted observations yet | first eligible in-window observation |
| Large-SMC research architecture (HTF context, E1/E2/E3+M1/M2/M3) | A | EDGE_VALIDATION (research) | IMPLEMENTED | FOCUSED_VERIFIED | RESEARCH_ONLY | BLOCKED (C10) | READY (research) | `src/large_smc_research/`, v1.0.6 | C10 broker-stop unsigned | C10 contract-freeze milestone |
| Large-SMC C10 invalidation/stop contract | A | RISK_CONTROL | PARTIAL (concept selected, not implemented) | UNVERIFIED | NOT_APPLICABLE | BLOCKED | INACTIVE | owner selected `AG_NATIVE_INVALIDATION` concept 2026-09-03; `implementation_status: PENDING` | buffer/spread/min-distance policy still UNSIGNED | `ST_LARGE_SMC_V1_C10_AG_NATIVE_CONTRACT_FREEZE` milestone (not started) |
| Large-SMC proposal/Demo/live authority | A | N/A | NOT_STARTED | N/A | NONE | NOT_STARTED | INACTIVE | `proposal_generation_authorized: false` | engine fails closed to BLOCKED | C10 resolution, then evidence review |

## 7. Section B capability matrix

| CAPABILITY | SECTION | PROFIT_ROLE | IMPLEMENTATION | VERIFICATION | AUTHORITY | QUALIFICATION | CURRENT_USE | EVIDENCE | GAP | NEXT_GATE |
|---|---|---|---|---|---|---|---|---|---|---|
| Persistent decision state | B | OPERATIONAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `journal/post_asian_pilot/`, `journal/post_london_newyork_pilot/` | none | maintain |
| Proposal storage | B | OPERATIONAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `post_asian_pilot/store.py`, `find_decision()` (2026-09-04 fix) | none currently open | maintain |
| Execution journals | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED (2026-08-28, 2026-08-30 hardening) | N/A | NOT_REQUIRED | READY (dormant, no live sends yet by any authorized strategy) | `execution/journal.py`, O_EXCL atomic claim, deterministic hash filenames | none | maintain |
| Immutable archives | B | OPERATIONAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `post_asian_pilot/report_archive.py` — append-only, original never overwritten (verified with real evidence 2026-09-04) | none | maintain |
| Numbered corrections | B | OPERATIONAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED (real correction file: `2026-09-03.correction-001.json`) | N/A | NOT_REQUIRED | ACTIVE | same module | none | maintain |
| Restart/recovery | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `ready_restart_recovery: true` (release manifest); `execution/journal.py` atomic claim survives crash | none material | maintain |
| Session reports | B | OPERATIONAL_SUPPORT | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `report.render_pilot_end_report()` | key-casing defect found+fixed 2026-09-04 (`AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md`) | closed |
| Combined daily reports | B | OPERATIONAL_SUPPORT | IMPLEMENTED | FOCUSED_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `post_asian_pilot/daily_fx_report.py`, `AG_FX_DAILY_REPORT_V1` | none | maintain |
| Monitoring counters | B | OPERATIONAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `monitoring_counters: true` (release manifest) | none | maintain |
| CLI (FX/BTC operational) | B | OPERATIONAL_SUPPORT | IMPLEMENTED | PRODUCTION_DATA_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `scripts/run_post_asian_pilot.py`, `scripts/run_btc_daily_report.py` | none | maintain |
| Scheduler (BTC) | B | OPERATIONAL_SUPPORT | IMPLEMENTED (installer only) | UNVERIFIED (install state) | N/A | NOT_STARTED | READY | `scripts/install_btc_daily_task.ps1` | installer exists ≠ installed/running — not conflated here | confirm installation |
| MT5 command model | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED (2026-08-28) | N/A | NOT_REQUIRED | READY | `execution/models.py` (`TradeCommand`, `ExecutionSource`) | none | maintain |
| MT5 execution executor | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED (ticket 1879685149) | Application infra, explicit-command-gated | NOT_REQUIRED | READY, disabled absent a fresh explicit command | `execution/executor.py` | rejects non-TradeCommand objects (hardened 2026-09-02) | maintain |
| MT5 gateway | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED | N/A | NOT_REQUIRED | READY | `execution/mt5_gateway.py` | none | maintain |
| MT5 risk/normalization | B | RISK_CONTROL (execution-safety framing) | IMPLEMENTED | FOCUSED_VERIFIED | N/A | NOT_REQUIRED | READY | `execution/validator.py::validate_account_and_config()` — validates but does not supply a risk value | requires caller-supplied `risk_per_trade_pct` | CORE-D2 |
| order_check | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED | Gated (`allow_order_check`) | NOT_REQUIRED | READY, `allow_order_check: false` by default | `config/trading.yaml`, `execution/mt5_gateway.py` | none | maintain |
| order_send | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED (DEMO round trip 2026-08-28) | DEMO enabled generically, gated per-call by `user_confirmed=True`; not usable by `ST_ASIAN_SWEEP_5R_V1` (not `demo_authorized`) | NOT_REQUIRED | READY (generic), BLOCKED for the pilot strategy | `config/trading.yaml` `allow_order_send: false` default, per-call override requires explicit command | strategy-level gate (registry) independent of infra readiness | CORE-D2 owner decision |
| MT5 journal | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `execution/journal.py` | none | maintain |
| MT5 duplicate protection | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED (2026-08-30 hardening) | N/A | NOT_REQUIRED | ACTIVE | atomic O_EXCL claim, cross-process/thread safe | none on the core execution path (distinct from the Telegram-side store race, see §15) | maintain |
| MT5 reconciliation | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED (2026-08-28 milestone) | N/A | NOT_REQUIRED | READY | referenced in PROJECT_STATUS execution-authority restructure section | not independently re-audited this pass | dedicated review (CORE-D4 note) |
| MT5 Demo environment guards | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | DEMO_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `_account_authorized_for_send` requires demo unless `allow_live_trading` true | none | maintain |
| MT5 live guards | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | DISABLED | NOT_REQUIRED | DISABLED | `config/trading.yaml` `account.allow_live_trading: false` | none — deliberate | owner decision to ever enable |
| MT5 strategy integration (`ST_ASIAN_SWEEP_5R_V1`→MT5) | B | DIRECT bridge to A | PARTIAL (generic bridge implemented; strategy-specific wiring absent) | DEMO_VERIFIED generically (2026-08-28, ticket 1880212783), NOT for this strategy's own pilot-cycle proposals | BLOCKED (`demo_authorized: false`) | NOT_REQUIRED (proposal-only qualification does not need this) | BLOCKED | PROJECT_STATUS.md "Corrected architecture description" | strategy registry gate, not a missing code capability | CORE-D2 |
| MT5 current execution authority | B | N/A | N/A | N/A | Demo: generic infra enabled, gated per-call; strategy-specific: BLOCKED. Live: DISABLED | NOT_REQUIRED | mixed (see above) | registry + `config/trading.yaml` | none new | CORE-D2/D5 |
| Telegram authorization core (Phase A) | B | OPERATIONAL_SUPPORT | IMPLEMENTED (feature branch only) | FOCUSED_VERIFIED (35 tests, HTTP mocked) | N/A | NOT_REQUIRED | PAUSED | `.claude/worktrees/telegram-execution-gateway-v1/src/authorization/{store,models,config,integrity}.py` | not on `main` | owner reactivation |
| Telegram approval store (Phase B) | B | SAFETY_CRITICAL_SUPPORT | IMPLEMENTED (feature branch only) | FOCUSED_VERIFIED | N/A | NOT_REQUIRED | PAUSED | O_EXCL atomic one-time claim/reject | Windows `JsonKeyValueStore._save_all` concurrency race under heavy parallel load (see §15) | fix before resumption |
| Telegram transport/gateway (Phase C) | B | CONVENIENCE / OPERATIONAL_SUPPORT | IMPLEMENTED (feature branch only) | FOCUSED_VERIFIED (24+17+12 tests, all HTTP mocked) | N/A | NOT_REQUIRED | PAUSED | `src/notifications/{telegram_client,trade_ticket_formatter}.py`, `src/authorization/telegram_gateway.py` | never tested against real Telegram network | owner reactivation |
| Telegram real proposal integration (Phase D1) | B | OPERATIONAL_SUPPORT | IMPLEMENTED (feature branch only) | FOCUSED_VERIFIED (8 tests) | N/A | NOT_REQUIRED | PAUSED | `src/authorization/proposal_source.py` reads real `post_asian_pilot` journals read-only | not merged to `main` | owner reactivation |
| Telegram strategy-authority recheck | B | RISK_CONTROL (gate correctness) | IMPLEMENTED (feature branch only) | FOCUSED_VERIFIED (real Execute-Demo click against real registry → `BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED`) | N/A | NOT_REQUIRED | PAUSED | `src/authorization/strategy_authority.py` reads `strategies/registry.yaml` live on every call | none | maintain when resumed |
| Telegram→MT5 execution wiring | B | N/A | NOT_STARTED | N/A | NOT_APPLICABLE (broker unreachable by design) | NOT_REQUIRED | not present anywhere in the branch | AST import scan: zero references to `mt5`/`execution.executor`/`assistant.commands` | genuinely not built | future Phase D2+ |
| CryptoTradeCommand / exchange-specific command model | B | N/A | NOT_STARTED | N/A | NOT_APPLICABLE | NOT_REQUIRED | INACTIVE | not found in `src/execution/` | genuinely missing | future, if crypto execution ever authorized |
| Bybit Demo execution router | B | N/A | NOT_STARTED (crypto_router.py exists but for a different purpose — venue *routing*, not order submission) | N/A | NOT_APPLICABLE | NOT_REQUIRED | INACTIVE | `src/execution/crypto_router.py` defines `VenueDescriptor`/`UnroutableExecutionTarget` only, no order call | genuinely missing | future |
| Crypto quantity/metadata normalization | B | N/A | PARTIAL (metadata classes exist: `crypto_metadata.py`, `crypto_client_order_id.py`, `crypto_snapshot.py`) | UNVERIFIED for execution use (tests exist for modules per an out-of-band commit, not part of this baseline) | NOT_APPLICABLE | NOT_REQUIRED | INACTIVE | files present under `src/execution/crypto_*.py` | scaffolding only, no live order path | future |
| `CryptoExecutionAdapter` | B | N/A | NOT_IMPLEMENTED (explicit) | N/A | DISABLED, fail-closed | NOT_REQUIRED | DISABLED | `src/execution/adapter.py:138-150`: `class CryptoExecutionAdapter(ExecutionAdapter)` returns `AdapterSubmitResult(status="NOT_IMPLEMENTED", reason_code="CRYPTO_EXECUTION_NOT_IMPLEMENTED")` for every call | deliberate, matches expectation exactly | future, requires separate authorization |
| Release management (manifests) | B | OPERATIONAL_SUPPORT | IMPLEMENTED | INTEGRATION_VERIFIED | N/A | NOT_REQUIRED | ACTIVE | `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`, `status: RELEASE_CANDIDATE` | not yet `RELEASED` | owner RELEASED decision after qualification gates |
| Documentation / version history | B | OPERATIONAL_SUPPORT | IMPLEMENTED | N/A | N/A | NOT_REQUIRED | ACTIVE | `docs/VERSION_HISTORY.md`, `PROJECT_STATUS.md`, `docs/README.md` | none | maintain |
| Security / credentials | B | SAFETY_CRITICAL_SUPPORT | PARTIAL | Owner-confirmed, not independently re-verified via authenticated call | N/A | IN_PROGRESS | mostly resolved | `credential_rotation_owner_confirmation` block: rotation `OWNER_CONFIRMED_COMPLETE`, withdrawal `OWNER_CONFIRMED_RESTRICTED` | `ip_restriction_status: UNRESOLVED`, `minimum_permission_status: UNRESOLVED` | owner/independent verification |
| Environment separation / deployment readiness | B | OPERATIONAL_SUPPORT | PARTIAL | UNVERIFIED (no confirmed installed scheduled task; V1.0.2 remains the config-loaded default release, not V1.0.3) | N/A | NOT_STARTED | mixed | `pilot_config.py` default still points at V1.0.2 release manifest despite V1.0.3 label remediation on output | config existence ≠ deployment validated (explicit finding) | reconcile default release_path if/when V1.0.3 is RELEASED |

---

## 8. FX current state

Series: `AG_V1_0_3_FX_SHADOW_SERIES_002` (Series 001 — Day 001 `EXCLUDED_DAY`, Day 002
`PENDING_RECONCILIATION` — left unresolved and superseded, not retroactively fixed).

```
valid_days      = 0/20
invalid_days    = 1   (Day 001, 2026-09-04: reference-session key-casing defect found
                        and fixed; not retroactively counted)
excluded_days   = 0
pending_days    = 0
baseline        = source HEAD 3b2eeed (validation_source_baseline)
next_eligible   = Monday 2026-09-07 (2026-09-05/06 are weekend, and 2026-09-04 is
                   already Day 001's trading date)
series_restarted        = NO
historical_evidence_rewritten = NO
```

Decision contract, verified against `src/post_asian_pilot/decision.py`:
`STATUS_WATCH`, `STATUS_READY`, `STATUS_NO_TRADE`, `STATUS_DATA_ERROR`,
`STATUS_EXPIRED`, `STATUS_BLOCKED` — exactly matches the expected six-state contract;
no discrepancy found. Both symbols (EURUSD, GBPUSD) × both cycles (ASIAN_LONDON,
LONDON_NEWYORK) route through the same deterministic decision function
(`src/post_asian_pilot/decision.py`), so decision determinism holds structurally
across the full symbol×cycle matrix; live evidence exists for at least one concrete
combination per cycle (GBPUSD ASIAN_LONDON READY, 2026-09-04).

Risk completeness: pilot risk = 0.5% (`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`
and `AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml`, identical), account fallback = 1.0%
(`config/trading.yaml`), strategy-level numeric risk = **UNSPECIFIED**
(`strategies/ST_ASIAN_SWEEP_5R_V1.yaml` only declares `risk_mode:
FIXED_PERCENT_OR_CONTRACT`). Verified from code, not assumed: no execution-path
function performs an automatic fallback from an unset strategy value to the account
default — `execution/risk.py::size_position()` and
`execution/intent_builder.py::build_intent()` both require `risk_per_trade_pct` as a
mandatory parameter. The pilot-config value (0.5%) is what actually reaches the FX
proposal path. This absence is a real, unresolved CORE-D2 gap but does **not** block
proposal-only shadow qualification — it blocks future Demo/live authorization.

## 9. BTC current state

```
campaign            = AG_BTC_30_DAY_OBSERVATION (not formally named/started)
target              = 30 valid daily production-market observations
valid               = 0
invalid             = 0
excluded            = 0
pending             = 0
authorized          = NOT YET GRANTED
started             = false
market_data         = production market-data connectivity confirmed (Bybit, HTTP 200/retCode 0,
                      2026-09-05) — validates data access only, not trade execution or profitability
daily_decision_runtime = ready (scripts/run_btc_daily_report.py, scheduler installer added,
                          installed/running state not confirmed)
```

BTC daily CLI being ready is explicitly **not** the same fact as campaign
authorization — the release manifest's own `release_qualification_gates.btc` block
separately tracks `bybit_adapter_implemented: true`,
`btc_production_daily_decision_operational: true`, and
`observation_campaign_authorized: true` and `observation_campaign_started: false` as
independent booleans. The owner authorized the read-only campaign on 2026-09-06, but
authorization did not run a counted observation or count Day 1.

## 10. Large-SMC current state

```
research_version     = v1.0.6 (RESEARCH_DRAFT)
registry status       = registered=true, active=false, research=true,
                        demo_authorized=false, live_authorized=false
evidence_state        = C01/C11/C12/C16/C18 resolved; C14 PARTIALLY_RESOLVED
                        (setup-family identity reused, candidate-occurrence identity
                        implemented but not wired into the live shared store);
                        pending-entry expiry RESOLVED_BY_REUSE (v1.0.6)
blocking_contract      = C10 (broker stop-loss / invalidation distance) — owner selected
                        the AG_NATIVE_INVALIDATION conceptual model (2026-09-03) but
                        implementation_status=PENDING, contract_freeze_status=PENDING,
                        engine_runtime_status=UNSIGNED_BLOCKED (fails closed for any
                        candidate needing it)
next_gate             = ST_LARGE_SMC_V1_C10_AG_NATIVE_CONTRACT_FREEZE milestone (not
                        started as of this audit)
```

Large-SMC is not merged into, and does not borrow authority from, the operational FX
strategy (`ST_ASIAN_SWEEP_5R_V1`) — confirmed independent in `strategies/registry.yaml`
and `strategies/STRATEGY_LEDGER.md`. It is correctly classified `RESEARCH_DRAFT` /
`RESEARCH_ONLY` in both, matching this audit's expected classification exactly (no
discrepancy found).

## 11. MT5 state

MT5 Demo infrastructure: **IMPLEMENTED**. Prior Demo evidence: **PRESENT**
(order_send→order_close round trip, ticket `1879685149`, 2026-08-28; a second,
strategy-agnostic bridge round trip, ticket `1880212783`, same date). Live trading:
**DISABLED** (`config/trading.yaml` `account.allow_live_trading: false`, `mode:
ANALYSIS` by default, `allow_order_check: false`, `allow_order_send: false`).

`ST_ASIAN_SWEEP_5R_V1` → MT5: **BLOCKED / NOT AUTHORIZED** — but the precise reason
matters and must not be flattened to "execution blocked": the generic execution
subsystem (command model, executor, gateway, journal, duplicate protection) is fully
implemented and DEMO_VERIFIED (a real MT5 Demo-account order round trip, not real-money
execution evidence); the block is a **registry-level strategy authorization
gate** (`demo_authorized: false`), independent of and not caused by any missing
execution infrastructure. No `ST_ASIAN_SWEEP_5R_V1` pilot-cycle-origin proposal has
ever been observed to reach the executor — the one demo-verified bridge send used a
proposal from the assistant's own ad hoc analysis path, not a pilot journal entry.

## 12. Telegram state

Implemented phases: A, B, C, D1 — all present and committed, isolated to
`feature/telegram-demo-execution-gateway-v1` @ `740512b7b2e2e45770e150a4497056c511cc4168`,
readable read-only via the existing worktree at
`.claude/worktrees/telegram-execution-gateway-v1`. `main` has zero Telegram files
(`src/authorization/`, `src/notifications/` do not exist there) — confirmed by the
branch point (`63938cc`) and by `PROJECT_STATUS.md`'s own reconciliation.

- Real proposal lookup: **implemented** (`authorization/proposal_source.py`, Phase D1).
- Strategy authority recheck: **implemented** (`authorization/strategy_authority.py`,
  reads `strategies/registry.yaml` live on every Execute-Demo click).
- Broker reachability: **NO** — AST-based import scan confirms zero references to
  `mt5`, `assistant.commands`, `execution.executor`, or any Bybit/Binance order
  module anywhere in the branch's `src/authorization/`, `src/notifications/`.
- Telegram→MT5: **NOT WIRED**. Telegram→Bybit: **NOT WIRED** (never attempted).
- Test evidence: 117 focused tests passing (35+24+12+17+8+8, all Telegram HTTP
  mocked); this evidence was not rerun by this audit since the committed baseline is
  unchanged and no code changed — consistent with the "do not rerun tests unnecessarily"
  instruction.
- Development state: **PAUSED** by owner directive, reason = core-project (V1.0.3)
  qualification prioritized, resume_condition = explicit owner authorization after the
  V1.0.3 release-qualification decision.

## 13. Execution-authority matrix

| Strategy / component | proposal | demo | live |
|---|---|---|---|
| `ST_ASIAN_SWEEP_5R_V1` | PROPOSAL_ONLY (active) | BLOCKED (`demo_authorized: false`) | BLOCKED (`live_authorized: false`) |
| `SESSION_TRADE_V1` (separate strategy, separate repository engine — not part of this repository's core FX pipeline) | N/A here | `ASIAN_LONDON` cycle only: `demo_authorized: true`; `LONDON_NEWYORK`: `false` (`strategies/session_trade/contract.yaml`) | BLOCKED (`live_authorized: false`) |
| `ST_LIQUIDITY_SWEEP_RETEST_V1` | research=RESEARCH_ONLY (BTC profile active), Forex profile has no operating pilot yet | BLOCKED (`demo_authorized: false`) | BLOCKED (`live_authorized: false`) |
| `ST_LARGE_SMC_V1` | research=RESEARCH_ONLY (proposal generation itself `proposal_generation_authorized: false`) | NONE | NONE |
| MT5 infrastructure | implemented=YES | demo_verified=YES (2026-08-28, generic path); strategy_authority=N/A (infra doesn't self-authorize any strategy) | N/A |
| Telegram | proposal_display=IMPLEMENTED (feature branch only, not on `main`) | approval=IMPLEMENTED (feature branch only; broker execution handler unconditionally rejects) | broker_execution=NOT WIRED |
| Bybit | market_data=PRODUCTION_DATA_VERIFIED | research=IMPLEMENTED (RESEARCH_ONLY) | order_execution=NOT_IMPLEMENTED (`CryptoExecutionAdapter`, explicit fail-closed) |

Authority is never inferred from implementation anywhere in this matrix — every
BLOCKED/DISABLED/NOT_IMPLEMENTED value above is read directly from
`strategies/registry.yaml`, `config/trading.yaml`, or the named source module.

**No-authority-borrowing principle (binding):** strategy authorization and
execution-channel authorization are independent gates, and authority is never
inherited across strategies. `SESSION_TRADE_V1` being `demo_authorized: true` for its
`ASIAN_LONDON` cycle does not grant, share, or imply any execution authority for
`ST_ASIAN_SWEEP_5R_V1` (the active V1.0.3 FX pilot strategy), `ST_LIQUIDITY_SWEEP_RETEST_V1`,
`ST_LARGE_SMC_V1`, or any other strategy — they are independently registered,
independently gated, and run on different engines. Each strategy row in this matrix
must be read on its own; a value in one row never modifies another row.

## 14. Qualification/evidence state

**FX**: `series=AG_V1_0_3_FX_SHADOW_SERIES_002 / baseline=3b2eeed / target=20 /
valid=0 / invalid=1 / excluded=0 / pending=0 / latest=Day 002 checked 2026-09-04,
re-checked 2026-09-05 (BASELINE_VERIFIED_AWAITING_NEXT_ELIGIBLE_DAY) /
next_gate=2026-09-07`.

**BTC**: `campaign=NOT_STARTED / target=30 / valid=0 / invalid=0 / excluded=0 /
pending=0 / authorized=NOT_YET_GRANTED / started=false / next_gate=owner
authorization to start the 30-day observation campaign`.

**Large-SMC**: `research_version=v1.0.6 / evidence_state=C10 sole open contract
blocker, all other pipeline contracts (C01/C11/C12/C14(partial)/C16/C18) resolved /
blocking_contract=C10 (AG_NATIVE_INVALIDATION concept selected, implementation
PENDING) / next_gate=ST_LARGE_SMC_V1_C10_AG_NATIVE_CONTRACT_FREEZE milestone`.

## 15. Known gaps

- **FX strategy-level numeric risk contract** (`risk_per_trade_pct`) is genuinely
  UNSPECIFIED in `strategies/ST_ASIAN_SWEEP_5R_V1.yaml`, with no automatic code
  fallback to the account default. Does not block current proposal-only shadow
  qualification; blocks future Demo/live authorization (CORE-D2).
- **Windows Telegram approval-store concurrency race**: `JsonKeyValueStore._save_all`'s
  `os.replace(tmp, path)` can raise `PermissionError: [WinError 5]` under heavy
  parallel `ThreadPoolExecutor` load on Windows (observed in the combined test suite,
  clean on isolated re-runs). Scope: Telegram approval-store persistence layer only —
  the atomic O_EXCL claim/reject *decision* logic is unaffected. Reproduction status:
  intermittent, only under large combined-suite parallel load. FX qualification
  impact: **NONE** (FX never touches this store). BTC qualification impact: **NONE**
  (same reason). Future execution-authorization impact: **BLOCKING** — must be fixed
  before Telegram/MT5/Bybit execution work resumes. This audit did not fix it (out of
  scope, not affecting active qualification integrity).

  `TELEGRAM_EXECUTION_AUTHORIZATION BLOCKED_BY WINDOWS_APPROVAL_STORE_CONCURRENCY_FIX`.
  This defect currently has **NO qualification impact** (confirmed above and in the
  prior audit) but **IS a hard blocker** for any future execution authorization — this
  is not weakened or hidden here. Required future sequence before Telegram-triggered
  broker execution can be authorized, in order: (1) fix the
  `JsonKeyValueStore._save_all` concurrency race; (2) targeted concurrency tests;
  (3) restart/replay tests; (4) idempotency tests; (5) broker-unreachable safety
  re-validation; (6) authorization review; (7) controlled Demo execution. No step may
  be skipped or reordered.
- **BTC scheduler**: installer exists (`scripts/install_btc_daily_task.ps1`) but
  installed/running state as a live Windows scheduled task is not confirmed.
- **Deployment default drift**: `post_asian_pilot/pilot_config.py`'s
  `DEFAULT_RELEASE_CONFIG_PATH` still points at the V1.0.2 release manifest by
  default even though the FX release-identity remediation (2026-09-04) made active
  output self-label as V1.0.3 — the manifest file itself is not the runtime's loaded
  default. Not a behavioral defect (output is correctly labeled), but a
  config/manifest reconciliation item for whenever V1.0.3 is formally RELEASED.
  Not touched by this audit.
- **ST_LIQUIDITY_SWEEP_RETEST_V1 Forex profile** has no operating pilot (unlike the
  BTC/CRYPTO_PERP profile) — signal engine exists, no pilot cycle runs it.
- **IP-restriction / minimum-permission status** for rotated exchange credentials
  remains `UNRESOLVED` (owner-stated rotation is confirmed; these two sub-items are
  not independently verified via an authenticated call, which no agent task is
  authorized to make).

## 16. Priority classification

- **P0 (qualification/safety blocker):** none currently open that blocks the
  in-progress FX/BTC qualification path itself. The Windows Telegram concurrency race
  is P0-class but scoped to future execution authorization, not current qualification.
- **P1 (trading-edge validation):** continue `AG_V1_0_3_FX_SHADOW_SERIES_002` to
  20 valid days; obtain owner authorization for, then run, the BTC 30-day observation
  campaign.
- **P2 (evidence-backed trading defect):** none currently open — the one real
  evidence-discovered defect this cycle (FX report decision-key casing mismatch) was
  already found and fixed (2026-09-04); repair only new defects discovered by future
  evidence, do not manufacture speculative fixes.
- **P3 (required operational support):** maintain reporting/persistence/scheduler
  integrity (confirm BTC scheduled task installation; keep the immutable-archive and
  correction-record invariants intact).
- **P4 (future execution integration):** CORE-D2 (strategy risk-contract decision),
  CORE-D5 (controlled Demo verification gate), future Bybit Demo execution, future
  Telegram→MT5 resumption — all owner-authorization-gated, none started.
- **P5 (convenience/UX):** additional Telegram UX, dashboard/desktop packaging —
  explicitly out of V1.0.3 scope per the release manifest's `scope_freeze` block.

## 17. Current roadmap audit

| Item | Classification |
|---|---|
| A1 Continue FX Series 002 | VALID_NOW |
| A2 Obtain owner authorization for BTC observation | COMPLETE — owner authorized 2026-09-06 |
| A3 Run BTC 30-valid-observation campaign at eligible report checkpoints | VALID_NOW / first observation pending |
| A4 Collect outcomes/performance evidence | WAITING_TIME (depends on A1/A3 progressing) |
| A5 Record evidence-backed defects | VALID_NOW (ongoing practice, already exercised once) |
| A6 Fix only qualification-blocking strategy/data defects | VALID_NOW (ongoing practice) |
| A7 Complete V1.0.3 qualification | IN_PROGRESS / WAITING_TIME |
| A8 Consider future strategy changes only from evidence | VALID_NOW (policy, not an action item yet) |
| A9 Continue Large-SMC research separately | VALID_NOW (C10 contract-freeze milestone not started) |
| B1 Telegram D1 safely preserved | ALREADY_COMPLETE |
| B2 Telegram feature development paused | ALREADY_COMPLETE |
| B3 Maintain persistence/reporting | VALID_NOW |
| B4 Maintain execution safety | VALID_NOW |
| B5 Repair Windows approval-store concurrency before execution authorization | WAITING_AUTHORIZATION / FUTURE (blocking gate for that future work, not urgent now) |
| B6 Resolve FX Demo execution contract later | FUTURE (CORE-D2, owner decision) |
| B7 Resume Telegram→MT5 later | FUTURE (owner reactivation) |
| B8 Implement Bybit Demo execution later if separately authorized | FUTURE |
| B9 Live operations much later | FUTURE |

None of these were forced away from the evidence-suggested direction; the audit found
the expected roadmap shape substantially confirmed.

## 18. What NOT to build now

- Do not start the BTC 30-day observation campaign without explicit owner
  authorization (tooling is ready; authorization is not granted).
- Do not restart FX Shadow Series 002 or rewrite Day 001/002 evidence.
- Do not resume Telegram feature development (paused by owner directive).
- Do not implement `CryptoExecutionAdapter`, a Bybit order-submission router, or any
  crypto execution path — deliberately unauthorized/out of scope.
- Do not add a strategy-level `risk_per_trade_pct` to `ST_ASIAN_SWEEP_5R_V1.yaml`
  unilaterally — this is an explicit owner decision (CORE-D2), not an engineering
  default to invent.
- Do not implement C10 (Large-SMC broker stop-loss) buffer/spread/min-distance policy
  without the remaining owner-signed specifics.
- Do not build historical live-MT5 replay access — currently blocked, not prioritized
  relative to FX/BTC qualification.
- Do not fix the Windows Telegram concurrency race as part of routine work — it is a
  real defect but gated to a paused subsystem with no current qualification impact;
  fix it when Telegram/execution work resumes, not before.

## 19. Next owner decisions

- BTC campaign authorization is no longer open: the owner authorized the read-only
  30-valid-observation campaign on 2026-09-06. The next gate is the first eligible
  in-window observation; scheduler installation remains a separate operational action.
- Future `ST_ASIAN_SWEEP_5R_V1` Demo authorization (CORE-D2): choose among (A) add a
  strategy-specific `risk_per_trade_pct`, (B) explicitly authorize the pilot-config
  value as the strategy's real risk contract, or (C) remain proposal-only.
- Strategy-level risk contract resolution generally (same decision as above).
- Future Telegram→MT5 resumption timing and scope (Phase D2+).
- Future Bybit Demo execution authorization, if ever pursued.
- Future Large-SMC promotion beyond `RESEARCH_DRAFT` (after C10 resolution and
  subsequent evidence review — not decided by this audit).
- Whether/when `AG_TRADE_ASSISTANT_V1_0_3` moves from `RELEASE_CANDIDATE` to
  `RELEASED` (policy question, gated on the FX/BTC/security qualification gates in
  `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`).

## 20. Last-verified date + commit

Verified 2026-09-06 against `main` @ `651ade619c2c2df9a973d45cea37ae6599c2b9eb`
("Reconcile V1.0.3 evidence and pause Telegram development for qualification").
Telegram evidence verified against `feature/telegram-demo-execution-gateway-v1` @
`740512b7b2e2e45770e150a4497056c511cc4168`, read via the pre-existing worktree at
`.claude/worktrees/telegram-execution-gateway-v1` (not modified). BTC lineage
verified against the merged state on `main` (originally isolated on
`btc/bybit-qualification-v3`, merged via `3b4eb60` and `8289c2d`).

---

## Final assessment

**Q1 — How complete is Section A technically?** Substantially complete for the FX
day-trading and BTC research domains: market data, session logic, decision
classification, proposal construction, entry/stop/target semantics, and shadow/
observation tooling are all implemented and at least focused-verified or
production-data-verified. The
one open technical gap with direct profit-role consequence is the unspecified
strategy-level FX risk percentage (a policy gap, not an engineering one — the code
path exists and simply requires an explicit value). Large-SMC research architecture is
technically far along (five of six pipeline contracts resolved) but genuinely blocked
on C10.

**Q2 — How complete is Section A from an evidence/qualification perspective?** Low in
raw counted-day terms (FX 0/20 valid, BTC 0/30) but this does not mean "0% qualified"
— it means the qualification *process* is running correctly (one real defect was found
and fixed via the process itself) and the infrastructure/contract readiness that makes
counted days possible is largely in place. The limiting factor is elapsed valid trading
days and (for BTC) owner authorization to start counting, not missing decision
functionality.

**Q3 — How complete is Section B for proposal-only operations?** High. Persistence,
immutable archiving, numbered corrections, restart-safe journaling, CLI, and combined
daily reporting are all implemented and at least integration-verified for FX, with an
analogous BTC path confirmed diagnostically against production market data. This layer is mature enough that
further proposal-only tooling investment has diminishing returns right now.

**Q4 — How complete is Section B for automated Demo execution?** Partial and uneven.
Generic MT5 Demo execution infrastructure in *this repository* (command model,
executor, gateway, journal, duplicate protection, reconciliation) is implemented and
demo-verified — but `ST_ASIAN_SWEEP_5R_V1`, the active V1.0.3 FX pilot strategy, is not
`demo_authorized` and cannot use this repository's execution infrastructure
(`demo_authorized: false` is the binding constraint, not the infrastructure).
`SESSION_TRADE_V1` is independently `demo_authorized: true` for its `ASIAN_LONDON`
cycle only (`LONDON_NEWYORK` remains `false`), but it runs on its own separate engine
and execution ledger in a different repository (`D:\ddev\Session Trade Codex`) and does
not use, share, or grant this repository's MT5 execution infrastructure or
`ST_ASIAN_SWEEP_5R_V1`'s authority in any direction — strategy authorization and
execution-channel readiness are independent gates, and authority is never inherited
across strategies. Crypto execution is explicitly `NOT_IMPLEMENTED`, fail-closed by
design. Telegram's approval layer is fully built but paused, unmerged, and has a known
concurrency defect that must be fixed before any execution authorization resumes.

**Q5 — What is already complete enough that further development should stop?**
FX/BTC proposal-only operational tooling (persistence, archiving, reporting, CLI,
Entry Ticket); MT5 generic Demo execution infrastructure; Telegram Phases A-D1 as
built (further Telegram work is explicitly paused, not because it's finished, but by
owner priority).

**Q6 — What is incomplete because of missing code?** Genuinely missing, not merely
unauthorized: `CryptoExecutionAdapter` internals, a Bybit order-submission router,
Telegram→MT5/Bybit wiring, Large-SMC C10 implementation (buffer/min-distance/ATR
formula), a formal counted-observation state machine for BTC beyond the daily
report/archive primitives already reused from FX.

**Q7 — What is incomplete only because evidence hasn't accumulated?** FX shadow valid
days (0/20, mechanism proven correct via Day 001's defect-catch), BTC observations
(0/30, tooling ready), FX/BTC outcome and performance evidence (no broker fills exist
yet because everything is proposal-only), Large-SMC causal-outcome/robustness evidence
(blocked upstream of even starting, by C10).

**Q8 — What is technically ready but owner-authorization-gated?** BTC 30-day
observation campaign start; `ST_ASIAN_SWEEP_5R_V1` Demo authorization (CORE-D2); the
generic MT5→strategy bridge being extended to any specific strategy; Telegram
resumption; any future Bybit Demo execution.

**Q9 — What is deliberately disabled?** MT5 live trading
(`allow_live_trading: false`); FX/BTC/Large-SMC live and (for BTC/Large-SMC) demo
authorization; crypto execution (`CryptoExecutionAdapter` fail-closed by explicit
design); Telegram's broker execution handler (`phase_d1_broker_disabled_handler`
unconditionally returns failure, defense-in-depth even if authorization were ever
flipped).

**Q10 — What three workstreams have the highest expected project value?** (1)
Continue FX Shadow Series 002 to 20 valid days — the direct path to FX qualification
evidence. (2) Run the now-owner-authorized BTC 30-valid-observation campaign at the
frozen report checkpoints — tooling and data access are already ready. (3) Resolve
the CORE-D2 strategy risk-contract owner decision — it
is the single gating item standing between "FX proposals work" and "FX Demo execution
is even possible to authorize," and is inexpensive to resolve (a decision, not new
code).

### Expected strategic conclusion — verified

The evidence supports the expected strategic conclusion stated in the audit
specification without modification: AG Profit Trading is technically advanced as a
deterministic decision-support and research platform. Section A's main remaining
limitation is qualification evidence rather than missing FX/BTC decision
functionality. Section B is mature for proposal-only operations and contains
substantial independent MT5 Demo infrastructure, but strategy-specific Demo
integration, crypto execution, and live operations remain intentionally incomplete or
unauthorized. The current highest-value activity is qualification and evidence
collection, not additional execution/UI development. **Classification: SUPPORTED.**

**Explicit disclaimer — software completeness is not trading-edge validation.** FX and
BTC decision pipelines are substantially implemented. Trading-edge qualification
remains incomplete: FX has `valid_days=0/20` (`invalid_days=1` currently recorded);
BTC has `observations=0/30` and the campaign is not yet authorized
(`campaign_authorized=false`). Regression/test evidence (1356 passed / 1 skipped / 0
failed) proves deterministic software behavior only — it does not establish
profitability, expectancy, win rate, or trading edge. Nothing in this document should
be read as a claim that the trading edge itself is mature or validated merely because
the surrounding software pipeline is substantially implemented.

### Prior estimate validation

- `SECTION A_ENGINEERING_85_90`: **SUPPORTED**. FX and BTC decision pipelines
  (data→session→classification→proposal→ticket→archive) are implemented end-to-end
  and at least focused-verified/production-data-verified; Large-SMC is five-of-six
  contracts resolved.
  The remaining 10-15% is genuinely open code/contract work (C10, crypto execution
  internals, strategy-level risk value), not a hidden shortfall.
- `SECTION_A_QUALIFICATION_35_45`: **NOT_MEANINGFUL as stated, but not contradicted**.
  0/20 FX valid days and 0/30 BTC observations, taken as raw counts, would suggest
  ~0%, yet the qualification *infrastructure and contract readiness* (evidence
  contract frozen, defect-catching process demonstrated once already, BTC tooling
  fully ready) is close to 100% built. A single blended percentage conflates two
  different axes (infrastructure readiness vs. accumulated evidence) that this
  document deliberately keeps separate — hence `NOT_MEANINGFUL` rather than
  endorsing or rejecting a specific number. High test-pass counts (1356 passed) are
  evidence of code correctness, not evidence of strategy profitability — the two are
  categorically different kinds of evidence.
- `SECTION_B_PROPOSAL_OPS_85_90`: **SUPPORTED**. Persistence, immutable archiving,
  numbered corrections, CLI, and reporting are implemented and integration/live
  verified for both FX and BTC.
- `SECTION_B_DEMO_AUTOMATION_45_55`: **SUPPORTED, at the low-to-mid end**. Generic MT5
  Demo infrastructure in this repository is fully built and demo-verified, but
  `ST_ASIAN_SWEEP_5R_V1` (the active V1.0.3 FX pilot strategy) is not authorized to use
  it (`demo_authorized: false`); `SESSION_TRADE_V1` is separately `demo_authorized: true`
  for its own `ASIAN_LONDON` cycle only, on its own separate engine, and this does not
  extend to `ST_ASIAN_SWEEP_5R_V1` or any other strategy. Crypto execution is
  explicitly unimplemented, and Telegram (the most complete approval-interface
  candidate) is paused with a known pre-execution-authorization blocking defect.
  "Automation" in the full sense (strategy-authorized, end-to-end, unattended) is
  closer to the lower half of that range than the upper half.

### Optional planning estimates

No calculation contract for an overall completeness percentage exists anywhere in this
repository, and this document does not define one — a bare percentage would imply a
precision this audit cannot support. Report exact, machine-derivable counters instead:

- `SECTION_A_ENGINEERING`: capability matrix (Section 6) — count of `IMPLEMENTED` rows
  vs. total Section A rows directly from the table above; largest uncertainty:
  Large-SMC C10's true implementation cost is unknown until the buffer/min-distance
  policy is specified.
- `SECTION_A_QUALIFICATION`: `NOT_MEANINGFUL` as a single number (a percentage would
  conflate infrastructure-readiness with accumulated-evidence-days, which this document
  deliberately keeps separate); report the counters directly: FX
  `valid_days=0/20, invalid_days=1`; BTC `observations=0/30, campaign_authorized=false`.
- `SECTION_B_PROPOSAL_OPERATIONS`: capability matrix (Section 7) — count of
  `IMPLEMENTED` rows vs. total Section B proposal/reporting rows directly from the
  table above; largest uncertainty: BTC scheduler's actual installed/running state is
  unconfirmed.
- `SECTION_B_DEMO_AUTOMATION`: `ST_ASIAN_SWEEP_5R_V1: demo_authorized=false`;
  `SESSION_TRADE_V1: demo_authorized=true, authorized_cycle=ASIAN_LONDON` (separate
  engine, does not extend to other strategies); `Crypto execution: NOT_IMPLEMENTED,
  fail_closed=true`. This repository's MT5 Demo execution infrastructure exists and is
  demo-verified, but no strategy that uses it directly is currently `demo_authorized`;
  largest uncertainty: the true cost of the CORE-D2 decision and the Telegram
  concurrency fix once resumption is authorized.
