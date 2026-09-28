# AG FX Opportunity Platform V2 — P6-R1 Server-Time Authority + VT Markets Identity

**Date:** 2026-09-28 (UTC). Live runs ran at 18:37Z; both cycle windows had closed.
**Classification:** `LIVE_FX_OPPORTUNITY_3PAIR_VERIFIED`
**Base:** `0abddd520ea909bc4f19f644a2fc04269a2bc02d` (P6). The live runs used code at
`3bfa46a` (clean worktree), branch `platform/fx-opportunity-v2`.
Predecessor: [P6 live verification](AG_FX_OPPORTUNITY_PLATFORM_V2_LIVE_VERIFICATION_STATUS.md)
(`LIVE_MARKET_DATA_INSUFFICIENT`).

## What was wrong

1. `mt5.market_data` took the broker's UTC offset from `broker_time.detect_broker_utc_offset_hours`.
   That function relies on the single **largest** gap in the requesting symbol's own
   history. On VTMarkets-Demo, USDJPY is missing the Monday 2026-09-14 00:00 bar, so the
   gap to the 00:15 bar became the largest. The resulting 00:15 "reopen" does not resolve
   to a whole-hour offset, so the symbol failed closed.
2. Live provenance named the broker `VANTAGE`, while the connected, owner-confirmed server
   is VT Markets (`VTMarkets-Demo`).

## Server-time authority design (`src/mt5/time_authority.py`, pure)

- **Observations.** Every weekend-sized gap (≥ 40h) yields one reopen observation.
  - If the reading does not resolve to a whole-hour offset, it is **rejected as evidence**,
    so a missing bar never redefines the clock.
  - The raw history is never mutated or filled.
- **Effective periods.** A `TimeAuthorityPeriod` is keyed by (broker, server, week). The
  week runs from the true-UTC NY-17:00 reopen to the next reopen, and each period carries
  its own UTC offset.
  - DST is therefore derived per period rather than hardcoded. Tests show +2 in winter and
    both US transitions: 2026-03-08 (+2→+3) and 2026-11-01 (+3→+2).
  - A period never spans past its own week. An unobserved week stays uncovered and fails
    closed.
  - Broker readings map through the period that had already reopened, which resolves the
    DST-boundary ambiguity.
- **Authority order in `market_data.server_time_timeline`:**
  1. **Explicit configuration:** none exists in trusted config, so this level is unused.
  2. **Previously validated periods:** reused from a per-(broker, server) cache.
  3. **Consensus:** evidence from the requesting symbol plus the reference FX symbols on
     the same terminal connection (EURUSD, GBPUSD) is resolved per week.
  4. **Symbol-local:** the requesting symbol's own reopens, as a bounded fallback.
- **Failure handling.**
  - If valid observations disagree within a week, or disagree with an already-validated
    period, the result is `TIME_AUTHORITY_CONFLICT` (no majority vote).
  - With no evidence, or no server identity, the result is `TIME_AUTHORITY_UNAVAILABLE`.
- **Consumers.** `get_candles` converts both request bounds and every bar through their
  own period. `get_latest_candles` and `get_tick` use the current period, which is no
  longer cached per symbol for the whole process lifetime.
- **Legacy function kept.** `detect_broker_utc_offset_hours` is unchanged for the
  acquisition scripts, and its USDJPY failure is pinned in a regression test.

## Broker identity

- **New canonical entry.** `config/instruments/fx_opportunity_instruments.yaml` gains a
  `brokers:` section: `VTMARKETS` → `VT_MARKETS`, servers `[VTMarkets-Demo]`, DEMO. It
  also adds VTMARKETS symbol mappings, all read-only verified.
- **VANTAGE kept.** Its entries trace to genuine Vantage evidence in `config/mt5.yaml` and
  are kept, with no verified server.
- **CLI.**
  - `--broker` now defaults to `VTMARKETS`.
  - A non-Demo account is refused as `ACCOUNT_ENVIRONMENT_NOT_VERIFIED_DEMO`, and a server
    not listed for the broker as `BROKER_SERVER_MISMATCH`, both before any data read.
  - Output carries `broker`, `server` and `account_environment`, never the login.

## Live verification (VTMarkets-Demo, real MetaTrader5 5.0.5735, 3 × initialize total)

| Symbol | Broker symbol | digits / point / pip | POST_ASIAN | POST_LONDON |
|---|---|---|---|---|
| EURUSD | EURUSD | 5 / 1e-05 / 0.0001 | OPPORTUNITY (LONG); MarketState 24/24+16, last close 11:00Z | OPPORTUNITY (LONG); 20/20+12, last close 15:00Z |
| GBPUSD | GBPUSD | 5 / 1e-05 / 0.0001 | NO_OPPORTUNITY (EXPIRED); 24/24+16 | OPPORTUNITY (SHORT); 20/20+12 |
| USDJPY | USDJPY | 3 / 0.001 / 0.01 | **NO_COMPATIBLE_OPPORTUNITY_STRATEGY; MarketState BUILT 24/24+16** | **NO_COMPATIBLE_OPPORTUNITY_STRATEGY; MarketState BUILT 20/20+12** |

- **Server clock (every result).** Broker VT Markets, server `VTMarkets-Demo`, effective
  from 2026-09-27T21:00Z (NY 17:00 EDT). Offset +3, source `SERVER_CONSENSUS` over
  EURUSD and GBPUSD. The clock is part of each MarketState fingerprint.
- **Source string.** `mt5.market_data.get_candles:VT_MARKETS:VTMarkets-Demo:<symbol>`.
- **Determinism.** The closed candles were captured read-only and re-evaluated twice from
  the snapshot, using the CLI's `evaluated_at`, observed spread and server clock. The CLI
  output, the live capture and both replays are identical for all 3 symbols in both
  cycles, covering the MarketState fingerprint, evaluation fingerprint, status and
  candidate id. EURUSD and GBPUSD candidate ids equal P6's, so identity is stable. Their
  MarketState fingerprints changed from P6 only because of the new server_clock and the
  instrument-contract fingerprint.
- **Containment.** Every mutation counter was 0 across the 2 CLI runs and the harness. No
  execution, authorization, ticket_delivery, strategy_manager or proposal_envelope module
  was loaded. Proposal, Demo and Live authority are NONE, and the trade ticket was
  NOT_CREATED.
- **Unchanged.** Strategy (runtime `ST_ASIAN_SWEEP_5R_V1` 1.1.1; research outcome contract
  1.2.0-CANDIDATE, not relabelled), pilot universes and USDJPY binding (NONE).
  SEALED_OOS was not accessed.

## Tests (Windows, Python 3.14.0)

- **Focused:** instruments, market_state, runner, scanner, containment, opportunity,
  broker_time, broker_time_authority, market_data and mt5_market_data suites: **308
  passed, 4 skipped**.
- **Full:** `python -m pytest -q -p no:cacheprovider` gave **618 passed, 4 skipped, 1
  failed**. The failure is the same baseline-unrelated `api.app` one: `src/api/app.py` is
  absent at the restore base.

## Known limits

- **Cache hits skip the requester's own check.** When a validated period is reused from
  the cache, the requesting symbol's own reopen for that week is not re-checked against
  it. The USDJPY 2026-09-27 reopen was therefore consumed, not independently confirmed,
  in the live run.
- **Whole-hour delays conflict by design.** A missing-bar delay of a whole hour would read
  as a different offset. It raises `TIME_AUTHORITY_CONFLICT` rather than being explained
  away.
- **`get_latest_candles` uses one offset.** It maps a whole multi-week request through the
  current period, which matches its prior behavior. `get_candles` is period-exact.
