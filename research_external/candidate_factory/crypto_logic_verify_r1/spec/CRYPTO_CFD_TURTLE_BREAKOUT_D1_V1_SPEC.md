# CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1 — Frozen Candidate Spec

```
spec_id: CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1_SPEC
version: 1.0.0
frozen_at_utc: 2026-10-07T10:30:00Z
frozen_before: T3 (fixtures/property tests), T4 (differential check), T5 (blind handoff)
derived_from_candidate: OSS_CRYPTO_C001 (research_external/candidate_factory/candidates/OSS_CRYPTO_C001.json)
derived_candidate_id: OSS_CRYPTO_C001_D1_TICKETIZED_V1
status: RESEARCH_ONLY — NOT registered in strategies/registry.yaml, NOT demo_authorized,
        NOT live_authorized, grants no proposal/execution authority. This is a logic-
        verification-lane artifact only.
amendment_policy: Immutable once committed (sha256 recorded in the adjacent .sha256.txt).
                  Any rule change requires a new spec_id/version, never an edit of this file.
```

## Provenance and declared deviations from the source

Source rule (OSS_CRYPTO_C001, Turtle Trading System Two, Dennis & Eckhardt 1983, rule
extracted from `CoenTan/Donchian-Breakout-Strategy-with-Turtle-Trading-System-2`'s README,
LICENSE_UNKNOWN — rule-extraction only, no code reused or executed):

> "Entry: flat position opens LONG if today's close > max close of prior N=55 days; SHORT
> if close < min close of prior N=55 days. Exit: while long, close if close < min close of
> prior M=20 days; while short, close if close > max close of prior M=20 days. Position
> size inversely scaled to ATR(20)."

This spec makes the following **declared, explicit** translations (all `MATERIAL_DEVIATION`
from the source, consistent with G5 of the parent campaign — never silently absorbed as if
equivalent to the source):

1. **Continuous position → discrete ticket.** The source holds a position indefinitely
   until the M=20-day rolling exit. This spec instead emits ONE discrete ticket per trigger
   with a fixed initial stop and a fixed profit target (see below), because the parent
   mission's ticketability rules (`AG_CF_R1_TICKETABILITY_V1`, reused unchanged) require a
   discrete entry + fixed SL + at least one fixed TP.
2. **Stop-loss level.** The source defines no explicit stop-loss (only ATR-scaled position
   *sizing*). This spec reuses the source's own ATR(20) computation but applies it as a
   **stop distance** (`stop_atr_multiple = 2.0`), a new, explicitly-labeled addition.
3. **Entry mechanism.** The source enters "at" the breakout (implementation-dependent,
   not specified exactly). This spec uses a **LIMIT entry at the triggering D1 bar's own
   close price**, valid for a bounded number of subsequent bars (see Expiry) — a
   retest-style entry. This is an AG addition, not sourced, chosen specifically so the
   candidate has genuine, testable fill/no-fill/expiry behavior (required by T3).
4. **Session/weekend window.** The source is silent on market closure (written for
   continuously-traded futures). This spec reuses the **existing, already-operational**
   VT Markets crypto-ticket precedent (`config/v1_tickets/crypto_ticket_v2.yaml`:
   `window.kind: LOCAL_WEEKDAY`, weekdays only, "no weekend runs") rather than inventing a
   new convention: **no new ticket is emitted during the weekend window** (Saturday
   00:00 UTC through Monday 00:00 UTC); any D1 bar that closes inside that window is used
   for channel/ATR context only.
5. **Price rounding.** Stop rounds away from entry; target rounds toward entry — reusing
   the exact, already-signed convention from PR #48 (`src/host_delivery/telegram_message.py`
   display-tick-normalization fix), not a new invention.

## Context (D1 bars, VT Markets BTCUSD/ETHUSD CFD)

- `N = 55` (entry channel length, trading days/D1 bars)
- `M = 20` (retained from source for documentation only; NOT used by this spec's discrete-
  ticket exit — see deviation #1. Recorded so a future audit can see what was intentionally
  not carried forward.)
- `ATR_PERIOD = 20` (source value, reused for stop-distance, not position sizing — this
  spec does not do position sizing)
