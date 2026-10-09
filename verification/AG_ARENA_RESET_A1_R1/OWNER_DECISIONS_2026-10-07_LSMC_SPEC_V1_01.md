# Owner decisions, 2026-10-07 -- LSMC_SPEC_V1 batch 1 (provenance capture)

**Status:** provenance capture, not a governance record.
**Captured by:** Arena session `arena/cc31c23d-ag-profit-trading-assit` (PR #51).
**Applied to:** `docs/specs/LSMC_SPEC_V1_FROZEN.md` v1.0.0 -> **v1.0.1**.
**Spec superseded:** SHA-256 `94dd0fb9226bd078d0ee8d49125af58692fe595e0f65bc57181354f60e999a7e`.

## Why this lives under `verification/`, not `docs/governance/`

The canonical governance record for this project states its own provenance as
"approved by the owner in chat ... and **placed in the repo by the owner**"
(`OWNER_DECISIONS_2026-10-07_LSMC_ACTIONABILITY_V1.md`, 94-line version,
`67bb1a57...eb7b56`). This agent therefore did **not** self-author a
`docs/governance/` record on the owner's behalf. This file captures the decision text
verbatim so the spec has a citable, hashable provenance anchor; promoting it into
`docs/governance/` is the owner's action.

`docs/specs/LSMC_SPEC_V1_FROZEN.md` section 9.3 requires an owner signature before any
`OWNER_DECISION_REQUIRED` row may be closed. The rows in section 1 below were closed on
the strength of the instruction reproduced here.

## 1. Decision text as received (verbatim)

```text
OWNER DECISIONS on LSMC_SPEC_V1 (spec SHA-256 94dd0fb9…9a7e):

OD-13: long stop/target = bid; short stop = bid (C10-B embeds spread); short target = ask.

OD-14: ask = bid + bar MT5 spread field; fallback symbol typical spread, flag ASK_APPROXIMATED.

OD-12: outcome AMBIGUOUS_SAME_BAR; resolve with M1 if available, else excluded from ratios,
counted separately.

OD-09: rename outcomes to TARGET_REACHED / STOP_REACHED (structural, not trade results).

OD-17/18/19: gap through a level records the gap open price, flag GAP_THROUGH.

OD-02/10: non-C10 symbols use STOP_BASIS=SWEEP_EXTREME (consistent with R_AT_SEND basis).
```

## 2. How each line was applied

| Line | Rows closed | Spec section |
|---|---|---|
| OD-13 | `LSMC-OD-13`, and `LSMC-OD-16` by direct implication (the ruling resolves the exact case OD-16 posed: a bid-derived `target_c11` tested on ask) | 7.1 |
| OD-14 | `LSMC-OD-14` | 7.2 |
| OD-12 | `LSMC-OD-12` | 6.1 |
| OD-09 | `LSMC-OD-09` | 5.1 |
| OD-17/18/19 | **`LSMC-OD-17` only** -- see section 3 | 6.2 |
| OD-02/10 | `LSMC-OD-02`, `LSMC-OD-10` | 3.3, 5.4 |

## 3. Deviation from the literal instruction, and why

The line `OD-17/18/19` names three rows but states one rule: *"gap through a level records
the gap open price, flag GAP_THROUGH."* That rule fully determines `LSMC-OD-17` (a pricing
question). It does **not** determine the other two, which are different questions:

- `LSMC-OD-18` asks how to tell a **data outage** from a **true market gap**. The bar
  series cannot distinguish them, and a pricing rule does not either. Recording an outage
  at a "gap open price" would convert a measurement failure into a fabricated market move.
- `LSMC-OD-19` asks what happens when `expires_at` falls **inside a scheduled market
  closure**, where no bar exists at all -- so no gap price exists to record.

Both were therefore left **OPEN**, narrowed to their undetermined residual, and given a
recommended default in spec section 8.2 for the next sign-off batch. Closing them on a
rule that does not address them would be exactly the silent resolution this spec exists to
prevent.

## 4. Consequences surfaced, not absorbed

Applying the batch produced six findings that were **not** silently accepted. Each became
a new `OWNER_DECISION_REQUIRED` row (spec 8.2) with a recommended default:

| New row | Finding | Evidence |
|---|---|---|
| `LSMC-OD-21` | `STOP_BASIS = SWEEP_EXTREME` puts the stop exactly at the invalidation level. A close beyond the level implies a touch of it on the same bar, so `STOP_REACHED` always fires first and **`INVALIDATED` is structurally unreachable** for USDJPY, XAUUSD, BTCUSDT, ETHUSDT. | `detect.m5_opportunities` (invalidation = close beyond `sweep_extreme`); `lsmc_outcome.resolve` evaluates `stopped` before `invalid` |
| `LSMC-OD-22` | `STOP_C10` symbols carry `max(1.5 pips, 0.35 x ATR14)` of buffer; `SWEEP_EXTREME` symbols carry **zero**, so they will show a structurally higher `STOP_REACHED` rate for reasons unrelated to setup quality. | `c10_stop_policy.compute_c10_stop` vs the bare level |
| `LSMC-OD-23` | OD-14's **primary** path is unavailable: `Candle` carries only `time/open/high/low/close/volume` -- **no spread field**. The repo's own record says the exported column "is not synchronized bid/ask OHLC, is not carried by TD-8E `Candle`, and lacks a frozen point-in-time interpretation." | `src/strategy_engine/session/candles.py`; `docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3A_STATUS.md:15` |
| `LSMC-OD-24` | The primary path is itself an approximation -- one spread value per bar applied to an intra-bar extreme observed at a different instant. Flagging only the fallback implies the primary is exact. | MT5 bar schema (`spread` is a single int per bar) |
| `LSMC-OD-25` | No typical-spread constant exists for this universe. The only precedent covers EURUSD (1.0) and GBPUSD (1.4) and is labelled "not broker-verified"; the other four symbols have none. | `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml` `friction.default_spread_pips` |
| `LSMC-OD-26` | OD-12's M1 branch is **never taken today**: the LSMC pipeline carries `TIMEFRAME_MINUTES = {D1, H1, M5}` only. | `src/large_smc_watch/contract.py:21` |

## 5. Integrity note

No `FROZEN` rule from v1.0.0 was altered. This batch only closed `OPEN` rows, which spec
section 9.3 permits within the same file at a new version. In particular the owner's OD-13
ruling **confirms** the v1.0.0 §7.3 finding (the SHORT stop must stay on bid because C10-B
already embeds the spread) rather than overriding it.
