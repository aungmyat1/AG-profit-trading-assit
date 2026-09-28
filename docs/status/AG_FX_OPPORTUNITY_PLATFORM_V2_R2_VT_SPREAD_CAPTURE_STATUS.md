# AG P6-R2 — VT Markets Demo Immutable Spread Evidence Capture

**Date:** 2026-09-28 (UTC)
**Classification:** `VT_CAPTURE_OUTSIDE_TARGET_SESSION`. The capture was valid and
complete, but it ran at 19:04–19:16Z, which is outside both the POST_ASIAN and POST_LONDON
windows, so it is labelled `OTHER`.
**Base:** P6-R1 `1e265339ce5ca6ca39e8ee032d429583a77cc09b`. The collector commit is
`18ee81e`, and the capture ran on that clean lineage.
**Role:** this is broker-connected data acquisition only. It has no friction model, no
aggregation authority and no strategy economics. It is handed to Arena for independent A6
analysis.

## A5 compatibility

- `A5_SOURCE_CODE_AVAILABLE = NO`
- `A5_SEMANTIC_SOURCE = OWNER/ARCHITECT_PROVIDED_INTERFACE_CONTRACT`
- `A5_SEMANTIC_COMPATIBILITY = PASS`

**Semantics.**
- `spread_price = ask − bid` and `spread_pips = spread_price / pip_size`, computed from
  contemporaneous `symbol_info_tick` bid and ask. The bar `spread` field is never used.
- Pip sizes are EURUSD 0.0001 and GBPUSD 0.0001. They were verified before capture against
  broker metadata: `digits = 5` and `point = 1e-05` for both.

**Classification.** Each observation gets one validity code, and invalid ones are recorded,
never dropped. The codes, in precedence order:
1. WRONG_BROKER, WRONG_SERVER, WRONG_ENVIRONMENT, WRONG_SYMBOL
2. MISSING_TICK
3. NONFINITE_QUOTE, NONPOSITIVE_BID, NONPOSITIVE_ASK, ASK_BELOW_BID
4. STALE_TICK, meaning older than a frozen **60 s** tolerance
5. VALID

**Zero spread.** A zero spread is preserved and flagged (`zero_spread: true`); it is not
interpreted as zero economic friction.

**Venue isolation.** The broker, server and environment are re-read every round. Any
wrong-venue row, or any mix of venues, fails the whole capture as
`VT_CAPTURE_VALIDATION_FAILED`. `VantageMarkets-Demo` resolves to broker `UNKNOWN`, which
is WRONG_BROKER.

**Session labels.** These are the actual UTC execution windows (POST_ASIAN 07:00–11:00,
POST_LONDON 12:00–15:00, weekdays). Any other time is `OTHER` and is never relabelled.

## Capture

| Field | Value |
|---|---|
| Capture ID | `VT_SPREAD_20260928T190357Z_18ee81e6` |
| Venue | broker VT_MARKETS, server VTMarkets-Demo, environment DEMO, real MetaTrader5 5.0.5735 |
| Window | 2026-09-28T19:03:57.799Z → 19:15:53.402Z (715.6 s), session `OTHER` |
| Cadence | fixed 5.0 s, 144 rounds, EURUSD then GBPUSD back-to-back each round |
| Server clock | +3, SERVER_CONSENSUS [EURUSD, GBPUSD], effective from 2026-09-27T21:00Z |
| Collector | `AG_VT_SPREAD_COLLECTOR_V1`, lineage `18ee81e684da79f5e6dfba1ba4942e7f86094076` |
| Collector hashes | module `c7e3f1cc…b809`, script `d744d12e…b221` |

The acquisition sanity counts below are **not** aggregation authority:

| Symbol | Attempted | Valid | Missing | Invalid | Zero-spread | Min pips | Max pips | Distinct ticks |
|---|---|---|---|---|---|---|---|---|
| EURUSD | 144 | 144 | 0 | 0 | 53 | 0.0 | 0.2 | 128 |
| GBPUSD | 144 | 144 | 0 | 0 | 34 | 0.0 | 0.7 | 141 |

