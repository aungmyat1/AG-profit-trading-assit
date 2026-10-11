---
class: authority
state: DESIGN
owner_reviewed: 2026-10-11
review_by: 2026-11-07
---
# OWNER DECISION — AGP-C14-AUTO-DEMO-2026-10-11

**Status:** RATIFIED BY OWNER (2026-10-11, explicit owner chat instruction). **Scope:** objective/governance only; no strategy-specific order authorization.

## Decision

The future operating model is **automatic VT Markets MT5 DEMO-only order execution** under explicit, revocable, strategy-specific standing owner authorization. This supersedes the historical Issue #47 V5 requirement for an owner confirmation on every order *within an already standing-authorized strategy scope*. Until a scope receives separate authorization, Confirm/Reject remains informational/decision capture and broker mutation remains blocked.

## Required gates before a demo order

1. Exact frozen strategy version, symbol and session pass accepted L1–L6 logical verification, including causality, deterministic replay and complete entry/SL/TP geometry.
2. Runtime strategy identity/code SHA, broker symbol/venue mapping, market data/session/DST, READY/actionability, freshness and expiry are verified.
3. Windows MT5 DEMO host acceptance and broker account identity are verified.
4. Every proposed order passes server-owned risk, spread/cost, margin, sizing, duplicate/idempotency, order-check, reconciliation and emergency-stop gates; failures block orders.
5. A separate, auditable, revocable standing DEMO authorization explicitly binds the strategy version and allowed scope. Each order is independently checked against that authorization. No AI/Telegram/watch path can mutate the broker directly.

**Not prerequisites for DEMO:** EDGE_VERIFIED/economic profitability qualification, or any mandatory 10-cycle scheduled zero-order shadow soak. Both remain optional research/operational validation, not execution-authority gates. LOGIC_VERIFIED is not evidence of profitability and does not alone authorize an order.

## Approved initial demo risk ceilings

- 0.5% of demo account equity risk per trade.
- Maximum one open position per instrument, across all strategies.
- Maximum five trades per strategy per day.
- Maximum 1% daily loss per strategy.
- Maximum 2% account-wide daily loss.

Daily reset timezone and notification-failure policy remain pending owner decisions; any unset execution-critical policy must fail closed. Do not invent defaults.

## Activation boundary

This is **policy ratification only**. It does not change `demo_authorized`, `live_authorized`, READY flags, strategy admission, broker permissions, or runtime behavior. No demo order may be placed until all remaining gates and a separate strategy-specific standing authorization are accepted. Live trading remains disabled/out of scope. Any existing implementation requiring per-order confirmation must be revised in a separate reviewed implementation PR, not bypassed here.

## Reconciliation

Issue #47 remains a historical requirements record. Its six-instrument ticket/watch coverage, deterministic terminal outcomes, venue specificity, Telegram reporting and execution auditability are preserved. Its universal per-order owner-confirmation requirement is superseded for future standing-authorized DEMO scopes. Historical G5 soak and post-soak sequencing in the 2026-10-09 objective are superseded as mandatory DEMO prerequisites; the remaining G1–G4 requirements and independently gated broker round-trip acceptance remain applicable.
