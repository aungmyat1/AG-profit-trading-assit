# OWNER DECISION RECORD — 2026-10-07
Owner: Aung | Status: SIGNED | Supersedes: open decisions listed in PR #48
Scope: delivery/actionability + governance only. NO strategy market-logic change.

## Principle
Signal validity (strategy) and actionability (delivery) are separate layers.
A signal may be VALID at trigger and NOT ACTIONABLE at send; both facts are persisted.
Pipeline: Strategy -> Deterministic opportunity -> ACTIONABILITY GATE -> WATCH_READY | INFO_ONLY | EXPIRED | MISSED

## Policy: LSMC_ACTIONABILITY_POLICY_V1 (operational config, versioned, not strategy YAML)
D1 FRESHNESS — APPROVED
   freshness_age = send_ts - trigger_bar_close_ts
   READY iff freshness_age <= 2 x trigger_timeframe (completed bars)
   else INFO_ONLY_STALE
D2 REMAINING R — APPROVED (modified)
   Persist: reference_price, send_price, R_AT_TRIGGER, R_AT_SEND
   READY requires R_AT_SEND >= min_remaining_r
   min_remaining_r = 1.5 (owner-signed initial value; owner-changeable config)
   Fail => INFO_ONLY, reason INSUFFICIENT_REMAINING_R, both R values shown
D3 DOWNTIME RECOVERY — APPROVED
   Never emit historical READY. One MISSED_NOT_ACTIONABLE digest after restart.
D4 STATE SEMANTICS — APPROVED
   States: PENDING_BAR_CLOSE | FRESH | STALE | EXPIRED | MISSED_DOWNTIME
   Unclosed required bar => PENDING_BAR_CLOSE; deterministic re-evaluation on close.
   STALE = valid information that is now too old (only).
D5 PRICE NORMALIZATION — APPROVED
   Current shadow/advisory lane: display-only.
   Before Demo: executable normalization (tick size, stop-distance validation)
   = new frozen execution-compatible identity + re-verify affected geometry.
D6 ST_ASIAN_SWEEP_5R_V1 — APPROVED
   READY authority OFF until logical verification (R4B) passes.
   SHADOW / DIAGNOSTIC / INFO_ONLY allowed if clearly labelled.
D7 CORRELATION — APPROVED (modified)
   Add CORRELATION_CLUSTER_ID + CORRELATED_EXPOSURE (e.g. USD_SHORT, USD_SHORT_SENSITIVE for XAUUSD).
   Classify and warn only. No automatic suppression or selection.
   Ranking is INFORMATIONAL; gate order: validity > freshness > geometry > remaining R > costs > correlation > rank.
   Target metric (later): effective_remaining_R = remaining_R - normalized_friction_cost.
D8 SESSION_TRADE_V1 DEMO — NOT AUTHORIZED
   10 consecutive reconciled sessions = HOST-ACCEPTANCE gate only.
   DEMO_AUTHORIZED requires ALL: LOGIC_VERIFIED; explicit signed strategy Demo authority;
   owner-required economic qualification; immutable ticket identity; Telegram message_id;
   approval command identity; attempt_id; freshness/current price; valid risk sizing;
   spread/cost gate; duplicate protection; idempotency; order_check; same-turn owner
   confirmation; Demo-account proof; reconciliation; Live statically disabled.

## Implementation priority
P0 PENDING_BAR_CLOSE, freshness cutoff, no catch-up READY
P0 persist trigger/send timestamps + send-time price
P0 compute + expose R_AT_SEND
P1 LSMC expiry/outcome resolver, duplicate/late-alert fixes
P1 correlation cluster warning + informational ranking
P1 Telegram message_id -> owner command -> attempt_id audit chain
P2 executable price normalization + Demo safety gates
P2 host reconciliation campaign
