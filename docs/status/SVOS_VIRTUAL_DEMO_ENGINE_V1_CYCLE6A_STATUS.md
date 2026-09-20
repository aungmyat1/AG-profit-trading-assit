# SVOS Virtual Demo Engine V1 — Cycle 6A reality authority

Date: 2026-09-20. Classification: **VD_REALITY_AUTHORITY_READY**.

HEAD before/after: `c5a2565316f47ee6510363a5b7dd5c05735ac4eb` before documentation; no code or WIP was changed. Existing scheduler, live-watch, proposal-identity, and scheduling changes remain untouched and untracked/modified.

The evidence inventory is [VD_BROKER_REALITY_AUTHORITY.json](../svos/VD_BROKER_REALITY_AUTHORITY.json), with the draft account profile and model readiness matrix beside it. Existing read-only evidence identifies VantageMarkets-Demo (not VT Markets), USD account currency, EURUSD digits 5, point/tick size 0.00001, derived pip 0.0001, 100,000 EUR/lot, USD 1/tick/lot, and EUR margin currency. Minimum/maximum/step volume, leverage/margin rate, and a VD-bound account profile remain unavailable.

EURUSD data supports `OHLC_M1` only. Spread evidence is empirical narrow-window/live observation (12 samples in one 55-second window and later 12 session summaries × 120 samples), not historical executable spread coverage. Commission is unavailable for EURUSD; BTCUSD zero commission is not reused. Slippage is unavailable; one favorable fill is not a distribution. Latency is unavailable; M1 cannot establish millisecond timing. USD quote-currency mechanical P&L is a derived engineering path; account cash conversion remains blocked until the VD account profile is bound.

Readiness is separated: spread and P&L have engineering proxies only; commission, slippage, latency, broker volume, margin, and base economics are not ready. `VD_BASE` requires preregistered defensible authority. `VD_STRESS_*` may worsen an established base assumption and cannot conceal missing base inputs; no stress multiplier was selected.

No new broker query was acquired this cycle. No order submission, Demo/Live execution, sealed dataset, holdout/OOS access, optimization, or strategy/MI/TD-8E/VirtualDemo semantic change occurred. JSON validation and `git diff --check` passed.

Readiness remains `engineering_ready = true`, `integration_ready = true`, `ledger_ready = true`, `e2e_ready = true`, `reality_authority_ready = true`, `economic_qualification_ready = false`. Exact blockers are the unresolved account binding, volume/margin metadata, historical executable spread, EURUSD commission, slippage distribution, latency authority, and preregistered base economics.
