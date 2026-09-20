# SVOS Virtual Demo Engine V1 — Cycle 6A-R2

Date: 2026-09-20
Classification: **VD_BROKER_SPEC_AUTHORITY_READY**

## Repository

- HEAD before: `7b51ecc7731ec2944f8c13c5903c787c900f2f7f`
- HEAD after: recorded by the scoped remediation commit
- Existing scheduler, live-watch, proposal-identity, and scheduling WIP was preserved and not staged.

## Capability inventory

Existing read-only authorities were reused:

- `src/mt5/symbol_resolver.py`: `symbol_info` metadata including tick, contract, volume, digits, stops, and freeze fields.
- `src/mt5/account.py`: server, demo flag, trade permission, and hedging mode.
- `src/mt5/deals.py`: narrow `history_deals_get` wrappers for position and symbol history.
- `src/mt5/market_data.py`: bid/ask tick observation and candle retrieval.

The adapters do not expose leverage, trade mode, filling modes, or a complete broker commission schedule. No duplicate adapter was created.

## Read-only evidence

One bounded metadata/history probe was run through the existing adapters. It called `symbol_info`, `account_info`, and EURUSD `history_deals_get` for the prior 365 days. It made zero order or order-check calls, zero position mutations, and found zero EURUSD deal rows. No account identifier, balance, or credential was persisted.

EURUSD on `VantageMarkets-Demo`:

| Field | Value | Authority |
|---|---:|---|
| digits | 5 | BROKER_SPECIFIED |
| point / tick size | 0.00001 | BROKER_SPECIFIED |
| tick value | USD 1.00 per tick/lot | BROKER_SPECIFIED |
| contract size | 100000 EUR/lot | BROKER_SPECIFIED |
| volume min/max/step | 0.01 / 100.0 / 0.01 | BROKER_SPECIFIED |
| stops/freeze level | 0 / 0 points | BROKER_SPECIFIED |
| account environment | DEMO, USD, hedging mode | BROKER_SPECIFIED |

Trade mode, filling modes, leverage, margin rate/schedule, and account profile selection remain unavailable or unresolved. The metadata is point-in-time and not historical execution coverage.

## Existing history and friction

EURUSD deal history returned zero rows for the inspected 365-day window. Commission is therefore `UNAVAILABLE`, not zero. Existing spread campaigns remain narrow empirical observations and do not establish historical executable spread. Slippage and latency remain `REQUIRES_CONTROLLED_DEMO_CALIBRATION`; OHLC and an absent deal history cannot infer either.

Fresh spread collection capability exists through `src/mt5/market_data.py` and `scripts/check_mt5.py`, but no uncontrolled campaign was run and the observed market data is not promoted to `VD_BASE` evidence.

## VD_BASE reassessment

- Volume authority: engineering ready from broker metadata; economic base still pending explicit account-profile binding.
- Margin/leverage: not ready.
- Commission: not ready.
- Spread: engineering proxy only; not ready for base economics.
- Slippage/latency: not ready.
- Account binding: Vantage Demo/USD environment confirmed; VD account profile selection remains pending.
- `vd_base_ready = false`.
- `economic_qualification_ready = false`.

Remaining evidence requirements are classified as: read-only spread observation for coverage, controlled Demo calibration for paired submit/ack/fill slippage and latency, and external historical bid/ask or tick data for executable historical coverage. No order is authorized or requested by this cycle.

## Validation and safety

Validated JSON syntax for all three authority artifacts and ran `git diff --check`. No MI, TD-8E, SSC, strategy, risk, execution-authority, dataset, holdout/OOS, or qualification state changed. No `order_send`, `order_check`, position modification, close, Demo order, or Live order was performed.
