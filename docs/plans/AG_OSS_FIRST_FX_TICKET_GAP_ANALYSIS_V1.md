# AG OSS-First FX Trade Ticket Gap Analysis V1

**Date:** 2026-09-28  
**Classification:** `DISCOVERY_PARTIAL_PASS`  
**Base SHA:** `4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8`  
**Base tree:** `95b5cb38aebe985b457c3aa8e6acd3b9ae537281`  
**Scope:** read-only repository/OSS discovery plus documentation only. No runtime, strategy, proposal, execution, broker, MT5 order, or authorization code is changed.

## Objective

Reach the first trustworthy FX decision product through the shortest safe path:

`canonical MT5 data -> session context -> deterministic features -> Opportunity -> strategy qualification -> ProposalEligibility -> CanonicalProposal/TradeTicket or NO_TRADE`

Initial proof: EURUSD. Expansion after proof: EURUSD, GBPUSD, USDJPY for post-Asian and post-London cycles.

## Phase 0 — authoritative remote state

Verified remote `main` at `4bbba3192b2c26245b4e7f0d6d7b15960e0d96c8`, tree `95b5cb38aebe985b457c3aa8e6acd3b9ae537281`. The merge adds read-only MCP launcher upgrades on top of the proposal foundation; it does not authorize trading.

The parent proposal foundation (`0f149c5825ac2a6bccaec722a151a61fbfeb4b51`) already establishes the capability-zero data path:

`OpportunityCandidate -> ProposalEligibility -> CanonicalProposal -> proposal ledger -> STOP`

It also hardens symbol, direction, finite geometry, entry/stop inequality, and stop-side geometry. Its own status explicitly excludes `formation_gate.py`, `fx_adapter.py`, execution/authorization/owner-decision/ticket surfaces, and any scanner-to-proposal composition runner.

`AGENTS.md` remains authoritative for safety: deterministic strategy engine owns signals; agent skills are advisory; a ticket is not a broker order; no strategy rule or NO_TRADE may be overridden; frozen strategy versions cannot be behaviorally changed in place.

### Phase-0 result

- Remote commit identity: **PASS**
- Remote tree identity: **PASS**
- Proposal data-only foundation present: **PASS**
- Execution authority added by this discovery: **NO**
- Local Windows worktree cleanliness / MT5 runtime / installed packages: **NOT_EVALUATED from GitHub connector**

## Gap classification

| Capability | Classification | Decision |
|---|---|---|
| ProposalEligibility | `REUSE_EXISTING` | Already hardened in current lineage; do not create a second eligibility engine. |
| CanonicalProposal + proposal ledger | `REUSE_EXISTING` | Current proposal foundation is the target downstream envelope. |
| MT5 read-only market acquisition | `REUSE_EXISTING` | Current main has a pinned read-only MT5 MCP launcher; production scanner should still use the repository's canonical market-data boundary rather than make OSS packages broker-aware. |
| Session definitions | `REUSE_EXISTING` | AG session authority remains canonical. OSS packages must not redefine trading windows. |
| Standard indicators | `REUSE_EXISTING_OR_ADAPT_OSS` | Do not add a dependency unless the selected strategy actually needs an indicator missing from AG. `pandas-ta-classic` is a permissive fallback. |
| SMC primitives | `ADAPT_OSS` | Evaluate a thin deterministic adapter; never propagate third-party objects into Proposal or execution layers. |
| Multi-timeframe MarketState | `REUSE_EXISTING_OR_IMPLEMENT_SMALL` | Reuse existing contracts if sufficient; otherwise add only a normalized D1/H1/M15/M5 fact object. |
| FX Opportunity composition | `IMPLEMENT_SMALL` | This is the key missing vertical-slice composition: canonical facts -> OpportunityCandidate. |
| Strategy qualification | `BLOCKED_PENDING_AUTHORITY_CHECK` | Exact current strategy/version/symbol/session authority must be established locally before a Proposal can be called strategy-qualified. Do not silently repurpose SSC or an external-reference strategy. |
| Scanner -> Proposal composition runner | `IMPLEMENT_SMALL_AFTER_AUTHORITY` | Parent proposal status explicitly says this composition runner is excluded. |
| Demo/live execution | `DEFER` | Not required for first ticket proof. |
| Crypto/CCXT/Nautilus migration | `DEFER` | Not required for FX vertical slice. |

## OSS evaluation

### 1. `joshyattridge/smart-money-concepts`

Reference: https://github.com/joshyattridge/smart-money-concepts  
License: MIT.  
Observed latest commit during discovery: `1b62fd6c41e1f508e7ed76831a039fa4c82d42f6` (2026-04-03, version 0.0.27).  
Decision: **PRIMARY ADAPTER CANDIDATE FOR CONTROLLED EVALUATION**, not yet adopted.

Why: materially longer project history than the alternative SMC-MCP candidate, permissive license, and focused SMC primitives. It should be treated as a feature implementation behind an AG-owned interface. Before adoption, parity fixtures must establish exact semantics for swings, BOS/CHoCH, FVG, liquidity and order blocks, especially confirmation timing/look-ahead behavior.

### 2. `AkhileshSelvan/smc-mcp`

