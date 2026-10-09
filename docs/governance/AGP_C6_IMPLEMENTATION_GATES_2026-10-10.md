# AGP-C6 implementation gates — plan only

Status: PROPOSED. No executable code, registry flags, demo authorization, or broker mutations in this PR.

## Delivery sequence

1. **C6-A — Symbol authority:** approve canonical-to-broker mapping from fresh VT DEMO symbol_info; validate point/tick/volume/stop constraints per instrument. Fail closed on unavailable metadata.
2. **C6-B — Three logic gates:** separately verify FX Asian Sweep 1.1.2, CFD Crypto Sweep Retest, and Large-SMC 1.1.0 at L1–L6, with instrument coverage and immutable contract/engine hashes. LSMC alert-only if missing SL/TP.
3. **C6-C — Reporting:** two separate ASCII Telegram messages for WATCH/OPPORTUNITY and detailed PROPOSAL; deterministic terminal reasons, persistent deduplication, and host delivery proof. No invented READY or fill states.
4. **C6-D — Host acceptance:** read-only real MT5 data and verified symbol map; heartbeat, scheduler session/weekend coverage and Telegram receipt. At least 10 clean shadow cycles per admitted strategy, no broker mutations.
5. **C6-E — Authority implementation (disabled):** versioned per-strategy owner authorization with explicit caps, expiry/revocation and persistent kill switch; separate independent safety review. Defaults false. Owner limits and notification-failure policy pending.
6. **C6-F — Automatic demo executor (disabled):** exact ticket/strategy/SHA binding, account DEMO check at send time, duplicate protection, risk/cost/expiry checks, order_check then order_send only through execute_command; reconciliation before retry; durable append-only audit. Fail closed on unknown order result.
7. **C6-G — Telegram control plane (disabled):** verified owner identity, per-order edit/close/cancel/kill commands, replay protection, same canonical authority checks, explicit command results and audited delivery retries. Do not allow Telegram to bypass authority.
8. **C6-H — Activation acceptance:** only after owner approves caps, per-strategy demo authorization and independent tests; perform a controlled G6 DEMO-only round trip. Live stays disabled.

## Acceptance tests
- Non-DEMO, missing metadata, stale/expired/mismatched ticket, unset caps, duplicate ID, account daily loss breach and disabled strategy must all block before order_send.
- Unknown broker result must reconcile before retry, never blindly resubmit.
- Unauthorized Telegram chat, replayed edit, risk-increasing modification, invalid stop geometry and revoked authorization must reject.
- Kill switch blocks new orders while preserving owner ability to manage existing DEMO positions through independently authorized controls.
- Telegram outage has a recorded policy and auditable queued notification; never falsely mark delivery success.
- Shadow evidence must cover applicable FX sessions and crypto weekends and contain zero silent evaluations and zero broker mutations.

## Owner decisions still required
For **each** of FX, Crypto, Large-SMC: max_open_positions, max_trades_per_day, daily_loss_limit; plus account-wide exposure limit, daily reset timezone, kill-switch semantics, and Telegram failure policy. No default risk limits should be inferred from examples. Crypto target of up to two qualified tickets/day is not a forced trade count. The 0.5% OD1009-D2 value applies only within its approved scope.