**Immutable raw evidence.** The files were created with exclusive-create and set read-only.
A correction requires a new capture ID.

| Artifact | SHA-256 |
|---|---|
| `artifacts/validation/VT_MARKETS_FRICTION_EVIDENCE/VT_SPREAD_20260928T190357Z_18ee81e6/EURUSD_raw.jsonl` | `1c235c6ec1216aeb8840f36a01d974d98778a15d7df9b35dcb97dad8ba83fb34` |
| `…/GBPUSD_raw.jsonl` | `b53c62af4f1ca8d44479a3ee99a11d27dc67ba9ece10088885d74a5669e5143a` |
| `…/manifest.json` | `f8bd649da3e8f81dedfaf9d1d2c46022c586beecfa1d9caf66f24849e2bbb018` |

All three hashes were re-verified independently with `sha256sum` after capture. Rows and
the manifest contain no login, account number, password or `.env` data. A grep for
secret-like terms found 0 hits, and the serializer fails closed on secret-like keys.

## Observations for Arena (not interpreted here)

- **Clock skew.** Every `tick_age_seconds` is ≥ ~4.8 s (EURUSD 4.9–24.4 s, GBPUSD
  4.8–12.3 s), even though quotes change almost every sample. This is consistent with a
  constant offset of about 5 s between the local sampling clock and the broker server
  clock. Two things follow:
  - the tick ages include that offset;
  - no sample approached the 60 s stale tolerance.

  `tick_time_msc_broker_clock` is preserved raw.
- **Repeated quotes.** Consecutive samples can repeat the same tick: EURUSD had 128
  distinct ticks across 144 samples, GBPUSD 141. Deduplication is left to the analyst.
- **Timing.** This window is in the post-New-York, pre-rollover period. It is not a
  strategy session and should not stand in for POST_ASIAN or POST_LONDON conditions.
- **Commission and slippage.** COMMISSION_STATUS = UNKNOWN, and SLIPPAGE_STATUS =
  UNKNOWN/INSUFFICIENT_SAMPLE. No trades were placed, and no Vantage assumptions were
  imported.

## Containment and platform preservation

- **Containment.** Broker order_check, order_send and every other mutation counter were 0,
  since the collector replaces those APIs with blocking counters. The collector has no
  execution, authorization, ticket, strategy or opportunity imports (static test).
  Proposal, Demo-trade and Live authority are NONE, and no trade ticket was created.
- **Frozen modules.** `git diff 1e26533..HEAD` shows no changes under `src/mt5`,
  `src/fx_opportunity`, `src/opportunity`, `strategies` or `config`, so time authority,
  MarketState, Opportunity, bindings and instrument semantics are unchanged.
- **Sealed OOS.** SEALED_OOS was not accessed, and no strategy, outcome or friction-model
  work was done.

## Tests (Windows, Python 3.14.0, 2026-09-28)

- **Collector:** `python -m pytest -q tests/test_fx_friction_capture.py` gave **29
  passed**. It covers spread arithmetic, EURUSD and GBPUSD pips, each wrong-venue and
  wrong-symbol case, missing, stale (including the boundary), ask<bid, non-finite values,
  zero-spread preservation, deterministic hashing, secret-free serialization, venue-mix
  failure, session labels and static containment.
- **Platform regression:** the fx_opportunity, opportunity, broker_time, time-authority,
  market_data and mt5_market_data suites gave **308 passed, 4 skipped**, identical to
  P6-R1.

## Handoff

`NEXT_STEP = HANDOFF_TO_ARENA_A6_FOR_INDEPENDENT_ANALYSIS`. Arena owns aggregation,
including any median, P95 or EMPIRICAL_BASE/STRESS figure and any friction contract.
Target-session captures, POST_ASIAN and POST_LONDON, are still needed for session-relevant
evidence; each gets its own new capture ID.
