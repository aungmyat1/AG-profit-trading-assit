# OSS Dependency Ledger

**Purpose:** commercial/SaaS-aware dependency review for AG Profit Trading. A row marked `EVALUATE` or `REFERENCE` is not an adopted production dependency.

| Project | Upstream | License | Observed revision/activity | Intended capability | Status | Authority boundary |
|---|---|---|---|---|---|---|
| smart-money-concepts | https://github.com/joshyattridge/smart-money-concepts | MIT | latest observed `1b62fd6c41e1f508e7ed76831a039fa4c82d42f6`, 2026-04-03 | SMC primitives / semantic fixtures | `EVALUATE_PRIMARY` | Analysis only; no proposal/risk/execution authority |
| smc-mcp | https://github.com/AkhileshSelvan/smc-mcp | MIT | latest observed `719862b404ec4bd4d52b3bfa4c39ef0c034bb654`, 2026-06-14; very young history | Independent SMC semantic/no-look-ahead reference | `REFERENCE_SECONDARY` | Analysis only; MCP execution interface not adopted |
| pandas-ta-classic | https://github.com/xgboosted/pandas-ta-classic | MIT | active project observed 2026-09-28 | Commodity indicators only if AG lacks a required one | `OPTIONAL` | Pure calculation only |
| NautilusTrader | https://github.com/nautechsystems/nautilus_trader | LGPL-3.0 | active project observed 2026-09-28 | Event-driven architecture reference | `REFERENCE_ONLY` | No integration in FX-ticket milestone |
| CCXT | https://github.com/ccxt/ccxt | verify exact license at adoption gate | deferred | Future crypto exchange normalization | `DEFER` | No current FX role |
| Freqtrade | https://github.com/freqtrade/freqtrade | verify exact license at adoption gate | deferred | Future crypto architecture/reference | `DEFER` | No current FX role |
| Backtesting.py | https://github.com/kernc/backtesting.py | verify exact license at adoption gate | deferred | Backtest reference only if AG replay is insufficient | `DEFER` | No current role |
| vectorbt | https://github.com/polakowo/vectorbt | verify exact current licensing terms at adoption gate | deferred | Research acceleration only if needed | `DEFER` | No current role |

## Adoption gate

Before any `EVALUATE` row becomes `ADOPTED`:

1. record exact upstream commit/tag/version;
2. verify the authoritative LICENSE file at that revision;
3. preserve required notices/attribution;
4. run deterministic parity fixtures against the AG strategy contract;
5. run future-candle mutation/no-look-ahead tests;
6. prove no execution, proposal override, risk override, broker credential or broker mutation capability crosses the adapter;
7. document replacement/fallback strategy;
8. pin the dependency so upstream semantic drift cannot silently change tickets.

## Current decision

No new production OSS dependency is adopted by this documentation mission. The next bounded mission should evaluate `smart-money-concepts` behind a thin AG-owned adapter contract, with `smc-mcp` used as an independent semantic reference. If parity fails, reject the dependency rather than changing the frozen strategy semantics to match the library.
