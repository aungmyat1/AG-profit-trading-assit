# AG FX Opportunity Platform V2 — Status

**Date:** 2026-09-28 (UTC)
**Classification:** `LIVE_MT5_AUTH_BLOCKED_PLATFORM_READY`
**Branch:** `platform/fx-opportunity-v2` (worktree `D:/ddev/AG-platform-fx-opportunity-v2`)
**Base:** `restore/fx-opportunity-foundation-v1` @ `6c574309fe2ded1688ec6a2d85faec672c4ed247`
(tree `111b731717238029c1a410856474ac3b8fa80b2a`; merge-base with `origin/main` `4bbba31`)

This change generalizes the capability-zero EURUSD Opportunity slice
([foundation V1](AG_FX_OPPORTUNITY_FOUNDATION_V1_STATUS.md)) to EURUSD, GBPUSD and USDJPY.
It adds no strategy change, promotion, authorization, proposal formation, ticket, scheduler
or execution path. It does not change strategy authority. `ST_ASIAN_SWEEP_5R_V1` is still
research-only (V1.2 candidate: NEGATIVE_BASELINE), and Proposal, Demo and Live authority are
all NONE.

## Architecture

```
MT5 read-only M15 candles (or injected REPLAY fixtures)
  -> closed-bar filter (close <= now)                  fx_opportunity.market_state.closed_only
  -> MarketState (strategy-neutral facts + fingerprint) fx_opportunity.market_state
  -> [symbol bound for the cycle?]
       yes -> frozen ST_ASIAN_SWEEP_5R_V1 v1.1.1 -> OpportunityCandidate (RESEARCH_STRATEGY)
       no  -> NO_COMPATIBLE_OPPORTUNITY_STRATEGY (MarketState still observed)
  -> optional CandidateStore persistence (existing, atomic, idempotent)
  -> STOP: Proposal = NO_PROPOSAL_AUTHORITY, TradeTicket = NOT_CREATED
```

| Component | Path |
|---|---|
| Instrument contract | `config/instruments/fx_opportunity_instruments.yaml`, `src/fx_opportunity/instruments.py` |
| MarketState | `src/fx_opportunity/market_state.py` |
| Runner, generalized | `src/fx_opportunity/runner.py` |
| Three-pair scanner | `src/fx_opportunity/scanner.py` |
| Manual CLI | `scripts/run_fx_opportunity_once.py` |

## Audit of the V1 slice (before any change)

| Class | Components |
|---|---|
| SYMBOL_GENERIC | `opportunity/*` (contracts, funnel engine, candidate store), `post_asian_pilot.snapshot/decision`, `strategy_engine` (ER_ONLY_V2; scale-invariant, no pip constant used in evaluation), `session_clock`, runner closed-bar filter and fingerprints |
| EURUSD_SPECIFIC | `runner.SLICE_SYMBOLS = ("EURUSD",)`, the CLI default symbol. `max_range_pips_eurusd` in the strategy YAML is loaded but unused by evaluation |
| STRATEGY_SPECIFIC | runner scope check (id and version 1.1.1), `AsianSweepFunnelAdapter`, `ASIAN_SWEEP:` event id, pilot universes `[EURUSD, GBPUSD]` |
| BROKER_SPECIFIC | CLI MT5 attach, stub detection, and the `config/mt5.yaml` VANTAGE symbol_map (EURUSD and GBPUSD verified; USDJPY absent) |
| DATA_SOURCE_SPECIFIC | `mt5.market_data.get_candles` (broker UTC-offset normalization), `scripts/replay_fx_opportunity.py` |

## Per-symbol result

| Symbol | Digits / point / pip | Strategy binding (both cycles) | Platform state |
|---|---|---|---|
| EURUSD | 5 / 0.00001 / 0.0001 | pilot universe ∩ strategy instruments | OPPORTUNITY / NO_OPPORTUNITY / DATA_UNAVAILABLE |
| GBPUSD | 5 / 0.00001 / 0.0001 | pilot universe ∩ strategy instruments | same as EURUSD |
| USDJPY | 3 / 0.001 / 0.01 | **none**: USDJPY is in the strategy's instruments but not in either pilot universe | `NO_COMPATIBLE_OPPORTUNITY_STRATEGY` + MarketState |

The platform does not widen a pilot universe to bind USDJPY. Doing so would be a
strategy/pilot decision, which is outside this mission. The USDJPY broker mapping is
recorded as `verified: false`. Before any data is read, the live CLI cross-checks
`symbol_info().digits/point` read-only and fails closed with `INSTRUMENT_SPEC_MISMATCH`.

## Guarantees and evidence

