# Owner Decision Packet: D_TARGET_WORDING

## Option A — "daily trade tickets"

Implies the system should be judged by whether it produces a ticket every day for every
symbol/window. This is inconsistent with how every strategy in this repo currently
behaves: e.g. `ST_MTF_CONTROL_SHIFT_V1`'s DEV replay produced 0 signals across ~1 year
(`HTF_BIAS_NOT_ALIGNED` on 252/305 days) without that being a defect — the strategy's
own rule correctly abstained.

## Option B — "daily decision per symbol/window"

The decision space is `TICKET_READY | NO_TRADE | WATCH | BLOCKED | DATA_ERROR`.
`NO_TRADE` is a valid, correct output whenever the strategy's own rules do not qualify
a setup — it is not a failure state to be engineered away. This matches the mission's
own framing (`DAILY_DECISION = ...`, crypto target = "up to 2 qualified tickets",
not "must generate 2 trades").

This packet does not choose between A and B; it exists so the owner can pick the
wording used in future mission prompts and status reports, since A and B imply
different (and sometimes contradictory) success criteria for the same evidence.
