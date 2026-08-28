---
name: market-data
description: Read live MT5 market data — Bid/Ask, latest candles, session-window completeness and high/low, symbol metadata, data freshness. Use for "what's the current price", "give me the latest N candles", "is today's Asian session complete", "what's today's Asian high/low". Read-only; produces normalized data, not trading interpretation.
---

# Market Data

Foundation layer of the AG Profit Trading Assistant pyramid (Market Data → Structure →
Supply/Demand → Liquidity → Entry/Confirmation → Trade Management). Every other
capability consumes this layer's output rather than talking to MT5 directly.

## Scope

- Current Bid/Ask and spread for a symbol (`mt5.market_data.get_tick`).
- Latest N closed M15 candles, or a session-window-bounded range
  (`mt5.market_data.get_latest_candles` / `get_candles`).
- Session-window completeness and high/low, sourced from `config/canonical_sessions.yaml`
  via `session_clock.py` — a low-level derived-data read, not a trading regime call.
- Symbol metadata (tick size/value, contract size, volume min/max/step) and symbol
  discovery (`mt5.symbol_resolver`).
- Data-quality flags: connection state, symbol existence, completeness, freshness,
  monotonic/duplicate timestamps.

## Tooling

`python scripts/check_mt5.py --symbol EURUSD [--candles N] [--session asian] [--json]`
is the compact report for everything in this skill's scope. Prefer it over composing raw
`mt5.*` calls unless a specific field it doesn't expose is needed.

## Fail-closed reason codes

`MT5_NOT_CONNECTED`, `SYMBOL_NOT_FOUND`, `DATA_MISSING`, `INSUFFICIENT_CANDLES`,
`STALE_DATA`, `DUPLICATE_TIMESTAMPS`, `NON_MONOTONIC_TIMESTAMPS`, `SESSION_INCOMPLETE`,
`TIME_NORMALIZATION_ERROR`, `UNSUPPORTED_TIMEFRAME`. Report these verbatim rather than
guessing what the data would have shown — a `STALE_DATA` or `DATA_MISSING` result is a
real, reportable outcome, not a reason to fall back to stale memory or a plausible-looking
guess.

## Guardrails

- This layer returns normalized data only — no regime classification, no structure, no
  liquidity, no setup judgment. Those belong to the layers above it.
- This skill has no independent broker execution authority. It may return analysis,
  structured evidence, levels, trade candidates, and management recommendations. Actual
  broker execution is delegated to the central Trade Assistant execution layer
  (`execution/executor.py`, via `assistant/commands.py`) and requires explicit user
  authorization.
- Timestamps are true UTC, already corrected for the broker's own clock offset (see
  `mt5/broker_time.py`). Never re-derive or re-adjust a timestamp this layer already
  returned — a past bug here (naive datetimes silently reinterpreted via the host
  machine's own timezone) is exactly the kind of thing re-deriving would reintroduce.
