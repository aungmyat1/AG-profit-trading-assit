# AG Stage 1 — Catch-Up and Retry Policy Decision Packet V1

Dated: 2026-09-08. For owner review only. This document does not authorize, activate,
or sign any value — it presents options for a decision. Nothing here changes strategy
semantics, risk, or execution authority. Until an owner signs a value here,
`src/ticket_delivery/policy.py`'s `CatchUpPolicy` and `RetryPolicy` remain
mechanism-complete and fail closed (every evaluation refused) — see
`docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md` Addendum 2 for
the tested proof of that fail-closed behavior.

## Why this decision is needed

Two Stage 1 mechanisms exist but cannot be activated without a numeric value nobody has
signed:

1. **Missed-checkpoint catch-up** — if a scheduled run is delayed or missed (PC asleep,
   network interruption, a prior run still in progress), should a later run still
   evaluate that occurrence, and for how long after the checkpoint?
2. **Delivery retry** — if a message-only Telegram send fails with a retryable error
   (e.g. rate limiting), how many times should it retry, and with what backoff?

Both remain relevant only once `MESSAGE_DELIVERY` mode is ever activated (see
`config/ticket_delivery.yaml` — currently shipped as `DISABLED`). Catch-up also affects
whether `ARCHIVE_ONLY` mode is allowed to process a late-running cycle at all, but that
question is currently moot: this repository's real scheduled tasks
(`AG_FX_ASIAN_LONDON_SHADOW` / `AG_FX_LONDON_NEWYORK_SHADOW`, verified live via
`Get-ScheduledTask` on 2026-09-08) run every 15 minutes with `MultipleInstances:
IgnoreNew` — Windows Task Scheduler's own overlap guard already prevents concurrent
runs at the OS level, and `process_pair_result()`'s own idempotent archive/registration
means a same-cycle rerun within the next 15-minute tick converges safely without any
catch-up logic being invoked at all. Catch-up only matters for a genuinely **missed**
tick (the task didn't fire, or the machine was off) — not routine 15-minute
re-evaluation.

## FX_MAX_CATCH_UP_AGE

| Option | Value | Tradeoff |
|---|---|---|
| A (recommended) | 60 minutes | Covers a typical PC sleep/reboot or a brief network outage without risking evaluation against candles that are hours stale. At 15-minute scheduler granularity, this permits up to 4 missed ticks to still recover. |
| B (conservative) | 30 minutes | Tighter — recovers a single missed tick reliably, refuses anything longer. Lower risk of evaluating against a materially different market state than the original checkpoint intended, but less resilient to a longer outage (e.g. an overnight PC sleep). |
| C | Cycle-specific bound (e.g. remainder of that cycle's own execution window) | Most precise — ties catch-up exactly to each cycle's own `execution_window_end_utc` (already defined per pilot config), so catch-up can never outlive the window the strategy itself considers valid. Higher implementation complexity (requires reading the pilot config's window fields into the policy call, not just a flat duration) — not built this pass; would be the next refinement if the owner prefers precision over a flat bound. |

**Failure behavior while unsigned:** every `CatchUpPolicy.evaluate()` call with no
configured `max_catch_up_age` returns `allowed=False,
reason_code=CATCH_UP_POLICY_NOT_CONFIGURED` — no catch-up evaluation of any kind occurs
until this is signed. Ordinary on-time evaluation (the vast majority of real scheduled
runs) is entirely unaffected; this only gates the missed-and-recovered case.

**Does changing this later affect historical identity?** No. `FX_MAX_CATCH_UP_AGE`
only gates *whether a NEW evaluation attempt is permitted* at a given `now`; it never
alters `logical_ticket_id` (which has no time component beyond `trading_date`) or any
already-archived record. Changing the bound only affects future attempts.

## DELIVERY_MAX_ATTEMPTS

| Option | Value | Tradeoff |
|---|---|---|
| A (recommended) | 3 | Enough to absorb a transient rate-limit or single dropped connection without indefinitely hammering the Telegram API for a persistently-failing destination. |
| B (conservative) | 1 (no automatic retry) | Simplest, lowest risk of any duplicate-adjacent behavior — a retryable failure just becomes a manual/operator-visible `DELIVERY_FAILED_RETRYABLE` record requiring explicit re-trigger. Least resilient to routine transient failures. |

## DELIVERY_RETRY_BASE_DELAY / DELIVERY_RETRY_MAX_DELAY

| Option | base | max | Tradeoff |
|---|---|---|---|
| A (recommended) | 30 seconds | 5 minutes | With `DELIVERY_MAX_ATTEMPTS=3`, backoff sequence is 30s, 60s, 120s (capped well under 5 min) — bounded, predictable retry traffic, unlikely to still be retrying by the time the next 15-minute scheduler tick fires. |
| B (conservative) | 60 seconds | 5 minutes | Slower first retry, same cap — marginally lower request rate against Telegram, marginally slower recovery from a very brief blip. |

**Failure behavior while unsigned:** every `RetryPolicy.should_retry()` call with no
configured attempts/delays returns `should_retry=False,
reason_code=RETRY_POLICY_NOT_CONFIGURED` regardless of failure classification — a
retryable failure simply stays `DELIVERY_FAILED_RETRYABLE` (terminal for now, pending
either a signed policy or a manual/operator re-trigger), never silently retried with an
undefined bound. Terminal and ambiguous classifications are refused unconditionally
either way — this value never affects them.

**Does changing this later affect historical identity?** No. Retry bounds only affect
whether `claim_for_delivery()` is called again for an already-existing
`logical_ticket_id`; `delivery_attempt_id` always increments per real attempt
regardless of the configured bound, and no already-recorded attempt is ever rewritten.

## Recommended packet (for owner sign-off, not yet authorized)

```yaml
# PROPOSED -- requires explicit owner sign-off before use. Do not activate by editing
# this file alone; also requires MESSAGE_DELIVERY mode activation, which is a separate,
# later decision (WP7).
fx_max_catch_up_age_minutes: 60       # Option A
delivery_max_attempts: 3              # Option A
delivery_retry_base_delay_seconds: 30 # Option A
delivery_retry_max_delay_seconds: 300 # Option A
```

## What this packet does NOT do

- Does not activate `MESSAGE_DELIVERY` mode (`config/ticket_delivery.yaml` remains
  `DISABLED`, unchanged by this document).
- Does not modify `src/ticket_delivery/policy.py` (still mechanism-only, no default
  values).
- Does not authorize any real Telegram send.
- Does not change any strategy YAML, risk rule, or execution authority — these values
  belong to `config/ticket_delivery.yaml` (operational configuration), never to
  `strategies/*.yaml` or `strategies/registry.yaml`.

## Next step after sign-off

Once an owner selects and signs values above, a separate, later task should: (1) add
the signed values to `config/ticket_delivery.yaml` (or a dedicated policy section of
it), (2) wire `CatchUpPolicy`/`RetryPolicy` construction from that config in
`scheduler_integration.py`, (3) re-run the existing fail-closed-vs-configured test
matrix in `tests/test_ticket_delivery_policy.py` against the real signed values, and
only then consider activating `MESSAGE_DELIVERY` mode under WP7's own separately
authorized synthetic-message proof.

---

## Approval addendum (OWNER_APPROVED 2026-09-08)

The owner explicitly approved Option A for all four values above, exactly as
recommended:

```yaml
fx_max_catch_up_age_minutes: 60
delivery_max_attempts: 3
delivery_retry_base_delay_seconds: 30
delivery_retry_max_delay_seconds: 300
```

These apply **prospectively** to Stage 1 FX ticket-delivery operations from this date
forward. They do **not** alter any frozen strategy rule (entry, stop, target, risk,
session, or quota logic), and do **not** retroactively change any already-archived
record's identity -- `logical_ticket_id` has no dependency on any of these four values,
so changing them again later (a future re-sign) would only affect future evaluation
attempts, never rewrite history.

**Attempt-semantics confirmation:** `delivery_max_attempts=3` means the TOTAL number of
attempts including the initial attempt -- this is the pre-existing interpretation
already implemented in `RetryPolicy.should_retry()` (`attempt_number >= max_attempts`
refuses a further retry), not a new choice made for this approval. Under the approved
values this yields exactly: attempt 1 (initial) -> 30s delay -> attempt 2 -> 60s delay
-> attempt 3 -> exhausted (no attempt 4). Locked in by
`tests/test_ticket_delivery_policy.py`'s signed-contract-specific test section.

**The original alternatives table above is preserved unchanged** as the historical
record of what was considered before this approval -- this addendum records the
decision, it does not retroactively rewrite the options that were weighed.

**Where these values now live:** `config/ticket_delivery.yaml`'s `policy:` block
(operational configuration only -- never `strategies/*.yaml` or
`strategies/registry.yaml`), validated by
`src/ticket_delivery/scheduler_integration.py::_parse_policy()` and wired into
`CatchUpPolicy`/`RetryPolicy` via `load_integration_config()`. Demo/live execution
authorization is unchanged by this approval.

**What this approval does NOT do:** it does not authorize `MESSAGE_DELIVERY` (still
inert/unauthorized -- see `config/ticket_delivery.yaml`'s mode documentation) and does
not itself activate `ARCHIVE_ONLY` -- that is recorded as a separate, explicit
authorization in the same session (see
`docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`'s dated entry and
`docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s Addendum 5).
