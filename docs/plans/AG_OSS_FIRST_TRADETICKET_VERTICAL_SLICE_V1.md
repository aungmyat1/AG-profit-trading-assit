# AG OSS-First TradeTicket Vertical Slice V1 — Phase 0 component map

Status: PHASE 0 FROZEN (written before any production code in this mission); R2 amendments marked **R2**. Result: `docs/status/AG_OSS_FIRST_TRADETICKET_VERTICAL_SLICE_V1_STATUS.md`.
Date: 2026-09-29. Mission scope ends at `TradeTicket PREPARED_ONLY`, `EXECUTION_AUTHORITY = NONE`.

## 1. Lineage (verified, not assumed)

| Item | Value |
|---|---|
| Working branch | `feat/oss-first-tradeticket-slice-v1` (worktree `D:/ddev/AG-tradeticket-slice-v1`) |
| Base (authoritative platform lineage) | `platform/fx-opportunity-v2` @ `76348c728b2229de2ad0a5c22f857bf0263de60f` (Collector V2) |
| Base tree | `5f27bf5e56f4412361482c9329ebe8bb3a837c71` |
| origin/main | `4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8` (= merge-base; platform is 31 commits ahead, unpushed) |
| P6-R1 `1e26533`, P6-R2 `6fdc921`, Collector V2 `76348c7` | all ancestors of base; contained only in `platform/fx-opportunity-v2` (+ `origin/audit/vt-spread-evidence-p6-r2` for the first two) |
| Not used | `arch/edge-ai-runtime-v1-foundation` (primary checkout) does NOT contain the platform lineage; it is left untouched (friction-campaign files are written there by the scheduled task). |

## 2. Existing authorities verified on this lineage

| Concern | Authority | Verdict |
|---|---|---|
| Live Opportunity | `src/fx_opportunity/{runner,scanner,market_state,instruments}.py` | live-verified P6-R1 (VT Markets Demo, 3 pairs) |
| MarketState | `fx_opportunity.market_state.MarketState` (closed-bar facts + fingerprint) | reuse |
| Opportunity | `opportunity.contracts.OpportunityCandidate` via `asian_sweep_adapter` + `engine.evaluate_funnel` | reuse |
| ProposalEligibility | `opportunity.proposal_eligibility.evaluate_proposal_eligibility` (hardened: identity, registry, terminal, expiry, synthetic/replay firewall, stage, geometry, canonical symbol, side, finite, entry≠stop, stop side) | reuse unchanged — the ONLY eligibility authority |
| Canonical proposal | `proposal_envelope.models.CanonicalProposal` + `adapters.opportunity_adapter.to_canonical_proposal` | reuse unchanged |
| Governance fields | `proposal_envelope.strategy_authority.resolve_strategy_authority` | reuse |
| Strategy registry | `strategies/registry.yaml` — **no entry carries `proposal_authorized`**; `ST_ASIAN_SWEEP_5R_V1` is `research: true`, `demo_authorized: false`; lifecycle `OPERATIONAL_SHADOW` v1.1.1 | NO strategy is proposal-authorized |
| Owner-decision boundary | not on this lineage (`owner_decision/` removed by `3f1f955`; gate2 work lives on `fix/gate2-r3-auditor-remediation`, unmerged) | DEFER — contract constants only |
| Execution containment | `tests/test_fx_opportunity_containment.py` asserts `src/execution`, `authorization`, `ticket_delivery` are NOT restored | preserve |
| Risk/sizing | not on this lineage; historical canonical `execution.risk.size_position` @ `1a8e7c5` (blob `ecda12d2`) — pure, depends only on `mt5.symbol_resolver.SymbolMeta` (present) | restore function verbatim outside `execution` |
| Risk policy | cycle pilot config `risk.risk_per_trade_pct` 0.5 / `max_aggregate_open_risk_pct` 1.0 (via `PilotConfig`) | reuse (read-only); **R2:** `config/trading.demo.yaml` (1.0) is the historically divergent generic default and is NOT consulted — no fallback |
| Instrument/broker identity | `config/instruments/fx_opportunity_instruments.yaml` (VTMARKETS / VTMarkets-Demo / DEMO) | reuse |
| Fingerprint | `post_asian_pilot.fingerprint.fingerprint` (canonical JSON SHA-256) | reuse |

## 3. OSS decision (per Arena `origin/audit/oss-first-fx-ticket-discovery-v1`, `docs/third_party/OSS_DEPENDENCY_LEDGER.md`)

