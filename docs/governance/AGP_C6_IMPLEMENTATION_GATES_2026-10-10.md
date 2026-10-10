# AGP-C6 implementation gates — plan only

Status: PROPOSED. No executable code, registry flags, demo authorization, or broker mutations in this PR.

## Delivery sequence

1. **C6-A — Symbol authority:** approve canonical-to-broker mapping from fresh VT DEMO symbol_info; validate point/tick/volume/stop constraints per instrument. Fail closed on unavailable metadata.
2. **C6-B — Three logic gates:** separately verify FX Asian Sweep 1.1.2, CFD Crypto Sweep Retest, and Large-SMC 1.1.0 at L1–L6, with instrument coverage and immutable contract/engine hashes. LSMC alert-only if missing SL/TP.
3. **C6-C — Reporting:** two separate ASCII Telegram messages for WATCH/OPPORTUNITY and detailed PROPOSAL; deterministic terminal reasons, persistent deduplication, and host delivery proof. No invented READY or fill states.
4. **C6-D — Host acceptance:** read-only real MT5 data and verified symbol map; heartbeat, scheduler session/weekend coverage and Telegram receipt. At least 10 clean shadow cycles per admitted strategy, no broker mutations.
5. **C6-E — Authority implementation (disabled):** versioned per-strategy owner authorization with explicit caps, expiry/revocation and persistent kill switch; separate independent safety review. Defaults false. Owner-approved numerical limits are recorded as OD1010-C6-RISK; daily reset timezone and notification-failure policy remain pending.
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

## Approved owner numerical limits — OD1010-C6-RISK (2026-10-10)
For FX/Gold, Crypto CFD and Large-SMC: **0.5% demo account equity risk per trade**, **1 maximum open position per instrument across all strategies**, **5 maximum trades per day per strategy**, and **1% per-strategy daily loss ceiling**. Across the demo account: **2% account-wide daily loss ceiling**. Evaluate all applicable caps before any order and fail closed if required accounting, equity or daily P&L cannot be verified. These limits are ceilings, never targets. Any stricter existing broker/strategy policy continues to apply. Numerical limit approval is not per-strategy execution authorization; `demo_authorized=false` and `live_authorized=false` remain in force unless separately and explicitly changed under the applicable authorization process.

## Remaining owner decisions and prerequisites
Daily reset timezone, Telegram delivery failure behavior, and kill-switch semantics remain PENDING_OWNER; no default values should be invented. The one-position-per-instrument cap applies across all strategies on the demo account. A separate per-strategy DEMO_AUTHORIZED decision and all independent evidence gates are still mandatory. No demo/live flags may be enabled by this documentation change.