- Symbols: `BTCUSD`, `ETHUSD` (VT Markets CFD canonical symbols; CRYPTO_CFD asset class,
  NOT `BTCUSDT`/`ETHUSDT` perpetual — see `docs/decisions/D_CRYPTO_VENUE.md`)

## Entry trigger (close-confirmed only — no intrabar evaluation)

At the close of each D1 bar `t` (only once the bar is fully closed):
- `channel_high[t] = max(close[t-55 .. t-1])`
- `channel_low[t]  = min(close[t-55 .. t-1])`
- If `close[t] > channel_high[t]` → `TRIGGER_LONG`
- If `close[t] < channel_low[t]` → `TRIGGER_SHORT`
- Otherwise → `NO_TRIGGER`
- Requires at least 55 prior closed D1 bars; otherwise → `INSUFFICIENT_WARMUP` (never a
  trigger, never a fabricated decision)
- A trigger must NOT be emitted on a bar whose close time falls inside the weekend window
  (deviation #4) — such a bar is used for channel computation but its own close is
  evaluated for triggering only once the next weekday bar closes. (A trigger is never lost
  silently: if the weekend-closed bar itself would have triggered, the engine re-evaluates
  using that bar's own close value once weekday evaluation resumes, and reports
  `reason=TRIGGER_DEFERRED_WEEKEND` on the weekend bar itself.)

## Ticket construction (on TRIGGER_LONG / TRIGGER_SHORT only)

- `entry_order_type = LIMIT`
- `entry_price = close[t]` (the triggering bar's own close), rounded to `trade_tick_size`
- `atr20 = ATR(20)` computed from the 20 D1 bars ending at `t` (Wilder or simple average,
  **simple average of true range** is used here — declared choice, not sourced)
- `risk_distance = 2.0 * atr20`
- LONG: `stop_loss = entry_price - risk_distance` (rounded DOWN/away from entry, i.e. to
  the tick boundary further from entry_price); `tp1 = entry_price + 2.0 * risk_distance`
  (rounded toward entry, per deviation #5)
- SHORT: mirrored (`stop_loss = entry_price + risk_distance` rounded away; `tp1 = entry_price
  - 2.0 * risk_distance` rounded toward entry)
- No TP2 (ticketability rules only require TP2 "if the source rule defines a two-leg
  management structure" — it does not)

## Expiry (always terminates — required by T3)

- `expiry = close_time[t] + 5 trading D1 bars` (i.e. the LIMIT order is cancelled if not
  filled by the close of the 5th subsequent D1 bar). 5 is an AG-chosen, declared value
  (not sourced) chosen to give the retest-entry a bounded, testable window.
- If price never reaches `entry_price` between `t+1` and the expiry bar (inclusive): ticket
  state becomes `EXPIRED_UNFILLED`. This is a normal, valid outcome, not an error.
- If the LIMIT fills: standard R-multiple resolution against `stop_loss`/`tp1` applies
  (stop-first-on-same-bar-collision, consistent with the parent campaign's replay
  convention in `research_external/candidate_factory/replay/common.py`).
- The engine never leaves a ticket in an unresolved/pending state past its expiry bar.

## Explicit non-scope: ticket actionability / emission

This spec defines the **deterministic opportunity layer only** (PR #48's own stated
pipeline: `Strategy -> Deterministic opportunity -> ACTIONABILITY GATE -> WATCH_READY |
INFO_ONLY | EXPIRED | MISSED`). **Freshness and remaining-R gating are explicitly NOT
implemented here.** Per the mission's own instruction, any eventual ticket emission for
this candidate MUST go through `LSMC_ACTIONABILITY_POLICY_V1`
(`docs/governance/OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, SIGNED, in PR #48 —
open, not merged). **That policy is currently a signed decision document only; no
implementing state-machine code exists anywhere in this repository yet** (verified: PR #48
itself shipped only a delivery-dedup fix and a display-tick-normalization fix, not the
D1/D2 freshness/remaining-R engine listed in its own "Implementation priority" section).
This is recorded as an **unresolved upstream dependency**, not something this mission
builds a substitute for. No separate freshness/R logic is implemented by this candidate.

## Gate result

```
T2 = PASS (spec frozen; sha256 recorded in CRYPTO_CFD_TURTLE_BREAKOUT_D1_V1_SPEC.sha256.txt)
```