Reference: https://github.com/AkhileshSelvan/smc-mcp  
License: MIT.  
Observed latest commit: `719862b404ec4bd4d52b3bfa4c39ef0c034bb654` (2026-06-14). Repository history observed during discovery is very small (2 commits). README states pure-Python OHLC logic, hand-built tests, and formed-fractal/no-look-ahead handling for BOS/CHoCH, order blocks, FVG and liquidity sweeps.  
Decision: **SECONDARY SEMANTIC/TEST REFERENCE** initially, not production dependency.

Why: its definitions map closely to AG's intended vocabulary and it explicitly addresses look-ahead, but the project is very young. Use it to cross-check semantics and test cases before considering adoption.

### 3. `xgboosted/pandas-ta-classic`

Reference: https://github.com/xgboosted/pandas-ta-classic  
License: MIT.  
Decision: **OPTIONAL COMMODITY-INDICATOR DEPENDENCY** only if an authoritative strategy needs indicators AG does not already provide.

Do not add it merely because it has many indicators. Every dependency expands the validation surface.

### 4. `nautechsystems/nautilus_trader`

Reference: https://github.com/nautechsystems/nautilus_trader  
License: LGPL-3.0.  
Decision: **ARCHITECTURAL REFERENCE ONLY** for this milestone.

Its event-driven/research-to-live architecture is useful future reference, but migrating the current project would increase scope and licensing obligations without shortening the first FX ticket path.

### 5. CCXT / Freqtrade / backtesting frameworks

Decision: **DEFER**. Current objective is FX/MT5 and the repository already has replay/validation infrastructure. Revisit for crypto or a demonstrated missing capability only.

## Recommended dependency policy

1. Prefer an AG-owned adapter contract over direct imports throughout the codebase.
2. Pin an exact upstream version/commit after evaluation.
3. Keep third-party SMC code at `ANALYSIS_AUTHORITY` only: `EXECUTION_AUTHORITY=NONE`, `PROPOSAL_OVERRIDE=NONE`, `RISK_OVERRIDE=NONE`.
4. Preserve attribution/license text where required.
5. Reject packages with ambiguous licenses.
6. Do not add an OSS dependency until deterministic fixtures demonstrate that its semantics match the selected strategy contract.
7. Do not allow an OSS data fetcher to become proposal-stage market-data authority; canonical AG provenance stays upstream.

## Shortest implementation sequence

### M0 — local authority closure

On the Windows/repository worktree, verify current branch/HEAD/tree/cleanliness and locate the actual current strategy registry/contract. Resolve exactly one EURUSD strategy/version/session pair that is permitted to generate proposal facts. If no such authority exists, Opportunity work may continue but Proposal/TradeTicket must remain blocked.

### M1 — SMC semantic spike

Without changing execution or Proposal code, build fixture parity for the minimum features actually required by the selected strategy. Compare AG expected semantics against `smart-money-concepts`; use `smc-mcp` as an independent semantic reference. Required tests include future-candle mutation/no-look-ahead, wick sweep vs close-through, equal highs/lows, forming swings, incomplete FVG, duplicated timestamps, missing candles and session boundary behavior.

Terminal result: `OSS_SMC_ADAPTER_ACCEPTED` or `OSS_SMC_ADAPTER_REJECTED`. Rejection must fall back to the smallest local implementation of only required primitives, not a general SMC engine.

### M2 — AG feature adapter

Introduce a thin AG-owned interface such as:

`CanonicalCandle[] -> AGSmcAdapter -> SMCFeatures`

No broker credentials, proposal writes, risk decisions, execution imports, HTTP mutations or MCP execution surfaces are allowed in this adapter.

### M3 — EURUSD Opportunity vertical slice

Compose canonical MT5/session facts + deterministic features into `OpportunityCandidate`. Terminal outcomes are `NO_OPPORTUNITY` or a persisted Opportunity. Do not force a signal.

### M4 — Strategy qualification + existing ProposalEligibility

Resolve the Opportunity through the exact frozen strategy authority, then call the existing eligibility boundary. Do not duplicate or weaken its checks. Terminal outcomes: `PROPOSAL_REJECTED`, `NO_TRADE`, or `PROPOSAL_READY`.

### M5 — deterministic ticket/read model

Expose the existing CanonicalProposal as the owner-facing TradeTicket read model (or add only a pure presentation mapping if the current schema is insufficient). Same semantic input must reproduce the same semantic identity. Still zero broker calls.

### M6 — three-pair expansion

Only after EURUSD passes, parameterize the same path for EURUSD, GBPUSD and USDJPY, then attach it to the existing post-Asian and post-London scheduler slots. No per-symbol copy/paste engines and no ticket quotas.

## Acceptance for first milestone

A first milestone is complete when canonical EURUSD market data deterministically reaches one valid terminal state:

- `TRADE_TICKET/PROPOSAL_READY`, or
- `NO_TRADE/NO_OPPORTUNITY`,

with provenance intact, no look-ahead contamination, no duplicated proposal authority, and zero broker mutation.

## Work that cannot be proven from this connector-only discovery

The following require the local/Windows runtime or a code-writing agent with a checked-out worktree and must remain `NOT_EVALUATED` here:

- local dirty-tree state;
- MT5 terminal/runtime behavior;
- Python package installation/import compatibility;
- focused pytest results;
- exact current strategy registry contents if not present on the inspected remote tree/path;
- real D1/H1/M15/M5 market-data acquisition;
- live scheduler execution;
- zero-call runtime sentinels around MT5 order functions.

Do not convert any of these into PASS based on documentation alone.
