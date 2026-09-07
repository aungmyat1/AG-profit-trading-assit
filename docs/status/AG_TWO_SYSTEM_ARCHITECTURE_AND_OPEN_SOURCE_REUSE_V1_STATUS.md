# AG_TWO_SYSTEM_ARCHITECTURE_AND_OPEN_SOURCE_REUSE_STATUS

## REPOSITORY

```
branch                = main
HEAD                  = 218ed1ab02175370245d2f1ed8aac429fbe1f40c
origin_main            = unchanged (not fetched/pushed by this task)
ahead / behind         = not evaluated (no remote sync performed)
working_tree_before     = M PROJECT_STATUS.md
                          ?? docs/architecture/AG_MULTI_MARKET_OS_REUSE_LEDGER.md
                          ?? docs/status/AG_MULTI_MARKET_STRATEGY_OS_RESOURCE_REUSE_DISCOVERY_V1_STATUS.md
                          ?? docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1_STATUS.md
                          ?? docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1_STATUS.md
                          ?? tests/test_large_smc_execution_boundary.py
working_tree_after      = same five items (untouched) + two new files this task added:
                          ?? docs/architecture/AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md
                          ?? docs/status/AG_TWO_SYSTEM_ARCHITECTURE_AND_OPEN_SOURCE_REUSE_V1_STATUS.md (this file)
```

## BASELINE

```
application            = AG_TRADE_ASSISTANT_V1_0_3
application_state       = RELEASE_CANDIDATE (unchanged)
FX                     = ST_ASIAN_SWEEP_5R_V1 v1.1.1, OPERATIONAL_PROPOSAL_SHADOW_AUTHORITY (unchanged)
BTC                    = ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0, OPERATIONALLY_READY_FOR_FORWARD_RESEARCH,
                         broker_execution=DISABLED (unchanged)
Large_SMC              = ST_LARGE_SMC_V1 v1.0.6, RESEARCH_RUNTIME_READY_WITH_GOVERNANCE_BLOCKS,
                         C10=UNSIGNED, C14=PARTIALLY_RESOLVED, broker_execution=DISABLED (unchanged)
strategy_versions_changed  = NONE
execution_authority_changed = NONE
```

Re-verified directly against `strategies/registry.yaml` in this pass: no discrepancy
found against the notes carried into this task. No overwrite performed (would only
have been reported, not silently applied, if a mismatch had existed).

## TWO_SYSTEM_CLASSIFICATION

```
STRATEGY_SYSTEM
  existing   = strategy contracts/registry, per-strategy YAML, evidence id-linking
               pattern (FX/BTC/Large-SMC), version/campaign attribution, per-strategy
               research/replay tooling
  ambiguous  = decision/proposal model (3 independent signed shapes + 1 partial
               normalization, not yet unified); strategy-side pre-flight consultation
               of execution-owned DailyLossGuard/OpenPositionGuard/size_position
  missing    = cross-market opportunity ranking; cross-market statistics/analytics
               aggregation

EXECUTION_SYSTEM
  existing   = execution command/coordinator, ExecutionAdapter ABC (MT5/Crypto),
               TradeProposal, DailyLossGuard, OpenPositionGuard, size_position,
               lifecycle/idempotency, crypto reconciliation, MT5/Bybit/Binance
               connectors (Bybit/Binance currently read-only feeds), paused Telegram
               authorization module (own branch)
  ambiguous  = same pre-flight-consultation imports noted above (execution risk
               primitives imported directly by strategy modules rather than exposed
               through a narrower public query surface)
  missing    = unified cross-strategy portfolio/account exposure budget; Bybit/
               Binance order-routing adapters (currently feed-only by design,
               execution stays disabled)

trust_boundary      = Strategy decides WHAT trade should exist; Execution decides
                      WHETHER/HOW MUCH/HOW it reaches a broker. Verified: no strategy
                      module calls a broker API, reads execution credentials, or
                      mutates a position; no execution module changes qualification/
                      direction/entry/SL/TP/strategy version/historical attribution.
bridge_contract     = No single existing object satisfies the spec's full
                      TradeProposal-equivalent field list; `execution/adapter.py::
                      TradeProposal` (setup_id/strategy_id/symbol/profile_id/
                      direction/entry/stop_loss/tp1/tp2/volume/risk_amount/
                      risk_percent) is the closest asset-independent shape and is
                      already reused across FX/BTC paths; `assistant.models.
                      StrategyResult` is the closest normalized-decision analogue but
                      is wired only for SESSION_TRADE_V1. No new bridge object was
                      created this pass (Phase-1 normalization remains deferred, per
                      the prior ledger's own assessment, unchanged this pass).
boundary_violations = Bidirectional imports found between strategy packages
                      (`strategy_engine.sweep_retest.engine`, `btc_sweep_research.
                      pipeline`, `post_asian_pilot.*`) and execution-owned risk/
                      coordinator modules (`execution.daily_loss_guard`,
                      `execution.position_guard`, `execution.risk`,
                      `execution.coordinator`, `execution.adapter`, `execution.
                      intent_builder`, `execution.validator`, `execution.
                      bar_tracker`), plus execution modules importing strategy
                      terminal-contract types (`strategy_engine.sweep_retest.
                      {models,profile}`, `strategy_engine.models.{StrategyConfig,
                      TradeSignal}`). This is a genuine, intentional, pre-existing
                      pattern (pre-flight guard checks + terminal-contract
                      consumption) — no broker call, no authority bypass, no
                      economics change found in any of it. Documented as a boundary
                      ambiguity, not treated as a stop condition (see ledger for the
                      full import-by-import list).
```

