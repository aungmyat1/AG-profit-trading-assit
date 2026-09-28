# AG FX Opportunity Platform V2 — Live Read-Only Verification (P6)

**Date:** 2026-09-28, 18:09–18:20 UTC (Monday; both cycle windows had closed)
**Classification:** `LIVE_MARKET_DATA_INSUFFICIENT`. EURUSD and GBPUSD are live-verified.
USDJPY live data fails closed on broker-time normalization.
**Commit verified:** `972d2e674545bb46c73af3cd98e73858e436dd63` (tree `6e82f6e2…`),
branch `platform/fx-opportunity-v2`, with a clean worktree. No production code changed.
Parent evidence: [platform V2 status](AG_FX_OPPORTUNITY_PLATFORM_V2_STATUS.md).

## Environment

| Item | Value |
|---|---|
| MT5 package | real `MetaTrader5` 5.0.5735 at `D:\ddev\AG profit trading\.venv\Lib\site-packages\MetaTrader5\__init__.py`, not the repo stub |
| Terminal | `C:\Users\aungp\AppData\Roaming\MetaTrader 5`, build 6230, connected |
| Account | server **`VTMarkets-Demo`**, trade_mode 0 (demo). The instrument contract and CLI label the broker `VANTAGE`; this naming is inconsistent with the connected server (see Findings) |
| Initialize | one attempt, `(1, "Success")`. The earlier −6 authorization block is resolved |

## Broker instrument specification (exact `symbol_info()` values)

| Symbol | Broker name | digits | point | AG pip | contract | trade_mode | Spec check |
|---|---|---|---|---|---|---|---|
| EURUSD | `EURUSD` | 5 | 1e-05 | 0.0001 | 100000 | 0 (DISABLED) | MATCH |
| GBPUSD | `GBPUSD` | 5 | 1e-05 | 0.0001 | 100000 | 0 (DISABLED) | MATCH |
| USDJPY | `USDJPY` (a `USDJPY-VIP` alias also exists) | 3 | 0.001 | 0.01 | 100000 | 0 (DISABLED) | MATCH |

There is no digits, point or naming mismatch, so the configuration needs no correction.
`trade_mode = 0` means these symbols are not tradable on this account. That does not
affect read-only use.

## Live cycle results

Commands: `python scripts/run_fx_opportunity_once.py --cycle POST_ASIAN --symbol ALL` (evaluated at
18:09:34Z) and `--cycle POST_LONDON --symbol ALL` (evaluated at 18:09:43Z). Both exited 0 and
produced exactly one result per symbol. Mode is REAL, and the application lineage is
`972d2e6…` (clean).

| Symbol | POST_ASIAN | POST_LONDON |
|---|---|---|
| EURUSD | OPPORTUNITY (READY, LONG, `LOWER_SWEEP_STRICT_PENETRATION`), ref 24/24, post 16, last closed 11:00Z, range 13.8 pips | OPPORTUNITY (READY, LONG), ref 20/20, post 12, last closed 15:00Z, range 24.7 pips |
| GBPUSD | NO_OPPORTUNITY (EXPIRED, `NO_SETUP_BY_WINDOW_END`), ref 24/24, post 16, range 20.3 pips | OPPORTUNITY (READY, SHORT, `UPPER_SWEEP_STRICT_PENETRATION`), ref 20/20, post 12, range 43.4 pips |
| USDJPY | NO_COMPATIBLE_OPPORTUNITY_STRATEGY; data `DATA_MISSING` (no MarketState) | NO_COMPATIBLE_OPPORTUNITY_STRATEGY; MarketState built (ref 20/20, post 12, range 126.3 pips); see Findings |

Every result is labelled RESEARCH_STRATEGY (`ST_ASIAN_SWEEP_5R_V1` v1.1.1), proposal
`NO_PROPOSAL_AUTHORITY`, trade ticket `NOT_CREATED`. An OPPORTUNITY is research evidence
from an economically negative baseline strategy, not a recommendation.

## Determinism (Phase 7)

I captured the exact closed candles read-only through the same `mt5.market_data.get_candles`
path, then re-evaluated twice from the captured snapshot. Each re-evaluation used the CLI's
own `evaluated_at` and its observed spread.

