# AG Web Vantage Demo Execution Bridge V1

Date: 2026-09-10

Status: **UNIT_TESTED / DEMO CONNECTION VERIFIED / ORDER SEND NOT EXERCISED**

The real-mode Express endpoint now delegates a frontend-confirmed FX order to
`scripts/web_execute_trade.py`. That bridge calls
`assistant.commands.execute_command()` and never imports or calls the MT5 gateway
directly. `user_confirmed=True` is supplied only after the existing frontend confirmation
modal posts `user_confirmed: true` for that individual order.

The bridge selects `config/trading.demo.yaml`, which enables order checking and sending
for this explicit pathway while retaining `account.allow_live_trading: false`. The
connected account identity and Demo classification are still checked by the existing
MT5 account guard. The default `config/trading.yaml` remains `ANALYSIS` with sends off.

Validation evidence:

- Frontend TypeScript: `npm run lint` — passed with no diagnostics.
- Execution/gateway focused suite: run after restoring the default fail-closed profile.
- Read-only MT5 position bridge: `python scripts/web_mt5_positions.py` — connected and
  returned the current position list successfully.
- Frontend positions endpoint: HTTP 200 with the same current empty list.
- Non-confirmed execution bridge check: rejected with `EXECUTION_NOT_AUTHORIZED` before
  any broker mutation.
- Broker order submission: `NOT_EVALUATED`; no order was sent.

Operational prerequisite: open MetaTrader 5, log in to the configured Vantage Demo
account, verify automated trading is permitted, then restart the web server so its
environment is refreshed.

## Follow-up: manual controls

The prerequisite was subsequently satisfied: a read-only check returned the configured
`VantageMarkets-Demo` account with fresh EURUSD quotes. Real-mode `/api/execution/positions`
now returns sanitized terminal positions. The frontend's breakeven, partial-close, and
close actions call `trade_management.manager.run_cycle_for_ticket()` and require both a
persisted claim and eligibility for the specifically requested next action. Management
gateway sends use the dedicated demo profile and independently reject non-Demo accounts
before any broker call. No broker-mutating action was used for this verification.
The execution cockpit's claim form now calls the existing `scripts/manage_trade.py claim`
boundary; it no longer reports a client-only synthetic claim.

## Follow-up: crypto symbols on the same bridge (2026-09-13)

The same Vantage Demo MT5 account's crypto CFDs (`BTCUSD`, `ETHUSD`; canonical
`BTCUSDT`, `ETHUSDT`) were traced through this identical chain and found already
supported by it, with one asset-class-specific defect fixed in `mt5/market_data.py`.
Gate semantics are unchanged and identical for crypto and FX. Broker order submission
for crypto remains `NOT_EVALUATED`. See
`docs/status/AG_VANTAGE_MT5_CRYPTO_VENUE_V1.md`.