## STRATEGY_SYSTEM_REUSE

```
AG          = Strategy contract (complete), evidence id-pattern (complete), version/
              campaign attribution (complete), per-strategy research/replay tooling
              (complete)
LOCAL       = smc-lss-platform provider-registry shape (conceptual reference only,
              no license, nothing copied)
JESSE       = license unverified this pass; excluded from any reuse claim
LEAN        = Apache-2.0/C#; CONCEPTUAL_PORT ceiling only (Insight/PortfolioTarget/
              Algorithm shapes as inspiration, not source)
FREQTRADE   = GPL-3.0; REFERENCE_ONLY by default (copyleft, not adopted)
recommended_reuse    = Extend `assistant.models.StrategyResult` additively
                       (market/authority/confidence/expected_r/evidence_ref/
                       proposal_ref/blockers/targets) as the normalized
                       StrategyDecision, if/when the owner authorizes Phase-1 — not
                       done this pass
new_code_required    = Cross-market opportunity ranking (deterministic, V1, no
                       external ML); cross-market analytics aggregation (if wanted)
```

## EXECUTION_SYSTEM_REUSE

```
AG          = Execution command/coordinator (complete), ExecutionAdapter ABC
              (complete), account risk/position sizing/daily loss guard (complete,
              tested), lifecycle/idempotency (complete), crypto reconciliation
              (complete, BTC-wired), MT5/Bybit/Binance connectors (complete as feeds;
              Bybit/Binance order-routing not built), paused Telegram authorization
              module (complete through Phase D1, 8 tests, not resumed)
LOCAL       = ai-trade-systemD (Bybit client tests, unlicensed, reference only);
              01Binance futures trading setup07 (Docker/VPS bot, unlicensed,
              reference only) — nothing copied from either
HUMMINGBOT  = Apache-2.0; no local clone found to inspect an exact file/commit ->
              REFERENCE_ONLY / CONCEPTUAL for all rows (ConnectorBase, order
              tracking, Bybit/Binance perpetual connectors), never claimed as
              ADAPTED_REUSE without a verified commit
LEAN        = Apache-2.0/C#; CONCEPTUAL_PORT ceiling (Order/OrderTicket/OrderEvent/
              IBrokerage/portfolio-sync concepts)
FREQTRADE   = GPL-3.0; REFERENCE_ONLY (Telegram/dry-run/live UX workflow reference
              only, no code adapted)
recommended_reuse    = Reuse AG's own execution-safety stack unchanged; when the
                       owner lifts the Telegram pause, reuse
                       `src/authorization/*` as-is (verified this pass to already
                       satisfy the control-plane-only boundary); if/when Bybit/
                       Binance order routing is ever built, treat Hummingbot's
                       connector patterns as structural reference only pending a
                       verified local clone/commit
new_code_required    = Unified cross-strategy portfolio/account exposure budget (if
                       ever authorized); Bybit/Binance order-routing adapters (not
                       built, execution stays disabled)
```

## BROKER_REUSE

```
MT5     = src/mt5/ (management_gateway, broker_time, deals, symbol_resolver) —
          EXACT_REUSE, mature, in active use, no external candidate applies
BYBIT   = execution_runtime/bybit_linear_perp_feed.py — EXACT_REUSE (read-only feed,
          Bybit V5 linear perpetual, owner-approved qualification exception scope);
          order-routing adapter REFERENCE_ONLY/not built (Hummingbot Bybit perp
          connector as future structural reference only)
BINANCE = execution_runtime/binance_usdtm_feed.py — EXACT_REUSE (read-only feed,
          environment-blocked HTTP 451, retained as alternate implementation);
          order-routing adapter REFERENCE_ONLY/not built (Hummingbot Binance USDT-M
          connector as future structural reference only)
```

## TELEGRAM_REUSE

```
existing_AG      = Complete, paused module on `feature/telegram-demo-execution-
                   gateway-v1` (commit 740512b), checked out at
                   `.claude/worktrees/telegram-execution-gateway-v1/src/
                   authorization/` — config.py, integrity.py, models.py,
                   proposal_source.py, store.py, strategy_authority.py,
                   telegram_gateway.py. Phases A/B/C/D1 committed, 8 tests, owner-
                   paused, not connected to execution.executor/coordinator anywhere
                   in its own file set.
local_candidate  = none found (no local Telegram bot implementation outside this
                   same repository's paused branch)
external_reference = Freqtrade's Telegram bot (GPL-3.0) — UX/operational-controls
                     reference only, no code adopted
recommended_path = Reuse existing AG module as-is once owner lifts the pause; do
                   not build a new Telegram integration or import an external bot
                   framework
```

Boundary properties verified this pass by reading the actual code (not assumed):
`TelegramExecutionGateway` never imports a broker/exchange client; the only
"execution" reachable is a caller-injected `ExecutionHandler` (committed handlers are
`fake_execution_handler`, always succeeds/no broker call, and
`phase_d1_broker_disabled_handler`, always fails closed); it never reconstructs a
`TradeProposal` from Telegram data, only resolves an already-persisted immutable one;
`strategy_authority.check_strategy_demo_authorized()` re-reads
`strategies/registry.yaml` live at click time with no independent cached copy, and
the check runs and can block before `mark_executing()` / before the execution handler
is ever invoked; keyboards/buttons render from backend approval/authority state, not
from strategy names. This already matches the spec's required Telegram flow exactly.

## LICENSE_REVIEW

```
HUMMINGBOT           = Apache-2.0 (permissive); no local clone found on this machine
                       to inspect an exact file/commit this pass -> all rows stay
                       REFERENCE_ONLY/CONCEPTUAL, never ADAPTED_REUSE
LEAN                 = Apache-2.0 (permissive) but C# -> CONCEPTUAL_PORT ceiling per
                       task default regardless of license
FREQTRADE            = GPL-3.0 (copyleft) -> REFERENCE_ONLY by default; not adopted,
                       no mechanical rewriting performed to evade copyleft
JESSE                = License unverified this pass (no local clone, no license file
                       inspected) -> excluded from any reuse claim entirely
direct_reuse_approved = NONE (no external source code copied or adapted in this pass)
reference_only        = Hummingbot (all rows), LEAN (all rows, conceptual only),
                        Freqtrade (all rows), Jesse (excluded, not even referenced)
```

## BOUNDARY_VERIFICATION

```
strategy_to_execution   = No strategy module calls a broker API, reads execution
                          credentials, or mutates a position. Strategy modules DO
                          import execution-owned pre-flight guards
                          (DailyLossGuard/OpenPositionGuard/size_position) and the
                          coordinator/adapter/proposal types — documented as a
                          boundary ambiguity, not a violation of authority or safety.
execution_to_strategy   = No execution module changes qualification/direction/
                          entry/SL/TP/session rules/strategy version/historical
                          attribution. Execution modules import only the strategy
                          engine's terminal contract types (SetupState/
                          STATE_ENTRY_READY/StrategyConfig/TradeSignal/profile
                          constants), not internal detector/indicator logic.
BTC_execution_boundary       = Unchanged; existing
                               tests/test_btc_proposal_execution_boundary.py and
                               tests/test_crypto_command_execution_boundary.py left
                               untouched, not re-run beyond what this task's own
                               (nonexistent) code changes would require.
Large_SMC_execution_boundary = Unchanged; pre-existing
                               tests/test_large_smc_execution_boundary.py (untracked,
                               left exactly as found) not modified by this task.
FX_execution_authority       = Unchanged; ST_ASIAN_SWEEP_5R_V1 demo_authorized=false,
                               live_authorized=false in strategies/registry.yaml,
                               re-verified, not touched.
```

## EVIDENCE

```
strategy_evidence   = decision/proposal/campaign/outcome/strategy-version records,
                      per strategy (FX PostAsianEntryProposal + DailyTradeSlot; BTC
                      BTCSweepResearchProposal + ResearchCycleReport; Large-SMC
                      engine occurrence/outcome + historical_replay artifacts)
execution_evidence  = authorization/command/order/fill/position/reconciliation/
                      broker-account records (execution/lifecycle.py,
                      execution/crypto_reconciliation.py, src/mt5/deals.py, paused
                      authorization/store.py::ExecutionApprovalStore)
historical_attribution = Unchanged; FX historical records remain attributed to
                        ST_ASIAN_SWEEP_5R_V1 v1.1.1; nothing rewritten by this task.
lineage_model       = decision_id -> proposal_id -> authorization_id ->
                      execution_command_id -> broker_order_id -> fill_id ->
                      position/reconciliation events (conceptual, as specified;
                      not implemented as a single new object this pass — the two
                      evidence ledgers stay separate and linked by existing IDs,
                      not merged)
```

## TESTS

```
focused          = None run. This pass is documentation/classification only — no
                   production code, strategy file, execution/authority/risk module,
                   registry entry, or test was created or modified.
full_suite       = Not run.
full_suite_reason = No shared production behavior was changed (two new markdown
                    files only); running the full suite would not validate anything
                    this task touched and is not required by the test policy for a
                    docs-only, isolated-additive change.
```

## FILES_CHANGED

```
Created (new files only):
  docs/architecture/AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md
  docs/status/AG_TWO_SYSTEM_ARCHITECTURE_AND_OPEN_SOURCE_REUSE_V1_STATUS.md (this file)

Left untouched (pre-existing, out of this task's scope):
  PROJECT_STATUS.md (modified before this task started)
  docs/architecture/AG_MULTI_MARKET_OS_REUSE_LEDGER.md (prior task's output)
  docs/status/AG_MULTI_MARKET_STRATEGY_OS_RESOURCE_REUSE_DISCOVERY_V1_STATUS.md
  docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_AND_VERSION_PROMOTION_V1_STATUS.md
  docs/status/AG_MULTI_STRATEGY_OPERATIONAL_BASELINE_FREEZE_AND_BOUNDARY_HARDENING_V1_STATUS.md
  tests/test_large_smc_execution_boundary.py

No strategy YAML, execution/authority/risk module, registry entry, or existing test
was modified. No boundary-hardening test was added (see ledger's "Boundary
hardening — evaluated, not implemented this pass" section for why).
```

## REUSE_SUMMARY

```
AG_existing_reused        = 17 capabilities across both systems (strategy contract,
                            evidence pattern, version/campaign attribution,
                            research/replay tooling; execution command, order model,
                            order state, fill event, position model, account risk,
                            position sizing, authority, idempotency, broker
                            interface, MT5, Bybit feed, Binance feed, Telegram
                            (paused), reconciliation, journal)
local_components_reused   = 0 (all local candidates classified REFERENCE_ONLY/
                            CONCEPTUAL; nothing copied)
external_components_reused = 0
conceptual_ports          = LEAN (Order/OrderTicket/OrderEvent/IBrokerage/Portfolio
                            shapes, all rows, C#, Apache-2.0)
small_adapters_required   = Normalized StrategyDecision (additive fields on
                            assistant.models.StrategyResult) — deferred, requires
                            owner-scoped field-mapping decision, not built this pass
new_subsystems_required   = Cross-market opportunity ranking; unified cross-strategy
                            portfolio/account exposure budget; Bybit/Binance
                            order-routing adapters (all out of scope this pass)
```

## NEXT_IMPLEMENTATION_PRIORITY

```
1 = Freeze the two-system ownership map (this document + the ledger) as the
    reference for future agents; obtain owner sign-off on whether the strategy-side
    pre-flight consultation of DailyLossGuard/OpenPositionGuard should remain as-is
    or be moved behind a narrower execution-facing query function
2 = If pursued, implement the normalized StrategyDecision as additive fields on
    assistant.models.StrategyResult (owner-scoped field-mapping decision required
    first, per the deferred Phase-1 assessment)
3 = When the owner lifts the Telegram pause, reuse src/authorization/* as-is
    (verified this pass to already satisfy the required boundary) rather than
    rebuilding or importing an external bot framework
```

## FINAL_CLASSIFICATION

```
AG_TWO_SYSTEM_ARCHITECTURE_REUSE_DISCOVERY_COMPLETE
```

Discovery and STRATEGY-vs-EXECUTION reuse classification are complete for both
systems, documented in `docs/architecture/AG_TWO_SYSTEM_OPEN_SOURCE_REUSE_LEDGER.md`.
No boundary-hardening test was implemented (evaluated and deliberately skipped due to
genuine, by-design bidirectional imports that would produce false positives — see
ledger), so `AG_TWO_SYSTEM_ARCHITECTURE_BOUNDARY_HARDENING_COMPLETE` does not apply.
No license blocker was found for any capability AG already owns, and no external
code was copied, so `AG_TWO_SYSTEM_REUSE_BLOCKED_BY_LICENSE` does not apply. The one
boundary ambiguity found (strategy-side pre-flight consultation of execution-owned
risk guards) does not contradict the proposed Strategy-decides-WHAT/Execution-
decides-WHETHER boundary at the authority/safety/economics level — it is a documented
internal nuance, not evidence the two-system model itself is wrong — so
`AG_TWO_SYSTEM_ARCHITECTURE_RECONCILIATION_REQUIRED` does not apply either. This
scope is the two-system classification and reuse ledger only; the Multi-Market
Strategy OS as a whole remains not implemented and is not claimed complete.
