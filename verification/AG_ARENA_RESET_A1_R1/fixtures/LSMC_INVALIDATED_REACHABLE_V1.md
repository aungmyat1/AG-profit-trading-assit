# Fixture `LSMC_INVALIDATED_REACHABLE_V1` -- worked proof

Required by **`LSMC-OD-21`** (owner decision 2026-10-08): *"INVALIDATED must be reachable;
add a fixture proving it."*

Data: `LSMC_INVALIDATED_REACHABLE_V1.json` (same directory).
Spec: `docs/specs/LSMC_SPEC_V1_FROZEN.md` v1.0.2, sections 3.3 and 5.3.

## Why a fixture was needed

Under the **replaced** `LSMC-OD-02` ruling, non-C10 symbols used
`STOP_BASIS = SWEEP_EXTREME` -- the stop sat exactly on the invalidation level. Because
the stop is a **touch** and invalidation is a **close beyond**, any bar closing beyond the
level must first have touched it, and the resolver evaluates `stopped` before `invalid`:

```python
event = (AMBIGUOUS_SAME_BAR if hit and (stopped or invalid) else TARGET_REACHED if hit
         else STOP_TOUCHED if stopped else INVALIDATED if invalid else None)
```

So `INVALIDATED` was not merely rare, it was **unreachable** for USDJPY, XAUUSD, BTCUSDT
and ETHUSDT. The 2026-10-08 ruling separates the two levels with an ATR buffer.

## Setup

```text
stop_basis     = SWEEP_EXTREME_ATR_BUFFER
sweep_extreme  = 150.000
ATR14(M5)      = 0.040
buffer         = 0.35 x 0.040 = 0.014        (pip floor NOT applied, per LSMC-OD-21)

stop (LONG)    = 150.000 - 0.014 = 149.986
stop (SHORT)   = 150.000 + 0.014 = 150.014
replaced basis = 150.000 (both directions)
```

No pip or tick size is needed: the ATR term is already in price units. That is precisely
why dropping the pip floor unblocks the four symbols that never had an evidenced pip size.

## Results

| Case | Direction | Bar `O/H/L/C` | `SWEEP_EXTREME_ATR_BUFFER` | Replaced `SWEEP_EXTREME` |
|---|---|---|---|---|
| **L1** | LONG | 150.020 / 150.030 / 149.990 / 149.995 | **`INVALIDATED`** | `STOP_REACHED` |
| **S1** | SHORT | 149.980 / 150.010 / 149.970 / 150.005 | **`INVALIDATED`** | `STOP_REACHED` |
| L2 | LONG | 150.010 / 150.015 / 149.980 / 150.005 | `STOP_REACHED` | `STOP_REACHED` |
| L3 | LONG | 150.000 / 150.250 / 149.980 / 150.100 | `AMBIGUOUS_SAME_BAR` | `AMBIGUOUS_SAME_BAR` |

**L1** and **S1** are the proof: a bar closes beyond `sweep_extreme` while its extreme
stays inside the buffer, so `stopped` is false and `INVALIDATED` fires.

```text
L1  target_hit  : high 150.030 >= 150.200  -> false
    stopped     : low  149.990 <= 149.986  -> false     <-- true under the replaced basis
    invalidated : close 149.995 <  150.000 -> true
    => INVALIDATED

S1  target_hit  : low  149.970 <= 149.800  -> false
    stopped     : high 150.010 >= 150.014  -> false     <-- true under the replaced basis
    invalidated : close 150.005 >  150.000 -> true
    => INVALIDATED
```

**L2** and **L3** are controls: the buffer does not make `STOP_REACHED` unreachable, and a
genuine same-bar tie still resolves to `AMBIGUOUS_SAME_BAR` (counted separately; M1
resolution deferred to v1.1 per `LSMC-OD-26`).

All four rows were computed against the resolver's exact precedence expression, not by
hand.

## Reachability window -- and its limit

```text
LONG   INVALIDATED iff  bar.low  > sweep_extreme - buffer  AND  bar.close < sweep_extreme
SHORT  INVALIDATED iff  bar.high < sweep_extreme + buffer  AND  bar.close > sweep_extreme
```

The window width **is** `buffer = 0.35 x ATR14`. Reachability is therefore proportional to
volatility, and it is **not guaranteed**:

> `compute_c10_stop` raises `INVALID_ATR` only for `atr < 0`. At `atr == 0` the buffer is
> `0`, the window closes, and `INVALIDATED` becomes unreachable again -- exactly the
> condition `LSMC-OD-21` was raised to fix. The pip floor was the only lower bound and is
> now explicitly not applied. Raised as **`LSMC-OD-28`**; deliberately **not resolved**.

Related open rows: **`LSMC-OD-27`** (what happens when ATR is `NOT_READY`), **`LSMC-OD-29`**
(the SHORT stop here carries no spread term, unlike C10-B).

## Scope

Data plus worked proof only. Wiring this into `tests/` is a code-touching change and was
out of this session's scope (`docs/` and `verification/` only). The JSON is structured so
an implementing mission can load it directly as a parametrised case table.