| Component | Arena verdict | This slice |
|---|---|---|
| pandas-ta-classic | OPTIONAL (only if AG lacks a required indicator) | NOT NEEDED — ticket geometry is strategy-owned; no ATR/EMA required |
| smart-money-concepts | EVALUATE_PRIMARY (parity gate pending) | NOT USED — no SMC primitive on this path; not authoritative |
| smc-mcp | REFERENCE_SECONDARY | NOT USED; MCP path never reaches Proposal/execution |
| Freqtrade / NautilusTrader | DEFER / REFERENCE_ONLY | reference only (lifecycle naming) |
| CCXT | DEFER | not integrated (FX milestone) |
| Backtesting.py | DEFER (AGPL) | not introduced |

No new third-party dependency is added by this slice.

**R2 (Arena adoption gate):** pandas-ta-classic = ADOPT_BEHIND_THIN_ADAPTER *when needed* — this path needs no indicator, so no adapter is created (existing AG Wilder ATR in `src/fx_discovery/features.py` stays the parity oracle for a later adapter). smartmoneyconcepts = REFERENCE_ONLY (not imported by `src/`; requirements pin used only by two research scripts). vectorbt = DO_NOT_ADOPT. Backtesting.py = LICENSE_CONTAINMENT_REQUIRED → PRODUCT_RUNTIME_REACHABILITY = NOT_REACHABLE (only `research_external/adapters/backtesting_py.py`); boundary test added.

## 4. Component classification

| Component | Class | Notes |
|---|---|---|
| MarketState / Opportunity / funnel | REUSE_EXISTING | unchanged |
| ProposalEligibility | REUSE_EXISTING | unchanged; never duplicated or weakened |
| CanonicalProposal + opportunity bridge | REUSE_EXISTING | the ticket embeds the unmodified `CanonicalProposal` as its trade plan |
| Strategy governance fields | REUSE_EXISTING | `resolve_strategy_authority` |
| Position sizing math | REUSE_EXISTING (restored verbatim) | `size_position` from `1a8e7c5:src/execution/risk.py`, relocated to `src/trade_ticket/sizing.py` because `src/execution` must stay absent |
| Standard indicators | DEFER | none required |
| SMC primitives | DEFER | Arena parity gate pending |
| StrategyQualification | SMALL_CUSTOM | thin pre-eligibility gate: proposal authority, pipeline mode, MarketState↔candidate consistency, staleness, look-ahead, setup presence. `CUSTOM_BUILD_REASON = NO_ACCEPTABLE_EXISTING_OR_OSS_COMPONENT` (no existing module ties MarketState + Opportunity + proposal authority; OSS has no AG authority concept) |
| TradeTicket (PREPARED_ONLY) | SMALL_CUSTOM (wrapper) | wraps the canonical proposal + ticket-only facts (broker/server/env, cycle, sizing, fingerprints, expiry, status). Arena M5 permits "a pure presentation mapping if the current schema is insufficient": `CanonicalProposal` has no broker/server/environment/cycle/sizing/instrument-fingerprint/semantic-hash. `CUSTOM_BUILD_REASON = NO_ACCEPTABLE_EXISTING_OR_OSS_COMPONENT` |
| Owner analysis view | SMALL_CUSTOM | pure dict projection of the ticket; AI explanation slot is advisory and non-authoritative |
| Owner-confirm contract | SMALL_CUSTOM (constants only) | PREPARED_ONLY → OWNER_CONFIRMED → DEMO_EXECUTION_REQUESTED declared; nothing beyond PREPARED is implemented |
| Aggregate risk policy | BLOCKED/NOT_AVAILABLE | no aggregate policy exists on this lineage; recorded as `NOT_AVAILABLE`, never invented |
| Owner-decision bridge, Demo execution | DEFER | out of mission |

## 5. Strategy authority modes (Phase 2)

- `REAL_STRATEGY_MODE`: requires the registry entry to carry `proposal_authorized: true` (read-only; this slice never writes it). Today no entry does → `NO_PROPOSAL_AUTHORITY` (successful fail-closed result). Reserved test namespace strategies are refused.
- `PIPELINE_TEST_MODE`: only strategy ids in the reserved `PIPELINE_TEST_` namespace (never registry entries), deterministic fixtures; ticket status `PREPARED_TEST_ONLY`, `market_authoritative = false`, no lifecycle successor. The unmodified eligibility firewall still applies (a SYNTHETIC-labelled fixture is BLOCKED; the fixtures reproduce the REAL-mode shape so the whole gate is exercised, and their non-authority is carried by mode + namespace + status, not by weakening eligibility).

## 6. Scope

EURUSD first (POST_ASIAN, one cycle), then GBPUSD by configuration only. USDJPY: `NO_COMPATIBLE_OPPORTUNITY_STRATEGY`, strategy binding NONE (sizing geometry tested only). No runner/scanner/eligibility/bridge modification; the new package composes downstream of `FxOpportunityResult`. No scheduler, no Demo/Live order, no registry authorization change.
