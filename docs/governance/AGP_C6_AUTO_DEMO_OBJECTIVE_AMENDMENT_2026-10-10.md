---
class: authority
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# AGP-C6 — Three-lane strategy qualification and governed automatic demo trading

Status: HISTORICAL PROPOSAL — superseded on demo sequencing by ratified C14 (2026-10-11). Retained for traceability; it is not current authority or execution authorization. C14 supersedes the proposed mandatory 10-cycle zero-order soak, post-soak authorization sequence, and per-order Confirm requirement. The proposal's L1–L6, runtime, READY, host, risk, broker, audit and separate strategy-specific authorization safeguards remain relevant to implementation, subject to the current objective and owner-approved policy.

Base: main 8f803e0 (PR #107 merged). Preserve the proposal text below as the historical record of the 2026-10-10 request.

## Target objective
Qualify exactly three strategy lanes: (1) FX and gold daily session tickets using ST_ASIAN_SWEEP_5R_V1@1.1.2, (2) VT Markets BTCUSD/ETHUSD CFD tickets using ST_CRYPTO_CFD_SWEEP_RETEST_V1, and (3) six-instrument Large-SMC watch and eligible trades using ST_LARGE_SMC_V1@1.1.0. Each lane must pass L1–L6 with explicit per-instrument coverage and versioned contract/engine hashes. Large-SMC without validated entry, stop and target remains ALERT_ONLY, never auto-traded.

## Required sequential gates, independently per strategy
1. LOGIC_VERIFIED L1–L6 and exact strategy/engine identity; never infer EDGE_VERIFIED.
2. Host acceptance with approved AGP-C2-SYMMAP, live VT Markets MT5 DEMO data, geometry, risk and cost validation, deterministic terminal states and Telegram proof.
3. At least 10 clean scheduled shadow cycles per admitted strategy, zero broker mutations, zero silent outcomes, zero duplicate messages; cover relevant FX sessions and crypto weekends.
4. Separate owner-recorded per-strategy DEMO_AUTHORIZED after G1–G5; never infer from this objective, a Telegram Confirm, or logic verification. No live trading.
5. AUTO_DEMO_EXECUTION only when the exact immutable ticket, strategy version, code SHA, broker symbol, expiry, account identity, risk and cost checks pass at send time. Execute only through assistant.commands.execute_command() and canonical execution authority, with broker order_check before order_send. Reject stale, duplicate, mismatched, incomplete and unauthorized orders; reconcile uncertain sends before retry.

## Owner-approved DEMO numerical limits — OD1010-C6-RISK (2026-10-10)
Risk per trade is capped at 0.5% of demo account equity. Maximum open positions: 1 per instrument across all strategies. Maximum trades: 5 per day per strategy. Daily loss limit: 1% per strategy; account-wide daily loss limit: 2%. These are numerical ceilings, not targets or trade instructions. This approval does not authorize any strategy to execute: `demo_authorized=false` and `live_authorized=false` remain in force, and separate per-strategy DEMO_AUTHORIZED approval plus all required gates are mandatory. Daily reset timezone and notification-failure behavior remain pending owner policy; unset required operational policy blocks execution. FX manual-ticket reference policy OD1009-D2 (`risk_pct: 0.5`, `cost_warn_R: 0.10`, `cost_block_R: 0.25`) applies only within its stated scope and approved strategy risk contract. Crypto CFD spread/cost and contract sizing must be validated independently; perpetual authority never transfers.

## Telegram reporting and owner controls
Send a mobile-friendly ASCII WATCH/OPPORTUNITY alert separately from a detailed TRADE PROPOSAL. On every attempted automatic order, send a correlated pre-trade ticket and post-result report (success, reject or uncertain) with ticket_id, strategy@version, code SHA, broker symbol, side, entry, SL, TP, R, risk%, estimated cost R, expiry, account DEMO identity, broker order/position ID if available, fill price, slippage and timestamp. Never silently claim a fill; if Telegram fails, persist an auditable pending-delivery record and enforce the owner-approved notification-failure policy before any further automatic order.

Owner Telegram controls (verified allowlisted identity only): modify SL, modify TP, partial close, close, cancel pending, halt new auto orders, and revoke strategy authorization. Every command must bind the immutable ticket and exact broker order/position identity, reject replay/duplicate/stale requests, recheck DEMO account and applicable geometry, risk, volume and broker constraints, route only through canonical execution authority, and return an explicit audited success/reject/uncertain outcome. Never permit silent risk increases; any owner override requires separate explicit command-specific authorization and must respect hard account caps. A Telegram or local kill switch halts all new orders fail-closed; existing positions remain owner-managed, with close controls separately available. No Telegram chat can directly mutate broker state.

## Invariants and acceptance
Owner authorizes each strategy for DEMO; qualified tickets may then place demo orders automatically and are reported to Telegram for review/edit/close. This replaces per-entry Confirm only after the new authority is implemented and explicitly activated; until then existing Confirm/Reject remains decision capture only. EDGE_VERIFIED=false is visible on PRE-EDGE tickets. LIVE_AUTHORIZED remains false/out of scope. Every action appends a durable audit chain ticket -> decision -> order_check -> send -> broker reconciliation -> Telegram notification -> edits -> close. G6 requires a separately authorized demo round trip with one correlated order and audit record. No code/config/authorization flags change in this proposal.

## Governance decisions to record before activation (historical proposal text)
At proposal time, the suggested decision ID was OD1010-OBJ-AUTO-DEMO and C14 approval was pending. C14 was subsequently ratified by the owner on 2026-10-11, superseding this proposal's demo sequencing. OD1010-C6-RISK numerical limits are approved; notification-failure behavior remains PENDING_OWNER. Preserve OD1009 decisions and the 2026-10-09 ratification history. Implementation PRs must be separately reviewed; neither this historical proposal nor numerical limit approval alone authorizes execution.
