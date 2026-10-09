# Fixture `LSMC_PUBLICATION_GUARDS_V1` -- worked proof

Required by **owner batch 3** (2026-10-08): fixtures for `SKIPPED_ATR_NOT_READY`,
`SKIPPED_PRE_CLOSURE`, and the ATR14 floor case.

Data: `LSMC_PUBLICATION_GUARDS_V1.json`. Spec: `docs/specs/LSMC_SPEC_V2_FROZEN.md` §3.6.

A guard result is a **publication decision, not an outcome**. It never enters the §5
outcome taxonomy and is counted separately.

## Results

| Case | Guard | Input | Result |
|---|---|---|---|
| **G1** | ATR14 warm-up | 12 closed M5 bars before CHoCH (need 15) | **`SKIPPED_ATR_NOT_READY`** / `INSUFFICIENT_WARMUP` |
| **G2** | ATR14 validity | `ATR14 = 0.0` | **`SKIPPED_ATR_NOT_READY`** / `NON_POSITIVE_ATR` |
| **G3** | 1-point floor binds | BTCUSDT, `point 0.1`, `ATR14 0.2` | **`INVALIDATED`** (would be `STOP_REACHED` without the floor) |
| **G4** | Pre-closure | CHoCH close Fri 16:40 NY -> 4 bars left | **`SKIPPED_PRE_CLOSURE`** |
| **G5** | Pre-closure boundary | CHoCH close Fri 16:30 NY -> 6 bars left | **PUBLISHED** (test is `< 6`) |
| **G6** | Pre-closure, crypto | BTCUSDT, no maintenance calendar | **PUBLISHED** -- guard never fires (BACKLOG B2) |

## G3 -- the floor is load-bearing

```text
buffer = max(0.35 x ATR14, 1 x point) = max(0.35 x 0.2, 1 x 0.1) = max(0.070, 0.100) = 0.100

stop with    floor = 60000.0 - 0.100 = 59999.90
stop without floor = 60000.0 - 0.070 = 59999.93

bar  O 60000.50  H 60000.60  L 59999.92  C 59999.98

  target_hit            : high 60000.60 >= 60010.00 -> false
  stopped WITH floor    : low  59999.92 <= 59999.90 -> false   => INVALIDATED
  stopped WITHOUT floor : low  59999.92 <= 59999.93 -> true    => STOP_REACHED
  invalidated           : close 59999.98 < 60000.00 -> true
```

The floor moves the stop out of the bar's low, which is what keeps the `INVALIDATED`
window open. Without it this bar would have been recorded as `STOP_REACHED`.

## G2 -- why the guard is stricter than the code

`c10_stop_policy.compute_c10_stop` raises `INVALID_ATR` only for `atr < 0`; `atr == 0` is
accepted. Guard 2 rejects `ATR14 <= 0` outright. Before `LSMC-OD-28` a zero ATR collapsed
the buffer to zero and restored exactly the `INVALIDATED` unreachability that
`LSMC-OD-21` was raised to fix.

## G4 / G5 -- the boundary convention

`tradable_m5_remaining` counts M5 bars between `choch_close` and the next scheduled
closure, counting only bars the market is open.

```text
closure = Friday 17:00 America/New_York

choch_close 16:40  ->  4 bars  ->  4 < 6  ->  SKIPPED_PRE_CLOSURE
choch_close 16:30  ->  6 bars  ->  6 < 6 is false  ->  PUBLISHED
choch_close 16:25  ->  7 bars  ->  PUBLISHED
```

The `< 6` reading makes the `LSMC-OD-06` floor of 6 M5 bars exactly satisfiable in
tradable bars, which is the guard's purpose. Recorded as **BACKLOG B7** in case the
inclusive reading was intended.

## G6 -- crypto fails open

`watch.evaluate_snapshot` bypasses `fx_market_closed` for `CRYPTO_SYMBOLS`, and no broker
maintenance calendar exists anywhere in this repository. Guard 3 therefore evaluates
against an empty closure set and never fires for BTCUSDT/ETHUSDT. The rule is evaluable
(vacuously), so this is **BACKLOG B2**, not blocking -- but it fails **open**: an
opportunity may publish inside an unmodelled maintenance window.

## Scope

Data plus worked proof only. Wiring into `tests/` is a code-touching change, out of this
session's scope. The JSON is structured for direct use as a parametrised case table.
