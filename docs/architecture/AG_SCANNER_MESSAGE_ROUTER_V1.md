---
class: design
state: DESIGN
owner_reviewed: null
review_by: 2027-01-06
---
# AG Scanner Message Router V1

## Contract and authority

The router is an additive presentation adapter downstream of Scanner V1 and Checklist
V1.1. It consumes their explicit final decision, opportunity, governance, and eligibility
fields. It does not inspect prose to infer eligibility and does not re-evaluate strategy,
economic, data, or risk gates. Canonical timestamps remain UTC.

Stable message types are `INFORMATIONAL_TICKET`, `OPPORTUNITY_ALERT`,
`NO_TRADE_SUMMARY`, `BLOCKED_ALERT`, and `SYSTEM_STATUS`. The typed common model is
`session_scanner.message_models.NormalizedMessage`; fields unavailable upstream remain
null. Upstream reason codes are retained.

- **INFORMATIONAL_TICKET** presents upstream proposal geometry, including strategy-ready
  geometry blocked by governance. **INFORMATIONAL_TICKET != BROKER ORDER.**
- **OPPORTUNITY_ALERT** presents an observed condition and its supplied POI/path/expiry.
  **OPPORTUNITY_ALERT != TRADE SIGNAL AUTHORIZATION.**
- **NO_TRADE_SUMMARY** reports a non-trade final decision without inventing geometry.
- **BLOCKED_ALERT** makes a fail-closed upstream gate visible without upgrading it.
- **SYSTEM_STATUS** is a separate non-trading channel; trading geometry is stripped.

`READY`, `SETUP_VALID`, `READY_FOR_PROPOSAL`, and `EXECUTION_AUTHORIZED` remain distinct.
At this project stage normalized `execution_authorized` is unconditionally false. A
strategy `READY` with ambiguous risk remains an informational ticket with an explicit
governance block and `proposal_eligible = false`. Large-SMC `NOT_EVALUATED` economic
status remains visible and grants no proposal authority.

## Formatting and expiry

`telegram_formatter.format_telegram` is a pure string formatter downstream of routing.
It always labels trading messages `INFORMATIONAL ONLY` and `NOT A BROKER ORDER`; it has no
transport, credential, broker, or execution dependency. Telegram may show expiry in UTC
and MMT (UTC+06:30) while the model retains the canonical UTC datetime. Expired
opportunities are prominently rendered `EXPIRED — NO LONGER CURRENT`, without changing
the upstream strategy state.

The existing Telegram sender, UI, or another output can consume the formatter result as
a separate transport step. Unit tests intentionally do not send Telegram messages.
