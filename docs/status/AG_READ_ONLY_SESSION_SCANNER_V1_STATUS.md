# AG Read-Only Session Scanner V1 — Status (2026-10-02)

**Capability:** `LIVE_READ_ONLY_VERIFIED` (market data → decision state on the VT Markets
Demo broker feed). **Execution authority added: none.** **Broker orders sent: 0.**

## What it is

`src/session_scanner/` + `scripts/run_session_scan.py` + `config/session_scanner_v1.yaml`.
For EURUSD / GBPUSD / USDJPY / XAUUSD it answers "what is happening now in the current
session, does an authorized strategy have an actionable setup, and what would the
proposal look like" — and stops. Pipeline:

```
Terminal MCP (read-only allowlist) -> instrument registry -> time authority
-> history sync (1 bounded retry) / quality gate -> UTC session engine
-> D1/H1/M15/M5 market state -> strategy_engine.evaluate() -> checklist
-> READY / NO_TRADE / INSUFFICIENT_DATA / OUT_OF_SESSION / STRATEGY_NOT_AUTHORIZED
-> non-executable proposal (execution_authorized = False) -> STOP
```

## Authorities reused (not redefined)

| Concern | Authority |
|---|---|
| Broker symbol names | `config/mt5.yaml` `symbol_map.VT_MARKETS` via `mt5.broker_symbol_resolver` (fail-closed). Added: EURUSD/GBPUSD/USDJPY/XAUUSD → `-VIP`. |
| Session windows | `config/canonical_sessions.yaml` (UTC, half-open); trade cycles from the contract's `session_pairs` |
| Setup decision | `strategy_engine.evaluate()` on frozen `ST_ASIAN_SWEEP_5R_V1` v1.1.1 (unchanged) |
| Structure (descriptive) | `market_structure.smc_adapter` (same path as `analyze_structure`) |
| Spread ceiling | contract `max_spread_allowed_pips: 2.0` (FX only; metals `SPREAD_OBSERVED`, no invented limit) |
| Proposal scope + risk % | release V1.0.3 pilots `AG_POST_*_V1_0_1` → EURUSD/GBPUSD, 0.5%; all else `NOT_AUTHORIZED` / `NOT_CALCULATED` |
| Registration | `strategies/registry.yaml` (read only; nothing promoted) |

Scanner-level rules introduced (scanner policy, not strategy changes):

- **Time:** broker offset derived at runtime from Terminal `get_time_information`, corroborated
  by the latest broker tick (observed UTC+03:00, `HIGH`). Any `Z`/`+00:00` label on a
  broker wall-clock timestamp (mt5ReadOnly) is discarded before conversion.
- **Signal actionability:** the contract's entry is MARKET at the sweep candle close, "entered
  immediately after signal detection". An engine `SIGNAL` is `READY` only while its signal
  candle is the latest closed M15 bar; otherwise `NO_TRADE (SIGNAL_ENTRY_WINDOW_PASSED)`.
  TREND (box-mid) signals carry no signal candle → `ENTRY_TIMING_NOT_DEFINED_FOR_SETUP`.
- **Expected closures:** weekend (server Sat–Sun) for all; XAUUSD daily break server 00:00–01:00
  (observed 2026-09-28..10-02).

## Safety controls

- `terminal_client.READ_ONLY_TOOLS` allowlist (5 `get_*` tools); everything else raises
  `TerminalToolBlocked` before any network call. Static test forbids `trade_*`,
  `order_send/check`, gateways and `execution` imports in the package.
- Owner PC, user scope `~/.claude/settings.json`: 31 `permissions.deny` rules for every
  mutating / potentially-mutating Terminal MCP tool (incl. `mcp__terminal__trade_*`). These
  govern Claude Code tool calls only; the scanner's own allowlist governs its HTTP calls.
- Token read from env var `MT5_APP_MCP_TOKEN` at call time; never stored, logged, or committed.

## Evidence

- `pytest tests/test_session_scanner_v1.py -q` → **23 passed** (Windows, project `.venv`).
- Related existing tests (126 files touching the resolver/strategy engine/import
  boundaries) → 1628 passed, 1 skipped, 9 failed. All 9 failures are in
  `tests/test_fx_occurrence_identity_promotion.py` and fail identically on the unmodified
  base `d266f90` (pre-existing, unrelated).
- Live read-only smoke, 2026-10-02 14:16:54 UTC, VT Markets **Demo** (`type: demo`),
  cycle `LONDON_NEWYORK`: all 4 instruments D1/H1/M15/M5 `VALID`, quotes `FRESH`; every
  engine SIGNAL had fired earlier in the window → 4× `NO_TRADE (SIGNAL_ENTRY_WINDOW_PASSED)`,
  0 READY, 0 blocked. The first smoke (14:13:55, before the actionability rule and the 2 s
  sync delay) had reported an expired EURUSD sweep as READY and two M5 series STALE after an
  immediate retry — both fixed and re-verified.

## Known gaps

- mt5ReadOnly (secondary) and MetaTrader public MarketData (tertiary) are not wired; a
  Terminal failure blocks the scan (no silent fallback).
- Only `ST_ASIAN_SWEEP_5R_V1` has a scanner adapter; SSC / Large-SMC / others report
  `scanner_adapter: NONE`.
- PDH/PDL sweeps, displacement, premium/discount, M5 reclaim/retest are
  `STRATEGY_CONTRACT_INCOMPLETE` (no contract rule).
- Lots are computed only when quote currency = account currency (USDJPY → `NOT_CALCULATED`).
- XAUUSD pip size (10 × point) is a labeled convention only.
