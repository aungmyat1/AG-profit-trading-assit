# SVOS Virtual Demo Engine V1 — Cycle 6A-R reality remediation

Date: 2026-09-20. Classification: **VD_REALITY_REMEDIATION_READY**.

HEAD before/after: `eade339a1b842a25d968bdc590aedc590aed83763049240` before documentation; remediation artifacts are committed after this report. Unrelated scheduler, live-watch, proposal-identity, and scheduling WIP was preserved and not staged.

Evidence inspected: Cycle 6A authority artifacts; Vantage read-only E1 audit; EURUSD friction evidence and campaign summaries; SSC M1 acquisition status; MT5 symbol/account adapters; existing execution journals and deal-history findings. One new read-only query occurred: `python scripts/check_mt5.py --symbol EURUSD --json`. It returned OK for VantageMarkets-Demo/EURUSD, but market data was marked `STALE_DATA`; no order, order check, or account mutation occurred. Full account identifiers and balances are not persisted here.

The query confirms the already documented Vantage Demo/USD environment and provided a current snapshot bid 1.14849, ask 1.14871, 22 points / 2.2 pips. This is a point-in-time narrow observation, explicitly not historical executable spread coverage. Existing evidence remains authoritative for EURUSD digits 5, point/tick 0.00001, derived pip 0.0001, contract size 100000 EUR/lot, and USD 1/tick/lot. Volume min/max/step, leverage/margin rate, and a VD-selected account profile remain unresolved; the read-only script does not expose those symbol constraints.

Commission remains `UNAVAILABLE` for EURUSD: no applicable EURUSD deal-history schedule exists, and BTCUSD zero commission is not transferable. Slippage remains `UNAVAILABLE`: one paired EURUSD fill is insufficient for a distribution and OHLC cannot supply it. Latency remains `UNAVAILABLE`: no defensible paired submission/ack/fill timing series exists. USD quote-currency mechanical P&L is available as an engineering derivation; account cash binding and conversion remain profile-dependent.

Residual blocker classes:

- `A RESOLVABLE_READ_ONLY`: bind one explicitly selected VD account profile and capture EURUSD volume/margin fields if the terminal exposes them.
- `B REQUIRES_CONTROLLED_DEMO_EXECUTION`: commission/slippage/latency calibration requiring paired requested, acknowledged, and filled order evidence; no order was placed here.
- `C REQUIRES_EXTERNAL_HISTORICAL_DATA`: representative historical executable bid/ask or tick path beyond the admitted OHLC_M1 source.
- `D FUNDAMENTALLY_UNAVAILABLE_FROM_OHLC`: exact intrabar queue/slippage/latency precision.
- `E NOT_REQUIRED_FOR_VD_BASE`: cross-currency conversion if and only if a USD account profile is explicitly bound; otherwise it becomes required and blocks.

Readiness matrix: spread `ENGINEERING_PROXY_READY` / base not ready; commission, slippage, latency, volume, and margin `NOT_READY`; mechanical USD P&L `ENGINEERING_PROXY_READY`; base economic model and stress calibration not ready. `VD_BASE = NOT_READY`; requirements were not lowered. `VD_STRESS_*` may worsen an established base assumption only; no stress multiplier was selected.

Readiness remains `engineering_ready = true`, `integration_ready = true`, `ledger_ready = true`, `e2e_ready = true`, `reality_authority_ready = true`, `vd_base_ready = false`, `economic_qualification_ready = false`. JSON validation and `git diff --check` passed. No strategy, MI, TD-8E, VirtualDemo semantics, optimization, protected data, qualification campaign, Demo order, Live order, or execution-authority change occurred.
