# OWNER DECISION RECORD — 2026-10-07

- Owner: Aung
- Status: SIGNED
- Provenance: approved by the owner in chat on 2026-10-07 and placed in the repo by the owner.
- Supersedes: the open owner decisions listed in PR #48 (audit/v1-followup-2026-10-07).
- Scope: delivery/actionability and governance only. NO change to strategy market logic.

## Principle

Signal validity (strategy) and actionability (delivery) are separate layers.
A signal may be VALID at trigger time and NOT ACTIONABLE at send time. Both facts are persisted.

Pipeline: Strategy -> Deterministic opportunity -> ACTIONABILITY GATE -> WATCH_READY | INFO_ONLY | EXPIRED | MISSED

## Canonical names (these resolve any wording differences in earlier chat pastes)

- Opportunity states: `PENDING_BAR_CLOSE`, `FRESH`, `STALE`, `EXPIRED`, `MISSED_DOWNTIME`
- Delivery outcomes: `WATCH_READY`, `INFO_ONLY_STALE`, `INFO_ONLY` (with a reason), `MISSED_NOT_ACTIONABLE` (digest only)
- R fields: `R_AT_TRIGGER`, `R_AT_SEND`
- Price fields: `reference_price`, `send_price`, plus `send_price_side` (state which of bid/ask/mid is used)
- Time fields: `trigger_bar_close_ts`, `send_ts`
- Policy config: `LSMC_ACTIONABILITY_POLICY_V1`. This is versioned operational config, NOT strategy YAML.
- `min_remaining_r` lives ONLY in `LSMC_ACTIONABILITY_POLICY_V1`.

## Policy: LSMC_ACTIONABILITY_POLICY_V1

**D1 — Freshness: APPROVED**
- `freshness_age = send_ts - trigger_bar_close_ts`
- READY only if `freshness_age <= 2 x trigger_timeframe`, counted in completed bars.
- Otherwise the outcome is `INFO_ONLY_STALE`.

**D2 — Remaining R: APPROVED (modified)**
- Persist `reference_price`, `send_price`, `R_AT_TRIGGER` and `R_AT_SEND`.
- READY requires `R_AT_SEND >= min_remaining_r`.
- `min_remaining_r = 1.5`. This is the owner-signed initial value and can be changed by the owner in config without a strategy version change.
- If the gate fails, the outcome is `INFO_ONLY` with reason `INSUFFICIENT_REMAINING_R`, and both R values are shown.

**D3 — Downtime recovery: APPROVED**
- Never emit a historical READY after downtime.
- Send one `MISSED_NOT_ACTIONABLE` digest after a restart.
- The digest is deduplicated, so the same missed list is never sent twice.

**D4 — State semantics: APPROVED**
- If a required bar has not closed, the state is `PENDING_BAR_CLOSE`. The opportunity is re-evaluated deterministically when that bar closes.
- `STALE` means valid information that is now too old. It means nothing else.

**D5 — Price normalization: APPROVED**
- In the current shadow/advisory lane, normalization is display-only.
- Before Demo, executable normalization (tick size and stop-distance validation) requires a new frozen execution-compatible identity, and the affected geometry must be re-verified.

**D6 — ST_ASIAN_SWEEP_5R_V1: APPROVED**
- READY authority is OFF until logical verification (R4B) passes.
- SHADOW, DIAGNOSTIC and INFO_ONLY outputs are allowed if clearly labelled.

**D7 — Correlation: APPROVED (modified)**
- Add `CORRELATION_CLUSTER_ID` and `CORRELATED_EXPOSURE` (e.g. `USD_SHORT`; `USD_SHORT_SENSITIVE` for XAUUSD).
- Classify and warn only. No automatic suppression or selection.
- Ranking is INFORMATIONAL. Gate order: validity > freshness > geometry > remaining R > costs > correlation > rank.
- Target metric for later: `effective_remaining_R = R_AT_SEND - normalized_friction_cost`.

**D8 — SESSION_TRADE_V1 Demo: NOT AUTHORIZED**
- 10 consecutive reconciled sessions is a HOST-ACCEPTANCE gate only.
- `DEMO_AUTHORIZED` requires ALL of the following:
  - LOGIC_VERIFIED
  - explicit signed strategy Demo authority
  - owner-required economic qualification
  - immutable ticket identity
  - Telegram `message_id`
  - approval command identity
  - `attempt_id`
  - freshness / current price check
  - valid risk sizing
  - spread/cost gate
  - duplicate protection
  - idempotency
  - `order_check`
  - same-turn owner confirmation
  - Demo-account proof
  - reconciliation
  - Live statically disabled

## Implementation priority

| Priority | Item |
|---|---|
| P0 | `PENDING_BAR_CLOSE`, freshness cutoff, no catch-up READY |
| P0 | Persist trigger/send timestamps and send-time price |
| P0 | Compute and expose `R_AT_SEND` |
| P1 | LSMC expiry/outcome resolver; duplicate and late-alert fixes |
| P1 | Correlation cluster warning and informational ranking |
| P1 | Telegram `message_id` -> owner command -> `attempt_id` audit chain (extend `src/ticket_delivery/attempt_journal.py`) |
| P2 | Executable price normalization and Demo safety gates |
| P2 | Host reconciliation campaign |