- **MarketState:** holds facts only. It carries the reference box and range in instrument
  pips, post-session extremes, whether reference liquidity was taken, the last closed bar,
  the spread (only when it was actually observed), provenance and a fingerprint. A test
  asserts that no field is an authority, direction, order, ticket or broker field.
- **Look-ahead:** for each of the three symbols, adding or mutating candles at or after
  the forming bar leaves the MarketState, its fingerprint and the Opportunity summary
  unchanged. `build_market_state` rejects a forming bar. The first implementation counted
  dropped forming bars inside MarketState, which let the *presence* of future bars change
  its fingerprint. The mutation test caught this, and the count now lives only in
  provenance diagnostics.
- **Determinism:** identical closed data and configuration produce an identical
  MarketState, Opportunity summary and three-pair scan output.
- **Provenance:** records source, mode (REPLAY/REAL), timeframe, session and windows, the
  last closed bar, the reference and post-session fingerprints, and the strategy id and
  version. It also records fingerprints of the strategy config, pilot config and
  instrument, plus market_state and evaluation fingerprints. The application lineage (git
  HEAD, `+dirty`) is recorded but kept out of identity and fingerprints. REPLAY and REAL
  states have distinct fingerprints.
- **Persistence:** reuses `opportunity.candidate_store` unchanged. Candidate identity is
  per (strategy, cycle, symbol, trading date). Re-polling after a restart appends no
  transition, and an unbound symbol persists nothing.
- **Containment:** `execution/`, `authorization/` and `ticket_delivery/` are absent. Four
  checks cover it:
  - a static AST scan of `src/fx_opportunity/*` and the CLI finds no mutation-API call and
    no execution, strategy_manager or scheduler import;
  - a fresh-interpreter check confirms the transitive imports stay clean;
  - a runtime sentinel runs three pairs × two cycles × five phases × REPLAY/REAL and
    records 0 mutation calls;
  - the CLI replaces order/position/trade APIs with blocking counters.
- **MT5 stub:** when the repo-root `MetaTrader5.py` shadows the real package, the CLI
  reports `MT5_REAL_PACKAGE_UNAVAILABLE` for every symbol and reads no data (tested in a
  subprocess).

## Live MT5

One read-only attempt was made at 2026-09-28T17:35:51Z:
`python scripts/run_fx_opportunity_once.py --cycle POST_ASIAN --symbol ALL` using the real
package (`.venv` MetaTrader5 5.0.5735).

- **Result:** `initialize()` failed with error `-6` (Terminal: Authorization failed). All
  three symbols reported `LIVE_MT5_AUTH_BLOCKED`, exit code 2, and every broker-mutation
  counter was 0.
- **Not retried.** No credentials were requested and login was not automated.
- **Not evaluated:** live candles, live spreads, the USDJPY broker spec cross-check, and a
  live POST_LONDON run. These are deferred until the owner restores terminal authorization
  manually.

## Tests (2026-09-28, Windows, Python 3.14.0, fixtures only)

The fixtures are synthetic and deterministic. No historical dataset was read, and the
sealed OOS `EURUSD_HIST_1Y_2025_09_TO_2026_09` was not opened.

- **Focused:** `python -m pytest -q tests/test_fx_opportunity_*.py tests/test_opportunity_*.py`
  gave **253 passed**. That includes 55 new tests across instruments, market_state,
  scanner and containment, plus the updated runner suite.
- **Full:** `python -m pytest -q -p no:cacheprovider` gave **590 passed, 4 skipped, 1 failed**. The single failure,
  `test_crypto_opportunity_scanner.py::test_actual_api_route_is_read_only_candidate_projection`,
  is `BASELINE_UNRELATED`: `src/api/app.py` does not exist at base `6c57430` (a restoration
  gap), and this change does not touch `src/api` or the crypto scanner.

## Scheduler recommendation (design only; not implemented)

Do not restore the historical scheduler. A capability-zero trigger is enough: one Windows
Task Scheduler entry per cycle, set just after each execution window opens and again at
window end (UTC 07:16 and 11:00 for POST_ASIAN; 12:16 and 15:00 for POST_LONDON). Each
entry runs `run_fx_opportunity_once.py --cycle <C> --symbol ALL` and appends the JSON to a
dated log.

Idempotence already comes from the candidate store, and polling stays safe because of the
closed-bar guarantee. This trigger needs no strategy_manager or execution imports. A second
run within a phase adds no transition. Installing it needs separate authorization.

## Next smallest mission

Once the owner restores MT5 authorization, run one read-only live validation of both cycles
with `--symbol ALL`. That run covers the USDJPY spec cross-check and the live spread and
MarketState. Binding GBPUSD/USDJPY to a *qualified* strategy is a separate strategy-side
decision.