- **EURUSD and GBPUSD, both cycles:** replay 1 equals replay 2, which equals the live
  capture, which equals the CLI output. The match covers status, reasons, MarketState
  fingerprint, evaluation fingerprint, candidate id, decision and direction.
- **USDJPY:** the capture itself failed (see Findings), so there is no snapshot to compare.

Captured counts matched the canonical sessions exactly:
- POST_ASIAN: asian 00:00–06:00 has 24 bars, and the window 07:00–11:00 has 16.
- POST_LONDON: london_am 06:00–11:00 has 20 bars, and the window 12:00–15:00 has 12.

No M1 data was used.

## Look-ahead

Both live runs happened after the execution windows closed. The closed-bar horizon was
therefore the window end: the last bar opened at 10:45 or 14:45 and closed at 11:00 or
15:00. The forming-bar and future-mutation guard is covered by the unit suites and was not
exercised live.

## Provenance

Every live strategy result carries the following, with no field missing:
- source `mt5.market_data.get_candles:VANTAGE:<symbol>` and mode REAL;
- timeframe, session and window, and the last closed bar;
- strategy id and version;
- fingerprints for strategy config, pilot config, instrument, MarketState, evaluation and
  lineage;
- the git lineage.

## Containment

- **CLI runs:** every blocked-API counter was 0 (order_send, order_check, positions/orders,
  trade_*).
- **Determinism harness:** also recorded 0 mutation calls. Running the full platform loaded
  no `execution`, `execution_runtime`, `authorization`, `ticket_delivery`,
  `strategy_manager` or `proposal_envelope` module.
- **Persistence:** candidates were written only to the gitignored
  `journal/fx_opportunity/candidates.json`.

## Findings

1. **USDJPY broker-time normalization defect, blocking.** The USDJPY M15 history on this
   server is missing the 2026-09-14 00:00 reopen bar; the first bar after the weekend is
   00:15. That makes the 09-11→09-14 gap (2d 00:30) the largest in the 3000-bar lookback.
   `mt5.broker_time.detect_broker_utc_offset_hours` anchors on the largest gap, reads a
   00:15 reopen, and raises `OFFSET_FROM_REOPEN_AMBIGUOUS`. Market data then fails closed
   with `TIME_NORMALIZATION_ERROR`, and the error reproduced deterministically in two
   separate processes. EURUSD on the same server resolves to offset +3 from the most
   recent weekend.

   The CLI's one successful USDJPY MarketState (POST_LONDON) most likely came from a moment
   when that week was not yet in the loaded history, so it is not accepted as verification.
   `broker_time.py` is a shared, byte-exact-restored module, so it was **not patched**.
   One candidate fix is to derive the offset from the most recent weekend-sized gap
   (≥ `MIN_WEEKEND_GAP`) instead of the single largest gap. Another is to borrow the offset
   from a reference FX symbol on the same server, as the existing 24/7 fallback already
   does. Either needs separate authorization and its own tests.
2. **Broker label vs connected server.** The contract and CLI source string say `VANTAGE`,
   but the connected server is `VTMarkets-Demo`. The symbol names are identical, so data
   correctness is unaffected, but provenance names the wrong broker. The smallest
   correction is to add a `VTMARKETS` broker key (or rename it), plus a CLI `--broker`
   default, once the owner confirms which broker is intended.
3. EURUSD's observed tick spread was 0.0 pips at 18:09Z. It is recorded as observed and
   is not a decision input.

## Tests

`python -m pytest -q -p no:cacheprovider tests/test_fx_opportunity_*.py tests/test_opportunity_*.py tests/test_broker_time.py tests/test_market_data.py`
gave **263 passed, 4 skipped** (Windows, Python 3.14.0, 2026-09-28). The SEALED_OOS dataset
was not read.

## Unchanged

`ST_ASIAN_SWEEP_5R_V1`, pilot universes, `proposal_authority`, `demo_authorized`,
`live_authorized` and the USDJPY binding (NONE) are all unchanged. Proposal, Demo and Live
authority remain NONE.
