# Owner Decision Packet: D_ASIAN_TICKETS_WHILE_NEGATIVE

## Current evidence

- `ST_ASIAN_SWEEP_5R_V1@1.1.1` is the active runtime version; registry records
  `logic_status: NOT_VERIFIED`, `economic_status: NOT_EVALUATED`,
  `ticket_authority: MANUAL_ONLY`, `demo_order_authority: NONE`.
- `@1.2.0` (PR #45 candidate) has an R3 blind-parity report with `logic_verified: false`
  and `economic_status: NOT_VERIFIED`; R4B (the real blind check) has not run.
- No candidate version of Asian Sweep has passed an economic/net-of-cost verification
  in evidence reviewed this mission (PR #46's own DEV screens were for different
  strategies — `SESSION_TRADE_V2` and `ST_MTF_CONTROL_SHIFT_V1` — both unrelated to
  Asian Sweep's economics).

## Options (no selection made)

- **Continue informational delivery**: keep sending Asian Sweep tickets as
  informational/manual-only, as today, while logic/economic verification proceeds.
- **Shadow-only**: stop any ticket delivery that could look actionable; record
  decisions only to an evidence log, no Telegram delivery of ticket content.
- **Suspend READY delivery**: stop delivering anything labeled `TICKET_READY` for
  Asian Sweep until `LOGIC_VERIFIED` and an economic gate both pass, while still
  allowing `NO_TRADE`/`WATCH`/`BLOCKED` status messages.

This is an owner call about acceptable operational risk during an unverified period,
not a technical correctness question — no option is recommended here.
